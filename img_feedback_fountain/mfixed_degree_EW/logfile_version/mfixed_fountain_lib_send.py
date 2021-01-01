# _*_ coding=utf-8 _*_
from __future__ import print_function
from math import ceil, log
import sys, os
import random
import json
import bitarray
import numpy as np
from time import sleep
import logging

LIB_PATH = os.path.dirname(__file__)
logFilename = os.path.join(LIB_PATH, 'sendlog.log')

logging.basicConfig(level=logging.INFO, 
                filename=logFilename,
                filemode='a',
                format='%(asctime)s %(filename)s:%(lineno)s %(levelname)s-%(message)s',
                datefmt = '%y-%m-%d %H:%M'
                )

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


# 度分布函数
def soliton(K):
    ''' 理想弧波函数 '''
    d = [ii + 1 for ii in range(K)]
    d_f = [1.0 / K if ii == 1 else 1.0 / (ii * (ii - 1)) for ii in d]
    while 1:
        # i = np.random.choice(d, 1, False, d_f)[0]
        yield np.random.choice(d, 1, False, d_f)[0]

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

def poisson_func(k):
    d = [1, 2, 3, 4, 5, 8, 9, 19, 65, 66]
    tmp = 1.0 / (k * log(k))
    d_f = [0.003269+65*tmp, 0.49357-17*tmp, 0.16622-33*tmp, 0.072646-15*tmp, 0.082558-tmp, 0.056028-9*tmp, 0.037229+8*tmp, 0.05559, 0.029723-tmp, 0.003167+3*tmp]
    while True:
        yield np.random.choice(d, 1, False, d_f)[0]


# 度分布函数选出度值后随机选码块
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
    return [ii for ii in np.random.choice(chunks, 1, False)]

def mfixed_degree_randChunkNums(num_chunks):
    size = poisson_func(num_chunks).__next__()
    return [ii for ii in random.sample(range(num_chunks), size)]



class Droplet:
    ''' 储存随机数种子，并有一个计算本水滴中包含的数据块编码的方法'''
    def __init__(self, data, seed, num_chunks, process, func_id, feedback_idx):
        self.data = data
        self.seed = seed
        self.num_chunks = num_chunks
        self.process = process
        self.func_id = func_id
        self.feedback_idx = feedback_idx # 反馈时此编码包编码时的进度，用于和接收端同步，译码才能正确

    # 下面两个用于接收端恢复出这个块是由哪些块异或出来的
    def robust_chunkNums(self):
        random.seed(self.seed)
        np.random.seed(self.seed)
        return robust_randChunkNums(self.num_chunks)
    
    def all_at_once_chunkNums(self):
        random.seed(self.seed)
        np.random.seed(self.seed)
        return all_at_once_randChunkNums(self.process)

    def mfixed_degree_chunkNums(self):
        random.seed(self.seed)
        np.random.seed(self.seed)
        return mfixed_degree_randChunkNums(self.num_chunks)

    # 发送用
    def toBytes(self):
        '''
        使用一个字节存储chunks_size,
        num_chunks int 度数，一个字节                                  2个字节
        seed 随机数种子，两个字节                                       4个字节
        返回的结构是一个字节加后面跟着2 * n 个字节，后续跟着数据
        '''
        num_chunks_bits = format(int(self.num_chunks), "016b")
        seed_bits = format(int(self.seed), "032b")
        func_id_bits = format(int(self.func_id), "08b")
        feedback_idx_bits = format(int(self.feedback_idx), "08b")
        logging.info('fountain num_chunks:{}, seed:{}, func_id:{}, feedback_idx:{}'.format(self.num_chunks, self.seed, self.func_id, self.feedback_idx))

        return bitarray.bitarray(num_chunks_bits + seed_bits + func_id_bits + feedback_idx_bits).tobytes() + self.data



