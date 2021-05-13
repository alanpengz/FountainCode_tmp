## 带反馈喷泉码
RSD_EW和mfixed_degree_EW的区别在于用的度分布函数：
- RSD_EW的w1和w2用的都是RSD
- mfixed_degree_EW的w1采用RSD，w2采用mfixed固定度分布
- 论文和实际使用中我使用的是RSD_EW，因为通过仿真发现RSD_EW的译码开销性能更加稳定且更低

imgSonicFeedback* 和 imgVLCFeedback*的区别：
- imgSonicFeedback* 使用水声进行反馈，在代码中体现在反馈信息通过串口进行读写，且水声反馈存在传播和处理延迟
- imgVLCFeedback* 使用可见光通信进行反馈，在代码中体现在反馈信息通过SPI接口进行读写，反馈延迟可忽略不计


数据传输序列化和反序列化测试
```py
#序列化
nextid = format(int(1), "08b")
w1size = format(int(6), "08b")
imgW = format(int(256), "016b")
imgH = format(int(256), "016b")
SPIHTlen = format(int(24600), "032b")
level = format(int(3), "08b")
wavelet = format(int(1), "08b")
mode = format(int(1), "08b")

byte = bitarray.bitarray(nextid + w1size + imgW+ imgH+ SPIHTlen+ level+ wavelet+ mode).tobytes()
print(byte)

#反序列化
byte_factory = bitarray.bitarray(endian='big')
byte_factory.frombytes(byte[0:1])
nextids = int(byte_factory.to01(), base=2)

byte_factory1 = bitarray.bitarray(endian='big')
byte_factory1.frombytes(byte[1:2])
w1sizes = int(byte_factory1.to01(), base=2)

byte_factory3 = bitarray.bitarray(endian='big')
byte_factory3.frombytes(byte[2:4])
imgWs = int(byte_factory3.to01(), base=2)

byte_factory4 = bitarray.bitarray(endian='big')
byte_factory4.frombytes(byte[4:6])
imgHs = int(byte_factory4.to01(), base=2)

byte_factory5 = bitarray.bitarray(endian='big')
byte_factory5.frombytes(byte[6:10])
SPIHTlens = int(byte_factory5.to01(), base=2)

print(nextids,w1sizes,imgWs,imgHs,SPIHTlens)
```