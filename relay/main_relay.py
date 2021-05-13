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

from rov_lib import ROV
from fountain_lib import Fountain, Glass, EW_Fountain, EW_Droplet
from acoustic_lib import Acoustic
from common_lib import file_to_code, send_check, cal_ttl, hex2bit, recv_check, spi_init

LIB_PATH = os.path.dirname(__file__)
RECV_PATH = os.path.join(LIB_PATH, "../imgRecv")

logging.basicConfig(level=logging.INFO, 
        format="%(asctime)s %(filename)s:%(lineno)s %(levelname)s-%(message)s",)



class NodeRLY:
    def __init__(self, 
                 portSNC,
                 baudrateSNC,
                 timeoutSNC,
                 portROV,
                 baudrateROV,
                 timeoutROV
                ):
        self.ID = 1                 #本节点id
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

        # 初始化光通信spi、水声串口、ROV串口
        spi_init()
        self.acoustic = Acoustic(portSNC, baudrateSNC, timeoutSNC)
        self.rov = ROV(portROV, baudrateROV, timeoutROV)

        # 自动对准
        self.align_rov_state = 0 #记录上次循环的转向状态，0为左，1为右

        # 喷泉码接收
        self.rx_packet_id = 0
        self.rx_drop_id = 0
        self.glass = Glass(0)
        self.chunk_size = 0
        self.recv_done_flag = False
        self.feedback_ack_flag = False # 用于度函数切换过程不接收
        self.chunk_process = []
        self.feedback_idx = 0
        self.data_rec = ""
        self.recv_dir = os.path.join(RECV_PATH, time.asctime().replace(' ', '_').replace(':', '_'))
        
        self.rx_packid_save = []
        self.rx_dropid_save = []
        self.rx_packs_per_sec = []
        self.rx_drops_per_sec = []
        self.rx_ttl_timer_start=False
        self.t0 = 0
        self.t1 = 0
        self.process_bytes = b''
        self.img_recv_bits = bitarray.bitarray(endian='big')
        self.decode_time = []

        # 喷泉码中继发送
        self.tx_drop_id = 0
        self.recvdone_ack = False
        self.chunk_process = []
        self.feedback_num = 0
        self.tx_dropid_save = []

    '''LT喷泉码接收解码部分'''
    def begin_to_catch(self):
        a_drop_bytes = self.catch_a_drop_spi()          # bytes

        if a_drop_bytes is not b'':
            decode_t0 = time.time()
            # 从收到第一个包之后,开启定时记录吞吐量线程，记录时间
            if self.rx_ttl_timer_start==False:
                self.t0 = time.time()
                self.creat_ttl_Timer()
                self.rx_ttl_timer_start = True

            self.rx_packet_id += 1
            print("Recv Packet id : ", self.rx_packet_id)
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
        self.rx_drop_id += 1
        print("====================")
        print("Recv dropid : ", self.rx_drop_id)
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
            self.img_recv_bits = img_data
            os.mkdir(self.recv_dir)
            with open(os.path.join(self.recv_dir, "img_recv" + ".bmp"), 'wb') as f:
                f.write(img_data)

            self.send_recv_done_ack() # 接收完成返回ack

            # 记录吞吐量
            self.rx_cal_ttl()
            logging.info('Recv drops: ' + str(self.rx_drop_id))
            logging.info('Feedback num: '+ str(self.feedback_idx))

            print('drops_per_sec: ', self.rx_drops_per_sec, len(self.rx_drops_per_sec))
            res = pd.DataFrame({'packet_id_history':self.rx_packid_save, 
            'packets_per_sec':self.rx_packs_per_sec, 
            'drop_id_history':self.rx_dropid_save, 
            'drops_per_sec':self.rx_drops_per_sec})
            res.to_csv(('data_save/Recv_ttl'+ '_' + time.asctime().replace(' ', '_').replace(':', '_') + '.csv'),  mode='a')
            
        # 反馈
        n1 = self.glass.w1_done_dropid
        n2 = 30
        if self.glass.is_w1_done(0.6) and self.recv_done_flag==False:
            if (self.rx_drop_id - n1)%n2==0:
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

    # 定时器线程每隔1s记录收包数,即接收吞吐量
    def rx_save_throughput(self):
        if(self.recv_done_flag==False):
            self.rx_packid_save.append(self.rx_packet_id)
            self.rx_dropid_save.append(self.rx_drop_id)
            self.rx_creat_ttl_Timer()

    def rx_creat_ttl_Timer(self):
        if(self.recv_done_flag==False):
            t = threading.Timer(1, self.rx_save_throughput)
            t.start()
    
    # 计算接收瞬时吞吐量
    def rx_cal_ttl(self):
        idx = 0
        while idx < len(self.rx_packid_save):
            if idx==0:
                self.rx_packs_per_sec.append(self.rx_packid_save[0])
            else:
                self.rx_packs_per_sec.append(self.rx_packid_save[idx]-self.rx_packid_save[idx-1])
            idx += 1
        idx = 0
        while idx < len(self.rx_dropid_save):
            if idx==0:
                self.rx_drops_per_sec.append(self.rx_dropid_save[0])
            else:
                self.rx_drops_per_sec.append(self.rx_dropid_save[idx]-self.rx_dropid_save[idx-1])
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
        print("===...waiting for connection...===")
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

    # 下面3个是ROV可见光通信自动对准程序
    def rov_vlc_align(self):
        last_state = 1 #右转
        start = time.time()
        align_flag = False   #对准标志位
        print("===Start to align===")
        while not align_flag:
            align_flag = self.align_stability_test()
            if not align_flag:
                if self.align_rov_state == 0:
                    if(last_state == 1):
                        print("===Rov turn right===")
                        self.rov.port.write(b'#8868$')    #右转
                else:
                    if(last_state == 0):
                        print("===Rov turn left===")
                        self.rov.port.write(b'#88a8$')    #左转
            last_state = self.align_rov_state
            #对准成功
            if align_flag:               
                print('===Align Successed!===')
                print("===Sending VLC handshake ACK===")
                self.vlc_handshake_done = True
                self.acoustic.mfsk_tx_config()
                self.acoustic.mfsk_tx(b'$$vlc')
                break
            #超过30s，对准失败
            elif (time.time() - start) > 30:   
                print('===Align Failed!===')
                self.vlc_handshake_done = False
                break

    # 稳定性测试
    def align_stability_test(self):
        if self.align_vlc_rx():         #当前时刻能接收光信号
            if self.align_rov_state == 0:    #记录旋转状态，如因惯性过转，下次反转
                self.align_rov_state = 1
            else:
                self.align_rov_state = 0
            print("===Rov stop===")
            self.rov.port.write(b'#0000$')    #rov停转
            time.sleep(1)
            #静止后仍然能接收光信号
            print("===stop and receive===")
            rnum = 0
            start = time.time()
            while True:
                if(self.align_vlc_rx()):
                    rnum += 1
                    print("rnum = ",rnum)
                if (time.time() - start) > 3:
                    if(rnum > 24):
                        return True
                    else:
                        return False
        else:
            return False 
    
    # 接收可见光通信探测包并检测
    def align_vlc_rx(self):
        a_drop_bytes = self.catch_a_drop_spi()
        if a_drop_bytes is not b'':
            check_data = recv_check(a_drop_bytes)
            if check_data is not b'':
                print("Receive a valid packet!!!")
                return True
            else:
                return False
        else:
            return False

    '''中继转发部分'''
    def relay_forward(self):
        # 状态重新初始化
        self.align_rov_state = 0
        self.vlc_handshake_done = False
        self.snc_handshake_done = False
        self.vlc_handshake_timedout = False
        # 中继转发
        print('========================================================================')
        print('INFO: srcID=0, selfID=1, desID=2, starting Relay Forwarding procedure...')
        self.send_acoustic_handshake()
        self.wait_acoustic_handshake_ACK()
        if self.snc_handshake_done==True:
            self.rov_vlc_align()
            if self.vlc_handshake_done:
                time.sleep(3)
                print("===Starting data relay forwarding transfer===")
                self.fountain = EW_Fountain(self.img_recv_bits, chunk_size=215)
                self.send_drops_spi()
        else:
            print("Acoustic handshake failed, Relay Forwarding Transmission Terminated !!!")

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
            srcid = format(int(0), "08b")
            desid = format(int(2), "08b")
            w1size = format(int(6), "08b")
            imgW = format(int(256), "016b")
            imgH = format(int(256), "016b")
            SPIHTlen = format(int(len(self.m)), "032b")
            level = format(int(3), "08b")
            wavelet = format(int(1), "08b") # 1代表bior4.4
            mode = format(int(1), "08b")    # 1代表periodization
            acoustic_handshake = b'##' + bitarray.bitarray(nextid + srcid + desid + w1size + imgW+ imgH+ SPIHTlen+ level+ wavelet+ mode).tobytes()
            # 切换成发送模式，发送水声握手包
            print('===Send desID=2 acoustic broadcast handshake===')
            self.acoustic.mfsk_tx_config()
            self.acoustic.mfsk_tx(acoustic_handshake)
        else:
            print("nextID Not Found !!!")
    
    # 等待水声握手包的ACK
    def wait_acoustic_handshake_ACK(self):
        self.acoustic.mfsk_rx_config()
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

    # 中继转发喷泉码
    def a_drop(self):
        return self.fountain.droplet().toBytes()

    def send_drops_spi(self):
        # 启动反馈检测、吞吐量计算线程
        self.tx_creat_ttl_Timer()
        self.creat_detect_feedback_Timer()
        # 主线程
        while True:
            self.tx_drop_id += 1
            # 发送一帧补0到239字节
            sendbytes = send_check(self.a_drop())
            sendbytearray = bytearray(sendbytes)
            datalen = len(sendbytearray)
            while(datalen < 239):
                sendbytearray.insert(datalen, 0)
                datalen += 1

            self.spiSend.xfer2(sendbytearray)
            print("====================")
            print("Relay Forward Send dropid: ", self.tx_drop_id)
            print("====================")
            print("FountainFrameLen: ", len(self.a_drop()))
            print("SendFrameLen: ", len(sendbytearray))

            if(self.recvdone_ack):
                logging.info('============Fountain Send done===========')
                logging.info('Send drops used: ' + str(self.tx_drop_id))
                logging.info('Feedback num: ' + str(self.feedback_num))

                # 记录吞吐量
                throughput_list = cal_ttl(self.tx_dropid_save)
                # print('dropid history: ', self.dropid_save, len(self.dropid_save))
                print('drops_per_sec: ', throughput_list, len(throughput_list))
                res = pd.DataFrame({'dropid_history':self.tx_dropid_save,  
                'drops_per_sec':throughput_list
                })
                res.to_csv(('data_save/Send_ttl'+ '_' + time.asctime().replace(' ', '_').replace(':', '_') + '.csv'),  mode='a')
                break

            time.sleep(0.09) #发包间隔

    # 定时器线程每隔1s记录发包数,即吞吐量
    def tx_save_throughput(self):
        if(self.recvdone_ack==False):
            self.tx_dropid_save.append(self.tx_drop_id)
            self.tx_creat_ttl_Timer()

    def tx_creat_ttl_Timer(self):
        if(self.recvdone_ack==False):
            t = threading.Timer(1, self.tx_save_throughput)
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




if __name__ == '__main__':
    node1 = NodeRLY(portSNC='/dev/ttyUSB1', baudrateSNC=115200, timeoutSNC=1, portROV='/dev/ttyUSB0', baudrateROV=115200, timeoutROV=1)
    # 等待水声握手
    node1.wait_acoustic_handshake()
    # 进入可见光通信自动对准程序
    node1.rov_vlc_align()
    # 光学握手成功，进入喷泉码数据接收
    if node1.vlc_handshake_done:
        print("===Waiting for data transfer===")
        while True:
            node1.begin_to_catch()
            if node1.recv_done_flag:
                break
        # 中继转发
        if node1.ID != 2:              
            node1.relay_forward()
    else:
        print("VLC align failed, Transmission Terminated !!!")













