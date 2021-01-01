# _*_ coding=utf-8 _*_
from __future__ import print_function
from math import ceil, log
import sys, os
import random
import json
import bitarray
import numpy as np
from time import sleep
import time
import logging
import pandas as pd

LIB_PATH = os.path.dirname(__file__)
DOC_PATH = os.path.join(LIB_PATH, '../doc')
SIM_PATH = os.path.join(LIB_PATH, '../simulation')

logging.basicConfig(level=logging.INFO, 
        format="%(asctime)s %(filename)s:%(lineno)s %(levelname)s-%(message)s",)

def charN(str, N):
    if N < len(str):
        return str[N]
    return 'X'

def xor(str1, str2):
    '''
    按位运算str1, str2
    将 str1 和 str2 中每一个字符转为acsii 表中的编号，再将两个编号转为2进制按位异或运算
    ，最后返回异或运算的数字在ascii 表中的字符
    '''
    length = max(len(str1),len(str2))
    a1 = charN(str1, 700)
    a2 = charN(str2, 700)
    return ''.join(chr(ord(charN(str1,i)) ^ ord(charN(str2,i))) for i in range(length))

def x_o_r(bytes1, bytes2):  # 传入两个数，并返回它们的异或结果，结果为16进制数
    length = max(len(bytes1), len(bytes2))

    if len(bytes1) < len(bytes2):
        add_num = len(bytes2) - len(bytes1)
        bytes1_array = bytearray(bytes1)
        add = b'0'*add_num

        for ii in range(add_num):
            bytes1_array.insert(0, add[ii])
            bytes1 = bytes(bytes1_array)

    else:
        add_num = len(bytes1) - len(bytes2)
        bytes2_array = bytearray(bytes2)
        add = b'0' * add_num

        for ii in range(add_num):
            bytes2_array.insert(0, add[ii])
            bytes2 = bytes(bytes2_array)

    result_bytes = b''
    for i in range(length):
        result_bytes += (bytes1[i] ^ bytes2[i]).to_bytes(1, 'little')

    return result_bytes

def randChunkNums(num_chunks):
    '''
    size 是每次选取的度数，这里选取的是一个度函数，size 分布是
    度函数的文章要在这里做, 这里的度函数是一个 5 到 K 的均匀分布
    num_chunks : int, 编码块总数量
    return : list, 被选中的编码块序号
    '''
    size = random.randint(1,min(5, num_chunks))
    # random.sample 是一个均匀分布的采样
    return random.sample(range(num_chunks), size)

def robust_randChunkNums(num_chunks):
    size = robust_soliton(num_chunks).__next__()
    return [ii for ii in random.sample(range(num_chunks), size)]

def all_at_once_randChunkNums(chunks):
    # return random.sample(chunks, 1)
    return [ii for ii in np.random.choice(chunks, 1, False)]

def all_at_once_solition(K):
    d = [ii + 1 for ii in range(K)]
    d_f = [1.0 if ii==1 else 0 for ii in d]
    while 1:
        yield np.random.choice(d, 1, False, d_f)[0]

def soliton(K):
    ''' 理想弧波函数 '''
    d = [ii + 1 for ii in range(K)]
    d_f = [1.0 / K if ii == 1 else 1.0 / (ii * (ii - 1)) for ii in d]
    while 1:
        # i = np.random.choice(d, 1, False, d_f)[0]
        yield np.random.choice(d, 1, False, d_f)[0]

# dafualt: 0.03 0.05 
def robust_soliton(K, c= 0.03, delta= 0.05):
    # c是自由变量，delta是接收到M个确知数据包后无法译码的概率极限。c确定时delta越大R越小
    ''' 鲁棒理想弧波函数 '''
    d = [ii + 1 for ii in range(K)]
    soliton_d_f = [1.0 / K if ii == 1 else 1.0 / (ii * (ii - 1)) for ii in d]

    R = c * log(K / delta) * (K ** 0.5)                         # 每次解码中度数为1的编码符号的数目
    d_interval_0 = [ii + 1 for ii in list(range(int(round(K / R)) - 1))]
    d_interval_1 = [int(round(K / R))]
    tau = [R / (K * dd) if dd in d_interval_0
            else R / float(K) * log(R / delta) if dd in d_interval_1
            else 0 for dd in d]

    Z = sum([soliton_d_f[ii] + tau[ii] for ii in range(K)])
    u_d_f = [(soliton_d_f[ii] + tau[ii]) / Z for ii in range(K)]    #概率密度分布函数

    while True :
        # i = np.random.choice(d, 1, False, u_d_f)[0]
        yield np.random.choice(d, 1, False, u_d_f)[0]             # 返回一个度值



