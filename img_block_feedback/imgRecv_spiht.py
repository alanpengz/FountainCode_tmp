# _*_ coding=utf-8 _*_

from __future__ import print_function
from math import ceil, log
import sys, os
import random
import json
import bitarray
from time import sleep
import logging
import time
import spidev
import datetime
import serial
import threading
import RPi.GPIO as GPIO
import pandas as pd


LIB_PATH = os.path.dirname(__file__)
RECV_PATH = os.path.join(LIB_PATH, "imgRecv")

logging.basicConfig(level=logging.INFO, 
        format="%(asctime)s %(filename)s:%(lineno)s %(levelname)s-%(message)s",)

def bitarray2str(bit):
    return bit.tobytes().decode('utf-8')

# 接收校验
def recv_check(recv_data):
    data_array = bytearray(recv_data)
    sum = int(0)
    zero = bytes(0)
    odd_flag = False

    if not len(data_array) % 2 == 0:
        odd_flag = True
        data_array.insert(len(data_array), 0)

    for i in range(0, len(data_array), 2):
        val = int.from_bytes(data_array[i:i + 2], 'big')
        sum = sum + val
        sum = sum & 0xffffffff

    sum = (sum >> 16) + (sum & 0xffff)
    while sum > 65535:
        sum = (sum >> 16) + (sum & 0xffff)
    # print('checksum:', sum)

    if sum == 65535:
        if odd_flag:
            data_array.pop()
            data_array.pop(0)
            data_array.pop(0)
        else:
            data_array.pop(0)
            data_array.pop(0)
        return bytes(data_array)
    else:
        print('Receive check wrong!')

def spi_init():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(19,GPIO.OUT,initial=GPIO.LOW)
    GPIO.setup(25,GPIO.IN)
    GPIO.setup(26,GPIO.OUT,initial=GPIO.LOW)
    GPIO.output(26,GPIO.HIGH)

