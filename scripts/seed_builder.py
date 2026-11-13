"""Produces verified initial (offline) snapshot from user-provided sample files.
Not needed for hosted runtime; examples show the week 09.11-14.11.2026."""
import json,re,sys,datetime
from pathlib import Path
from xls_biff import xls_book
DAYS=['Понедельник','Вторник','Среда','Четверг','Пятница','Суббота']
DAY_RE=re.compile(r'(Понедельник|Вторник|Среда|Четверг|Пятница|Пянтица|Суббота)\s+(\d{2}\.\d{2}\.\d{2})',re.I)
TIME_RE=re.compile(r'(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})')

def clean(val):
 return re.sub(r'\s+',' ',val).strip() if isinstance(val,str) else ''

def parse_xls(raw_path):
 data={};dates=[]
 for sh in xls_book(raw_path):
  cells=sh['cells'];h=sh['height'];w=sh['width']; headers=[]
  for c in range(3,w,3):
   t=clean(cells.get((0,c)))
   if t and not t.startswith(('Фамилия','Каб')) and re.search(r'-\d{2}-',t):headers.append((c,t))
  day='';date=''
  for r in range(1,h):
   dt=DAY_RE.search(clean(cells.get((r,0))))
   if dt:
    day=dt.group(1).replace('Пянтица','Пятница').capitalize();date=dt.group(2)
    if date not in dates:dates.append(date)
   if not day:continue
   time_raw=clean(cells.get((r,2)));m=TIME_RE.search(time_raw)
   if not m:continue
   tm=f'{int(m.group(1).split(":")[0]):02}:{m.group(1).split(":")[1]}–{int(m.group(2).split(":")[0]):02}:{m.group(2).split(":")[1]}'
   num=cells.get((r,1));number=int(num) if isinstance(num,(int,float)) and 1<=num<=15 and num==int(num) else None
   for c,grp in headers:
    subject=clean(cells.get((r,c)))
    if not subject or subject in ('.','-'):continue
    teacher=clean(cells.get((r,c+1)));room=clean(cells.get((r,c+2)))
    if teacher=='.':teacher=''
    if room=='.':room=''
    dest=data.setdefault(grp,{'days':{day:[] for day in DAYS}})
    dest['days'][day].append({'date':date,'number':number,'time':tm,'subject':subject,'teacher':teacher,'room':room})
 for grp in data:
  if not any(data[grp]['days'].values()):raise ValueError('Пустая группа '+grp)
 return {'groups':data,'dates':dates,'format':'xls'}

