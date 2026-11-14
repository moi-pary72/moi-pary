"""Prepare current and next week timetables for GitHub Pages.

Only download XLS when public Yandex Disk metadata changes (with a daily deep
verification fallback). A tiny sync-status.json is published every ~30 minutes
so the site can distinguish source checks from visitors refreshing the page.
No source XLS is committed; errors keep the last known week.
"""
from __future__ import annotations
import datetime as dt
import hashlib
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
            if not content:raise ValueError('Пустой ответ сервера')
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
        verified=dt.datetime.fromisoformat(previous.get('downloaded_at',previous['checked_at']).replace('Z','+00:00'))
        if first!=week_start or not dt.timedelta(0)<=utc_now()-verified<DEEP_VERIFY_INTERVAL:
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
    if doc.get('size') is not None and len(b)!=doc['size']:
        raise ValueError('Размер скачанного XLS не совпадает с метаданными')
    if doc.get('md5') and hashlib.md5(b).hexdigest()!=doc['md5']:
        raise ValueError('Контрольная сумма XLS не совпадает с метаданными')
    if not b.startswith(bytes.fromhex('d0cf11e0a1b11ae1')):
        raise ValueError('Файл уже не является XLS (формат изменился)')
    with tempfile.NamedTemporaryFile(suffix='.xls') as temp:
        temp.write(b);temp.flush()
        parsed=parse_xls(temp.name)
    if not parsed['dates']:raise ValueError('В XLS не обнаружены даты')
    start=dt.datetime.strptime(parsed['dates'][0],'%d.%m.%y').date()
    if start!=week_start:raise ValueError('Даты в Excel не совпадают с датой недельной папки')
    validate_schedule(parsed,week_start)
    return {**parsed,'parser_version':PARSER_VERSION,'file':doc['name'],'department':dept,'week':folder_name,
            'source':PUBLIC,'file_modified':doc.get('modified'),
            'source_meta':file_metadata(doc),'checked_at':iso_now(),
            'downloaded_at':iso_now(),'sha256':hashlib.sha256(b).hexdigest()}

def read_json(path):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}

def written_at(value):
    try:return dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    except (ValueError,AttributeError,TypeError):return None

def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Serialize first: a bad value must not truncate the working file.
    content=json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n'
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,delete=False) as f:
        temp=Path(f.name)
        f.write(content)
    temp.replace(path)


def validate_schedule(parsed, week_start, previous=None):
    expected=[(week_start+dt.timedelta(days=i)).strftime('%d.%m.%y') for i in range(6)]
    if parsed.get('dates')!=expected:
        raise ValueError('Структура XLS изменилась: ожидаются шесть дат недели')
    groups=parsed.get('groups',{})
    if not groups:raise ValueError('В XLS не обнаружены учебные группы')
    def count(g):return sum(len(ls) for x in g.values() for ls in x['days'].values())
    if not count(groups):raise ValueError('В XLS нет занятий')
    for group in groups.values():
        if set(group.get('days',{}))!=set(['Понедельник','Вторник','Среда','Четверг','Пятница','Суббота']):
            raise ValueError('Изменена структура дней')
        for i,lessons in enumerate(group['days'].values()):
            for lesson in lessons:
                if lesson['date']!=expected[i] or not lesson['subject']:
                    raise ValueError('Неверная дата или пустой предмет')
                m=re.fullmatch(r'(\d{2}):(\d{2})–(\d{2}):(\d{2})',lesson['time'])
                if not m:raise ValueError('Неверное время занятия')
                h1,m1,h2,m2=map(int,m.groups())
                if not (0<=h1<=23 and 0<=h2<=23 and 0<=m1<60 and 0<=m2<60 and h1*60+m1<h2*60+m2):
                    raise ValueError('Неверное время занятия')
    if previous and previous.get('groups'):
        old=previous['groups']
        if set(old)-set(groups) or count(groups)<count(old)*0.6:
            raise ValueError('Подозрительная потеря групп/занятий: сохранена предыдущая версия')


