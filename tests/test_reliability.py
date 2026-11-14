import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import seed_builder as parser
import sync
from xls_biff import xls_book

FIXTURE = Path(__file__).parent / 'fixtures/ikim-2026-11-16.xls'
WEEK = dt.date(2026, 11, 16)
GROUP = 'ДПИ-26-9-1'


class ExcelRegressionTests(unittest.TestCase):
    def test_original_mulblank_cells_are_empty_and_not_numbers(self):
        sheet = next(s for s in xls_book(FIXTURE) if s['name'] == 'ДЗ; ДПИ')
        for row in (28, 29, 30):
            self.assertNotIn((row, 20), sheet['cells'])
        parsed = parser.parse_xls(FIXTURE)
        sync.validate_schedule(parsed, WEEK)
        friday = parsed['groups'][GROUP]['days']['Пятница']
        self.assertEqual([x['number'] for x in friday], [4, 5, 6])
        self.assertEqual([x['time'] for x in friday], ['13:30–15:00', '15:20–16:50', '17:00–18:30'])
        for lesson in friday:
            self.assertEqual(lesson['room'], '')
            self.assertEqual(lesson['subject'], 'БД.05 Математика')
            self.assertEqual(lesson['teacher'], 'Овчинникова В.В.')
        saturday = parsed['groups'][GROUP]['days']['Суббота']
        self.assertEqual([x['number'] for x in saturday], [1, 2, 3])
        self.assertEqual([x['time'] for x in saturday], ['08:10–09:40', '09:50–11:20', '11:40–13:10'])
        self.assertEqual([x['subject'] for x in saturday], ['ПД.02 Обществознание', 'БД.02 История', 'БД.02 История'])
        self.assertEqual([x['teacher'] for x in saturday], ['Маков А.П.', 'Бирюков А.Б.', 'Бирюков А.Б.'])
        self.assertTrue(all(x['room'] == '' for x in saturday))

    def test_anomalous_rooms_and_legitimate_labels(self):
        for value in [2.22518929507823e-307, '2.22518929507823e-307', float('nan'), float('inf'), -1, 0, 301.5, 100000000, True, None, '', '.', '-']:
            with self.subTest(value=value): self.assertEqual(parser.clean_room(value), '')
        for value in [301, 301.0, '301']:
            self.assertEqual(parser.clean_room(value), '301')
        for value in ['112А/1', 'АЗ/1', 'ДО', 'БКИ', '301/2']:
            self.assertEqual(parser.clean_room(value), value)

    def test_corrupt_and_truncated_workbooks_rejected(self):
        for data in [b'', b'<html>Error</html>', FIXTURE.read_bytes()[:512]]:
            with tempfile.NamedTemporaryFile() as f:
                f.write(data); f.flush()
                with self.assertRaises(Exception): parser.parse_xls(f.name)

    def test_cached_formula_number_and_error_types(self):
        # xlrd exposes cached formula results with their Excel type. Boolean,
        # blank, and date cells must not be turned into room numbers.
        import xlrd
        sheet = MagicMock(name='sheet');sheet.name='test';sheet.nrows=1;sheet.ncols=5;sheet.merged_cells=[]
        sheet.cell.side_effect=[xlrd.sheet.Cell(t,v) for t,v in [(2,301),(1,'301/2'),(6,''),(4,1),(3,45000)]]
        book=MagicMock();book.__enter__.return_value=book;book.sheets.return_value=[sheet]
        with patch('xls_biff.xlrd.open_workbook',return_value=book):
            self.assertEqual(xls_book('cached-formula.xls')[0]['cells'], {(0,0):301,(0,1):'301/2'})
        sheet.cell.side_effect=[xlrd.sheet.Cell(5,7)]
        with patch('xls_biff.xlrd.open_workbook',return_value=book):
            with self.assertRaisesRegex(ValueError,'Ошибка Excel'):xls_book('error.xls')

    def test_layout_or_date_loss_rejected(self):
        good=parser.parse_xls(FIXTURE)
        for bad in [{**good,'dates':good['dates'][:1]}, {**good,'groups':{}}]:
            with self.assertRaises(ValueError):sync.validate_schedule(bad,WEEK)
        bad=copy.deepcopy(good);bad['groups'].pop(GROUP)
        with self.assertRaisesRegex(ValueError,'потеря'):sync.validate_schedule(bad,WEEK,good)

    def test_duplicates_removed_without_inventing_merged_lessons(self):
        sheet={'height':3,'width':6,'cells':{(0,3):'ТЕСТ-26-9-1', (1,0):'Понедельник 16.11.26', (1,1):1, (1,2):'08:10-09:40', (1,3):'Математика', (2,1):1, (2,2):'08:10-09:40', (2,3):'Математика'},'merged':[(1,2,0,0)]}
        with patch.object(parser,'xls_book',return_value=[sheet]):
            result=parser.parse_xls('fixture.xls')
        self.assertEqual(len(result['groups']['ТЕСТ-26-9-1']['days']['Понедельник']),1)
        del sheet['cells'][2,3]
        with patch.object(parser,'xls_book',return_value=[sheet]):
            self.assertEqual(len(parser.parse_xls('fixture.xls')['groups']['ТЕСТ-26-9-1']['days']['Понедельник']),1)


class SyncReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.out=Path(self.temp.name)/'schedules.json';self.status=Path(self.temp.name)/'status.json'
        self.data=parser.parse_xls(FIXTURE)
        self.baseline={'schema':1,'generated_at':'2026-11-14T08:00:00Z','last_changed_at':'2026-11-14T08:00:00Z','weeks':{'2026-11-16':{dep:copy.deepcopy(self.data) for dep in sync.DEPTS}},'checks':{}}
        sync.atomic_json(self.out,self.baseline)
        self.patches=[patch.object(sync,'OUT',self.out),patch.object(sync,'STATUS',self.status),patch.object(sync,'local_today',return_value=WEEK)]
        for p in self.patches:p.start();self.addCleanup(p.stop)
        self.docs=[{'name':name+'.xls','type':'file','size':len(FIXTURE.read_bytes()),'md5':hashlib.md5(FIXTURE.read_bytes()).hexdigest()} for name in ['ИКиМ','ИПиС','ПОиСПА','ЭУиК']]

    def test_root_outage_preserves_schedules_and_success_time_and_fails(self):
        sync.atomic_json(self.status,{'last_successful_checks':{'2026-11-16':{'ИКиМ':'2026-11-14T08:00:00Z'}}})
        with patch.object(sync,'listing',side_effect=RuntimeError('HTTP 503')):
            self.assertEqual(sync.sync(),1)
        result=json.loads(self.out.read_text());status=json.loads(self.status.read_text())
        self.assertEqual(result['weeks'],self.baseline['weeks'])
        self.assertEqual(result['last_changed_at'],self.baseline['last_changed_at'])
        self.assertEqual(status['last_successful_checks']['2026-11-16']['ИКиМ'],'2026-11-14T08:00:00Z')
        self.assertFalse(status['current_week_departments']['ИКиМ'])

    def test_source_failure_keeps_previous_department_and_reports_failure(self):
        def download(dep,*args):
            if dep=='ИКиМ':raise ValueError('Corrupt XLS')
            return copy.deepcopy(self.data)
        with patch.object(sync,'listing',return_value=self.docs),patch.object(sync,'download',side_effect=download):
            self.assertEqual(sync.sync(),1)
        result=json.loads(self.out.read_text())
        self.assertEqual(result['weeks']['2026-11-16']['ИКиМ'],self.data)
        self.assertFalse(result['checks']['2026-11-16']['ИКиМ']['ok'])

    def test_successful_checks_do_not_change_data_timestamp_and_next_week_is_pending(self):
        with patch.object(sync,'listing',return_value=self.docs),patch.object(sync,'download',return_value=self.data):
            self.assertEqual(sync.sync(),0)
        result=json.loads(self.out.read_text());status=json.loads(self.status.read_text())
        self.assertEqual(result['last_changed_at'],self.baseline['last_changed_at'])
        self.assertTrue(status['checks']['2026-11-23']['ИКиМ']['pending'])
        self.assertTrue(status['last_successful_checks']['2026-11-16']['ИКиМ'])

    def test_empty_http_response_retries_and_fails(self):
        response=MagicMock();response.__enter__.return_value=response;response.read.return_value=b''
        with patch.object(sync,'urlopen',return_value=response) as request,patch.object(sync.time,'sleep'):
            with self.assertRaisesRegex(RuntimeError,'Пустой ответ'):sync.request('https://example.test')
            self.assertEqual(request.call_count,3)

    def test_http_timeout_retries_and_fails(self):
        with patch.object(sync,'urlopen',side_effect=TimeoutError('timeout')) as request,patch.object(sync.time,'sleep'):
            with self.assertRaises(RuntimeError):sync.request('https://example.test')
            self.assertEqual(request.call_count,3)

    def test_download_rejects_checksum_size_and_html(self):
        doc=self.docs[0]
        cases=[(b'error',doc),(FIXTURE.read_bytes(),{**doc,'md5':'0'*32}),(b'<html/>',{'name':'test.xls'})]
        for content,metadata in cases:
            with patch.object(sync,'get_json',return_value={'href':'https://example.test/file'}),patch.object(sync,'request',return_value=content):
                with self.assertRaises(ValueError):sync.download('ИКиМ',WEEK,metadata,'','root')

    def test_deep_verify_not_extended_by_metadata_checks(self):
        doc={'name':'test.xls','modified':'2026-11-14T01:00:00Z'}
        prev={**self.data,'file':'test.xls','source_meta':sync.file_metadata(doc),'parser_version':parser.PARSER_VERSION,'checked_at':sync.iso_now(),'downloaded_at':'2020-01-01T00:00:00Z'}
        self.assertFalse(sync.previously_verified(prev,WEEK,doc))

    def test_invalid_serialization_cannot_truncate_working_file(self):
        before=self.out.read_bytes()
        with self.assertRaises(ValueError):sync.atomic_json(self.out,{'bad':float('nan')})
        self.assertEqual(self.out.read_bytes(),before)


if __name__=='__main__':unittest.main()
