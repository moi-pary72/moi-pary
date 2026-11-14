import struct,sys,re,datetime
from pathlib import Path
u16=lambda d,o:struct.unpack_from('<H',d,o)[0]
u32=lambda d,o:struct.unpack_from('<I',d,o)[0]
class OLE:
 def __init__(self,filename):
  self.b=Path(filename).read_bytes();assert self.b[:8]==bytes.fromhex('d0cf11e0a1b11ae1')
  self.sec=1<<u16(self.b,0x1e); self.mini=1<<u16(self.b,0x20)
  dif=list(struct.unpack_from('<109I',self.b,0x4c)); nxt=u32(self.b,0x44)
  for i in range(u32(self.b,0x48)):
   a=self.sect(nxt);dif+=list(struct.unpack_from('<%dI'%((self.sec//4)-1),a));nxt=u32(a,self.sec-4)
  fatidx=dif[:u32(self.b,0x2c)];self.fat=[]
  for idx in fatidx:
   if idx < 0xfffffffa:self.fat+=list(struct.unpack('<%dI'%(self.sec//4),self.sect(idx)))
  dire=self.chain(u32(self.b,0x30));self.entries={}
  for i in range(0,len(dire),128):
   e=dire[i:i+128];
   if len(e)!=128:continue
   n=e[:u16(e,64)-2].decode('utf-16le',errors='ignore') if u16(e,64)>2 else ''
   if n:self.entries[n]={'type':e[66],'start':u32(e,116),'size':struct.unpack_from('<Q',e,120)[0]}
  root=self.entries.get('Root Entry');self.mstream=self.chain(root['start']) if root else b''
  self.minifat=[];n=u32(self.b,0x3c)
  if n<0xfffffffa and u32(self.b,0x40):
   mini_fat_raw=self.chain(n)
   self.minifat=list(struct.unpack('<%dI'%(len(mini_fat_raw)//4),mini_fat_raw))
 def sect(self,i):return self.b[(i+1)*self.sec:(i+2)*self.sec]
 def chain(self,i):
  out=bytearray();seen=set()
  while i<0xfffffffa and i not in seen and i<len(self.fat):
   seen.add(i);out+=self.sect(i);i=self.fat[i]
  return bytes(out)
 def read(self,name):
  e=self.entries[name];sz=e['size'];i=e['start']
  if sz>=u32(self.b,0x38):return self.chain(i)[:sz]
  out=bytearray();seen=set()
  while i<0xfffffffa and i not in seen and i<len(self.minifat):
   seen.add(i);out+=self.mstream[i*self.mini:(i+1)*self.mini];i=self.minifat[i]
  return bytes(out[:sz])

def records(b,start=0):
 p=start
 while p+4<=len(b):
  typ,size=struct.unpack_from('<HH',b,p);data=b[p+4:p+4+size]
  if len(data)<size:break
  yield (p,typ,data)
  p+=4+size

def uni(d,pos,size,flag):
 # BIFF uncompressed (UTF-16) or compressed latin-1
 return (d[pos:pos+size*(2 if flag&1 else 1)].decode('utf-16le' if flag&1 else 'latin-1','replace'),pos+size*(2 if flag&1 else 1))

def read_sst(chunks):
 # SST sometimes has CONTINUE segments; handle properly by returning padded string count
 allbytes=b''.join(chunks)
 if len(allbytes)<8:return []
 count,unique=struct.unpack_from('<II',allbytes)
 # track chunk boundaries for compression flag at continuation of character data
 boundary=[sum(map(len,chunks[:i])) for i in range(1,len(chunks))]
 out=[];pos=8
 for j in range(unique):
  try:
   cch=u16(allbytes,pos);flags=allbytes[pos+2];pos+=3
   rich=0;ext=0
   if flags&8:rich=u16(allbytes,pos);pos+=2
   if flags&4:ext=u32(allbytes,pos);pos+=4
   # strings may cross chunk boundaries. at transition inside chars flags byte
   chars=[];wide=bool(flags&1)
   while len(chars)<cch:
    bnd=next((x for x in boundary if x>pos),len(allbytes))
    unit=2 if wide else 1
    n=min(cch-len(chars),(bnd-pos)//unit)
    if n:
     raw=allbytes[pos:pos+n*unit]
     chars.extend(raw.decode('utf-16le' if wide else 'latin1','replace'))
     pos+=n*unit
    if len(chars)<cch:
     if pos in boundary:wide=bool(allbytes[pos]&1);pos+=1
     elif pos<bnd:pos=bnd
     else:break
   s=''.join(chars)
   out.append(s)
   pos+=rich*4+ext
  except Exception as e:
   print('SST ERROR',j,type(e).__name__,str(e),file=sys.stderr);break
 return out

def xls_book(path):
 b=OLE(path).read('Workbook');bounds=[];sst=[];sst_pending=False
 for p,t,d in records(b):
  if t==0x85:
   off=u32(d,0);clen=d[6];flags=d[7];name,_=uni(d,8,clen,flags);bounds.append((name,off))
  if t==0xfc:sst=[d];sst_pending=True
  elif t==0x3c and sst_pending:sst.append(d)
  elif t!=0x3c:sst_pending=False
 strings=read_sst(sst);sheets=[]
 for name,off in bounds:
  cells={};merged=[];height=0;width=0
  for p,t,d in records(b,off):
   if t==0x0a:break
   if t==0x200:height=u32(d,4);width=u16(d,10)
   if t==0xe5:
    for i in range(u16(d,0)):
     if 2+i*8+8<=len(d):merged.append(struct.unpack_from('<HHHH',d,2+i*8))
   if t==0xfd:
    r,c,xf,idx=struct.unpack_from('<HHHI',d)
    if idx <len(strings): cells[(r,c)]=strings[idx]
   if t==0x27e:
    r,c,xf=struct.unpack_from('<HHH',d);v=u32(d,6);# RK
    if v&2: value=((v>>2) if v<0x80000000 else (v>>2)-0x40000000)
    else:value=struct.unpack('<d',struct.pack('<Q',(v & 0xfffffffc)<<32))[0]
    if v&1:value/=100
    cells[(r,c)]=value
   if t==0x203:
    r,c,xf=struct.unpack_from('<HHH',d);cells[(r,c)]=struct.unpack_from('<d',d,6)[0]
   if t==0xbe:
    r,c=struct.unpack_from('<HH',d);last=u16(d,len(d)-2)
    for k in range((len(d)-6)//6):
     xf,v=struct.unpack_from('<HI',d,4+6*k)
     if v&2:value=((v>>2) if v<0x80000000 else (v>>2)-0x40000000)
     else:value=struct.unpack('<d',struct.pack('<Q',(v & 0xfffffffc)<<32))[0]
     if v&1:value/=100
     cells[(r,c+k)]=value
  sheets.append({'name':name,'cells':cells,'merged':merged,'height':height,'width':width})
 return sheets

if __name__=='__main__':
 for path in sys.argv[1:]:
  print('\n###',path)
  try:
   ss=xls_book(path)
   for s in ss:
    print('sheet',repr(s['name']),'cells',len(s['cells']),'merges',len(s['merged']),'dims',s['height'],s['width'])
    for r in range(18):
     vals=['%d:%s'%(c,str(v)[:65]) for (row,c),v in sorted(s['cells'].items()) if row==r and str(v).strip()]
     if vals:print(' ',r,' | '.join(vals[:22]))
    break
  except Exception as e:import traceback;traceback.print_exc()