class Droplet:
    ''' 储存随机数种子，并有一个计算本水滴中包含的数据块编码的方法'''
    def __init__(self, data, seed, num_chunks, process):
        self.data = data
        self.seed = seed
        self.num_chunks = num_chunks
        self.process = process

    def robust_chunkNums(self):
        random.seed(self.seed)
        np.random.seed(self.seed)
        return robust_randChunkNums(self.num_chunks)
    
    def all_at_once_chunkNums(self):
        random.seed(self.seed)
        np.random.seed(self.seed)
        return all_at_once_randChunkNums(self.process)

    def toBytes(self):
        '''
        使用一个字节存储chunks_size,
        num_chunks int 度数，一个字节                                  2个字节？
        seed 随机数种子，两个字节                                       4个字节？
        返回的结构是一个字节加后面跟着2 * n 个字节，后续跟着数据
        '''
        num_chunks_bits = format(int(self.num_chunks), "016b")
        seed_bits = format(int(self.seed), "032b")
        logging.info('fountain num_chunks : {}, seed : {}'.format(self.num_chunks, self.seed))

        return bitarray.bitarray(num_chunks_bits + seed_bits).tobytes() + self.data



class Fountain(object):
    # 继承了object对象，拥有了好多可操作对象，这些都是类中的高级特性。python 3 中已经默认加载了object
    def __init__(self, data, chunk_size, seed=None):
        self.data = data
        self.chunk_size = chunk_size
        self.num_chunks = int(ceil(len(data) / float(chunk_size)))
        self.seed = seed
        self.all_at_once = False
        self.chunk_selected = []
        self.chunk_process = []
        random.seed(seed)
        np.random.seed(seed)
        # self.show_info()

    def show_info(self):
        logging.info('Fountain info')
        logging.info('data len: {}'.format(len(self.data)))
        logging.info('chunk_size: {}'.format(self.chunk_size))
        logging.info('num_chunks: {}'.format(self.num_chunks))

    def droplet(self):
        self.updateSeed()
        ### 修改
        if not self.all_at_once:
            self.chunk_selected = robust_randChunkNums(self.num_chunks)
        else:
            self.chunk_selected = all_at_once_randChunkNums(self.chunk_process)

        # chunk_selected = randChunkNums(self.num_chunks)
        # logging.info("seed: {}".format(self.seed))
        # logging.info("send chunk list: {}".format(self.chunk_selected))
        data = None
        for num in self.chunk_selected:
            if data is None:
                data = self.chunk(num)
            else:
                data = xor(data, self.chunk(num))
                # data = x_o_r(data, self.chunk(num))               # 被选到的数据块异或   异或时存在两字符串长度不一样

        return Droplet(data, self.seed, self.num_chunks, self.chunk_process) 

    def chunk(self, num):
        start = self.chunk_size * num
        end = min(self.chunk_size * (num+1), len(self.data))
        return self.data[start:end]

    def updateSeed(self):
        self.seed = random.randint(0, 2**31-1)
        random.seed(self.seed)
        np.random.seed(self.seed)



