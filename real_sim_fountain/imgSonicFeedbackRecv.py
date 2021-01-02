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
import serial
import spidev
import datetime
import RPi.GPIO as GPIO
import threading

from fountain_lib import Fountain, Glass
from fountain_lib import EW_Fountain, EW_Droplet

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
    print('checksum:', sum)

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
    GPIO.setup(25,GPIO.IN)
    GPIO.setup(26,GPIO.OUT,initial=GPIO.LOW)
    GPIO.output(26,GPIO.HIGH)

class Receiver:
    def __init__(self, bus,
                 device,
                 port,
                 baudrate,
                 timeout,
                ):
        self.spiRecv = spidev.SpiDev()
        self.spiRecv.open(bus, device)
        self.spiRecv.max_speed_hz = 6250000 #976000
        self.spiRecv.mode = 0b00

        self.spiSend = spidev.SpiDev()
        self.spiSend.open(bus, 0)
        self.spiSend.max_speed_hz = 6250000 #976000
        self.spiSend.mode = 0b00

        # 串口和spi初始化
        spi_init()
        self.port = serial.Serial(port, baudrate)

        self.pack_id = 0
        self.drop_id = 0
        self.glass = Glass(0)
        self.chunk_size = 0
        self.recv_done_flag = False
        self.feedback_ack_flag = False
        self.chunk_process = []
        self.feedback_idx = 0
        self.data_rec = ""
        self.recv_dir = os.path.join(RECV_PATH, time.asctime().replace(' ', '_').replace(':', '_'))
        self.t0 = 0
        self.t0_start = False
        self.t1 = 0
        self.process_bytes = b''


    '''LT喷泉码接收解码部分'''
    def begin_to_catch(self):
        a_drop_bytes = self.catch_a_drop_spi()          # bytes

        if a_drop_bytes is not None:
            # 从接收到第一个包开始计时
            if self.t0_start == False:
                self.t0 = time.time()
                self.t0_start = True
            self.pack_id += 1
            print("Recv Packet_id : ", self.pack_id)

            if len(a_drop_bytes) > 0:
                check_data = recv_check(a_drop_bytes)
                
                if not check_data == None:
                    self.drop_byte_size = len(check_data)
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
                    print(self.data_rec)
                    print('Wrong receive frame !')

    def add_a_drop(self, d_byte):
        self.drop_id += 1
        print("====================")
        print("Recv drop_id : ", self.drop_id)
        print("====================")
        drop = self.glass.droplet_from_Bytes(d_byte)           # drop
        if self.glass.num_chunks == 0:
            print('init num_chunks : ', drop.num_chunks)
            self.glass = Glass(drop.num_chunks)                 # 初始化接收glass
            self.chunk_size = len(drop.data)

        #若为ew，则需要将drop转为ewdrop，两个drop里译码方式不一样
        ew_drop = EW_Droplet(drop.data, drop.seed, drop.num_chunks, drop.process, drop.func_id, drop.feedback_idx)
        self.glass.addDroplet(ew_drop)         # glass add drops

        logging.info('=============================')
        logging.info('Decode Progress: '+str(self.glass.chunksDone())+'/'+str(self.glass.num_chunks))
        logging.info('=============================')
        
        # 接收完成
        if self.glass.isDone():
            self.t1 = time.time()
            self.recv_done_flag = True
            # 接收完成写入图像
            img_data = self.glass.get_bits()
            os.mkdir(self.recv_dir)
            with open(os.path.join(self.recv_dir, "img_recv" + ".bmp"), 'wb') as f:
                f.write(img_data)

            t1 = threading.Timer(1.8, self.send_recv_done_ack)
            t1.start()
            # self.send_recv_done_ack() # 接收完成返回ack
            logging.info('============Recv done===========')
            logging.info('Send Sonic Fountain ACK done')
            logging.info('Recv packets: ' + str(self.drop_id))
            logging.info('Recv drops: ' + str(self.drop_id))
            logging.info("Sonic Feedback Fountain time elapsed:" + str(self.t1 - self.t0))
            
        # 接收到K个数据包之后
        n1 = round(0.8*self.glass.num_chunks)
        n2 = 20
        if self.drop_id >= n1 and self.recv_done_flag==False:
            if (self.drop_id - n1)%n2==0:
                process = self.glass.getProcess()
                # 用于添加反馈历史数据, 用于droplet参数，正确译码
                self.chunk_process = process[0]
                self.glass.glass_process_history.append(self.chunk_process)
                # 用于实际反馈
                process_bitmap = process[1]
                process_bits = bitarray.bitarray(process_bitmap)
                self.process_bytes = process_bits.tobytes()

                t = threading.Timer(1.8, self.send_feedback)
                t.start()

                print("Feedback chunks: ", self.chunk_process)
                print("Feedback chunks num: ", len(self.chunk_process))
                print("Feedback idx: ", self.feedback_idx)
                self.feedback_idx += 1



    def send_recv_done_ack(self):
        if self.recv_done_flag:
            ack = b'#$\r\n'
            acksend = bytearray(ack)
            self.port.write(acksend)
            self.port.flushOutput()

    # 用定时器线程反馈仿真修改
    def send_feedback(self):
        # process_bitmap = self.glass.getProcess_bits()
        # process_bits = bitarray.bitarray(process_bitmap)
        fb = b'$#' + self.process_bytes 
        self.port.write(fb)
        self.port.flushOutput()



if __name__ == '__main__':
    receiver = Receiver(bus=0, device=1, port='/dev/ttyUSB1', baudrate=115200, timeout=1)
    # receiver.send_feedback()
    while True:
        receiver.begin_to_catch()
        if receiver.recv_done_flag:
            break














