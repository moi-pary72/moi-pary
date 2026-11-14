import json,sys,pathlib
from playwright.sync_api import sync_playwright
base=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8000/'
artifacts=pathlib.Path('.test-artifacts');artifacts.mkdir(exist_ok=True)
report=[]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
 for width in [320,375,390,768,1280]:
  page=browser.new_page(viewport={'width':width,'height':900},device_scale_factor=1)
  errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(base,wait_until='networkidle');page.wait_for_function("document.querySelectorAll('.lesson').length>0 && !document.querySelector('#refresh').disabled")
  page.locator('#weekNext').click();page.locator('[data-day="4"]').click()
  friday=page.locator('.day.active-day .lesson').all_inner_texts()
  assert len(friday)==3,friday
  assert all('Не указан' in x and 'Математика' in x and 'e-307' not in x for x in friday),friday
  page.locator('[data-day="5"]').click()
  saturday=page.locator('.day.active-day .lesson').all_inner_texts()
  assert len(saturday)==3,saturday
  assert 'Обществознание' in saturday[0] and 'История' in saturday[1],saturday
  assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'),width
  for dept in ['ИПиС','ПО и СПА','ЭУиК','ИКиМ']:
   page.select_option('#dept',dept)
   page.wait_for_function('!busy')
   assert page.locator('.lesson').count()>0,dept
  assert page.evaluate("roomValue('2.22518929507823e-307')")==''
  assert page.evaluate("roomValue('112А/1')")=='112А/1'
  page.evaluate("sourceMeta.last_successful_checks[period[selectedWeek].key][dep]='2026-11-10T00:00:00Z';render()")
  assert page.locator('#trustIndicator').inner_text()=='Проверка устарела',page.evaluate('({label:$("trustIndicator").textContent,dep,selectedWeek,key:period[selectedWeek].key,checked:sourceCheckedAt(),type:lastCheckType,note:statusChecks[period[selectedWeek].key]?.[dep],meta:sourceMeta})')
  page.evaluate("sourceMeta.last_successful_checks[period[selectedWeek].key][dep]=new Date().toISOString();render()")
  assert page.locator('#trustIndicator').inner_text()=='Данные загружены'
  page.evaluate("sourceMeta.checks[period[selectedWeek].key][dep]={ok:false,error:'test'};render()")
  assert page.locator('#trustIndicator').inner_text()=='Сбой источника'
  assert not errors,errors
  page.evaluate("sourceMeta.checks[period[selectedWeek].key][dep]={ok:true};render()")
  page.locator('[data-day="4"]').click()
  page.screenshot(path=str(artifacts/f'browser-{width}.png'),full_page=True)
  report.append({'width':width,'friday':friday,'saturday':saturday,'errors':errors,'overflow':False})
  page.close()
 browser.close()
(artifacts/'browser-results.json').write_text(json.dumps({'url':base,'checks':report},ensure_ascii=False,indent=2))
print('PASS',base,'widths',[r['width'] for r in report])
