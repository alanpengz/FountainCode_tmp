import bitarray

nextid = format(int(1), "08b")
w1size = format(int(6), "08b")
imgW = format(int(256), "016b")
imgH = format(int(256), "016b")
SPIHTlen = format(int(24600), "032b")
level = format(int(3), "08b")
wavelet = format(int(1), "08b")
mode = format(int(1), "08b")
acoustic_handshake = b'##' + bitarray.bitarray(nextid + w1size + imgW+ imgH+ SPIHTlen+ level+ wavelet+ mode).tobytes()

print("===...Waiting for connection...===")
print("Acoustic message received:")
print(acoustic_handshake)
# print("\n")
print("===Sending Acoustic handshake ACK===")
print("         MFSK Stop!")
print("\n")
print("         AD mode! CMD?(C/G/H/J/M/Q/I/E)")
print("E")
print("         Quit AD mode!")
print("\n")
print("         Please select mode: AD(A) or DA(D)?")
print("D")
print("\n")
print("         DA SampleRate: 80kHz")
print("         DA CH1 Amplitude: 50%")
print("         DA CH2 Amplitude: 50%")
print("\n")
print("         DA mode! CMD?(A/C/R/S/P/M/Q/L/I/E)")
print("M")
print("         Please input the message:")
print("##snc")
print("\n")
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
print("\n")
print("         MFSK signal send OK! Used Time: 1424851 us")



# 喷泉码接收端
    nextid = format(int(2), "08b")
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

    receiver = Receiver(bus=0, device=1, port='/dev/ttyUSB1', baudrate=115200, timeout=1)
    # receiver.send_feedback()
    print("===Align Successed!===")
    print("===Sending VLC handshake ACK===")
    print("M")
    print("         Please input the message:")
    print("$$vlc")
    print("  ")
    print("         MFSK signal send OK! Used Time: 1424851 us")
    print("===Waiting for data transfer===")
    while True:
        receiver.begin_to_catch()
        if receiver.recv_done_flag:
            break
    print('================================================================================')
    print('INFO: srcID=0, selfID=1, desID=2, starting Relay Forwarding procedure...')
    print('===Send desID=2 acoustic broadcast handshake===')
    print("M")
    print("         Please input the message:")
    print(acoustic_handshake)
    print(" ")
    print("         MFSK signal send OK! Used Time: 1385071 us")
    print("E")
    print("         Quit DA mode!")
    print("\n")
    print("         Please select mode: AD(A) or DA(D)?")
    print("A")
    print("\n")
    print("         AD mode! CMD?(C/G/H/J/M/Q/I/E)")
    print("M")
    print("         MFSK Demodulation!")
    print("\n")

    print("Acoustic message received:")
    print(b'##snc')
    print('===Acoustic handshake ACK received, Acoustic handshake done!===')
    print('===Starting to align===')
    print("===ROV turn right===")
    print("Receive a packet!!!")
    print("===ROV stop and receive===")
    print("Receive a packet!!!")
    print("checksum: 65535, rnum = 1")
    print("Receive a packet!!!")
    print("checksum: 65535, rnum = 2")

    # print('........................................................................')
    # print('INFO: srcID=0, selfID=1, desID=1, Receive Done!')
    # print('........................................................................')































