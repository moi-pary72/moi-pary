"""Browser acceptance check against the actual URL, including mobile layout."""
import json,sys,pathlib
from playwright.sync_api import sync_playwright
base=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8765/'
artifacts=pathlib.Path('.test-artifacts');artifacts.mkdir(exist_ok=True)
report=[]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width in [320,375,390,768,1280]:
  page=browser.new_page(viewport={'width':width,'height':900},device_scale_factor=1)
  errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(base,wait_until='networkidle')
  page.wait_for_function("localFetchedAt && !busy")
  page.locator('#weekNext').click();page.locator('[data-day="0"]').click()
  monday=page.locator('.day.active-day .lesson').all_inner_texts()
  assert len(monday)==4,monday
  assert '2 пара' in monday[0] and '408/2' in monday[0] and '10:25–11:45' in monday[0],monday
  assert '3 пара' in monday[1] and 'Иностранный язык' in monday[1],monday
  assert 'Разговоры о важном' in monday[2] and '201/2' in monday[2],monday
  assert '4 пара' in monday[3] and 'Основы безопасности' in monday[3] and '201/2' in monday[3],monday
  assert not page.locator('#print').is_disabled()
  page.locator('#sourceDetails').evaluate('(e)=>e.open=true')
  actual=page.locator('#trustIndicator').inner_text()
  details=page.locator('#status').inner_text()
  assert details.startswith('Следующая неделя:'),details
  assert 'Даты в Excel не совпадают' not in details,details
  assert actual in ['Расписание подтверждено','Расписание есть · ждём проверку'],actual
  page.locator('#sourceDetails').evaluate('(e)=>e.open=true')
  page.screenshot(path=str(artifacts/f'browser-{width}.png'),full_page=True)
  assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'),width
  # These are deliberately simulated failures after checking the real page above.
  page.evaluate("sourceMeta.checks[period[0].key][dep]={ok:false,state:'invalid',error:'OLD_WEEK_ERROR'};render()")
  assert 'OLD_WEEK_ERROR' not in page.locator('#status').inner_text()
  page.locator('#weekCurrent').click()
  assert page.locator('#trustIndicator').inner_text()=='Ошибка файла источника'
  page.locator('#weekNext').click()
  page.evaluate("sourceMeta.last_successful_checks[period[selectedWeek].key][dep]=new Date(Date.now()-6.5*3600000).toISOString();render()")
  assert page.locator('#trustIndicator').inner_text()=='Расписание есть · ждём проверку'
  assert page.locator('.day.active-day .lesson').count()==4
  for state,label in [('pending','Неделя ещё не опубликована'),('archived','Неделя в архиве'),('unavailable','Источник недоступен'),('invalid','Ошибка файла источника')]:
   page.evaluate('(state)=>{sourceMeta.checks[period[selectedWeek].key][dep]={ok:false,state,error:state};render()}',state)
   assert page.locator('#trustIndicator').inner_text()==label
  page.locator('#refresh').click();page.wait_for_function('!busy')
  assert page.locator('#refreshLabel').inner_text()=='Обновить копию сайта'
  assert 'не запускает проверку Яндекс Диска' in page.locator('#status').inner_text()
  assert page.locator('.day.active-day .lesson').count()==4
  for dept in ['ИПиС','ПО и СПА','ЭУиК','ИКиМ']:
   page.select_option('#dept',dept);page.wait_for_function('!busy')
   assert page.locator('.lesson').count()>0,dept
  assert page.evaluate("roomValue('2.22518929507823e-307')")==''
  assert page.evaluate("roomValue('112А/1')")=='112А/1'
  page.emulate_media(media='print')
  assert page.locator('.day').count()==6
  if width==390:page.pdf(path=str(artifacts/'schedule.pdf'),format='A4')
  assert not errors,errors
  report.append({'width':width,'monday':monday,'actual_status':actual,'actual_details':details,'errors':errors,'overflow':False})
  page.close()
 browser.close()
(artifacts/'browser-results.json').write_text(json.dumps({'url':base,'checks':report},ensure_ascii=False,indent=2))
print('PASS',base,'widths',[r['width'] for r in report])