class EW_Fountain(Fountain):
    ''' 扩展窗喷泉码 '''
    def __init__(self, data, chunk_size, ew_process=[], seed=None, w1_size=0.1, w1_pro=0.084):
        Fountain.__init__(self, data, chunk_size=chunk_size, seed=None)
        # logging.info("-----------------EW_Fountain------------")
        self.w1_p = w1_size
        self.w1_pro = w1_pro
        self.windows_id_gen = self.windows_selection()
        self.w1_size = int(round(self.num_chunks * self.w1_p))
        self.w2_size = self.num_chunks
        self.w1_random_chunk_gen = robust_soliton(self.w1_size),
        self.w2_random_chunk_gen = robust_soliton(self.w2_size)

        self.all_at_once = False
        self.chunk_process = ew_process
        self.chunk_selected = []

        # logging.info('w1_size : ', self.w1_size)
        # logging.info('w2_size : ', self.w2_size)
        # logging.info('w size ; ', self.num_chunks)

    def droplet(self):
        self.updateSeed()
        if not self.all_at_once:
            self.chunk_selected = self.EW_robust_RandChunkNums(self.num_chunks)
        else:
            self.chunk_selected = self.EW_all_at_once_RandChunkNums()
        # logging.info("send seed: {}\tnum_chunks: {}".format(self.seed, self.num_chunks))
        data = None
        for num in self.chunk_selected:
            if data is None:
                data = self.chunk(num)
            else:
                data = xor(data, self.chunk(num))
                # data = x_o_r(data, self.chunk(num))

        # logging.info('send chunk_list : {}'.format(chunk_selected))
        return EW_Droplet(data, self.seed, self.num_chunks, self.chunk_process)

    def EW_robust_RandChunkNums(self, num_chunks):
        '''扩展窗的不同在这里'''
        window_id = self.windows_id_gen.__next__()
        if window_id == 1:
            size = self.w1_random_chunk_gen[0].__next__()          # 鲁棒孤波返回的度值
            return random.sample(range(self.w1_size), size)
        else:
            size = self.w2_random_chunk_gen.__next__()
            return [ii for ii in random.sample(range(self.w2_size), size)]

    def EW_all_at_once_RandChunkNums(self):
        # w1未译出的块
        w1_chunk_process = []
        for i in self.chunk_process:
            if i <= self.w1_size:
                w1_chunk_process.append(i)

        window_id = self.windows_id_gen.__next__()
        if window_id == 1 and len(w1_chunk_process)>0:
            return [ii for ii in np.random.choice(w1_chunk_process, 1, False)]  
        else:
            return [ii for ii in np.random.choice(self.chunk_process, 1, False)]

    def windows_selection(self):
        '''以概率[{p:1, 1-p:2}返回选择的窗口'''
        d = [1, 2]
        w1_p = self.w1_pro
        w_f = [w1_p, 1-w1_p]
        while True:
            i = np.random.choice(d, 1, False, w_f)[0]    # 从d中以概率w_f，随机选择1个,replace抽样之后还放不放回去
            yield i



class EW_Droplet(Droplet):
    '''扩展窗喷泉码专用水滴, 计算水滴使用的数据块列表'''
    def __init__(self, data, seed, num_chunks, process, w1_size=0.1, w1_pro=0.084):
        Droplet.__init__(self, data, seed, num_chunks, process)
        m = ' ' * num_chunks * len(data)
        self.ower = EW_Fountain(m, len(self.data), w1_size=w1_size, w1_pro=w1_pro, ew_process=process)

    def robust_chunkNums(self):
        random.seed(self.seed)
        np.random.seed(self.seed)
        return self.ower.EW_robust_RandChunkNums(self.num_chunks)

    def all_at_once_chunkNums(self):
        random.seed(self.seed)
        np.random.seed(self.seed)
        return self.ower.EW_all_at_once_RandChunkNums()



