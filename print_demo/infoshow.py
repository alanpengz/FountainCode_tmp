import bitarray

nextid = format(int(1), "08b")
srcid = format(int(0), "08b")
desid = format(int(2), "08b")
w1size = format(int(6), "08b")
imgW = format(int(256), "016b")
imgH = format(int(256), "016b")
SPIHTlen = format(int(24600), "032b")
level = format(int(3), "08b")
wavelet = format(int(1), "08b")
mode = format(int(1), "08b")
acoustic_handshake = b'##' + bitarray.bitarray(nextid + srcid + desid + w1size + imgW+ imgH+ SPIHTlen+ level+ wavelet+ mode).tobytes()

print("===...Waiting for connection...===")
print("Acoustic message received:")
print(acoustic_handshake)
# print("\n")
print("===Sending Acoustic handshake ACK===")
print("         MFSK Stop!")
print(" ")
print("         AD mode! CMD?(C/G/H/J/M/Q/I/E)")
print("E")
print("         Quit AD mode!")
print(" ")
print("         Please select mode: AD(A) or DA(D)?")
print("D")
print(" ")
print("         DA SampleRate: 80kHz")
print("         DA CH1 Amplitude: 50%")
print("         DA CH2 Amplitude: 50%")
print(" ")
print("         DA mode! CMD?(A/C/R/S/P/M/Q/L/I/E)")
print("M")
print("         Please input the message:")
print("##snc")
print(" ")
print("         MFSK signal send OK! Used Time: 1378561 us")
print("===Starting to align===")
print("===ROV turn right===")
print("Receive a packet!!!")
print("===ROV stop and receive===")
print("Receive a packet!!!")
print("checksum: 65535, rnum = 1")
print("Receive a packet!!!")
print("checksum: 65535, rnum = 2")
print("Receive a packet!!!")
print("checksum: 65535, rnum = 3")
print("Receive a packet!!!")
print("checksum: 65535, rnum = 4")
print("Receive a packet!!!")
print("checksum: 65535, rnum = 5")
print("Receive a packet!!!")
print("checksum: 14726, check wrong, rnum = 5")
print("Receive a packet!!!")
print("checksum: 11572, check wrong, rnum = 25")
print("Receive a packet!!!")
print("checksum: 65535, rnum = 26")
print("Receive a packet!!!")
print("checksum: 65535, rnum = 27")
print("===Align Successed!===")
print("===Sending VLC handshake ACK===")
print("M")
print("         Please input the message:")
print("$$vlc")
print(" ")
print("         MFSK signal send OK! Used Time: 1424851 us")
print("===Waiting for data transfer===")


def test():
    nextid = format(int(1), "08b")
    srcid = format(int(0), "08b")
    desid = format(int(2), "08b")
    w1size = format(int(6), "08b")
    imgW = format(int(256), "016b")
    imgH = format(int(256), "016b")
    SPIHTlen = format(int(24600), "032b")
    level = format(int(3), "08b")
    wavelet = format(int(1), "08b")
    mode = format(int(1), "08b")

    byte = bitarray.bitarray(nextid + srcid + desid + w1size + imgW+ imgH+ SPIHTlen+ level+ wavelet+ mode).tobytes()
    print(byte)

    recv_str = str(byte, encoding="utf-8")
    print(recv_str)

    msg_byte = bytes(recv_str, encoding="utf-8")

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

    print(nextid, srcid, desid, w1size, imgW, imgH, SPIHTlen, level, wavelet, mode)





































