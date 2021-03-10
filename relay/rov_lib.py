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


class ROV:
    def __init__(self, port, baudrate, timeout):
        self.port = serial.Serial(port, baudrate)
        self.direction = 0 #记录上次循环的转向状态，0为左，1为右
        
    
if __name__ == '__main__':
    pass

    

