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

from fountain_lib import Fountain, Glass, EW_Fountain, EW_Droplet
from acoustic_lib import Acoustic
from common_lib import file_to_code, send_check, cal_ttl, hex2bit, recv_check, spi_init

LIB_PATH = os.path.dirname(__file__)
RECV_PATH = os.path.join(LIB_PATH, "../imgRecv")

logging.basicConfig(level=logging.INFO, 
        format="%(asctime)s %(filename)s:%(lineno)s %(levelname)s-%(message)s",)



class NodeDES:
    def __init__(self, 
                 port,
                 baudrate,
                 timeout,
                ):
        self.ID = 2                 #本节点id
        self.routing_table = [0,1,2]#路由
        self.snc_handshake_done = False
        self.vlc_handshake_done = False
        self.vlc_handshake_timedout = False

        # 初始化spi发送
        self.spiSend = spidev.SpiDev()
        self.spiSend.open(0, 0) # bus device
        self.spiSend.max_speed_hz = 6250000 #976000
        self.spiSend.mode = 0b00

        # 初始化spi接收
        self.spiRecv = spidev.SpiDev()
        self.spiRecv.open(0, 1)
        self.spiRecv.max_speed_hz = 6250000 #976000
        self.spiRecv.mode = 0b00

        # 初始化光通信spi、水声串口
        spi_init()
        self.acoustic = Acoustic(port, baudrate, timeout)

        self.packet_id = 0
        self.drop_id = 0
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
        self.packs_per_sec = []
        self.drops_per_sec = []
        self.ttl_timer_start=False
        self.t0 = 0
        self.t1 = 0
        self.process_bytes = b''

    '''LT喷泉码接收解码部分'''
    def begin_to_catch(self):
        a_drop_bytes = self.catch_a_drop_spi()          # bytes

        if a_drop_bytes is not b'':
            # 从收到第一个包之后,开启定时记录吞吐量线程，记录时间
            if self.ttl_timer_start==False:
                self.t0 = time.time()
                self.creat_ttl_Timer()
                self.ttl_timer_start = True

            self.packet_id += 1
            print("Recv Packet id : ", self.packet_id)
            if len(a_drop_bytes) > 0:
                check_data = recv_check(a_drop_bytes)
                if not check_data == b'':
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
                    return b''
            else:
                return b''

    def add_a_drop(self, d_byte):
        self.drop_id += 1
        print("====================")
        print("Recv dropid : ", self.drop_id)
        print("====================")

        print('glass_process_history len: ', len(self.glass.glass_process_history))
        drop = self.glass.droplet_from_Bytes(d_byte)           # drop
        if self.glass.num_chunks == 0:
            print('init num_chunks : ', drop.num_chunks)
            self.glass = Glass(drop.num_chunks)                 # 初始化接收glass
            self.chunk_size = len(drop.data)

        #若为ew，则需要将drop转为ewdrop，两个drop里译码方式不一样
        ew_drop = EW_Droplet(drop.data, drop.seed, drop.num_chunks, drop.process, drop.func_id, drop.feedback_idx)
        print('drop data len: ', len(drop.data))

        self.glass.addDroplet(ew_drop)

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

            self.send_recv_done_ack() # 接收完成返回ack

            # 记录吞吐量
            self.cal_ttl()
            logging.info('Recv drops: ' + str(self.drop_id))
            logging.info('Feedback num: '+ str(self.feedback_idx))

            print('drops_per_sec: ', self.drops_per_sec, len(self.drops_per_sec))
            res = pd.DataFrame({'packet_id_history':self.packid_save, 
            'packets_per_sec':self.packs_per_sec, 
            'drop_id_history':self.dropid_save, 
            'drops_per_sec':self.drops_per_sec})
            res.to_csv(('data_save/Recv_ttl'+ '_' + time.asctime().replace(' ', '_').replace(':', '_') + '.csv'),  mode='a')
          
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
                # self.process_bytes = self.bit2hex(process_bitmap)
                # print(process_bitmap)
                # print(self.process_bytes)
                process_bits = bitarray.bitarray(process_bitmap)
                self.process_bytes = process_bits.tobytes()

                self.send_feedback()
                print("Feedback chunks: ", self.chunk_process)
                print("Feedback chunks num: ", len(self.chunk_process))
                print("Feedback idx: ", self.feedback_idx)
                self.feedback_idx += 1
                self.feedback_ack_flag = True
                self.feedback_send_done=True

    # 定时器线程每隔1s记录收包数,即吞吐量
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
            self.acoustic.mfsk_tx_config()
            self.acoustic.mfsk_tx(b'#$\r\n')
            self.port.flushOutput()

    def send_feedback(self):
        self.acoustic.mfsk_tx_config()
        fb = b'$#' + self.process_bytes + b'\r\n'
        self.acoustic.mfsk_tx(fb)
        self.port.flushOutput()


 '''基于水声辅助的光通信链路建立部分'''
    # 等待水声握手，并反馈水声握手ACK
    def wait_acoustic_handshake(self):
        self.acoustic.mfsk_rx_config()
        while True:
            str_recv = self.acoustic.mfsk_rx()
            # 收到水声握手包
            if str_recv[0:2]=="##":
                var = self.acoustic.acoustic_handshake_pack_res(str_recv[2:])
                # 反馈水声握手ACK
                if var[0]==self.ID:
                    self.acoustic.mfsk_tx_config()
                    self.acoustic.mfsk_tx(b'##snc')
                    self.snc_handshake_done = True
                    break
    
    # 发送可见光通信探测包
    def send_vlc_detect(self):
        # 切换水声通信机为接收模式，接收光学握手ACK
        self.acoustic.mfsk_rx_config()
        # 启动光学握手成功反馈检测线程
        self.creat_detect_vlc_shakehand_done_Timer() 
        print("===Sending VLC detect packs===")
        vlc_handshake_time0 = time.time()
        while True:
            detect_bytes = b'0123456789abcdefghjklmnopqrstuvwxyz~!@#$%^&*()_+{}?<>:'
            # 发送一帧补0到239字节
            sendbytes = send_check(detect_bytes)
            sendbytearray = bytearray(sendbytes)
            datalen = len(sendbytearray)
            while(datalen < 239):
                sendbytearray.insert(datalen, 0)
                datalen += 1

            self.spiSend.xfer2(sendbytearray)
            if(self.vlc_handshake_done):
                break

            if (time.time() - vlc_handshake_time0)>=30:
                self.vlc_handshake_timedout = True
                break
            time.sleep(0.1) #发包间隔
    
    # 检测光学握手成功反馈
    def vlc_shakehand_ACK_detect(self):   
        msg_str = self.acoustic.mfsk_rx()
        if msg_str == "$$vlc":
            self.vlc_handshake_done = True
        self.creat_detect_feedback_Timer()

    def creat_detect_vlc_shakehand_done_Timer(self):
        if self.vlc_handshake_done==False and self.vlc_handshake_timedout==False:
            t = threading.Timer(0.001, self.vlc_shakehand_ACK_detect)
            t.start()


if __name__ == '__main__':
    node2 = NodeDES(port='/dev/ttyUSB1', baudrate=115200, timeout=1)
    # 等待水声握手
    node2.wait_acoustic_handshake()
    # 发送可见光通信探测包
    node2.send_vlc_detect()
    # 喷泉码数据接收
    node2.acoustic.mfsk_tx_config()
    if node2.vlc_handshake_done:
        while True:
            node2.begin_to_catch()
            if node2.recv_done_flag:
                break
    else:
        print("VLC handshake failed, Transmission Terminated !!!")

  
    











