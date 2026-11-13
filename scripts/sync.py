"""Prepare current and next week timetables for GitHub Pages.

Only normalized JSON is written to data/schedules.json, never source Excel files.
The official files are downloaded temporarily into the runner and discarded.
Runs without non-stdlib packages. Error preserves the last verified JSON for the same week.
"""
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from seed_builder import parse_xls

API='https://cloud-api.yandex.net/v1/disk/public/resources'
PUBLIC='https://disk.yandex.ru/d/Xc08g8WbTavdHQ'
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'schedules.json'
TZ=dt.timezone(dt.timedelta(hours=5))
DEPTS={'ИКиМ':('ИКИМ',),'ИПиС':('ИПИС',),'ПО и СПА':('ПОИСПА','ПОСПА'),'ЭУиК':('ЭУИК',)}
RE_DATE=re.compile(r'(\d{1,2})[.\-](\d{1,2})\s*[-–—]\s*(\d{1,2})[.\-](\d{1,2})')
UA='MoiPary/7.0 (+public academic schedule, no personal accounts)'

def utc_now():return dt.datetime.now(dt.timezone.utc)
def iso_now():return utc_now().replace(microsecond=0).isoformat().replace('+00:00','Z')
def local_today():return utc_now().astimezone(TZ).date()
def this_monday(day):return day-dt.timedelta(days=day.weekday())
def norm(s):return re.sub(r'[^А-ЯЁA-Z0-9]','',str(s).upper())

def request(url,params=None,size_limit=15_000_000):
    if params:url+='?'+urlencode(params)
    err=None
    for attempt in range(3):
        try:
            req=Request(url,headers={'User-Agent':UA,'Accept':'*/*'})
            with urlopen(req,timeout=35) as r:
                content=r.read(size_limit+1)
            if len(content)>size_limit:raise ValueError('Слишком большой ответ сервера')
            return content
        except Exception as e:
            err=e
            if attempt<2:time.sleep(1+attempt)
    raise RuntimeError('Яндекс Диск недоступен: '+str(err)[:110]) from err

def get_json(url,params):
    return json.loads(request(url,params,size_limit=4_000_000))

def listing(path=None):
    result=[]
    for offset in range(0,2000,200):
        p={'public_key':PUBLIC,'limit':200,'offset':offset}
        if path:p['path']=path
        meta=get_json(API,p)
        if meta.get('type')!='dir':raise ValueError('Общий ресурс Яндекс Диска не является папкой')
        block=meta.get('_embedded',{})
        items=block.get('items',[])
        result.extend(items)
        if not items or len(result)>=int(block.get('total',len(result))):break
    return result

def folder_start(name,today):
    m=RE_DATE.search(name)
    if not m:return None
    day,month,_,_=map(int,m.groups())
    d=[]
    for year in (today.year-1,today.year,today.year+1):
        try:d.append(dt.date(year,month,day))
        except ValueError:pass
    return min(d,key=lambda t:abs((t-today).days)) if d else None

def file_for_department(items,dept):
    matches=[]
    for x in items:
        if x.get('type')!='file':continue
        name=x.get('name','')
        if not name.lower().endswith('.xls'):continue
        if norm(name[:-4]) in DEPTS[dept]:matches.append(x)
    return max(matches,key=lambda x:x.get('modified','')) if matches else None

