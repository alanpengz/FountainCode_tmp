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
import RPi.GPIO as GPIO


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

    if sum != 65535:
        print('Receive check wrong!')
    # 修改
    if odd_flag:
        data_array.pop()
        data_array.pop(0)
        data_array.pop(0)
    else:
        data_array.pop(0)
        data_array.pop(0)
    return bytes(data_array)


def spi_init():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(25,GPIO.IN)
    GPIO.setup(26,GPIO.OUT,initial=GPIO.LOW)
    GPIO.output(26,GPIO.HIGH)

class Receiver:
    def __init__(self, bus,
                 device,
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

        self.drop_id = 0
        self.data_rec = ""
        self.recv_dir = os.path.join(RECV_PATH, time.asctime().replace(' ', '_').replace(':', '_'))
        self.entries = [[]]*984
        self.chunks = []

    '''LT喷泉码接收解码部分'''
    def begin_to_catch(self):
        a_drop_bytes = self.catch_a_drop_spi()          

        if a_drop_bytes is not None:
            if len(a_drop_bytes) > 0:
                check_data = recv_check(a_drop_bytes)
                
                # if not check_data == None:
                self.add_a_drop(check_data) 
            self.drop_id += 1      

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
        byte_factory = bitarray.bitarray(endian='big')
        byte_factory.frombytes(d_bytes[0:2])
        chunk_id = int(byte_factory.to01(), base=2)
        chunk_data = d_bytes[2:]
        entry = [chunk_id, chunk_data]
        self.entries[chunk_id] = entry

        logging.info('chunk_id: '+ str(chunk_id) + ' received, chunk_size: ' + str(len(chunk_data)))

    def get_bits(self):
        bitarray_factory = bitarray.bitarray(endian='big')

        cnt = 0
        for entry in self.entries:
            if entry == []:
                entry = [0, b''*200]
                cnt += 1
            else:
                tmp = bitarray_factory.frombytes(entry[1])
        
        print('Received num: ', 984-cnt)
        return bitarray_factory
  

if __name__ == '__main__':
    receiver = Receiver(bus=0, device=1)
    start = time.time()
    while True:
        now = time.time()
        receiver.begin_to_catch()
        if now - start > 18:
            img_data = receiver.get_bits()
            with open(os.path.join("lena_recv_"+time.asctime().replace(' ', '_').replace(':', '_')+".bmp"), 'wb') as f:
                f.write(img_data)
            break

    








