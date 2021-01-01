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
IMG_PATH = os.path.join(LIB_PATH, 'imgSend/whale.jpg')

logging.basicConfig(level=logging.INFO, 
        format="%(asctime)s %(filename)s:%(lineno)s %(levelname)s-%(message)s",)

def file_to_code(file_name):
    '''
    从文件中读取内容，转化为二进制编码
    read code from file
    '''
    fin = open(file_name, 'rb')
    read_bits = bitarray.bitarray()
    read_bits.fromfile(fin)
    fin.close()
    return read_bits

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
                 fountain_chunk_size=200,          
                 seed=None,
                 w1_size=0.1,
                 w1_pro=0.086):
        self.spiSend = spidev.SpiDev()
        self.spiSend.open(bus, device)
        self.spiSend.max_speed_hz = 6250000 #976000
        self.spiSend.mode = 0b00

        self.spiRecv = spidev.SpiDev()
        self.spiRecv.open(bus, 1)
        self.spiRecv.max_speed_hz = 6250000 #976000
        self.spiRecv.mode = 0b00
        spi_init()

        self.w1_size = w1_size
        self.w1_pro = w1_pro
        self.imgsend = imgsend
        self.dropid = 0
        self.fountain_chunk_size = fountain_chunk_size
        self.seed = seed
        self.recvdone_ack = False
        self.fountain_type = 'normal'

        # with open(self.imgsend, 'rb') as f:
        #     self.m = f.read()

        temp_file = './imgSend/lena.png'
        rgb_list = ['r', 'g', 'b']
        temp_file_list = [temp_file + '_' + ii for ii in rgb_list]
        self.m = self.compose_rgb(temp_file_list)
        self.fountain = self.fountain_builder()
        self.show_info()

    def compose_rgb(self, file_list, each_chunk_bit_size=4000):                          # each_chunk_bit_size=2500, len(m_byte)不等于240000/8=30000
        '''                                                                             # each_chunk_bit_size=4000，m_byte=30000，fountain_chunk_size设置成能被30000整除，每个块长度一样，方便异或
        将三个文件和并为一个文件
        '''
        m_list = []
        m_list.append(file_to_code(file_list[0]))  # 不用file_to_code()                             bitaray
        m_list.append(file_to_code(file_list[1]))
        m_list.append(file_to_code(file_list[2]))

        m_bytes = b''
        print('r bitstream len:', len(m_list[0]))
        print('g bitstream len:', len(m_list[1]))
        print('b bitstream len:', len(m_list[2]))
        print('rgb bitstream len:', len(m_list[0]) + len(m_list[1])+len(m_list[2]))
        print('rgb bytes should be:', (len(m_list[0]) + len(m_list[1])+len(m_list[2])) /8)

        for i in range(int(ceil(len(m_list[0]) / float(each_chunk_bit_size)))):     #
            start = i * each_chunk_bit_size
            end = min((i + 1) * each_chunk_bit_size, len(m_list[0]))

            m_bytes += m_list[0][start: end].tobytes()
            m_bytes += m_list[1][start: end].tobytes()
            m_bytes += m_list[2][start: end].tobytes()

        print('compose_rgb bytes len(m):', len(m_bytes))  # r,g,b(size)+...+
        return m_bytes

    def fountain_builder(self):
        if self.fountain_type == 'normal':
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
                logging.info('============Fountain Send done===========')
                logging.info('Send drops used: ' + str(self.dropid))
                break
            time.sleep(0.1)

    def recvdone_ack_detect(self):   
        if GPIO.input(25):
            spi_recv = self.spiRecv.readbytes(239)
            rec_bytes = bytes(spi_recv) 
            frame_len = len(rec_bytes)

            if rec_bytes[:2]==b'#$':
                self.recvdone_ack = True



if __name__ == '__main__':
    sender = Sender(bus=0, device=0)
    sender.send_drops_spi()

    # with open('./imgSend/lena.bmp', 'rb') as f:
    #     m = f.read()
    
    # mm = m[0:round(len(m)*0.15)]
    # with open('img_recv.png', 'wb') as ff:
    #     ff.write(mm)

