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
import pandas as pd


from fountain_lib import Fountain, Glass
from fountain_lib import EW_Fountain, EW_Droplet

LIB_PATH = os.path.dirname(__file__)
RECV_PATH = os.path.join(LIB_PATH, "../imgRecv")

logging.basicConfig(level=logging.INFO, 
        format="%(asctime)s %(filename)s:%(lineno)s %(levelname)s-%(message)s",)

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

        self.packet_id = 0  # 数据包数量
        self.drop_id = 0    # 校验正确的有效数据包数量
        self.real_drop_id = 0 # dropid除去度函数切换和进度包更新时收到的drop
        self.glass = Glass(0)
        self.chunk_size = 0
        self.recv_done_flag = False
        self.feedback_ack_flag = False # 用于度函数切换过程不接收
        self.feedback_send_done = False
        self.chunk_process = []
        self.feedback_idx = 0
        self.data_rec = ""
        self.recv_dir = os.path.join(RECV_PATH, time.asctime().replace(' ', '_').replace(':', '_'))
        
        # 吞吐量统计
        self.packid_save = []
        self.dropid_save = []
        self.valid_dropid_save = []
        self.packs_per_sec = []
        self.drops_per_sec = []
        self.valid_drops_per_sec = []
        self.ttl_timer_start=False
        self.t0 = 0
        self.t1 = 0

        self.process_bytes = b''
        self.decode_time = [] # 用于统计每个编码包的译码时间

    '''LT喷泉码接收解码部分'''
    def begin_to_catch(self):
        a_drop_bytes = self.catch_a_drop_spi()          # bytes

        if a_drop_bytes is not None:
            decode_t0 = time.time()
            # 从收到第一个包之后,开启定时记录吞吐量线程，记录时间
            if self.ttl_timer_start==False:
                self.t0 = time.time()
                self.creat_ttl_Timer()
                self.ttl_timer_start = True

            self.packet_id += 1
            print("Recv Packet id : ", self.packet_id)
            if len(a_drop_bytes) > 0:
                check_data = recv_check(a_drop_bytes) # 接收校验
                
                if not check_data == None:
                    self.drop_byte_size = len(check_data)
                    self.add_a_drop(check_data)       # bytes --- drop --- bits
                    decode_t1 = time.time()
                    self.decode_time.append(decode_t1 - decode_t0)

    def catch_a_drop_spi(self):
            if GPIO.input(25):
                spi_recv = self.spiRecv.readbytes(239)
                rec_bytes = bytes(spi_recv) 
                frame_len = len(rec_bytes)
                print("framelen: ", frame_len)

                # 去掉末尾补充的0
                if(frame_len > 1):
                    while(rec_bytes[frame_len-1] == 0 and frame_len>=1):
                        frame_len = frame_len - 1
                rec_bytes = rec_bytes[:frame_len]
                print("droplen: ", frame_len)

                self.data_rec = rec_bytes
                # 判断帧头帧尾
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
        print("Recv dropid : ", self.drop_id)
        print("====================")

        print('glass_process_history len: ', len(self.glass.glass_process_history))
        drop = self.glass.droplet_from_Bytes(d_byte)            # drop
        if self.glass.num_chunks == 0:
            print('init num_chunks : ', drop.num_chunks)
            self.glass = Glass(drop.num_chunks)                 # 初始化接收glass
            self.chunk_size = len(drop.data)

        #若为ew，则需要将drop转为ewdrop，两个drop里译码方式不一样
        ew_drop = EW_Droplet(drop.data, drop.seed, drop.num_chunks, drop.process, drop.func_id, drop.feedback_idx)
        print('drop data len: ', len(drop.data))

        self.glass.addDroplet(ew_drop)

        # 这里解决度函数切换过程不接收，解决进度包更新过程不接收
        # if (self.feedback_ack_flag==False) or (self.feedback_ack_flag==True and ew_drop.func_id==1 and ew_drop.feedback_idx==self.feedback_idx-1):
        #     self.real_drop_id += 1
        #     self.glass.addDroplet(ew_drop)         # glass add drops
        #     print("=============================================================")
        #     print("除去度函数切换和进度包更新时收到的drop，Real_Recv_dropid : ", self.real_drop_id)
        #     print("=============================================================")
        #     self.feedback_send_done=False

        logging.info('=============================')
        logging.info('Decode Progress: '+str(self.glass.chunksDone())+'/'+str(self.glass.num_chunks))
        logging.info('=============================')
        
        # 接收完成
        if self.glass.isDone():
            self.recv_done_flag = True
            self.t1 = time.time()
            logging.info('============Recv done===========')
            logging.info("Fountain time elapsed:"+ str(self.t1-self.t0))
            # 接收完成写入图像
            img_data = self.glass.get_bits()
            os.mkdir(self.recv_dir)
            with open(os.path.join(self.recv_dir, "img_recv" + ".bmp"), 'wb') as f:
                f.write(img_data)

            # 串口模拟水声延迟进行反馈
            t1 = threading.Timer(1.8, self.send_recv_done_ack)
            t1.start()

            # 实际写入水声通信机进行反馈
            # self.send_recv_done_ack() # 接收完成返回ack

            # 记录吞吐量
            self.cal_ttl()
            print('packet_id history: ', self.packid_save, len(self.packid_save))
            print('packets_per_sec: ', self.packs_per_sec, len(self.packs_per_sec))
            print('drop_id history: ', self.dropid_save, len(self.dropid_save))
            logging.info('Send Sonic Fountain ACK done')
            logging.info('Recv Packets: : ' + str(self.packet_id))
            logging.info('Recv drops: ' + str(self.drop_id))
            logging.info('Feedback num: '+ str(self.feedback_idx))

            print('drops_per_sec: ', self.drops_per_sec, len(self.drops_per_sec))
            res = pd.DataFrame({'packet_id_history':self.packid_save, 
            'packets_per_sec':self.packs_per_sec, 
            'drop_id_history':self.dropid_save, 
            'drops_per_sec':self.drops_per_sec})
            res.to_csv(('data_save/Recv_ttl'+ '_' + time.asctime().replace(' ', '_').replace(':', '_') + '.csv'),  mode='a')

            # print('avgs_decode_time: ', float(sum(self.decode_time)/len(self.decode_time)))
            # print('max_decode_time:', max(self.decode_time))
            # print('min_decode_time:', min(self.decode_time))
          
            
        # 反馈
        n1 = self.glass.w1_done_dropid
        n2 = 30
        if self.glass.is_w1_done(0.6) and self.recv_done_flag==False:
            if (self.drop_id - n1)%n2==0:
                process = self.glass.getProcess()
                # 用于添加反馈历史数据, 用于droplet参数，正确译码
                self.chunk_process = process[0]
                self.glass.glass_process_history.append(self.chunk_process)
                # 用于实际反馈
                process_bitmap = process[1]
                # self.process_bytes = self.bit2hex(process_bitmap) # 实际水声通信机反馈可能需要用到这个
                # print(process_bitmap)
                # print(self.process_bytes)
                process_bits = bitarray.bitarray(process_bitmap)
                self.process_bytes = process_bits.tobytes()

                # 串口模拟水声延迟进行反馈
                t = threading.Timer(1.8, self.send_feedback)
                t.start()

                # 实际写入水声通信机进行反馈
                # self.send_feedback()
                print("Feedback chunks: ", self.chunk_process)
                print("Feedback chunks num: ", len(self.chunk_process))
                print("Feedback idx: ", self.feedback_idx)
                self.feedback_idx += 1
                self.feedback_ack_flag = True
                self.feedback_send_done=True

     # 定时器线程每隔1s记录发包数,即吞吐量
    def save_throughout_put(self):
        if(self.recv_done_flag==False):
            self.packid_save.append(self.packet_id)
            self.dropid_save.append(self.drop_id)
            self.valid_dropid_save.append(self.real_drop_id)
            self.creat_ttl_Timer()

    def creat_ttl_Timer(self):
        if(self.recv_done_flag==False):
            t = threading.Timer(1, self.save_throughout_put)
            t.start()
    
    # 计算吞吐量
    def cal_ttl(self):
        idx = 0
        while idx < len(self.packid_save):
            if idx==0:
                self.packs_per_sec.append(self.packid_save[0])
            else:
                self.packs_per_sec.append(self.packid_save[idx]-self.packid_save[idx-1])
            idx += 1
        idx = 0
        while idx < len(self.dropid_save):
            if idx==0:
                self.drops_per_sec.append(self.dropid_save[0])
            else:
                self.drops_per_sec.append(self.dropid_save[idx]-self.dropid_save[idx-1])
            idx += 1
        
    # 串口发送译码完成ack
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

    # 串口反馈译码进度
    def send_feedback(self):
        fb = b'$#' + self.process_bytes + b'\r\n'
        # M = b'M\r\n'
        # self.port.write(M)
        # self.port.flushOutput()
        # time.sleep(0.01)
        self.port.write(fb)
        self.port.flushOutput()


    def bit2hex(self, bit_array_source):
        bit_array = bit_array_source
        a = len(bit_array) % 4
        for j in range (0,a):
            bit_array.append(0)
        result = b''
        i = 0
        while i < len(bit_array):
            bit4 = bit_array[i:i+4]
            if(bit4 == [0,0,0,0]):
                result += b'0'
            elif(bit4 == [0,0,0,1]):
                result += b'1'
            elif(bit4 == [0,0,1,0]):
                result += b'2'
            elif(bit4 == [0,0,1,1]):
                result += b'3'  
            elif(bit4 == [0,1,0,0]):
                result += b'4'
            elif(bit4 == [0,1,0,1]):
                result += b'5'
            elif(bit4 == [0,1,1,0]):
                result += b'6'
            elif(bit4 == [0,1,1,1]):
                result += b'7'  
            elif(bit4 == [1,0,0,0]):
                result += b'8'
            elif(bit4 == [1,0,0,1]):
                result += b'9'
            elif(bit4 == [1,0,1,0]):
                result += b'a'
            elif(bit4 == [1,0,1,1]):
                result += b'b'  
            elif(bit4 == [1,1,0,0]):
                result += b'c'
            elif(bit4 == [1,1,0,1]):
                result += b'd'
            elif(bit4 == [1,1,1,0]):
                result += b'e'
            elif(bit4 == [1,1,1,1]):
                result += b'f'
            i += 4
        return result



if __name__ == '__main__':
    receiver = Receiver(bus=0, device=1, port='/dev/ttyUSB1', baudrate=115200, timeout=1)
    while True:
        receiver.begin_to_catch()
        if receiver.recv_done_flag:
            break













