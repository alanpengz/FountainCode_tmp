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


































