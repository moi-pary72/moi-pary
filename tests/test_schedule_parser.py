import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import seed_builder
import sync


class ScheduleParserTests(unittest.TestCase):
    def test_excel_numeric_and_text_rooms_are_preserved(self):
        for room, expected in [(301, '301'), (301.0, '301'), ('301/2', '301/2'), (None, ''), ('.', '')]:
            with self.subTest(room=room):
                sheet = {'height': 2, 'width': 6, 'cells': {
                    (0, 3): 'ТЕСТ-26-9-1', (1, 0): 'Понедельник 09.11.26',
                    (1, 1): 1, (1, 2): '08:10-09:40', (1, 3): 'Математика',
                    (1, 4): 'Иванов', (1, 5): room,
                }}
                with patch.object(seed_builder, 'xls_book', return_value=[sheet]):
                    result = seed_builder.parse_xls('fixture.xls')
                lesson = result['groups']['ТЕСТ-26-9-1']['days']['Понедельник'][0]
                self.assertEqual(lesson['room'], expected)
                self.assertEqual(lesson['number'], 1)

    def test_numeric_placeholders_are_not_subjects(self):
        self.assertEqual(seed_builder.clean(0), '')
        self.assertEqual(seed_builder.clean(301), '')
        self.assertEqual(seed_builder.clean_room(301), '301')

    def test_old_parser_cache_is_rebuilt(self):
        doc = {'name': 'ИКиМ.xls', 'modified': '2026-11-14T01:00:00Z'}
        previous = {'groups': {'test': {}}, 'file': doc['name'],
                    'source_meta': sync.file_metadata(doc), 'dates': ['09.11.26'],
                    'checked_at': sync.iso_now()}
        week = dt.date(2026, 11, 9)
        self.assertFalse(sync.previously_verified(previous, week, doc))
        previous['parser_version'] = seed_builder.PARSER_VERSION
        self.assertTrue(sync.previously_verified(previous, week, doc))


if __name__ == '__main__':
    unittest.main()
