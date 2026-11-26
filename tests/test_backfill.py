from copy import deepcopy
from datetime import date
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from backfill import SourceClient, collect, topic_url
from history import publish_backfill, publish_snapshot, prepare_backfill
from test_history import snapshot, contents


def historical():
    return {'schema_version': 1, 'requested_end': '2026-01-31', 'completed_at': '2026-02-01T02:00:00+00:00',
            'topic_start': '2015-07-01', 'country_start': '2021-01-01', 'baseline_days': 7,
            'topics': [{'title': 'Halifax', 'project': 'en.wikipedia', 'group': 'Places', 'history': [
                {'date': '2015-07-01', 'views': 0}, {'date': '2015-07-03', 'views': 4},
                {'date': '2021-01-01', 'views': 12}, {'date': '2026-01-31', 'views': 999}]}],
            'country_days': [{'date': '2021-01-01', 'retrieved_at': '2026-02-01T01:00:00+00:00',
                'source_url': 'https://wikimedia.org/api/rest_v1/metrics/pageviews/top-per-country/CA/all-access/2021/01/01',
                'articles': [{'title': 'Ranked', 'project': 'en.wikipedia', 'rank': 2, 'views_ceil': 1000}]}]}


class BackfillTests(unittest.TestCase):
    def test_topic_only_history_does_not_fabricate_country_or_missing_days(self):
        days = prepare_backfill(historical())
        self.assertEqual(days['2015-07-01']['topics'][0]['views'], 0)
        self.assertNotIn('2015-07-02', days)
        self.assertNotIn('country', days['2015-07-01'])
        self.assertEqual(days['2021-01-01']['country']['articles'][0]['views_ceil'], 1000)

    def test_backfill_preserves_saved_values_live_snapshot_and_check_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)/'data'
            publish_snapshot(snapshot(), target)
            live = (target/'snapshot.json').read_bytes()
            checked = json.loads((target/'status.json').read_text())['checked_at']
            manifest = publish_backfill(historical(), target)
            self.assertEqual((target/'snapshot.json').read_bytes(), live)
            self.assertEqual(json.loads((target/'status.json').read_text())['checked_at'], checked)
            self.assertEqual(manifest['earliest_date'], '2015-07-01')
            self.assertEqual(manifest['country_days'], 2)
            saved = json.loads((target/'history/2026-01.json').read_text())['days'][0]
            self.assertEqual(saved['topics'][0]['views'], 10)
            original = contents(target/'history')
            publish_backfill(historical(), target)
            self.assertEqual(contents(target/'history'), original)

    def test_country_history_can_precede_the_requested_topic_range(self):
        result=historical();result['topic_start']='2026-01-01'
        result['topics'][0]['history']=[{'date':'2026-01-31','views':99}]
        days=prepare_backfill(result)
        self.assertEqual(days['2021-01-01']['topics'],[])
        self.assertIn('country',days['2021-01-01'])

    def test_absent_topic_coverage_can_be_filled_without_replacing_a_saved_ranking(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'data';publish_snapshot(snapshot(),target)
            limited=historical();limited['topic_start']='2026-01-01'
            limited['topics'][0]['history']=[{'date':'2026-01-31','views':99}]
            publish_backfill(limited,target)
            complete=historical();complete['completed_at']='2026-02-02T02:00:00+00:00'
            complete['country_days'][0]['articles'][0]['views_ceil']=9999
            publish_backfill(complete,target)
            saved=json.loads((target/'history/2021-01.json').read_text())['days'][0]
            self.assertEqual(saved['topics'][0]['views'],12)
            self.assertEqual(saved['topics_saved_at'],'2026-02-02T02:00:00+00:00')
            self.assertEqual(saved['country']['articles'][0]['views_ceil'],1000)

    def test_valid_source_article_titles_longer_than_form_limit_are_retained(self):
        result=historical();result['country_days'][0]['articles'][0]['title']='A'*211
        days=prepare_backfill(result)
        self.assertEqual(len(days['2021-01-01']['country']['articles'][0]['title']),211)

    def test_invalid_import_leaves_every_published_file_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)/'data';publish_snapshot(snapshot(), target)
            before = contents(target)
            bad = historical();bad['topics'][0]['history'][0]['views'] = -1
            with self.assertRaises(ValueError):publish_backfill(bad,target)
            self.assertEqual(contents(target), before)
            bad = historical();bad['country_days'][0]['date'] = '2015-07-01'
            with self.assertRaises(ValueError):publish_backfill(bad,target)
            self.assertEqual(contents(target), before)

    def test_checkpoint_skips_successful_requests_and_retains_404_as_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch('backfill.urlopen', return_value=BytesIO(b'{"items":[]}')) as upstream, patch('backfill.time.sleep'):
                client = SourceClient(tmp)
                first = client.request('https://wikimedia.org/example')
                second = SourceClient(tmp).request('https://wikimedia.org/example')
            self.assertEqual(first, second);self.assertEqual(upstream.call_count,1)
            error = HTTPError('https://wikimedia.org/missing',404,'missing',{},None)
            with patch('backfill.urlopen',side_effect=error) as upstream, patch('backfill.time.sleep'):
                missing = client.request('https://wikimedia.org/missing')
                again = client.request('https://wikimedia.org/missing')
            self.assertEqual(missing['status'],404);self.assertNotIn('data',missing)
            self.assertEqual(missing,again);self.assertEqual(upstream.call_count,1)

    def test_rate_limit_stops_immediately_instead_of_retrying_or_publishing(self):
        with tempfile.TemporaryDirectory() as tmp:
            error = HTTPError('https://wikimedia.org/limited',429,'limited',{'Retry-After':'300'},None)
            with patch('backfill.urlopen',side_effect=error) as upstream, patch('backfill.time.sleep'):
                with self.assertRaisesRegex(RuntimeError,'rate limited'):SourceClient(tmp).request('https://wikimedia.org/limited')
            self.assertEqual(upstream.call_count,1)
            self.assertEqual(list(Path(tmp).glob('*.json')),[])

    def test_server_retry_after_is_not_shortened(self):
        with tempfile.TemporaryDirectory() as tmp:
            error = HTTPError('https://wikimedia.org/busy',503,'busy',{'Retry-After':'120'},None)
            with patch('backfill.urlopen',side_effect=error) as upstream, patch('backfill.time.sleep'):
                with self.assertRaisesRegex(RuntimeError,'Retry-After: 120'):SourceClient(tmp).request('https://wikimedia.org/busy')
            self.assertEqual(upstream.call_count,1)

    def test_optional_reused_connection_keeps_status_and_response_limits(self):
        class Response:
            status_code=200;reason='OK';headers={}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def iter_content(self,size):yield b'{"items":[]}'
        class Session:
            def get(self,*args,**kwargs):
                self.kwargs=kwargs
                return Response()
        with tempfile.TemporaryDirectory() as tmp, patch('backfill.time.sleep'):
            session=Session();result=SourceClient(tmp,session=session).request('https://wikimedia.org/example')
            self.assertEqual(result['status'],200)
            self.assertEqual(result['data'],{'items':[]})
            self.assertFalse(session.kwargs['allow_redirects'])
            self.assertTrue(session.kwargs['stream'])

    def test_empty_country_era_is_allowed_without_requesting_pre_2021_rankings(self):
        config={'country':'CA','history_days':2,'baseline_days':7,'country_limit':20,'topics':[{'title':'Halifax','project':'en.wikipedia','group':'Places'}]}
        class Client:
            requests=1;cache_hits=0
            def request(self,url):
                self.url=url
                return {'status':200,'url':url,'retrieved_at':'2026-02-01T01:00:00Z','data':{'items':[
                    {'timestamp':'2015070100','views':2,'project':'en.wikipedia','article':'Halifax','agent':'user','access':'all-access','granularity':'daily'}]}}
        client=Client()
        result=collect(config,date(2015,7,3),client,progress=lambda *a,**kw:None)
        self.assertEqual(result['country_days'],[])
        self.assertEqual(len(result['topics'][0]['history']),1)
        self.assertIn('/per-article/',client.url)

    def test_wrong_article_identity_is_rejected(self):
        config={'country':'CA','history_days':2,'baseline_days':7,'country_limit':20,'topics':[{'title':'Halifax','project':'en.wikipedia','group':'Places'}]}
        class Client:
            def request(self,url):
                return {'status':200,'url':url,'retrieved_at':'2026-02-01T01:00:00Z','data':{'items':[
                    {'timestamp':'2015070100','views':2,'project':'en.wikipedia','article':'Toronto','agent':'user','access':'all-access','granularity':'daily'}]}}
        with self.assertRaisesRegex(ValueError,'identity'):collect(config,date(2015,7,3),Client(),progress=lambda *a,**kw:None)

    def test_topic_url_encodes_path_characters(self):
        url=topic_url({'title':'A/B ?#','project':'en.wikipedia'},date(2015,7,1),date(2015,7,3))
        self.assertIn('A%2FB_%3F%23/daily/',url)

if __name__ == '__main__':unittest.main()
