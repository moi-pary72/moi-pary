"""Calendar/source regression cases; no live network or source mutation."""
import copy
import datetime as dt
import json
import unittest
from unittest.mock import patch
import test_reliability as fixtures
from test_reliability import WEEK, GROUP
import sync


class WeekRolloverTests(unittest.TestCase):
    setUp = fixtures.SyncReliabilityTests.setUp

    def run_day(self, day, root=None, folder=False, broken=None):
        docs=self.docs if root is None else root
        folder_doc={'name':'16.11-21.11','type':'dir'}
        def listing(path=None):
            return self.docs if path else docs+([folder_doc] if folder else [])
        def download(dep,week,*args):
            if broken==dep:raise ValueError('Повреждённый Excel')
            if week is not None and week!=WEEK:raise ValueError('Даты в Excel не совпадают с датой недельной папки')
            return copy.deepcopy(self.data)
        with patch.object(sync,'local_today',return_value=day),patch.object(sync,'listing',side_effect=listing),patch.object(sync,'download',side_effect=download):
            code=sync.sync()
        return code,json.loads(self.status.read_text()),json.loads(self.out.read_text())

    def test_sunday_root_next_week_and_missing_finished_folder(self):
        code,status,data=self.run_day(dt.date(2026,11,15))
        self.assertEqual(code,0)
        for dep in sync.DEPTS:
            self.assertEqual(status['checks']['2026-11-09'][dep]['state'],'archived')
            self.assertTrue(status['checks']['2026-11-16'][dep]['ok'])
        self.assertNotIn('2026-11-09',data['weeks'])

    def test_saturday_missing_current_is_an_error_not_archive(self):
        code,status,_=self.run_day(dt.date(2026,11,14))
        self.assertEqual(code,1)
        self.assertEqual(status['checks']['2026-11-09']['ИКиМ']['state'],'unavailable')
        self.assertTrue(status['checks']['2026-11-16']['ИКиМ']['ok'])

    def test_monday_root_current_and_future_not_published(self):
        code,status,data=self.run_day(WEEK)
        self.assertEqual(code,0)
        self.assertTrue(status['checks']['2026-11-16']['ИКиМ']['ok'])
        self.assertEqual(status['checks']['2026-11-23']['ИКиМ']['state'],'pending')
        lessons=data['weeks']['2026-11-16']['ИКиМ']['groups'][GROUP]['days']['Понедельник']
        self.assertEqual([x['number'] for x in lessons],[2,3,4])
        self.assertTrue(all(x['room']=='' for x in lessons))

    def test_wrong_week_in_named_folder_is_not_pending(self):
        root=[{'name':'23.11-28.11','type':'dir'}]
        code,status,data=self.run_day(WEEK,root=root)
        self.assertEqual(code,1)
        self.assertEqual(status['checks']['2026-11-23']['ИКиМ']['state'],'invalid')
        self.assertEqual(data['weeks']['2026-11-16'],self.baseline['weeks']['2026-11-16'])

    def test_partial_success_preserves_corrupt_department(self):
        code,status,data=self.run_day(dt.date(2026,11,15),folder=True,broken='ИКиМ')
        self.assertEqual(code,1)
        self.assertEqual(status['checks']['2026-11-16']['ИКиМ']['state'],'invalid')
        self.assertTrue(status['checks']['2026-11-16']['ИПиС']['ok'])
        self.assertEqual(data['weeks']['2026-11-16']['ИКиМ'],self.data)

    def test_removed_previously_published_future_is_not_pending(self):
        code,status,data=self.run_day(dt.date(2026,11,15),root=[])
        self.assertEqual(code,1)
        self.assertEqual(status['checks']['2026-11-16']['ИКиМ']['state'],'unavailable')
        self.assertEqual(data['weeks']['2026-11-16'],self.baseline['weeks']['2026-11-16'])

    def test_real_download_accepts_root_dates_but_rejects_wrong_folder(self):
        from test_reliability import FIXTURE
        with patch.object(sync,'get_json',return_value={'href':'https://example.test/xls'}),patch.object(sync,'request',return_value=FIXTURE.read_bytes()):
            parsed=sync.download('ИКиМ',None,self.docs[0],'','root')
            self.assertEqual(parsed['dates'][0],'16.11.26')
            with self.assertRaisesRegex(ValueError,'не совпадают'):
                sync.download('ИКиМ',dt.date(2026,11,9),self.docs[0],'/old','old')

    def test_latest_official_root_has_real_rooms_and_changed_times(self):
        from pathlib import Path
        import seed_builder
        fixture=Path(__file__).parent/'fixtures/ikim-2026-11-16-root-20261115.xls'
        parsed=seed_builder.parse_xls(fixture)
        sync.validate_schedule(parsed,WEEK)
        lessons=parsed['groups'][GROUP]['days']['Понедельник']
        self.assertEqual([x['number'] for x in lessons],[2,3,None,4])
        self.assertEqual([x['room'] for x in lessons],['408/2','408/2','201/2','201/2'])
        self.assertEqual([x['time'] for x in lessons],['10:25–11:45','11:55–13:15','13:30–14:15','14:25–15:45'])

    def test_newer_matching_root_revision_is_used(self):
        def download(dep,week,*args):
            return {**copy.deepcopy(self.data),'file_modified':'2026-11-15T05:00:00Z' if week is None else '2026-11-12T05:00:00Z'}
        with patch.object(sync,'local_today',return_value=dt.date(2026,11,15)),patch.object(sync,'listing',side_effect=lambda path=None:self.docs if path else self.docs+[{'name':'16.11-21.11','type':'dir'}]),patch.object(sync,'download',side_effect=download):
            self.assertEqual(sync.sync(),0)
        data=json.loads(self.out.read_text())
        self.assertEqual(data['weeks']['2026-11-16']['ИКиМ']['file_modified'],'2026-11-15T05:00:00Z')
