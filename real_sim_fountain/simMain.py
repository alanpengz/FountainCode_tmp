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

from simSend import Sender
from simRecv import Receiver