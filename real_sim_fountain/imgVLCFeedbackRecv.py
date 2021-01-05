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
    GPIO.setup(19,GPIO.OUT,initial=GPIO.LOW)
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
        self.glass = Glass(0)
        self.chunk_size = 0
        self.recv_done_flag = False
        self.feedback_ack_flag = False
        self.chunk_process = []
        self.feedback_idx = 0
        self.data_rec = ""
        self.recv_dir = os.path.join(RECV_PATH, time.asctime().replace(' ', '_').replace(':', '_'))


    '''LT喷泉码接收解码部分'''
    def begin_to_catch(self):
        a_drop_bytes = self.catch_a_drop_spi()          # bytes

        if a_drop_bytes is not None:
            self.drop_id += 1
            print("====================")
            print("Recv dropid : ", self.drop_id)
            print("====================")
            if len(a_drop_bytes) > 0:
                check_data = recv_check(a_drop_bytes)
                
                if not check_data == None:
                    self.drop_byte_size = len(check_data)
                    self.add_a_drop(check_data)       # bytes --- drop --- bits

    def catch_a_drop_spi(self):
            if GPIO.input(25):
                spi_recv = self.spiRecv.readbytes(239)
                rec_bytes = bytes(spi_recv) 
                frame_len = len(rec_bytes)
                print("framelen: ", frame_len)

                if(frame_len > 1):
                    while(rec_bytes[frame_len-1] == 0 and frame_len>=1):
                        frame_len = frame_len - 1
                rec_bytes = rec_bytes[:frame_len]
                print("droplen: ", frame_len)

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
        drop = self.glass.droplet_from_Bytes(d_byte)           # drop
        if self.glass.num_chunks == 0:
            print('init num_chunks : ', drop.num_chunks)
            self.glass = Glass(drop.num_chunks)                 # 初始化接收glass
            self.chunk_size = len(drop.data)

        #若为ew，则需要将drop转为ewdrop，两个drop里译码方式不一样
        ew_drop = EW_Droplet(drop.data, drop.seed, drop.num_chunks, drop.process, drop.func_id, drop.feedback_idx)
        print('drop data len: ', len(drop.data))    

        self.glass.addDroplet(drop)                             # glass add drops

        logging.info('=============================')
        logging.info('Decode Progress: '+str(self.glass.chunksDone())+'/'+str(self.glass.num_chunks))
        logging.info('=============================')

        # 接收完成
        if self.glass.isDone():
            self.recv_done_flag = True
            logging.info('============Recv done===========')
            # 接收完成写入图像
            img_data = self.glass.get_bits()
            os.mkdir(self.recv_dir)
            with open(os.path.join(self.recv_dir, "img_recv" + ".jpg"), 'wb') as f:
                f.write(img_data)
            self.send_recv_done_ack() # 接收完成返回ack

        # 接收到K个数据包之后
        if self.drop_id >= self.glass.num_chunks:
            if (self.drop_id - self.glass.num_chunks)%10==0:
                self.chunk_process = self.glass.getProcess() # 用于返回进程包
                self.glass.glass_process_history.append(self.chunk_process) # 添加反馈历史数据，用于droplet参数，正确译码
                self.send_feedback()
                print("Feedback chunks: ", self.chunk_process)
                print("Feedback chunks num: ", len(self.chunk_process))
                print("Feedback idx: ", self.feedback_idx)
                self.feedback_idx += 1


    def send_recv_done_ack(self):
        if self.recv_done_flag:
            ack = b'#$'
            acklen = len(ack)
            acksend = bytearray(ack)
            while(acklen < 239):
                acksend.insert(acklen, 0)
                acklen += 1
            self.spiSend.xfer2(acksend)
            logging.info('Send fountain ACK done')
            logging.info('Recv drops: ' + str(self.drop_id))
            logging.info('Wrong frame drops: ' + str(self.drop_id))
            logging.info('Wrong checksum drops: ' + str(self.drop_id))

    def send_feedback(self):
        fb = b'$#'
        for chunk_id in self.chunk_process:
            chunk_id_bits = format(int(chunk_id), "016b")
            fb += bitarray.bitarray(chunk_id_bits).tobytes()
            
        fblen = len(fb)
        fbsend = bytearray(fb)
        while(fblen < 239):
            fbsend.insert(fblen, 0)
            fblen += 1
        self.spiSend.xfer2(fbsend)



if __name__ == '__main__':
    receiver = Receiver(bus=0, device=1)
    # receiver.send_feedback()
    time.sleep(1)
    start = time.time()
    while True:
        receiver.begin_to_catch()
        if receiver.glass.isDone():
            end = time.time()
            print("Feedback Fountain time elapsed:", end - start)
            break

    # fb = b'##'
    # chunk_process = [0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 17, 18, 19, 20, 21, 22, 24, 25, 26, 29, 30, 31, 32, 33, 34, 35, 37, 39, 40, 41, 42, 43, 45, 46, 48, 50, 51, 52, 53, 54, 56, 57, 59, 61, 62, 65, 66, 67, 68, 70, 71, 72, 74, 75, 76, 77, 78, 79, 80, 84, 85, 86, 87, 88, 89, 90, 91, 93, 94, 96, 97, 98, 100, 101, 102, 104, 105, 108, 111, 112, 113, 115, 116, 118, 122]
    # for chunk_id in chunk_process:
    #     chunk_id_bits = format(int(chunk_id), "016b")
    #     fb += bitarray.bitarray(chunk_id_bits).tobytes()
        
    # print(fb)
    # ret = []
    # idx = 0
    # rec_bytes = fb[2:]
    # print(rec_bytes)
    # while idx < len(rec_bytes):
    #     byte_factory = bitarray.bitarray(endian='big')
    #     byte_factory.frombytes(rec_bytes[idx:idx+2])
    #     chunk_id = int(byte_factory.to01(), base=2)
    #     print(chunk_id)
    #     ret.append(chunk_id)
    #     idx += 2
    # print(ret)

    








