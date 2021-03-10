# _*_ coding=utf-8 _*_
from __future__ import print_function
from math import ceil, log
import sys, os
import bitarray
import serial
import threading
import spidev
import RPi.GPIO as GPIO

# 初始化spi
def spi_init():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(19,GPIO.OUT,initial=GPIO.LOW)
    GPIO.setup(25,GPIO.IN)
    GPIO.setup(26,GPIO.OUT,initial=GPIO.LOW)
    GPIO.output(26,GPIO.HIGH)

# 读取压缩编码二进制文件
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
        return b''

# 计算吞吐量
def cal_ttl(dropid_save_list):
    idx = 0
    throughput_list = []
    while idx < len(dropid_save_list):
        if idx==0:
            throughput_list.append(dropid_save_list[0])
        else:
            throughput_list.append(dropid_save_list[idx] - dropid_save_list[idx-1])
        idx += 1
    return throughput_list

# 水声通信机接收如果是全0，会自动剔除全零部分，重新映射
def hex2bit(self, hex_source, num_chunks):
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
    result = result[0:num_chunks]
    return result

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