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
import threading
import spidev
import datetime
import RPi.GPIO as GPIO
import pandas as pd

from fountain_lib import Fountain, Glass
from fountain_lib import EW_Fountain, EW_Droplet

LIB_PATH = os.path.dirname(__file__)
IMG_PATH = os.path.join(LIB_PATH, '../imgSend/whale.jpg')

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
    GPIO.setup(19,GPIO.OUT,initial=GPIO.LOW)
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
                 fountain_chunk_size=215,
                 fountain_type = 'normal',
                 ):
        self.spiSend = spidev.SpiDev()
        self.spiSend.open(bus, device)
        self.spiSend.max_speed_hz = 6250000 #976000
        self.spiSend.mode = 0b00

        self.spiRecv = spidev.SpiDev()
        self.spiRecv.open(bus, 1)
        self.spiRecv.max_speed_hz = 6250000 #976000
        self.spiRecv.mode = 0b00

        # 串口和spi初始化
        spi_init()
        self.port = serial.Serial(port, baudrate)

        self.imgsend = imgsend
        self.fountain_chunk_size = fountain_chunk_size
        self.fountain_type = fountain_type
        self.dropid = 0
        self.recvdone_ack = False
        self.chunk_process = []
        self.feedback_num = 0

        self.dropid_save = []
        self.throughout_put = []

        self.encode_time = []

        # with open(self.imgsend, 'rb') as f:
        #     self.m = f.read()

        temp_file = '../imgSend/lena.png'
        rgb_list = ['r', 'g', 'b']
        temp_file_list = [temp_file + '_' + ii for ii in rgb_list]
        self.m = self.compose_rgb(temp_file_list)
        self.fountain = self.fountain_builder()
        self.show_info()

    def compose_rgb(self, file_list, each_chunk_bit_size=1):                          # (应该设置为1)each_chunk_bit_size=4000，m_byte=30000，fountain_chunk_size设置成能被30000整除，每个块长度一样，方便异或
        '''                                                                              
        将三个文件和并为一个文件
        '''
        m_list = []
        m_list.append(file_to_code(file_list[0]))  # 不用file_to_code()                             bitaray
        m_list.append(file_to_code(file_list[1]))
        m_list.append(file_to_code(file_list[2]))

        m_bits_list = []
        print('r bitstream len:', len(m_list[0]))
        print('g bitstream len:', len(m_list[1]))
        print('b bitstream len:', len(m_list[2]))
        print('rgb bitstream len:', len(m_list[0]) + len(m_list[1])+len(m_list[2]))
        print('rgb bytes should be:', (len(m_list[0]) + len(m_list[1])+len(m_list[2])) /8)

        for i in range(int(ceil(len(m_list[0]) / float(each_chunk_bit_size)))):     #
            start = i * each_chunk_bit_size
            end = min((i + 1) * each_chunk_bit_size, len(m_list[0]))

            m_bits_list.append(m_list[0][start: end])
            m_bits_list.append(m_list[1][start: end])
            m_bits_list.append(m_list[2][start: end])

        m_bits = bitarray.bitarray(m_bits_list)
        m_bytes = m_bits.tobytes()
        print('compose_rgb bytes len(m):', len(m_bytes))
        return m_bytes

    def fountain_builder(self):
        if self.fountain_type == 'normal':
            return Fountain(self.m, chunk_size=self.fountain_chunk_size)
        elif self.fountain_type == 'ew':
            return EW_Fountain(self.m, chunk_size=self.fountain_chunk_size)

    def show_info(self):
        self.fountain.show_info()

    def a_drop(self):
        return self.fountain.droplet().toBytes()

    def send_drops_spi(self):
        # 启动反馈检测、吞吐量计算线程
        self.creat_ttl_Timer()
        self.creat_detect_feedback_Timer()
        # 主线程
        while True:
            self.dropid += 1
 
            # 发送一帧补0到239字节
            encode_t0 = time.time()
            sendbytes = send_check(self.a_drop())
            sendbytearray = bytearray(sendbytes)
            datalen = len(sendbytearray)
            while(datalen < 239):
                sendbytearray.insert(datalen, 0)
                datalen += 1

            if self.dropid % 29 !=0:
                self.spiSend.xfer2(sendbytearray)
            print("====================")
            print("Send dropid: ", self.dropid)
            print("====================")
            print("FountainFrameLen: ", len(self.a_drop()))
            # print("droplen: ", len(sendbytes))
            print("SendFrameLen: ", len(sendbytearray))

            if(self.recvdone_ack):
                logging.info('============Fountain Send done===========')
                logging.info('Send drops used: ' + str(self.dropid))
                logging.info('Feedback num: ' + str(self.feedback_num))

                # print('avgs_encode_time: ', float(sum(self.encode_time)/len(self.encode_time)))
                # print('max_encode_time:', max(self.encode_time))
                # print('min_encode_time:', min(self.encode_time))

                # 记录吞吐量
                self.cal_ttl()
                # print('dropid history: ', self.dropid_save, len(self.dropid_save))
                print('drops_per_sec: ', self.throughout_put, len(self.throughout_put))
                res = pd.DataFrame({'dropid_history':self.dropid_save,  
                'drops_per_sec':self.throughout_put
                })
                res.to_csv(('data_save/Send_ttl'+ '_' + time.asctime().replace(' ', '_').replace(':', '_') + '.csv'),  mode='a')
                break
            encode_t1 = time.time()
            self.encode_time.append(encode_t1 - encode_t0)
            time.sleep(0.09) #发包间隔

    # 定时器线程每隔1s记录发包数,即吞吐量
    def save_throughout_put(self):
        if(self.recvdone_ack==False):
            self.dropid_save.append(self.dropid)
            self.creat_ttl_Timer()

    def creat_ttl_Timer(self):
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

    # 检测反馈
    def feedback_detect(self):   
        usetime = 0
        data_rec = b''
        size = self.port.in_waiting
        if size>0:
            start = time.time()
            while(usetime < 0.1):
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
                self.fountain.all_at_once = True
                process_recv = self.get_process_from_feedback(msg_bytes)
                if process_recv==[]:
                    self.recvdone_ack = True
                else:
                    self.chunk_process = process_recv
                    self.fountain.chunk_process =  self.chunk_process
                    self.fountain.feedback_idx = self.feedback_num
                    self.feedback_num += 1
        self.creat_detect_feedback_Timer()

    def creat_detect_feedback_Timer(self):
        if self.recvdone_ack==False:
            t = threading.Timer(0.001, self.feedback_detect)
            t.start()

    # 从反馈中获取进度
    def get_process_from_feedback(self, rec_bytes):
        process = []
        chunk_id = 0
        rec_bytes = rec_bytes[2:]
        process_bits = self.hex2bit(rec_bytes)
        print(rec_bytes)
        print(process_bits)
        # process_bits = bitarray.bitarray(endian='big')
        # process_bits.frombytes(rec_bytes[2:])
        while chunk_id < self.fountain.num_chunks:
            if(process_bits[chunk_id]==False):
                process.append(chunk_id)
            chunk_id += 1
        return process

    def hex2bit(self, hex_source):
        result = []
        for i in range(0,len(hex_source)):
            if(hex_source[i] == 48):
                result.extend([0,0,0,0])
            elif(hex_source[i] == 49):
                result.extend([0,0,0,1])
            elif(hex_source[i] == 50):
                result.extend([0,0,1,0])
            elif(hex_source[i] == 51):
                result.extend([0,0,1,1])
            elif(hex_source[i] == 52):
                result.extend([0,1,0,0])
            elif(hex_source[i] == 53):
                result.extend([0,1,0,1])
            elif(hex_source[i] == 54):
                result.extend([0,1,1,0])
            elif(hex_source[i] == 55):
                result.extend([0,1,1,1])
            elif(hex_source[i] ==56):
                result.extend([1,0,0,0])
            elif(hex_source[i] == 57):
                result.extend([1,0,0,1])
            elif(hex_source[i] == 97):
                result.extend([1,0,1,0])
            elif(hex_source[i] == 98):
                result.extend([1,0,1,1])
            elif(hex_source[i] == 99):
                result.extend([1,1,0,0])
            elif(hex_source[i] == 100):
                result.extend([1,1,0,1])
            elif(hex_source[i] == 101):
                result.extend([1,1,1,0])
            elif(hex_source[i] == 102):
                result.extend([1,1,1,1])
        result = result[0:self.fountain.num_chunks]
        return result
        

if __name__ == '__main__':
    sender = Sender(bus=0, device=0, port='/dev/ttyUSB0', baudrate=115200, timeout=1, fountain_type='ew')
    sender.send_drops_spi()

    # 接入水声通信机的时候:
    # 1.改发送端解析反馈部分
    # 2.发送的图片改为压缩后的K=123
    # 3.串口设备号

