#!/usr/bin/env python2
import socket
import time
import random
import re
import sys

if len(sys.argv) == 4:
    host = sys.argv[1] # '192.168.10.2'
    port = int(sys.argv[2])
    url = sys.argv[3] # '/user=admin_password=tlJwpbo6_channel=1_stream=0.sdp?real_stream' # 92 93 94
else:
    print "%s host port url" % sys.argv[0]
    exit(1)

dump = True # Save RTP to file or not
dumpraw = False # Save raw RTP to file or not

def hx(s):
    return " ".join("{:02x}".format(ord(c)) for c in s)

def connect():
    descmsg = "DESCRIBE rtsp://"+host+url+" RTSP/1.0\r\nCSeq: 0\r\n"
    setupmsg = "SETUP rtsp://"+host+url+" RTSP/1.0\r\nCSeq: 1\r\nTransport: RTP/AVP/TCP;unicast\r\n"
    playmsg = "PLAY rtsp://"+host+url+" RTSP/1.0\r\nCSeq: 2\r\nRange: npt=0.000-\r\n"
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 16*1024*1024)
    s.setsockopt(socket.SOL_SOCKET, socket.TCP_WINDOW_CLAMP, 16*512*1024)
    s.connect((host, port))
    if True:
        s.send(descmsg+"\r\n")
        res = s.recv(1500)
    s.send(setupmsg+"\r\n")
    res = s.recv(1500)
    sess = re.search("\r\n(Session:.*?)(?:;|\r\n)", res).group(1)+"\r\n"
    s.send(playmsg+sess+"\r\n", 0)
    res = s.recv(1500)
    pos = res.find("\r\n\r\n")
    if pos>-1:
        res = res[pos+4:]
    else:
        res = ""
    return (s, res, sess)

def ping1(s, sess, cseq):
    pingmsg = "GET_PARAMETER rtsp://"+host+url+" RTSP/1.0\r\n CSeq: "+str(cseq)+"\r\n"+sess+"\r\n"
    s.send(pingmsg, 0)
    return cseq+1

def ping2(s, sess, cseq):
    pingmsg = "OPTIONS rtsp://"+host+url+" RTSP/1.0\r\n CSeq: "+str(cseq)+"\r\n"+sess+"\r\n"
    s.send(pingmsg, 0)
    return cseq+1

def ping(*args, **kwargs):
    return ping1(*args, **kwargs)

rtp = 0
rtpl = 0
k=1
q=1
pi=1
sl=0
sll=0
st=1
s,buf,sess=connect()
cseq = 3
prevts=None
prev=None
loss=0
frames=0
framesimp=0
framesimpt = 0
start = time.time()
wait=True
fdump = sys.stdout
fdumpraw = sys.stdout

while True:
  d = time.time()-start
  if (round(d)%30)<5:
    if pi==0:
      cseq=ping(s, sess, cseq)
      pi = 1
  else:
    pi = 0
  if (round(d*10)%3)==0:
    if k==0:
      #cseq=ping(s, sess, cseq)
      framesimp = frames
      framesimpt = d
      loss=0
      k=1
  else:
    k=0
  if (round(d)%4==0):
    if q==0:
      st = 0.5+round(random.random()*2,2) # 0.5+d.round/100.0
      q=1
      sl=1
  else:
    q=0
  while len(buf)<4:
    buf += s.recv(4-len(buf))
  if buf[0]=="$":
    l = (ord(buf[2])<<8)+ord(buf[3])
    while len(buf)-4 < l:
      buf += s.recv(l+4-len(buf))
    if buf[1]=="\x00":
      packno = (ord(buf[6])<<8)+ord(buf[7])
      if prev is not None:
          if prev>packno: prev-=65536
          loss += packno-prev-1
      prev = packno
      ts = (ord(buf[8])<<24)+(ord(buf[9])<<16)+(ord(buf[10])<<8)+ord(buf[11])
      if prevts is not None:
          if ts!=prevts:
              frames += 1
      prevts = ts
      rtp += 1
      rtpl += l
      if sl==1:
        sll += l+4
      if dumpraw:
          fdumpraw.write(buf[4:4+l])
      if dump:
          # get rtp header size
          cc = ord(buf[4])&0xF # Count of CSRC records
          rtphdr = 12 + cc*4
          frag = (ord(buf[4+rtphdr])&0x1F)
          nal = (ord(buf[4+rtphdr])&0xE0)|(ord(buf[4+rtphdr+1])&0x1F)
          pstart = (ord(buf[4+rtphdr+1])&0x80)!=0
          pend = (ord(buf[4+rtphdr+1])&0x20)!=0
          if frag==7 or frag==8:
              fdump.write("\000\000\001"+buf[4+rtphdr:4+l])
              wait=False
          elif frag==28:
              if not wait:
                  if pstart:
                      fdump.write("\000\000\001"+chr(nal)+buf[4+rtphdr+2:4+l])
                  else:
                      fdump.write(buf[4+rtphdr+2:4+l])
    else:
      pass
    buf = buf[4+l:]
  elif buf[0:4]=="RTSP":
    while not "\r\n\r\n" in buf:
      buf += s.recv(40)
    pos = buf.find("\r\n\r\n")
    buf = buf[pos+4:]
  else:
    #Hexdump.dump(res)
    # try to resync
    if False:
        s,buf=connect()
    else:
        sync = -1
        last = 0
        while sync<0 and len(buf)<9000:
            buf += s.recv(1500)
            last = 0
            while last<len(buf)-4:
                if buf[last]=="$" and buf[last+1]=="\x00":
                    synclen = (ord(buf[last+2])<<8)+ord(buf[last+3])
                    if synclen < 1500:
                        if len(buf)>last+4+synclen:
                            if buf[last+4+synclen]=="$":
                                sync = last # found correct resync position
                                break
                            else:
                                last += 1 # wrong position, check next
                        else:
                            break # need more info to verify is correct resync position
                    else:
                        last += 1 # wrong position, check next
                else:
                    last += 1 # wrong position, check next
        if sync >= 0:
            buf = buf[sync:]
        else:
            pass
s.close()