def semantic_weeks(weeks):
    return {key:{dep:{'dates':data.get('dates'),'groups':data.get('groups')}
                 for dep,data in departments.items()} for key,departments in weeks.items()}


def sync(force_download=False):
    now=local_today();keys=[this_monday(now)+dt.timedelta(days=d) for d in (0,7)]
    previous_data=read_json(OUT);prior=previous_data.get('weeks',{})
    old_status=read_json(STATUS);stamp=iso_now()
    result={'schema':1,'weeks':{},'checks':{}}
    successes=dict(old_status.get('last_successful_checks',{}))
    downloaded=0;reused=0;failures=[]
    try:
        root=listing()
        folders=[(folder_start(f.get('name',''),now),f) for f in root if f.get('type')=='dir']
        root_error=None
    except Exception as e:
        root=[];folders=[];root_error=str(e)[:170]
    for week in keys:
        key=week.isoformat();result['weeks'][key]={};result['checks'][key]={}
        folder=next((f for d,f in folders if d==week),None)
        path='/'+folder['name'].strip('/') if folder else ''
        folder_name=folder['name'] if folder else 'корень публичной папки'
        folder_error=root_error
        try:files=listing(path) if folder else root
        except Exception as e:files=[];folder_error=str(e)[:170]
        for dep in DEPTS:
            previous=prior.get(key,{}).get(dep)
            try:
                if folder_error:raise RuntimeError(folder_error)
                doc=file_for_department(files,dep)
                # An unpublished next week is expected; do not download this week's root XLS as next week.
                if not doc or (week!=keys[0] and not folder):
                    if week!=keys[0] and not folder and not previous:
                        result['checks'][key][dep]={'ok':False,'pending':True,'error':'Неделя ещё не опубликована'}
                        continue
                    raise FileNotFoundError('В папке нет XLS отделения')
                if not force_download and previously_verified(previous,week,doc):
                    data=previous;reused+=1
                else:
                    data=download(dep,week,doc,path,folder_name)
                    validate_schedule(data,week,previous);downloaded+=1
                result['weeks'][key][dep]=data
                result['checks'][key][dep]={'ok':True}
                successes.setdefault(key,{})[dep]=stamp
            except Exception as e:
                error=str(e)[:170];failures.append(f'{key} {dep}: {error}')
                result['checks'][key][dep]={'ok':False,'error':error}
                if previous and previous.get('groups') and previous.get('dates'):
                    try:
                        if dt.datetime.strptime(previous['dates'][0],'%d.%m.%y').date()==week:
                            result['weeks'][key][dep]=previous
                    except (ValueError,TypeError):pass
    result['weeks']={key:data for key,data in result['weeks'].items() if data}
    semantic_changed=semantic_weeks(prior)!=semantic_weeks(result['weeks'])
    changed=previous_data.get('weeks')!=result['weeks'] or previous_data.get('checks')!=result['checks']
    result['last_changed_at']=stamp if semantic_changed else previous_data.get('last_changed_at',previous_data.get('generated_at',stamp))
    result['generated_at']=stamp if changed else previous_data.get('generated_at',stamp)
    # No valid replacement at all: leave the working schedules file byte-for-byte intact.
    if changed and any(result['weeks'].values()):atomic_json(OUT,result)
    current_key=keys[0].isoformat()
    state={'schema':1,'checked_at':stamp,'last_attempt_at':stamp,'current_week':current_key,
           'last_successful_checks':{key:successes.get(key,{}) for key in result['checks']},
           'checks':result['checks'],'last_changed_at':result['last_changed_at'],
           'current_week_departments':{dep:bool(result['checks'][current_key][dep].get('ok')) for dep in DEPTS},
           'downloaded':downloaded,'reused':reused,'errors':failures}
    atomic_json(STATUS,state)
    print(f'Checked official XLS metadata: downloaded={downloaded}, reused={reused}, data_changed={semantic_changed}')
    for error in failures:print('ERROR: '+error)
    return 1 if failures else 0


if __name__=='__main__':
    import sys
    sys.exit(sync(force_download='--force-download' in sys.argv))
