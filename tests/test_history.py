from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from history import publish_snapshot
import history as archive
from refresh import collect


def snapshot(report='2026-01-31', dates=None, title='Halifax', value=10):
    dates = dates or [report]
    return {'schema_version': 1, 'country': 'CA', 'report_date': report,
            'retrieved_at': report+'T19:00:00+00:00', 'baseline_days': 7,
            'country_days': [{'date': report, 'articles': [{'title': 'Article', 'project': 'en.wikipedia', 'views_ceil': 100, 'rank': 1}]}],
            'topics': [{'title': title, 'project': 'en.wikipedia', 'group': 'Places', 'history': [{'date': d, 'views': value} for d in dates]}],
            'source': {'name': 'Measured test fixture'}}


def contents(path):
    return {str(p.relative_to(path)): p.read_bytes() for p in path.rglob('*') if p.is_file()}


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name) / 'data'

    def test_cold_checkout_retains_older_month_and_removed_topic(self):
        publish_snapshot(snapshot(), self.data)
        original = (self.data/'history/2026-01.json').read_bytes()
        checkout = Path(self.tmp.name)/'fresh-checkout/data'
        shutil.copytree(self.data, checkout)
        manifest = publish_snapshot(snapshot('2026-02-01', ['2026-01-31', '2026-02-01'], title='New topic'), checkout)
        self.assertEqual((checkout/'history/2026-01.json').read_bytes(), original)
        old = json.loads(original)['days'][0]
        self.assertEqual([t['title'] for t in old['topics']], ['Halifax'])
        self.assertEqual(manifest['day_count'], 2)
        self.assertEqual(manifest['country_days'], 2)

    def test_duplicate_date_is_idempotent_even_if_provider_revises(self):
        source = snapshot()
        publish_snapshot(source, self.data)
        original = contents(self.data/'history')
        source['retrieved_at'] = '2026-02-01T19:00:00+00:00'
        source['topics'][0]['history'][0]['views'] = 777
        source['country_days'][0]['articles'][0]['views_ceil'] = 999
        publish_snapshot(source, self.data)
        self.assertEqual(contents(self.data/'history'), original)
        self.assertEqual(json.loads((self.data/'snapshot.json').read_text())['topics'][0]['history'][0]['views'], 777)

    def test_country_can_fill_absent_coverage_without_changing_first_topic(self):
        publish_snapshot(snapshot('2026-02-01', ['2026-01-31', '2026-02-01']), self.data)
        publish_snapshot(snapshot('2026-01-31', value=99), self.data)
        old = json.loads((self.data/'history/2026-01.json').read_text())['days'][0]
        self.assertEqual(old['topics'][0]['views'], 10)
        self.assertEqual(old['country']['first_saved_at'], '2026-01-31T19:00:00+00:00')
        self.assertEqual(json.loads((self.data/'snapshot.json').read_text())['report_date'], '2026-02-01')
        self.assertEqual(json.loads((self.data/'status.json').read_text())['checked_at'], '2026-02-01T19:00:00+00:00')

    def test_missing_country_or_topic_days_are_never_zero_filled(self):
        manifest = publish_snapshot(snapshot('2026-02-02', ['2026-01-30', '2026-02-02']), self.data)
        self.assertEqual(manifest['day_count'], 2)
        self.assertEqual(manifest['country_days'], 1)
        january = json.loads((self.data/'history/2026-01.json').read_text())['days']
        self.assertNotIn('country', january[0])
        self.assertEqual([d['date'] for d in january], ['2026-01-30'])

    def test_partial_source_failure_preserves_all_persisted_files(self):
        publish_snapshot(snapshot(), self.data)
        original = contents(self.data)
        def fake_get(url):
            if '/per-article/' in url:
                raise TimeoutError('topic source failed after successful country requests')
            day = url.rsplit('/', 3)[1:]
            return {'items': [{'country': 'CA', 'year': day[0], 'month': day[1], 'day': day[2], 'articles': [
                {'article': f'Article_{i}', 'project': 'en.wikipedia', 'rank': i+1, 'views_ceil': 100} for i in range(20)]}]}
        config = {'country': 'CA', 'history_days': 2, 'baseline_days': 7, 'country_limit': 20,
                  'topics': [{'title': 'Halifax', 'project': 'en.wikipedia', 'group': 'Places'}]}
        with patch('refresh.get_json', side_effect=fake_get), self.assertRaises(TimeoutError):
            publish_snapshot(collect(config, date(2026, 2, 1)), self.data)
        self.assertEqual(contents(self.data), original)

    def test_invalid_snapshot_and_corrupt_or_missing_archive_do_not_replace_good_data(self):
        publish_snapshot(snapshot(), self.data)
        bad = snapshot('2026-02-01');bad['topics'][0]['history'][0]['views'] = -1
        original = contents(self.data)
        with self.assertRaises(ValueError):publish_snapshot(bad, self.data)
        self.assertEqual(contents(self.data), original)
        month = self.data/'history/2026-01.json'
        month.write_bytes(month.read_bytes().replace(b'"views":10', b'"views":11'))
        corrupted = contents(self.data)
        with self.assertRaisesRegex(ValueError, 'checksum'):publish_snapshot(snapshot('2026-02-01'), self.data)
        self.assertEqual(contents(self.data), corrupted)
        month.unlink();missing = contents(self.data)
        with self.assertRaisesRegex(ValueError, 'missing'):publish_snapshot(snapshot('2026-02-01'), self.data)
        self.assertEqual(contents(self.data), missing)

    def test_failed_directory_swap_restores_previous_complete_dataset(self):
        publish_snapshot(snapshot(), self.data)
        original = contents(self.data)
        real_replace = archive.os.replace
        def fail_stage(source, target):
            if Path(source).name == 'data' and Path(source).parent.name.startswith('.pulse-refresh-'):
                raise OSError('simulated filesystem failure')
            return real_replace(source, target)
        with patch('history.os.replace', side_effect=fail_stage), self.assertRaises(OSError):
            publish_snapshot(snapshot('2026-02-01'), self.data)
        self.assertEqual(contents(self.data), original)

    def test_workflow_persists_archives_and_serializes_main_collections(self):
        workflow = (Path(__file__).resolve().parents[1]/'.github/workflows/pages.yml').read_text()
        self.assertIn('git add web/data', workflow)
        self.assertIn('git push origin HEAD:main', workflow)
        self.assertIn('concurrency:\n  group:', workflow)
        self.assertIn("if: github.ref == 'refs/heads/main' && (github.event_name == 'schedule' || github.event_name == 'workflow_dispatch')", workflow)
        self.assertIn("&& 'main' || github.ref", workflow)

if __name__ == '__main__':unittest.main()
