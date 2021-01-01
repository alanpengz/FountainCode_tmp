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

from fountain_lib import Fountain, Glass
from fountain_lib import EW_Fountain, EW_Droplet

LIB_PATH = os.path.dirname(__file__)
# DOC_PATH = os.path.join(LIB_PATH, '../doc')
# SIM_PATH = os.path.join(LIB_PATH, '../simulation')
# SEND_PATH = os.path.join(DOC_PATH, 'sendbytes.txt')
# RECV_PATH = os.path.join(DOC_PATH, 'recvbytes.txt')

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
                 fountain_chunk_size=200,          
                 seed=None):
        self.spiSend = spidev.SpiDev()
        self.spiSend.open(bus, device)
        self.spiSend.max_speed_hz = 6250000 #976000
        self.spiSend.mode = 0b00

        self.spiRecv = spidev.SpiDev()
        self.spiRecv.open(bus, 1)
        self.spiRecv.max_speed_hz = 6250000 #976000
        self.spiRecv.mode = 0b00
        spi_init()

        self.dropid = 0
        self.fountain_chunk_size = fountain_chunk_size
        self.seed = seed
        self.recvdone_ack = False
        self.fountain_type = 'normal'
        self.fountain = self.fountain_builder()
        self.show_info()
        self.m


    def fountain_builder(self):
        if self.fountain_type == 'normal':
            self.m = open('./fountain.txt', 'r').read().encode()
            return Fountain(self.m, chunk_size=self.fountain_chunk_size, seed=self.seed)
        elif self.fountain_type == 'ew':
            return EW_Fountain(self.m,
                               chunk_size=self.fountain_chunk_size,
                               w1_size=self.w1_p,
                               w1_pro=self.w1_pro,
                               seed=self.seed)

    def show_info(self):
        self.fountain.show_info()

    def a_drop(self):
        return self.fountain.droplet().toBytes()

    def send_drops_spi(self):
        while True:
            self.dropid += 1
            time.sleep(0.5)

            # 发送一帧补0到239字节
            sendbytes = send_check(self.a_drop())
            sendbytearray = bytearray(sendbytes)
            datalen = len(sendbytearray)
            while(datalen < 239):
                sendbytearray.insert(datalen, 0)
                datalen += 1

            self.spiSend.xfer2(sendbytearray)
            print("dropid: ", self.dropid)
            print("dropdatalen: ", len(self.a_drop()))
            print("droplen: ", len(sendbytes))
            print("framelen: ", len(sendbytearray))
            self.recvdone_ack_detect()
            if(self.recvdone_ack):
                break

    def recvdone_ack_detect(self):   
        if GPIO.input(25):
            spi_recv = self.spiRecv.readbytes(239)
            rec_bytes = bytes(spi_recv) 
            frame_len = len(rec_bytes)

            if rec_bytes[:2]==b'#$':
                self.recvdone_ack = True

def main_test_ew_fountain():
    m = open(os.path.join(DOC_PATH, 'fountain.txt'), 'r').read()
    fountain = EW_Fountain(m, chunk_size=10)
    glass = Glass(fountain.num_chunks)
    ew_drop = None
    i = 0
    drop_size = 0
    while not glass.isDone():
        i += 1
        a_drop = fountain.droplet()
        ew_drop = EW_Droplet(a_drop.data, a_drop.seed, a_drop.num_chunks)
        drop_size = len(ew_drop.data)
        glass.addDroplet(ew_drop)
        #  sleep(1)
        logging.info('+++++++++++++++++++++++++++++')
        logging.info(glass.getString())
    logging.info("data size : {}".format(len(m)))
    logging.info("send drop num : {} drop size : {}".format(i, drop_size))        
    logging.info("send data size : {}".format(i * drop_size))
    logging.info("scale : {}".format((i* drop_size) / float(len(m))))
    logging.info('done')


if __name__ == '__main__':
    sender = Sender(bus=0, device=0)
    sender.send_drops_spi()