class Glass:
    '''接收水滴：与或计算后的数据，'''
    def __init__(self, num_chunks):
        self.entries = []
        self.droplets = []
        self.num_chunks = num_chunks
        self.chunks = [None] * num_chunks
        self.chunk_bit_size = 0
        self.dropid = 0
        self.all_at_once = False
        
    def addDroplet(self, drop):
        self.dropid += 1
        self.droplets.append(drop)
        # logging.info("recv seed: {}\tnum_chunks: {}".format(drop.seed, drop.num_chunks))    # \t=tab
         # drop.chunkNums()方法通过seed生成的所选数据块与fountain一样
        entry = [drop.robust_chunkNums(), drop.data] if not self.all_at_once else [drop.all_at_once_chunkNums(), drop.data] 
        self.entries.append(entry)
        # logging.info('recv chunk_list : {}'.format(entry[0]))
        self.updateEntry(entry)

    def droplet_from_Bytes(self, d_bytes):

        byte_factory = bitarray.bitarray(endian='big')
        byte_factory.frombytes(d_bytes[0:2])

        num_chunks = int(byte_factory.to01(), base=2)

        byte_factory1 = bitarray.bitarray(endian='big')
        byte_factory1.frombytes(d_bytes[2:6])
        seed = int(byte_factory1.to01(), base=2)

        data = d_bytes[6:]

        logging.info(' seed: {}\tglass num_chunks : {}\t data len: {},'.format(seed, num_chunks, len(data)))
        if self.chunk_bit_size == 0:
            byte_factory2 = bitarray.bitarray(endian='big')
            byte_factory2.frombytes(data)
            self.chunk_bit_size = byte_factory2.length()

        d = Droplet(data, seed, num_chunks)
        return d

    def updateEntry(self, entry):
        '''
        BP 译码算法
        #  logging.info(entry[0])
        #  entry 是一个解码缓存结果
        #  entry[0] 是喷泉码编码时选中的源符号编号列表，长度即为度
        #  entry[1] 是喷泉码选中的符号 xor 后的结果
        #  chunk 是解码后的结果
        '''
        #  下面的 for 用于更新 entry 中的水滴，若水滴中包含已解码的码块，则将该部分去除
        #  执行结果是 entry 中的水滴不包含已解码的码块，度会减少或不变
        for chunk_num in entry[0]:
            if self.chunks[chunk_num] is not None:
                entry[1] = xor(entry[1], self.chunks[chunk_num])
                # entry[1] = x_o_r(entry[1], self.chunks[chunk_num])
                entry[0].remove(chunk_num)
        #  若度为 1,则说明该度的码块已经被解码出来，更新 chunk 后继续进行entry 中的其他
        #  元素的更新
        if len(entry[0]) == 1:
            self.chunks[entry[0][0]] = entry[1]
            self.entries.remove(entry)
            for former_entry in self.entries:
                if entry[0][0] in former_entry[0]:
                    self.updateEntry(former_entry)
                    
    def getString(self):
        return ''.join(x or ' _ ' for x in self.chunks)

    def get_bits(self):
        current_bits = ''
        bitarray_factory = bitarray.bitarray(endian='big')
        logging.info('current chunks')
        logging.info([ii if ii == None else '++++' for ii in self.chunks])

        # data = ''.join(chunk for chunk in self.chunks)
        # with open(RECV_PATH, "w", encoding='utf-8') as f:
        #     f.write(data)

        for chunk in self.chunks:
            if chunk == None:
                break
            else:
                # for ii in chunk:
                    # a = str(ii)
                tmp = bitarray_factory.frombytes(chunk)
        return bitarray_factory

    def get_w1_bits(self, w1_size):
        current_bits = ''
        bitarray_factory = bitarray.bitarray(endian='big')
        logging.info('current chunks')
        logging.info([ii if ii == None else '++++' for ii in self.chunks])

        for chunk in self.chunks[:int(round(self.num_chunks * w1_size))]:
            if chunk == None:
                break
            else:
                # for ii in chunk:
                # a = str(ii)
                tmp = bitarray_factory.frombytes(chunk)
        return bitarray_factory

    def isDone(self):
        return (None not in self.chunks) and (len(self.chunks) != 0) 

    # 返回未译出码块
    def getProcess(self):
        idx = 0
        process = []
        for chunk in self.chunks:
            if chunk is None:
                process.append(idx)
            idx += 1
        return process

    def is_w1_done(self, w1_size):
        return None not in self.chunks[:int(round(self.num_chunks * w1_size))]

    def chunksDone(self):
        count = 0
        for c in self.chunks:
            if c is not None:
                count+=1
        return count



    
