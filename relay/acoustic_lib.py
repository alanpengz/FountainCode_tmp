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
import serial
import re


#水声通信
class Acoustic:
    def __init__(self, port, baudrate, timeout):
        self.port = serial.Serial(port, baudrate)
       
    
    # 向水声通信机串口发送指令
    def order_send(self, signal):
        signal_send = bytearray(signal + b'\r\n')
        self.port.write(signal_send)
        if self.modem_feedback()=="":
            print("send command failed!!!")

    # 水声通信机串口返回信息
    def modem_feedback(self, wait_time=0.1):
        usetime = 0
        txt_rec = b''
        if self.port.in_waiting > 0:
            start = time.time()
            while(usetime < wait_time):
                txt_rec += self.port.read_all()
                now = time.time()
                usetime = now - start
        return txt_rec

    # 设置并进入MFSK接收模式
    def mfsk_rx_config(self):
        self.order_send(b'E') #退出当前模式,第一次退出收发模式，第二次退出AD/DA模式
        self.order_send(b'E')
        self.order_send(b'A') #进入AD模式
        self.order_send(b'C') #设置采样率为80
        self.order_send(b'80')
        self.order_send(b'M') #进入MFSK解调模式
    
    # 设置并进入MFSK发送模式
    def mfsk_tx_config(self):
        self.order_send(b'E') #退出当前模式,第一次退出收发模式，第二次退出AD/DA模式
        self.order_send(b'E')
        self.order_send(b'D') #进入DA模式
        self.order_send(b'C') #设置采样率为80
        self.order_send(b'80')
        self.order_send(b'A') #设置双通道调制幅度为50
        self.order_send(b'50')
        self.order_send(b'50')
    

    # 水声发送数据
    def mfsk_tx(self, data):
        self.order_send(b'M')
        time.sleep(0.01)
        self.order_send(data)
        if self.modem_feedback(3)=="":
            print("MFSK Send failed!!!")
        
    # 水声接收数据
    def mfsk_rx(self):
        recv_bytes = self.modem_feedback()
        recv_str = str(recv_bytes, encoding="utf-8")
        msg = ""

        if recv_str is not "":
            print("===Acoustic received message: ===")
            idx_start = recv_str.find('Received String: ')
            idx_end = recv_str.find('MFSK Demodulate')
            if idx_start >= 0 :
                msg = recv_str[(idx_start+17) : (idx_end-1)]
                print(msg)
            else:
                print("CRC error!!!")
        return msg
    
    # 水声握手包数据解析
    def acoustic_handshake_pack_res(self, msg_str):
        var = []
        msg_byte = bytes(msg_str, encoding="utf-8")

        byte_factory0 = bitarray.bitarray(endian='big')
        byte_factory0.frombytes(msg_byte[0:1])
        nextid = int(byte_factory0.to01(), base=2)

        byte_factory1 = bitarray.bitarray(endian='big')
        byte_factory1.frombytes(msg_byte[1:2])
        srcid = int(byte_factory1.to01(), base=2)

        byte_factory2 = bitarray.bitarray(endian='big')
        byte_factory2.frombytes(msg_byte[2:3])
        desid = int(byte_factory2.to01(), base=2)

        byte_factory3 = bitarray.bitarray(endian='big')
        byte_factory3.frombytes(msg_byte[3:4])
        w1size = int(byte_factory3.to01(), base=2)

        byte_factory4 = bitarray.bitarray(endian='big')
        byte_factory4.frombytes(msg_byte[4:6])
        imgW = int(byte_factory4.to01(), base=2)

        byte_factory5 = bitarray.bitarray(endian='big')
        byte_factory5.frombytes(msg_byte[6:8])
        imgH = int(byte_factory5.to01(), base=2)

        byte_factory6 = bitarray.bitarray(endian='big')
        byte_factory6.frombytes(msg_byte[8:12])
        SPIHTlen = int(byte_factory6.to01(), base=2)

        byte_factory7 = bitarray.bitarray(endian='big')
        byte_factory7.frombytes(msg_byte[12:13])
        level = int(byte_factory7.to01(), base=2)

        byte_factory8 = bitarray.bitarray(endian='big')
        byte_factory8.frombytes(msg_byte[13:14])
        wavelet = int(byte_factory8.to01(), base=2)

        byte_factory9 = bitarray.bitarray(endian='big')
        byte_factory9.frombytes(msg_byte[14:15])
        mode = int(byte_factory9.to01(), base=2)

        var.extend[nextid, srcid, desid, w1size, imgW, imgH, SPIHTlen, level, wavelet, mode] 
        return var




if __name__ == '__main__':
    pass