def parse_pdf(raw_path):
 import fitz
 data={};doc=fitz.open(raw_path)
 for page in doc:
  words=page.get_text('words');headers=[]
  for w in words:
   if 20 < w[1] < 38 and re.fullmatch(r'[А-ЯЁA-Z0-9()]+(?:\([А-ЯЁA-Z]+\))?-\d{2}-\d{1,2}-\d+\*{0,2}',w[4]):
    headers.append((w[0],w[4]))
  headers.sort()
  if not headers:continue
  ticks=sorted([w for w in words if 20<w[0]<55 and re.fullmatch(r'\d{1,2}:\d{2}-',w[4])],key=lambda w:w[1])
  starts=[i for i,w in enumerate(ticks) if w[4] in ('08:10-','08:15-')]
  if len(starts)!=6:
   print('WARN PDF',page.number,'dayStarts',len(starts),file=sys.stderr);continue
  # Boundary is first row of the next weekday, not a printed page margin.
  for k,(gx,g) in enumerate(headers):
   nx=headers[k+1][0] if k+1<len(headers) else page.rect.width
   width=(nx-gx) if k+1<len(headers) else (gx-headers[k-1][0]) if k else 95
   left=gx-max(4,width*.13)
   hteacher=next((w[0] for w in words if w[4]=='Фамилия' and 22<w[1]<38 and gx<w[0]<nx),gx+width*.52)
   hroom=next((w[0] for w in words if w[4]=='Каб' and 22<w[1]<39 and hteacher<w[0]<nx),gx+width*.78)
   tbound=hteacher-min(8.0,width*.078)
   rbound=hroom-min(4.0,width*.04)
   right=min(nx-max(2,width*.11),page.rect.width)
   grp=data.setdefault(g,{'days':{day:[] for day in DAYS}})
   for i,tick in enumerate(ticks):
    di=sum(i>=n for n in starts)-1
    if di<0 or di>=6:continue
    day=DAYS[di]
    y0=tick[1]-2.1;y1=(ticks[i+1][1]-1.4 if i+1<len(ticks) else tick[1]+12)
    if y1<y0:continue
    def column(a,b):
     vs=[w for w in words if a<=w[0]<b and y0<=w[1]<y1 and w[4] not in ('Фамилия','преподавателя','И.О.','Каб')]
     vs.sort(key=lambda w:(round(w[1]/3),w[0]));return clean(' '.join(w[4] for w in vs))
    subject=column(left,tbound)
    if not subject:continue
    teacher=column(tbound,rbound)
    room=column(rbound,right)
    # PDF columns can visually overlap. Never display long spillover as a room.
    if room == '.':room=''
    elif not re.fullmatch(r'(?:\d{1,3}[А-ЯA-Z]?(?:\(\d\))?/\d|[А-ЯA-Z]{2,5}/\d|ДО|БКИ|Школа хлебоп\.)',room):
     mroom=re.match(r'^(?:\d{1,3}[А-ЯA-Z]?(?:\(\d\))?/\d|[А-ЯA-Z]{2,5}/\d|ДО|БКИ)\b',room)
     room=mroom.group(0) if mroom else ''
    ends=[w for w in words if 22<w[0]<55 and re.fullmatch(r'\d{1,2}:\d{2}',w[4]) and tick[1]<w[1]<tick[1]+10 and abs(w[0]-tick[0])<7]
    end=sorted(ends,key=lambda w:w[1])[0][4] if ends else ''
    numws=[w for w in words if tick[0]-9<w[0]<tick[0]-1 and y0<=w[1]<y1 and re.fullmatch('[1-6]',w[4])]
    num=int(numws[0][4]) if numws else None
    subject=re.sub(r'\s+',' ',subject)
    if subject and len(subject)>1 and not subject.lower().startswith(('недели','занятия')):
     grp['days'][day].append({'date':(datetime.date(2026,11,9)+datetime.timedelta(days=di)).strftime('%d.%m.%y'), 'number':num,'time':tick[4].zfill(6)+end if False else f"{int(tick[4].split(':')[0]):02}:{tick[4].split(':')[1].rstrip('-')}–{end}", 'subject':subject, 'teacher':teacher, 'room':room})
 return {'groups':data,'dates':[(datetime.date(2026,11,9)+datetime.timedelta(days=i)).strftime('%d.%m.%y') for i in range(6)],'format':'pdf'}

if __name__=='__main__':
 deps={'ИКиМ':'ИКиМ.xls','ИПиС':'ИПиС.xls','ПО и СПА':'ПОиСПА.xls','ЭУиК':'ЭУиК.pdf'}
 snapshot={'source':'Примеры файлов пользователя, неделя 09–14.11.2026','departments':{}}
 for dep,fname in deps.items():
  p=Path('/mnt/data')/fname
  result=(parse_pdf(p) if fname.endswith('.pdf') else parse_xls(p))
  result['file']=fname
  if fname.endswith('.pdf'):result['quality']='pdf_preview_unverified'
  snapshot['departments'][dep]=result
  print(dep,'Групп',len(result['groups']),'Занятий',sum(sum(len(v) for v in grp['days'].values()) for grp in result['groups'].values()),'Даты',result['dates'])
  if dep=='ИКиМ':
   a=result['groups']['ДПИ-26-9-1'];print('ДПИ пример понедельник',a['days']['Понедельник'])
 Path('/mnt/data/moi_pary_v2/static/snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
