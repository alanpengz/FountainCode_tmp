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

from fountain_lib import Fountain, Glass, EW_Fountain, EW_Droplet
from acoustic_lib import Acoustic
from common_lib import file_to_code, send_check, cal_ttl, hex2bit, spi_init

LIB_PATH = os.path.dirname(__file__)
IMG_PATH = os.path.join(LIB_PATH, '../imgSend/whale.jpg')

logging.basicConfig(level=logging.INFO, 
        format="%(asctime)s %(filename)s:%(lineno)s %(levelname)s-%(message)s",)



class NodeSRC:
    def __init__(self,
                 port,
                 baudrate,
                 timeout,
                 desID,
                 imgsend = IMG_PATH,
                 fountain_chunk_size=215,
                 fountain_type = 'normal',
                 ):
        self.ID = 0                 #本节点id
        self.routing_table = [0,1,2]#路由
        self.desID = desID          #目的节点id
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

        # 初始化光通信spi和水声串口
        spi_init()
        self.acoustic = Acoustic(port, baudrate, timeout)

        # 初始化喷泉码相关
        self.imgsend = imgsend
        self.fountain_chunk_size = fountain_chunk_size
        self.fountain_type = fountain_type
        self.dropid = 0
        self.recvdone_ack = False
        self.chunk_process = []
        self.feedback_num = 0

        self.dropid_save = []
        self.encode_time = []

        # with open(self.imgsend, 'rb') as f:
        #     self.m = f.read()

        temp_file = './imgSend/lena.png'
        rgb_list = ['r', 'g', 'b']
        temp_file_list = [temp_file + '_' + ii for ii in rgb_list]
        self.m = self.compose_rgb(temp_file_list)
        self.fountain = self.fountain_builder()
        self.show_info()

    '''喷泉码发送'''
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
                throughput_list = cal_ttl(self.dropid_save)
                # print('dropid history: ', self.dropid_save, len(self.dropid_save))
                print('drops_per_sec: ', throughput_list, len(throughput_list))
                res = pd.DataFrame({'dropid_history':self.dropid_save,  
                'drops_per_sec':throughput_list
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
    
    # 检测反馈
    def feedback_detect(self):   
        data_rec = self.acoustic.modem_feedback()
        if data_rec is not b'':
            data_str = str(data_rec, encoding="utf8")
            idx = data_str.find('Received String: ')
            if idx>=0:
                msg_str = data_str[idx+17:]
                msg_bytes = bytes(msg_str, encoding="utf-8")

            # msg_bytes = data_rec
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
        process_bits = bitarray.bitarray(endian='big')
        process_bits.frombytes(rec_bytes[2:])
        while chunk_id < self.fountain.num_chunks:
            if(process_bits[chunk_id]==False):
                process.append(chunk_id)
            chunk_id += 1
        return process


    '''基于水声辅助的可见光通信链路建立'''
    # 寻找下一跳节点id
    def find_next_id(self):
        idx = 0
        next_id = 0
        for id in self.routing_table:
            if id == self.ID:
                next_id = self.routing_table[idx+1]
                return next_id
            idx += 1
        return None

    # 发送水声握手包
    def send_acoustic_handshake(self):
        id = self.find_next_id()
        if id is not None:
            nextid = format(int(id), "08b")
            w1size = format(int(6), "08b")
            imgW = format(int(256), "016b")
            imgH = format(int(256), "016b")
            SPIHTlen = format(int(len(self.m)), "032b")
            level = format(int(3), "08b")
            wavelet = format(int(1), "08b") # 1代表bior4.4
            mode = format(int(1), "08b")    # 1代表periodization
            acoustic_handshake = b'##' + bitarray.bitarray(nextid + w1size + imgW+ imgH+ SPIHTlen+ level+ wavelet+ mode).tobytes()
            # 切换成发送模式，发送水声握手包
            self.acoustic.mfsk_tx_config()
            self.acoustic.mfsk_tx(acoustic_handshake)
        else:
            print("nextID Not Found !!!")
    
    # 等待水声握手包的ACK
    def wait_acoustic_handshake_ACK(self):
        snc_shake_time0 = time.time()
        snc_shake_retry_times = 0
        while True:
            if self.acoustic.mfsk_rx()=="##snc":
                print('===Acoustic handshake ACK received, Acoustic handshake done!===')
                self.snc_handshake_done = True
                break
            if (time.time() - snc_shake_time0)%6==0:
                self.send_acoustic_handshake()
                snc_shake_retry_times += 1
                if snc_shake_retry_times >= 3:
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
    node0 = NodeSRC(port='/dev/ttyUSB0', baudrate=115200, timeout=1, fountain_type='ew', desID=2)
    # 发送水声握手参数包
    node0.send_acoustic_handshake()
    # 等待水声握手包反馈ACK
    node0.wait_acoustic_handshake_ACK()
    # 进入光学握手
    if node0.snc_handshake_done==True:
        node0.send_vlc_detect()
        # 进入喷泉码发送
        if node0.vlc_handshake_done:
            node0.send_drops_spi()
        else:
            print("VLC handshake failed, Transmission Terminated !!!")
    else:
        print("Acoustic handshake failed, Transmission Terminated !!!")