def test_LT_fountain():
    suffix_list = ['50.txt', '100.txt', '150.txt', '200.txt', '250.txt', '300.txt', '350.txt', '400.txt', '450.txt', '500.txt']
    file_list = [DOC_PATH + '/text' + ii for ii in suffix_list]
    avg_drops_list = [0]*len(suffix_list)
    avg_idx = 0

    for f in file_list:
        m = open(f, 'r').read()
        # 测试1000次
        num_chunks_list = [0]*100
        times_list = [0]*100
        drop_num_used_list = [0]*100

        times = 0
        K = 0
        while times < 100:
            fountain = Fountain(m, 1)
            K = fountain.num_chunks
            glass = Glass(fountain.num_chunks)
            while not glass.isDone():
                a_drop = fountain.droplet()       # send

                glass.addDroplet(a_drop)          # recv
                # logging.info('+++++++++++++++++++++++++++++')
                # logging.info(glass.getString())

            num_chunks_list[times] = fountain.num_chunks
            times_list[times] = times
            drop_num_used_list[times] = glass.dropid

            logging.info("K=" + str(fountain.num_chunks) +" times: " + str(times) + 'done, receive_drop_used: ' + str(glass.dropid))
            times += 1

        res = pd.DataFrame({'num_chunks':num_chunks_list, 
            'times':times_list, 
            'drop_num_used':drop_num_used_list})
        res.to_csv(os.path.join(SIM_PATH, 'K' + '_'+ str(K) + '_' + time.asctime().replace(' ', '_').replace(':', '_') + '.csv'),  mode='a')

        avg_drops_list[avg_idx] = float(sum(drop_num_used_list) / len(drop_num_used_list))
        avg_idx += 1
    
    avg_res = pd.DataFrame({'K': [ii.split('.')[0] for ii in suffix_list], 
            'avgs':avg_drops_list})
    avg_res.to_csv(os.path.join(SIM_PATH, 'avgs' + '_' + time.asctime().replace(' ', '_').replace(':', '_') + '.csv'),  mode='a')

def test_LT_feedback_fountain():
    suffix_list = ['50.txt', '100.txt', '150.txt', '200.txt', '250.txt', '300.txt', '350.txt', '400.txt', '450.txt', '500.txt']
    file_list = [DOC_PATH + '/text' + ii for ii in suffix_list]
    avg_drops_list = [0]*len(suffix_list)
    avg_idx = 0

    for f in file_list:
        m = open(f, 'r').read()
        # 测试1000次
        num_chunks_list = [0]*100
        times_list = [0]*100
        drop_num_used_list = [0]*100

        times = 0
        K = 0
        while times < 100:
            fountain = Fountain(m, 1)
            K = fountain.num_chunks
            glass = Glass(fountain.num_chunks)
            while not glass.isDone():
                a_drop = fountain.droplet()       # send
                    
                glass.addDroplet(a_drop)          # recv
                if(glass.dropid >= K):
                    glass.all_at_once = True
                    fountain.all_at_once = True
                    # 之后每10个包反馈进度
                    if((glass.dropid-K)%10 == 0):
                        fountain.chunk_process = glass.getProcess()
                

                # logging.info('+++++++++++++++++++++++++++++')
                # logging.info(glass.getString())

            num_chunks_list[times] = fountain.num_chunks
            times_list[times] = times
            drop_num_used_list[times] = glass.dropid

            logging.info("feedback_K=" + str(fountain.num_chunks) +" times: " + str(times) + 'done, receive_drop_used: ' + str(glass.dropid))
            times += 1

        res = pd.DataFrame({'num_chunks':num_chunks_list, 
            'times':times_list, 
            'drop_num_used':drop_num_used_list})
        res.to_csv(os.path.join(SIM_PATH, 'feedback_K' + '_'+ str(K) + '_' + time.asctime().replace(' ', '_').replace(':', '_') + '.csv'),  mode='a')

        avg_drops_list[avg_idx] = float(sum(drop_num_used_list) / len(drop_num_used_list))
        avg_idx += 1
    
    avg_res = pd.DataFrame({'K': [ii.split('.')[0] for ii in suffix_list], 
            'avgs':avg_drops_list})
    avg_res.to_csv(os.path.join(SIM_PATH, 'feedback_avgs' + '_' + time.asctime().replace(' ', '_').replace(':', '_') + '.csv'),  mode='a')

