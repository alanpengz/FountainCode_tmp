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
import threading
import serial
import spidev
import datetime
import RPi.GPIO as GPIO
import pandas as pd


LIB_PATH = os.path.dirname(__file__)
IMG_PATH = os.path.join(LIB_PATH, './imgSend/lena.bmp')

logging.basicConfig(level=logging.INFO, 
        format="%(asctime)s %(filename)s:%(lineno)s %(levelname)s-%(message)s",)

def bitarray2str(bit):
    return bit.tobytes()

# 添加校验和、帧头
def send_check(send_bytes):
    data_array = bytearray(send_bytes)
    sum = int(0)
    zero = bytes(0)

    frame_start = b'##'
    frame_end = b'$$'

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

    get_reverse = 65535 - sum
    check_sum = get_reverse.to_bytes(2, 'big')

    data_array.insert(0, check_sum[0])
    data_array.insert(1, check_sum[1])
    data_array.insert(0, frame_start[0])
    data_array.insert(1, frame_start[1])

    if odd_flag:
        data_array.pop()

    data_array.insert(len(data_array), frame_end[0])
    data_array.insert(len(data_array), frame_end[1])
    return bytes(data_array)

def bits2string(b):
    return ''.join(chr(int(''.join(x), 2)) for x in zip(*[iter(b)]*8))

def spi_init():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(25,GPIO.IN)
    GPIO.setup(26,GPIO.OUT,initial=GPIO.LOW)
    GPIO.output(26,GPIO.HIGH)

class Sender:
    def __init__(self,
                 bus,
                 device,
                 port,
                 baudrate,
                 timeout,
                 imgsend = IMG_PATH,
                 chunk_size=215,          
                 ):
        self.spiSend = spidev.SpiDev()
        self.spiSend.open(bus, device)
        self.spiSend.max_speed_hz = 6250000 #976000
        self.spiSend.mode = 0b00

        self.spiRecv = spidev.SpiDev()
        self.spiRecv.open(bus, 1)
        self.spiRecv.max_speed_hz = 6250000 #976000
        self.spiRecv.mode = 0b00

        spi_init()
        self.port = serial.Serial(port, baudrate)

        self.imgsend = imgsend
        self.dropid = 0
        self.chunk_size = chunk_size

        self.recvdone_ack = False
        self.feedback_ack = False
        self.chunk_process = []
        self.old_feedback_num = 0
        self.feedback_num = 0
        self.pack_send_num = 0 # 发的总包数
        self.dropid_save = []
        self.throughout_put = []
        self.send_flag = [0]*915

        with open(self.imgsend, 'rb') as f:
            self.m = f.read()
        self.chunk_num = ceil(len(self.m)/self.chunk_size)

    def chunk_data(self, num):
        start = self.chunk_size * num
        end = min(self.chunk_size * (num+1), len(self.m))
        chunk_id_bits = format(int(num), "016b")
        return bitarray.bitarray(chunk_id_bits).tobytes() + self.m[start:end]

    def send_drops_spi(self):
        self.creatTimer()
        self.creat_detect_feedback_Timer()
        while True:
            idx = 0
            for flag in self.send_flag:
                if flag==0:
                    a_drop = self.chunk_data(idx)
                    sendbytes = send_check(a_drop)
                    sendbytearray = bytearray(sendbytes)
                    datalen = len(sendbytearray)
                    while(datalen < 239):
                        sendbytearray.insert(datalen, 0)
                        datalen += 1

                    self.spiSend.xfer2(sendbytearray)
                    self.send_flag[idx]=1
                    self.pack_send_num += 1
                    logging.info('chunk_id: '+ str(idx) + ' feedback_resend done, chunk size: ' + str(self.chunk_size) + ', frame size: ' + str(len(sendbytes)))
                    time.sleep(0.01)
                    idx += 1

                if(self.recvdone_ack):
                    break
                
            logging.info('============Send done===========')
            logging.info('Send Packets used: ' + str(self.pack_send_num))
            logging.info('Feedback num: ' + str(self.feedback_num))

            # 记录吞吐量
            self.cal_ttl()
            print('dropid history: ', self.dropid_save, len(self.dropid_save))
            print('drops_per_sec: ', self.throughout_put, len(self.throughout_put))
            res = pd.DataFrame({'dropid_history':self.dropid_save,  
            'drops_per_sec':self.throughout_put
            })
            res.to_csv(('data_save/Send_ttl'+ '_' + time.asctime().replace(' ', '_').replace(':', '_') + '.csv'),  mode='a')
            break
    
    # 定时器线程每隔1s记录发包数,即吞吐量
    def save_throughout_put(self):
        if(self.recvdone_ack==False):
            self.dropid_save.append(self.pack_send_num)
            self.creatTimer()

    def creatTimer(self):
        if(self.recvdone_ack==False):
            t = threading.Timer(1, self.save_throughout_put)
            t.start()
    
    # 计算吞吐量
    def cal_ttl(self):
        idx = 0
        while idx < len(self.dropid_save):
            if idx==0:
                self.throughout_put.append(self.dropid_save[0])
            else:
                self.throughout_put.append(self.dropid_save[idx]-self.dropid_save[idx-1])
            idx += 1
    
    # 从反馈中获取进度
    def get_process_from_feedback(self, rec_bytes):
        process = []
        chunk_id = 0
        process_bits = bitarray.bitarray(endian='big')
        process_bits.frombytes(rec_bytes[2:])
        while chunk_id < self.chunk_num:
            if(process_bits[chunk_id]==False):
                process.append(chunk_id)
            chunk_id += 1
        for idx in process:
            self.send_flag[idx]=0
        return process

    # 检测反馈
    def feedback_detect(self):   
        usetime = 0
        data_rec = b''
        size = self.port.in_waiting
        if size>0:
            start = time.time()
            while(usetime < 0.05):
                data_rec += self.port.read_all()
                now = time.time()
                usetime = now - start
            # data_str = str(data_rec)
            # idx = data_str.find('Received String: ')
            # if idx>=0:
            #     msg_str = data_str[idx+17:]
            #     msg_bytes = bytes(msg_str, encoding="utf-8")

            msg_bytes = data_rec
            # 接收完成
            if msg_bytes[:2] == b'#$':
                self.recvdone_ack = True
            # 进度包    
            elif msg_bytes[:2] == b'$#':
                self.feedback_ack = True
                self.chunk_process = sender.get_process_from_feedback(msg_bytes)
                self.feedback_num += 1
        self.creat_detect_feedback_Timer()

    def creat_detect_feedback_Timer(self):
        if self.recvdone_ack==False:
            t = threading.Timer(0.001, self.feedback_detect)
            t.start()

if __name__ == '__main__':
    sender = Sender(bus=0, device=0, port='/dev/ttyUSB0', baudrate=115200, timeout=1)
    sender.send_drops_spi()
