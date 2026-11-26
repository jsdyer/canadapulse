#!/usr/bin/env python3
"""Resume measured Wikimedia history without manufacturing dates or replacing saved values."""
import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from refresh import API, UA, parse_country, parse_series, valid_config

ROOT = Path(__file__).resolve().parents[1]
TOPIC_START = date(2015, 7, 1)
COUNTRY_START = date(2021, 1, 1)


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':'))+'\n')
    temporary.replace(path)


class SourceClient:
    def __init__(self, cache, interval=0.35, session=None):
        self.cache = Path(cache)
        self.interval = interval
        self.session = session
        self.last_finished = 0
        self.requests = 0
        self.cache_hits = 0

    def request(self, url):
        path = self.cache / (hashlib.sha256(url.encode()).hexdigest()+'.json')
        if path.exists():
            record = json.loads(path.read_text())
            if record.get('url') != url or record.get('status') not in (200, 404):
                raise ValueError('Unexpected backfill checkpoint')
            self.cache_hits += 1
            return record
        for attempt in range(3):
            time.sleep(max(0, self.interval - (time.monotonic()-self.last_finished)))
            self.requests += 1
            try:
                headers = {'User-Agent': UA, 'Accept': 'application/json'}
                if self.session is None:
                    with urlopen(Request(url, headers=headers), timeout=40) as response:
                        raw = response.read(8_000_001)
                else:
                    # Optional connection reuse avoids thousands of TLS handshakes.
                    # It remains one serial request at a time, with the same gap.
                    with self.session.get(url, headers=headers, timeout=40, stream=True, allow_redirects=False) as response:
                        if response.status_code != 200:
                            raise HTTPError(url, response.status_code, response.reason, response.headers, None)
                        raw = bytearray()
                        for chunk in response.iter_content(65536):
                            raw.extend(chunk)
                            if len(raw) > 8_000_000:
                                break
                if len(raw) > 8_000_000:
                    raise ValueError('Source response exceeds 8 MB')
                data = json.loads(raw)
                record = {'url': url, 'retrieved_at': now(), 'status': 200, 'data': data}
                write_json(path, record)
                return record
            except HTTPError as error:
                if error.code == 404:
                    record = {'url': url, 'retrieved_at': now(), 'status': 404}
                    write_json(path, record)
                    return record
                if error.code == 429:
                    # Never shorten Retry-After or continue a rate-limited run.
                    raise RuntimeError('Wikimedia rate limited the backfill. Checkpoints are saved; resume later.') from error
                if error.headers.get('Retry-After'):
                    raise RuntimeError('Wikimedia requested a pause; checkpoints are saved. Resume after Retry-After: '+error.headers['Retry-After']) from error
                if error.code not in (500, 502, 503, 504) or attempt == 2:
                    raise
                time.sleep(5 * 2 ** attempt)
            except (TimeoutError, URLError):
                if attempt == 2:
                    raise
                time.sleep(5 * 2 ** attempt)
            finally:
                self.last_finished = time.monotonic()
        raise RuntimeError('Source requests exhausted')


def topic_url(topic, start, end):
    title = quote(topic['title'].replace(' ', '_'), safe='')
    return f"{API}/per-article/{topic['project']}/all-access/user/{title}/daily/{start:%Y%m%d}00/{end:%Y%m%d}00"


def collect(config, end, client, country_start=COUNTRY_START, topic_start=TOPIC_START, progress=print):
    config = valid_config(config)
    if topic_start < TOPIC_START or country_start < COUNTRY_START or end < topic_start:
        raise ValueError('Date range precedes the supported source datasets')
    topics, countries, missing = [], [], []
    for topic in config['topics']:
        result = client.request(topic_url(topic, topic_start, end))
        points = [] if result['status'] == 404 else parse_series(result['data'], topic_start, end, require_complete=False)
        # A successful response for a different article/project must not be relabelled.
        if result['status'] == 200:
            for item in result['data'].get('items', []):
                if (item.get('project') != topic['project'] or item.get('article', '').replace('_', ' ') != topic['title'] or item.get('agent') != 'user' or item.get('access') != 'all-access' or item.get('granularity') != 'daily'):
                    raise ValueError('Article source identity mismatch')
        topics.append({**topic, 'history': points, 'source_url': result['url'], 'retrieved_at': result['retrieved_at'], 'source_status': result['status']})
        progress(f"Topic {len(topics)}/{len(config['topics'])}: {topic['title']} — {len(points)} observed days", flush=True)
    day = country_start
    while day <= end:
        result = client.request(f'{API}/top-per-country/CA/all-access/{day:%Y/%m/%d}')
        if result['status'] == 404:
            missing.append({'date': day.isoformat(), 'status': 404, 'checked_at': result['retrieved_at']})
        else:
            item = parse_country(result['data'], day, config['country_limit'])
            countries.append({**item, 'source_url': result['url'], 'retrieved_at': result['retrieved_at']})
        if day.day == 1 or day == end:
            progress(f'Country progress {day}: {len(countries)} measured days, {len(missing)} unavailable; {client.requests} new requests, {client.cache_hits} checkpoints', flush=True)
        day += timedelta(days=1)
    return {'schema_version': 1, 'started_at': min(t['retrieved_at'] for t in topics), 'completed_at': now(), 'requested_end': end.isoformat(), 'topic_start': topic_start.isoformat(), 'country_start': country_start.isoformat(), 'baseline_days': config['baseline_days'], 'country_limit': config['country_limit'], 'topics': topics, 'country_days': countries, 'unavailable_country_days': missing, 'requests_this_run': client.requests, 'checkpoint_hits': client.cache_hits}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--end', type=date.fromisoformat)
    parser.add_argument('--topic-start', type=date.fromisoformat, default=TOPIC_START)
    parser.add_argument('--country-start', type=date.fromisoformat, default=COUNTRY_START)
    parser.add_argument('--cache', type=Path, default=ROOT/'.cache/backfill')
    parser.add_argument('--collect-only', action='store_true')
    parser.add_argument('--keep-alive', action='store_true', help='Reuse a single HTTP connection via optional requests package (python -m pip install requests)')
    parser.add_argument('--interval', type=float, default=0.35, help='Minimum gap after each completed request (seconds, at least 0.35)')
    args = parser.parse_args()
    if args.interval < 0.35:
        parser.error('The minimum request interval is 0.35 seconds; requests are always serial')
    snapshot = json.loads((ROOT/'web/data/snapshot.json').read_text())
    end = args.end or date.fromisoformat(snapshot['report_date'])
    if end > datetime.now(timezone.utc).date()-timedelta(days=1):
        parser.error('Only completed UTC dates can be requested')
    session = None
    if args.keep_alive:
        import requests
        session = requests.Session()
    result = collect(json.loads((ROOT/'config/sources.json').read_text()), end, SourceClient(args.cache, args.interval, session), args.country_start, args.topic_start)
    write_json(args.cache/'collected.json', result)
    if not args.collect_only:
        from history import publish_backfill
        manifest = publish_backfill(result, ROOT/'web/data')
        print(f"Retained {manifest['day_count']} measured dates and {manifest['country_days']} country rankings; {manifest['earliest_date']} through {manifest['latest_date']}")


if __name__ == '__main__':
    main()
