"""Execute the actual site's status/calendar JavaScript in Node (no DOM mocks)."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

HTML=(Path(__file__).resolve().parents[1]/'index.html').read_text()

def function(name):
    start=HTML.index('function '+name+'(')
    end=HTML.find('\nfunction ',start+1)
    return HTML[start:end]

@unittest.skipUnless(shutil.which('node'),'Node required for browser logic tests')
class UIStatusTests(unittest.TestCase):
    def test_selected_week_status_and_missed_cron(self):
        code='''
const assert=require('node:assert/strict');
let period=[{key:'2026-11-09',label:'Эта неделя'},{key:'2026-11-16',label:'Следующая неделя'}],selectedWeek=1,dep='ИКиМ';
let sourceMeta={checks:{'2026-11-09':{'ИКиМ':{ok:false,state:'invalid',error:'old week error'}},'2026-11-16':{'ИКиМ':{ok:true,state:'confirmed'}}}},statusChecks={},lastCheckType='',lastCheck='',localFetchedAt='now',lastSyncISO='version';
let age=0,text='';
function sourceVerifiedAge(){return age}
function sourceCheckedAt(){return 'checked'}
function prettyTime(x){return x}
function status(x){text=x}
'''+function('selectedHealth')+'\n'+function('renderSelectedStatus')+'''
assert.equal(selectedHealth({}).label,'Расписание подтверждено');
renderSelectedStatus({});assert(!text.includes('old week error'));
selectedWeek=0;assert.equal(selectedHealth({}).label,'Ошибка файла источника');
selectedWeek=1;age=6.5*60*60*1000;
assert.equal(selectedHealth({}).label,'Расписание есть · ждём проверку');
renderSelectedStatus({});assert(text.includes('новых изменений в источнике пока не подтверждено'));
for(const [state,label] of [['pending','Неделя ещё не опубликована'],['archived','Неделя в архиве'],['unavailable','Источник недоступен'],['invalid','Ошибка файла источника']]){
sourceMeta.checks['2026-11-16']['ИКиМ']={ok:false,state,error:state};
assert.equal(selectedHealth({}).label,label);
}
'''
        subprocess.run(['node','-e',code],check=True,capture_output=True,text=True)

    def test_tyumen_sunday_monday_transition_independent_of_device_timezone(self):
        names=['dateKey','addDays','monday','tyumenDay','weeks']
        # Most date helpers are on individual lines; tyumenDay is multiline.
        code="const assert=require('node:assert/strict');\n"
        for name in names:
            start=HTML.index('function '+name+'(')
            if name=='tyumenDay':end=HTML.index('\n}',start)+2
            else:end=HTML.index('\n',start)
            code+=HTML[start:end]+'\n'
        code+="""
assert.deepEqual(weeks(new Date('2026-11-15T18:59:59Z')).map(x=>x.key),['2026-11-09','2026-11-16']);
assert.deepEqual(weeks(new Date('2026-11-15T19:00:00Z')).map(x=>x.key),['2026-11-16','2026-11-23']);
assert.deepEqual(weeks(new Date('2026-11-14T10:00:00Z')).map(x=>x.key),['2026-11-09','2026-11-16']);
"""
        subprocess.run(['node','-e',code],check=True,capture_output=True,text=True)