class Fountain(object):
    # 继承了object对象，拥有了好多可操作对象，这些都是类中的高级特性。python 3 中已经默认加载了object
    def __init__(self, data, chunk_size, seed=None):
        self.data = data
        self.chunk_size = chunk_size
        self.num_chunks = int(ceil(len(data) / float(chunk_size)))
        self.seed = seed
        # 反馈相关
        self.all_at_once = False
        self.chunk_selected = []
        self.chunk_process = []
        random.seed(seed)
        np.random.seed(seed)
        self.func_id = 0 # 度分布函数：0(RSD，默认)，1(度一分布)，2(改进固定度分布)
        self.feedback_idx = 0 # 反馈时此编码包编码时的进度，用于和接收端同步，译码才能正确。只有当func_id为1时，才有意义。
        self.show_info()

    def show_info(self):
        logging.info('Fountain info')
        logging.info('data len: {}'.format(len(self.data)))
        logging.info('chunk_size: {}'.format(self.chunk_size))
        logging.info('num_chunks: {}'.format(self.num_chunks))

    def droplet(self):
        self.updateSeed()

        if not self.all_at_once:
            self.chunk_selected = mfixed_degree_randChunkNums(self.num_chunks)
        else:
            self.func_id = 1
            self.chunk_selected = all_at_once_randChunkNums(self.chunk_process)
        logging.info("seed: {}".format(self.seed))
        logging.info("send chunk list: {}".format(self.chunk_selected))

        data = None
        for num in self.chunk_selected:
            if data is None:
                data = self.chunk(num)
            else:
                # data = xor(data, self.chunk(num))
                data = x_o_r(data, self.chunk(num))               # 被选到的数据块异或，异或时存在两字符串长度不一样
        return Droplet(data, self.seed, self.num_chunks, self.chunk_process, self.func_id, self.feedback_idx)

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
    def __init__(self, data, chunk_size, ew_process=[], seed=None, w1_size=0.15, w1_pro=0.084):
        Fountain.__init__(self, data, chunk_size=chunk_size, seed=None)
        logging.info("-----------------EW_Fountain------------")
        self.w1_p = w1_size
        self.w1_pro = w1_pro
        self.windows_id_gen = self.windows_selection()
        self.w1_size = int(round(self.num_chunks * self.w1_p))
        self.w2_size = self.num_chunks
        self.w1_random_chunk_gen = robust_soliton(self.w1_size),
        self.w2_random_chunk_gen = poisson_func(self.w2_size)

        self.all_at_once = False
        self.chunk_process = ew_process
        self.chunk_selected = []
        self.func_id = 0
        self.feedback_idx = 0

    def droplet(self):
        self.updateSeed()
        if not self.all_at_once:
            self.chunk_selected = self.EW_mfixed_RandChunkNums(self.num_chunks)
        else:
            self.func_id = 1
            self.chunk_selected = self.EW_all_at_once_RandChunkNums()

        data = None
        for num in self.chunk_selected:
            if data is None:
                data = self.chunk(num)
            else:
                data = x_o_r(data, self.chunk(num))
        logging.info('send chunk_list : {}'.format(self.chunk_selected))
        return EW_Droplet(data, self.seed, self.num_chunks, self.chunk_process, self.func_id, self.feedback_idx)

    def EW_mfixed_RandChunkNums(self, num_chunks):
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
    def __init__(self, data, seed, num_chunks, process, func_id, feedback_idx, w1_size=0.15, w1_pro=0.084):
        Droplet.__init__(self, data, seed, num_chunks, process, func_id=func_id, feedback_idx=feedback_idx)
        m = ' ' * num_chunks * len(data)
        self.ower = EW_Fountain(m, len(self.data), w1_size=w1_size, w1_pro=w1_pro, ew_process=process)

    def mfixed_degree_chunkNums(self):
        random.seed(self.seed)
        np.random.seed(self.seed)
        return self.ower.EW_mfixed_RandChunkNums(self.num_chunks)

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
        self.glass_process = []
        self.glass_process_history = []
        
    def addDroplet(self, drop):
        self.dropid += 1
        self.droplets.append(drop)
        entry = [drop.mfixed_degree_chunkNums(), drop.data] if drop.func_id==0 else [drop.all_at_once_chunkNums(), drop.data]      # 和发送端生成的所选数据块一样
        self.entries.append(entry)
        logging.info('recv chunk_list : {}'.format(entry[0]))
        self.updateEntry(entry)

    def droplet_from_Bytes(self, d_bytes):
        byte_factory = bitarray.bitarray(endian='big')
        byte_factory.frombytes(d_bytes[0:2])
        num_chunks = int(byte_factory.to01(), base=2)

        byte_factory1 = bitarray.bitarray(endian='big')
        byte_factory1.frombytes(d_bytes[2:6])
        seed = int(byte_factory1.to01(), base=2)

        byte_factory3 = bitarray.bitarray(endian='big')
        byte_factory3.frombytes(d_bytes[6:7])
        func_id = int(byte_factory3.to01(), base=2)

        byte_factory4 = bitarray.bitarray(endian='big')
        byte_factory4.frombytes(d_bytes[7:8])
        feedback_idx = int(byte_factory4.to01(), base=2)

        data = d_bytes[8:]

        logging.info('seed:{}, glass_num_chunks:{}, func_id:{}, feedback_idx:{}, data len:{},'.format(seed, num_chunks, func_id, feedback_idx, len(data)))
        if self.chunk_bit_size == 0:
            byte_factory2 = bitarray.bitarray(endian='big')
            byte_factory2.frombytes(data)
            self.chunk_bit_size = byte_factory2.length()
            
        return Droplet(data, seed, num_chunks, process=self.glass_process_history[feedback_idx], func_id = func_id, feedback_idx = feedback_idx) if func_id==1 else Droplet(data, seed, num_chunks, process=[], func_id = func_id, feedback_idx=feedback_idx)

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

                # str1 = str(entry[1])
                # str2 = str(self.chunks[chunk_num])                               ### xor str
                # entry[1] = xor(str1, str2)

                entry[1] = x_o_r(entry[1], self.chunks[chunk_num])
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
        return ''.join(x.decode() or ' _ ' for x in self.chunks)

    def get_bits(self):
        current_bits = ''
        bitarray_factory = bitarray.bitarray(endian='big')
        # logging.info('current chunks')
        # logging.info([ii if ii == None else '++++' for ii in self.chunks])

        for chunk in self.chunks:
            if chunk == None:
                break
            else:
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
                tmp = bitarray_factory.frombytes(chunk)
        return bitarray_factory

    def isDone(self):
        return (None not in self.chunks) and (len(self.chunks) != 0) 

    def is_w1_done(self, w1_size):
        return None not in self.chunks[:int(round(self.num_chunks * w1_size))]

    def chunksDone(self):
        count = 0
        for c in self.chunks:
            if c is not None:
                count+=1
        return count
    
    # 返回未译出码块
    def getProcess(self):
        idx = 0
        process = []
        for chunk in self.chunks:
            if chunk is None:
                process.append(idx)
            idx += 1
        return process
    
    def getProcess_bits(self):
        process_bits = []
        for chunk in self.chunks:
            if chunk is None:
                process_bits.append(0)
            else:
                process_bits.append(1)
        return process_bits



if __name__ == "__main__":
    pass


