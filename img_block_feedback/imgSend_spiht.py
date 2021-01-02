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
IMG_PATH = os.path.join(LIB_PATH, 'lena.bmp')

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

        temp_file = './imgSend/lena.png'
        rgb_list = ['r', 'g', 'b']
        temp_file_list = [temp_file + '_' + ii for ii in rgb_list]
        self.m = self.compose_rgb(temp_file_list)
        self.chunk_num = ceil(len(self.m)/self.chunk_size)

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

    def chunk_data(self, num):
        start = self.chunk_size * num
        end = min(self.chunk_size * (num+1), len(self.m))
        chunk_id_bits = format(int(num), "016b")

        return bitarray.bitarray(chunk_id_bits).tobytes() + self.m[start:end]

    def send_drops_spi(self):
        self.creatTimer()
        while True:
            if(self.feedback_ack==False):
                # 发送一帧补0到239字节发送
                a_drop = self.chunk_data(self.dropid)
                sendbytes = send_check(a_drop)
                sendbytearray = bytearray(sendbytes)
                datalen = len(sendbytearray)
                while(datalen < 239):
                    sendbytearray.insert(datalen, 0)
                    datalen += 1

                self.spiSend.xfer2(sendbytearray)
                logging.info('chunk_id: '+ str(self.dropid) + ' send done, chunk size: ' + str(self.chunk_size) + ', frame size: ' + str(len(sendbytes)))
                time.sleep(0.1)
                self.dropid += 1
                self.pack_send_num += 1

                # 没收到进度反馈时继续按顺序发
                if(self.dropid >= self.chunk_num):
                    logging.info('============一轮发送完成===========')
                    self.dropid = 0
            
            elif(self.feedback_ack):
                # 没收到新进度反馈时继续按之前进度顺序发
                while self.old_feedback_num == self.feedback_num - 1:
                    for idx in self.chunk_process:
                        a_drop = self.chunk_data(idx)
                        sendbytes = send_check(a_drop)
                        sendbytearray = bytearray(sendbytes)
                        datalen = len(sendbytearray)
                        while(datalen < 239):
                            sendbytearray.insert(datalen, 0)
                            datalen += 1

                        self.spiSend.xfer2(sendbytearray)
                        self.pack_send_num += 1
                        logging.info('============缺失块重发===========')
                        logging.info('chunk_id: '+ str(idx) + ' resend done, chunk size: ' + str(self.chunk_size) + ', frame size: ' + str(len(sendbytes)))
                        time.sleep(0.1)
                self.old_feedback_num += 1

            # 检测水声反馈
            self.feedback_detect()
            if(self.recvdone_ack):
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
            # if(self.feedback_ack):
            #     print('Progress Received: ', self.chunk_process)
            #     print('Progress num: ', len(self.chunk_process))
            #     self.feedback_ack = False
                # # 接收完成
                # if self.chunk_process==[]:
                #     break
    
    # 定时器线程每隔1s记录发包数,即吞吐量
    def save_throughout_put(self):
        if(self.recvdone_ack==False):
            self.dropid_save.append(self.dropid)
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

    # 检测反馈
    def feedback_detect(self):   
        size = self.port.in_waiting
        if size>0:
            data_rec = self.port.read_all()
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
                self.chunk_process = self.get_process_from_feedback(msg_bytes)
                self.feedback_num += 1
    

     # 从反馈中获取进度
    def get_process_from_feedback(self, rec_bytes):
        process = []
        chunk_id = 0
        process_bits = bitarray.bitarray(endian='big')
        process_bits.frombytes(rec_bytes[2:])
        print(process_bits)
        print(len(process_bits))
        while chunk_id < min(self.chunk_num, len(process_bits)):
            if(process_bits[chunk_id]==False):
                process.append(chunk_id)
            chunk_id += 1
        return process

if __name__ == '__main__':
    sender = Sender(bus=0, device=0, port='/dev/ttyUSB0', baudrate=115200, timeout=1)
    sender.send_drops_spi()
