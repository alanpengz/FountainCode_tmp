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
import threading
import pandas as pd


from fountain_lib import Fountain, Glass
from fountain_lib import EW_Fountain, EW_Droplet

LIB_PATH = os.path.dirname(__file__)
RECV_PATH = os.path.join(LIB_PATH, "../imgRecv")

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
                 device
                ):
        self.spiRecv = spidev.SpiDev()
        self.spiRecv.open(bus, device)
        self.spiRecv.max_speed_hz = 6250000 #976000
        self.spiRecv.mode = 0b00

        self.spiSend = spidev.SpiDev()
        self.spiSend.open(bus, 0)
        self.spiSend.max_speed_hz = 6250000 #976000
        self.spiSend.mode = 0b00

        # spi初始化
        spi_init()

        self.packet_id = 0
        self.drop_id = 0
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

    '''LT喷泉码接收解码部分'''
    def begin_to_catch(self):
        a_drop_bytes = self.catch_a_drop_spi()          # bytes

        if a_drop_bytes is not None:
            # 从收到第一个包之后,开启定时记录吞吐量线程，记录时间
            if self.ttl_timer_start==False:
                self.t0 = time.time()
                self.creat_ttl_Timer()
                self.ttl_timer_start = True

            self.packet_id += 1
            print("Recv Packet id : ", self.packet_id)
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
        self.drop_id += 1
        print("====================")
        print("Recv dropid : ", self.drop_id)
        print("====================")

        drop = self.glass.droplet_from_Bytes(d_byte)           # drop
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
            logging.info("Sonic Feedback Fountain time elapsed:"+ str(self.t1-self.t0))
            # 接收完成写入图像
            img_data = self.glass.get_bits()
            os.mkdir(self.recv_dir)
            with open(os.path.join(self.recv_dir, "img_recv" + ".bmp"), 'wb') as f:
                f.write(img_data)

            self.send_recv_done_ack() # 接收完成返回ack

            # 记录吞吐量
            self.cal_ttl()
            print('packet_id history: ', self.packid_save, len(self.packid_save))
            print('packets per sec: ', self.packs_per_sec, len(self.packs_per_sec))
            print('drop_id history: ', self.dropid_save, len(self.dropid_save))
            print('drops per sec: ', self.drops_per_sec, len(self.drops_per_sec))
            res = pd.DataFrame({'packet_id_history':self.packid_save, 
            'packets_per_sec':self.packs_per_sec, 
            'drop_id_history':self.dropid_save, 
            'drops_per_sec':self.drops_per_sec})
            res.to_csv(('data_save/Recv_ttl'+ '_' + time.asctime().replace(' ', '_').replace(':', '_') + '.csv'),  mode='a')

            
        # 反馈
        n1 = round(0.8*self.glass.num_chunks)
        n2 = 20
        if self.drop_id >= n1 and self.recv_done_flag==False:
            if (self.drop_id - n1)%n2==0:
                # 用于添加反馈历史数据
                self.chunk_process = self.glass.getProcess() 
                self.glass.glass_process_history.append(self.chunk_process) # 添加反馈历史数据，用于droplet参数，正确译码
                # 用于实际反馈
                process_bitmap = self.glass.getProcess_bits()
                process_bits = bitarray.bitarray(process_bitmap)
                self.process_bytes = process_bits.tobytes()

                self.send_feedback()
                print("Feedback chunks: ", self.chunk_process)
                print("Feedback chunks num: ", len(self.chunk_process))
                print("Feedback idx: ", self.feedback_idx)
                self.feedback_idx += 1
                self.feedback_ack_flag = True
                self.feedback_send_done=True

        # if self.real_drop_id >= self.glass.num_chunks:
        #     if (self.real_drop_id - self.glass.num_chunks)%10==0 and self.feedback_send_done==False:
        #         self.chunk_process = self.glass.getProcess() # 用于返回进程包
        #         self.glass.glass_process_history.append(self.chunk_process) # 添加反馈历史数据，用于droplet参数，正确译码
        #         self.send_feedback()
        #         print("Feedback chunks: ", self.chunk_process)
        #         print("Feedback chunks num: ", len(self.chunk_process))
        #         print("Feedback idx: ", self.feedback_idx)
        #         self.feedback_idx += 1
        #         self.feedback_ack_flag = True
        #         self.feedback_send_done=True

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
            logging.info('Recv Packets: : ' + str(self.packet_id))
            logging.info('Recv drops: ' + str(self.drop_id))

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
    while True:
        receiver.begin_to_catch()
        if receiver.recv_done_flag:
            break