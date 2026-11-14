"""Prepare current and next week timetables for GitHub Pages.

Only download XLS when public Yandex Disk metadata changes (with a daily deep
verification fallback). A tiny sync-status.json is published every ~30 minutes
so the site can distinguish source checks from visitors refreshing the page.
No source XLS is committed; errors keep the last known week.
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
from seed_builder import parse_xls, PARSER_VERSION

API='https://cloud-api.yandex.net/v1/disk/public/resources'
PUBLIC='https://disk.yandex.ru/d/Xc08g8WbTavdHQ'
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'schedules.json'
STATUS=ROOT/'data'/'sync-status.json'
STATUS_INTERVAL=dt.timedelta(minutes=30)
DEEP_VERIFY_INTERVAL=dt.timedelta(hours=24)
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

def file_metadata(doc):
    """Metadata provided by the official Yandex API; no file is downloaded."""
    # If Yandex provides no modification/fingerprint data, we must download.
    meta={key:doc.get(key) for key in ('modified','size','md5') if doc.get(key) is not None}
    return meta

def previously_verified(previous, week_start, doc):
    """True when we can safely reuse parsed XLS without downloading it."""
    if not isinstance(previous,dict) or not previous.get('groups'):
        return False
    if previous.get('parser_version')!=PARSER_VERSION:
        return False
    if previous.get('file')!=doc.get('name'):
        return False
    meta=file_metadata(doc)
    if not meta or not (meta.get('modified') or meta.get('md5')):
        return False
    if previous.get('source_meta')!=meta:
        return False
    try:
        dates=previous['dates']
        first=dt.datetime.strptime(dates[0],'%d.%m.%y').date()
        verified=dt.datetime.fromisoformat(previous['checked_at'].replace('Z','+00:00'))
        if first!=week_start or utc_now()-verified>=DEEP_VERIFY_INTERVAL:
            return False
    except (ValueError,TypeError,KeyError,IndexError,AttributeError):
        return False
    return True

def download(dept,week_start,doc,folder,folder_name):
    path='/'+('/'.join([folder.strip('/'),doc['name']]) if folder else doc['name'])
    link=get_json(API+'/download',{'public_key':PUBLIC,'path':path}).get('href')
    if not link or not link.startswith('https://'):
        raise RuntimeError('Яндекс Диск не выдал ссылку на скачивание')
    b=request(link)
    if not b.startswith(bytes.fromhex('d0cf11e0a1b11ae1')):
        raise ValueError('Файл уже не является XLS (формат изменился)')
    with tempfile.NamedTemporaryFile(suffix='.xls') as temp:
        temp.write(b);temp.flush()
        parsed=parse_xls(temp.name)
    if not parsed['dates']:raise ValueError('В XLS не обнаружены даты')
    start=dt.datetime.strptime(parsed['dates'][0],'%d.%m.%y').date()
    if start!=week_start:raise ValueError('Даты в Excel не совпадают с датой недельной папки')
    if not parsed['groups']:raise ValueError('В XLS не обнаружены учебные группы')
    return {**parsed,'parser_version':PARSER_VERSION,'file':doc['name'],'department':dept,'week':folder_name,
            'source':PUBLIC,'file_modified':doc.get('modified'),
            'source_meta':file_metadata(doc),'checked_at':iso_now()}

def read_json(path):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}

def written_at(value):
    try:return dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    except (ValueError,AttributeError,TypeError):return None

def sync():
    now=local_today();keys=[this_monday(now)+dt.timedelta(days=d) for d in (0,7)]
    previous_data=read_json(OUT)
    prior=previous_data.get('weeks',{})
    stamp=iso_now()
    result={'schema':1,'generated_at':stamp,'weeks':{},'checks':{}}
    # 1 root metadata call, then 1 call per available week folder.
    root=listing()
    folders=[(folder_start(f.get('name',''),now),f) for f in root if f.get('type')=='dir']
    folders=[(date,f) for date,f in folders if date]
    lists={}
    downloaded=0;reused=0
    for week in keys:
        key=week.isoformat();result['weeks'][key]={};result['checks'][key]={}
        folder=next((f for d,f in folders if d==week),None)
        if folder:
            path='/'+folder['name'].strip('/')
            try:files=listing(path);lists[key]=(files,path,folder['name'])
            except Exception as e:lists[key]=([],path,'Ошибка папки: '+str(e)[:110])
        else:
            lists[key]=(root,'','корень публичной папки')
        for dep in DEPTS:
            files,path,folder_name=lists[key]
            previous=prior.get(key,{}).get(dep)
            try:
                doc=file_for_department(files,dep)
                if not doc:raise FileNotFoundError('Неделя ещё не опубликована' if not folder else 'В папке нет XLS отделения')
                if previously_verified(previous,week,doc):
                    data=previous;reused+=1
                else:
                    data=download(dep,week,doc,path,folder_name);downloaded+=1
                result['weeks'][key][dep]=data
                result['checks'][key][dep]={'ok':True}
            except Exception as e:
                error=str(e)[:170]
                result['checks'][key][dep]={'ok':False,'error':error}
                # Never replace a valid week with empty data on a transient failure.
                if previous and previous.get('groups') and previous.get('dates'):
                    try:
                        first=dt.datetime.strptime(previous['dates'][0],'%d.%m.%y').date()
                        if first==week:result['weeks'][key][dep]=previous
                    except (ValueError,TypeError):pass
    OUT.parent.mkdir(parents=True,exist_ok=True)
    comparable=lambda x:{'weeks':x.get('weeks'), 'checks':x.get('checks')}
    changed=comparable(previous_data)!=comparable(result)
    if changed:
        OUT.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    # A small verification stamp is committed only every 30 minutes or on
    # actual data change. This prevents 12 GitHub Pages rebuilds per hour.
    last_status=read_json(STATUS)
    prev_status_time=written_at(last_status.get('checked_at'))
    status_due=not prev_status_time or utc_now()-prev_status_time>=STATUS_INTERVAL
    if changed or status_due:
        current_key=keys[0].isoformat()
        state={'schema':1,'checked_at':stamp,'current_week':current_key,
               'current_week_departments':{
                  dep:bool(result['checks'][current_key][dep].get('ok')) for dep in DEPTS}}
        STATUS.write_text(json.dumps(state,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print(f'Checked official XLS metadata: downloaded={downloaded}, reused={reused}, '
          f'data_changed={changed}, status_published={changed or status_due}')

if __name__=='__main__':sync()
