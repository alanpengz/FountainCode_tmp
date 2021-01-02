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
import spidev
import datetime
import RPi.GPIO as GPIO

LIB_PATH = os.path.dirname(__file__)
IMG_PATH = os.path.join(LIB_PATH, 'lena.bmp')

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

        self.imgsend = imgsend
        self.dropid = 0
        self.chunk_size = chunk_size
        self.recvdone_ack = False

        with open(self.imgsend, 'rb') as f:
            self.m = f.read()
        self.chunk_num = ceil(len(self.m)/self.chunk_size)


    def chunk_data(self, num):
        start = self.chunk_size * num
        end = min(self.chunk_size * (num+1), len(self.m))
        chunk_id_bits = format(int(num), "016b")

        return bitarray.bitarray(chunk_id_bits).tobytes() + self.m[start:end]


    def send_drops_spi(self):
        s = time.time()
        while True:
            # 发送一帧补0到239字节
            a_drop = self.chunk_data(self.dropid)
            sendbytes = send_check(a_drop)
            sendbytearray = bytearray(sendbytes)
            datalen = len(sendbytearray)
            while(datalen < 239):
                sendbytearray.insert(datalen, 0)
                datalen += 1

            self.spiSend.xfer2(sendbytearray)
            logging.info('chunk_id: '+ str(self.dropid) + ' send done, chunk size: ' + str(self.chunk_size) + ', frame size: ' + str(len(sendbytes)))
            time.sleep(0.01)
            self.dropid += 1

            if(self.dropid >= self.chunk_num):
                ss = time.time()
                logging.info('============Send Done===========')
                print(ss-s)
                break

if __name__ == '__main__':
    sender = Sender(bus=0, device=0)
    sender.send_drops_spi()