def download(dept,week_start,items,folder,folder_name):
    doc=file_for_department(items,dept)
    if not doc:return None, 'В папке нет файла XLS этого отделения'
    path='/'+('/'.join([folder.strip('/'),doc['name']]) if folder else doc['name'])
    link=get_json(API+'/download',{'public_key':PUBLIC,'path':path}).get('href')
    if not link or not link.startswith('https://'):raise RuntimeError('Яндекс Диск не выдал ссылку на скачивание')
    b=request(link)
    if not b.startswith(bytes.fromhex('d0cf11e0a1b11ae1')):raise ValueError('Файл уже не является XLS (формат изменился)')
    with tempfile.NamedTemporaryFile(suffix='.xls') as temp:
        temp.write(b);temp.flush()
        parsed=parse_xls(temp.name)
    if not parsed['dates']:raise ValueError('В XLS не обнаружены даты')
    start=dt.datetime.strptime(parsed['dates'][0],'%d.%m.%y').date()
    if start!=week_start:raise ValueError('Даты в Excel не совпадают с датой недельной папки')
    if not parsed['groups']:raise ValueError('В XLS не обнаружены учебные группы')
    # Important: only files officially provided by college; missing rooms are left blank.
    data={**parsed,'file':doc['name'],'department':dept,'week':folder_name,
          'source':PUBLIC,'file_modified':doc.get('modified'),'checked_at':iso_now()}
    return data,None

def sync():
    now=local_today();keys=[this_monday(now)+dt.timedelta(days=d) for d in (0,7)]
    prior={}
    if OUT.exists():
        try:prior=json.loads(OUT.read_text(encoding='utf-8')).get('weeks',{})
        except Exception:pass
    result={'schema':1,'generated_at':iso_now(),'weeks':{},'checks':{}}
    root=listing()
    folders=[(folder_start(f.get('name',''),now),f) for f in root if f.get('type')=='dir']
    folders=[(date,f) for date,f in folders if date]
    lists={}
    for week in keys:
        key=week.isoformat();result['weeks'][key]={};result['checks'][key]={}
        folder=next((f for d,f in folders if d==week),None)
        if folder:
            path='/'+folder['name'].strip('/')
            try:files=listing(path);lists[key]=(files,path,folder['name'])
            except Exception as e:lists[key]=([],path,str(e)[:125])
        else:
            lists[key]=(root,'','корень публичной папки')
        for dep in DEPTS:
            files,path,folder_name=lists[key]
            try:
                if not folder and not file_for_department(root,dep):
                    raise FileNotFoundError('Неделя ещё не опубликована')
                data,error=download(dep,week,files,path,folder_name)
                if error:raise FileNotFoundError(error)
                previous=prior.get(key,{}).get(dep)
                # Avoid creating commits every 30 min if official Excel has not changed.
                if (previous and previous.get('file_modified')==data.get('file_modified')
                      and previous.get('groups')==data.get('groups')
                      and previous.get('dates')==data.get('dates')):
                    data=previous
                result['weeks'][key][dep]=data
                result['checks'][key][dep]={'ok':True}
            except Exception as e:
                error=str(e)[:170]
                result['checks'][key][dep]={'ok':False,'error':error}
                previous=prior.get(key,{}).get(dep)
                if previous and previous.get('groups') and previous.get('dates'):
                    try:
                        start=dt.datetime.strptime(previous['dates'][0],'%d.%m.%y').date()
                        if start==week:result['weeks'][key][dep]=previous
                    except (ValueError,TypeError):pass
    OUT.parent.mkdir(parents=True,exist_ok=True)
    # For a normal 30-minute check, avoid writing almost-identical snapshots unless at
    # least 6 hours passed. Any real change in groups/source or error status writes now.
    previous_data={}
    if OUT.exists():
        try:previous_data=json.loads(OUT.read_text(encoding='utf-8'))
        except Exception:pass
    comparable=lambda x: {'weeks':x.get('weeks'), 'checks':x.get('checks')}
    if comparable(previous_data)==comparable(result):
        try:
            earlier=dt.datetime.fromisoformat(previous_data['generated_at'].replace('Z','+00:00'))
            if utc_now()-earlier<dt.timedelta(hours=6):
                print('No changed timetable; retaining last published data');return
        except Exception:pass
    OUT.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print('Data written; '+', '.join(f'{week}: {len(result["weeks"][week])} departments' for week in result['weeks']))

if __name__=='__main__':sync()