def test_ew_fountain():
    suffix_list = ['50.txt', '100.txt', '150.txt', '200.txt', '250.txt', '300.txt', '350.txt', '400.txt', '450.txt', '500.txt']
    file_list = [DOC_PATH + '/text' + ii for ii in suffix_list]
    avg_drops_list = [0]*len(suffix_list)
    avg_idx = 0

    for f in file_list:
        m = open(f, 'r').read()
        # 测试1000次
        num_chunks_list = [0]*100
        times_list = [0]*100
        drop_num_used_list = [0]*100

        times = 0
        K = 0
        while times < 100:
            fountain = EW_Fountain(m, 1)
            K = fountain.num_chunks
            glass = Glass(fountain.num_chunks)
            ew_drop = None
            while not glass.isDone():
                a_drop = fountain.droplet()       # send
                ew_drop = EW_Droplet(a_drop.data, a_drop.seed, a_drop.num_chunks)

                glass.addDroplet(ew_drop)          # recv

            num_chunks_list[times] = fountain.num_chunks
            times_list[times] = times
            drop_num_used_list[times] = glass.dropid

            logging.info("EW K=" + str(fountain.num_chunks) +" times: " + str(times) + 'done, receive_drop_used: ' + str(glass.dropid))
            times += 1

        res = pd.DataFrame({'num_chunks':num_chunks_list, 
            'times':times_list, 
            'drop_num_used':drop_num_used_list})
        res.to_csv(os.path.join(SIM_PATH, 'EW_K' + '_'+ str(K) + '_' + time.asctime().replace(' ', '_').replace(':', '_') + '.csv'),  mode='a')

        avg_drops_list[avg_idx] = float(sum(drop_num_used_list) / len(drop_num_used_list))
        avg_idx += 1
    
    avg_res = pd.DataFrame({'K': [ii.split('.')[0] for ii in suffix_list], 
            'avgs':avg_drops_list})
    avg_res.to_csv(os.path.join(SIM_PATH, 'EW_avgs' + '_' + time.asctime().replace(' ', '_').replace(':', '_') + '.csv'),  mode='a')

def test_ew_feedback_fountain():
    suffix_list = ['50.txt', '100.txt', '150.txt', '200.txt', '250.txt', '300.txt', '350.txt', '400.txt', '450.txt', '500.txt']
    file_list = [DOC_PATH + '/text' + ii for ii in suffix_list]
    avg_drops_list = [0]*len(suffix_list)
    avg_idx = 0

    for f in file_list:
        m = open(f, 'r').read()
        # 测试1000次
        num_chunks_list = [0]*100
        times_list = [0]*100
        drop_num_used_list = [0]*100

        times = 0
        K = 0
        while times < 100:
            fountain = EW_Fountain(m, 1)
            K = fountain.num_chunks
            glass = Glass(fountain.num_chunks)
            ew_drop = None
            while not glass.isDone():
                a_drop = fountain.droplet()       # send
                # ew_drop = EW_Droplet(a_drop.data, a_drop.seed, a_drop.num_chunks, a_drop.process)

                glass.addDroplet(a_drop)          # recv
                if(glass.dropid >= K):
                    glass.all_at_once = True
                    fountain.all_at_once = True
                    # 之后每10个包反馈进度
                    if((glass.dropid-K)%10 == 0):
                        fountain.chunk_process = glass.getProcess()
                

                # logging.info('+++++++++++++++++++++++++++++')
                # logging.info(glass.getString())

            num_chunks_list[times] = fountain.num_chunks
            times_list[times] = times
            drop_num_used_list[times] = glass.dropid

            logging.info("feedback_EW_K=" + str(fountain.num_chunks) +" times: " + str(times) + 'done, receive_drop_used: ' + str(glass.dropid))
            times += 1

        res = pd.DataFrame({'num_chunks':num_chunks_list, 
            'times':times_list, 
            'drop_num_used':drop_num_used_list})
        res.to_csv(os.path.join(SIM_PATH, 'feedback_EW_K' + '_'+ str(K) + '_' + time.asctime().replace(' ', '_').replace(':', '_') + '.csv'),  mode='a')

        avg_drops_list[avg_idx] = float(sum(drop_num_used_list) / len(drop_num_used_list))
        avg_idx += 1
    
    avg_res = pd.DataFrame({'K': [ii.split('.')[0] for ii in suffix_list], 
            'avgs':avg_drops_list})
    avg_res.to_csv(os.path.join(SIM_PATH, 'feedback_EW_avgs' + '_' + time.asctime().replace(' ', '_').replace(':', '_') + '.csv'),  mode='a')



if __name__ == "__main__":
    # test_LT_fountain()
    # test_LT_feedback_fountain()
    # test_ew_fountain()
    test_ew_feedback_fountain()
    pass