class Receiver:
    def __init__(self, bus,
                 device,
                 port,
                 baudrate,
                 timeout
                ):
        self.spiRecv = spidev.SpiDev()
        self.spiRecv.open(bus, device)
        self.spiRecv.max_speed_hz = 6250000 #976000
        self.spiRecv.mode = 0b00

        self.spiSend = spidev.SpiDev()
        self.spiSend.open(bus, 0)
        self.spiSend.max_speed_hz = 6250000 #976000
        self.spiSend.mode = 0b00
        spi_init()
        self.port = serial.Serial(port, baudrate)

        self.drop_id = 0
        self.data_rec = ""
        self.recv_dir = os.path.join(RECV_PATH, time.asctime().replace(' ', '_').replace(':', '_'))
        self.entries = [None]*115
        self.chunks = []

        self.pack_id = 0
        self.drop_id = 0
        self.pack_save = []
        self.drop_save = []
        self.pack_per_sec = []
        self.drop_per_sec = []
        self.recv_done_flag=False
        self.timer_start=False
        self.t0 = 0
        self.t1 = 0

    '''LT喷泉码接收解码部分'''
    def begin_to_catch(self):
        a_drop_bytes = self.catch_a_drop_spi()          

        if a_drop_bytes is not None:
            # 从收到第一个包之后,开启定时记录吞吐量线程
            if self.timer_start==False:
                self.t0 = time.time()
                self.creat_ttl_Timer()
                self.timer_start = True

            self.pack_id += 1
            if len(a_drop_bytes) > 0:
                check_data = recv_check(a_drop_bytes)
                
                if not check_data == None:
                    self.add_a_drop(check_data)      

    def catch_a_drop_spi(self):
            if GPIO.input(25):
                spi_recv = self.spiRecv.readbytes(239)
                rec_bytes = bytes(spi_recv) 
                frame_len = len(rec_bytes)

                if(frame_len > 1):
                    while(rec_bytes[frame_len-1] == 0 and frame_len>=1):
                        frame_len = frame_len - 1
                rec_bytes = rec_bytes[:frame_len]

                self.data_rec = rec_bytes
                if self.data_rec[0:2] == b'##' and self.data_rec[frame_len - 2:frame_len] == b'$$':
                    data_array = bytearray(self.data_rec)
                    data_array.pop(0)
                    data_array.pop(0)
                    data_array.pop()
                    data_array.pop()
                    return bytes(data_array)
                else:
                    print('Wrong receive frame !')

    def add_a_drop(self, d_bytes):
        self.drop_id += 1 
        byte_factory = bitarray.bitarray(endian='big')
        byte_factory.frombytes(d_bytes[0:2])
        chunk_id = int(byte_factory.to01(), base=2)
        chunk_data = d_bytes[2:]

        entry = [chunk_id, chunk_data]
        self.entries[chunk_id] = entry
        logging.info('chunk_id: '+ str(chunk_id) + ' received, chunk_size: ' + str(len(chunk_data)))

        if self.isDone():
            self.t1 = time.time()
            self.recv_done_flag=True
            print('time used: ', self.t1-self.t0)
            # 记录吞吐量
            self.cal_ttl()
            print('packid history: ', self.pack_save, len(self.pack_save))
            print('packs_per_sec: ', self.pack_per_sec, len(self.pack_per_sec))
            print('dropid history: ', self.drop_save, len(self.drop_save))
            print('drops_per_sec: ', self.drop_per_sec, len(self.drop_per_sec))
            res = pd.DataFrame({'packid_history':self.pack_save,  
            'packs_per_sec':self.pack_per_sec,
            'dropid_history':self.drop_save,  
            'drops_per_sec':self.drop_per_sec
            })
            res.to_csv(('data_save/Send_ttl'+ '_' + time.asctime().replace(' ', '_').replace(':', '_') + '.csv'),  mode='a')
            self.send_recv_done_ack()
        
        # 进度反馈
        n1 = round(0.8*115)
        n2 = 20
        if self.drop_id >= n1 and self.recv_done_flag==False:
            if (self.drop_id - n1)%n2==0:
                self.send_feedback()

    def get_bits(self):
        bitarray_factory = bitarray.bitarray(endian='big')
        for entry in self.entries:
            tmp = bitarray_factory.frombytes(entry[1])
        return bitarray_factory
  
    # 定时器线程每隔1s记录发包数,即吞吐量
    def save_throughout_put(self):
        if(self.recv_done_flag==False):
            self.pack_save.append(self.pack_id)
            self.drop_save.append(self.drop_id)
            self.creat_ttl_Timer()

    def creat_ttl_Timer(self):
        if(self.recv_done_flag==False):
            t = threading.Timer(1, self.save_throughout_put)
            t.start()
    
    # 计算吞吐量
    def cal_ttl(self):
        idx = 0
        while idx < len(self.pack_save):
            if idx==0:
                self.pack_per_sec.append(self.pack_save[0])
            else:
                self.pack_per_sec.append(self.pack_save[idx]-self.pack_save[idx-1])
            idx += 1
        idx = 0
        while idx < len(self.drop_save):
            if idx==0:
                self.drop_per_sec.append(self.drop_save[0])
            else:
                self.drop_per_sec.append(self.drop_save[idx]-self.drop_save[idx-1])
            idx += 1

    def isDone(self):
        return None not in self.entries

    def send_recv_done_ack(self):
        if self.recv_done_flag:
            # M = b'M\r\n'
            # self.port.write(M)
            # self.port.flushOutput()
            # time.sleep(0.01)

            ack = b'#$\r\n'
            acksend = bytearray(ack)
            self.port.write(acksend)
            self.port.flushOutput()
            logging.info('Send ACK done')
            logging.info('Recv Packets: : ' + str(self.pack_id))
            logging.info('Recv drops: ' + str(self.drop_id))

    def send_feedback(self):
        process_bitmap = self.getProcess_bits()
        process_bits = bitarray.bitarray(process_bitmap)
        process_bytes = process_bits.tobytes()
        fb = b'$#' + process_bytes + b'\r\n'
        # M = b'M\r\n'
        # self.port.write(M)
        # self.port.flushOutput()
        # time.sleep(0.01)
        self.port.write(fb)
        self.port.flushOutput()

    def getProcess_bits(self):
        process_bits = []
        for entry in self.entries:
            if entry is None:
                process_bits.append(0)
            else:
                process_bits.append(1)
        return process_bits


if __name__ == '__main__':
    receiver = Receiver(bus=0, device=1, port='/dev/ttyUSB1', baudrate=115200, timeout=1)
    while True:
        receiver.begin_to_catch()
        if receiver.recv_done_flag:
            img_data = receiver.get_bits()
            with open(os.path.join("lena_recv_"+time.asctime().replace(' ', '_').replace(':', '_')+".bmp"), 'wb') as f:
                f.write(img_data)
            break