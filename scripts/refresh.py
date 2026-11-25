#!/usr/bin/env python3
"""Collect real Wikimedia daily data atomically; never manufacture a missing day."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
API = "https://wikimedia.org/api/rest_v1/metrics/pageviews"
UA = "CanadaPulse/1.0 (https://coolcode.ca/canadapulse/; https://github.com/jsdyer/canadapulse)"
PROJECT = re.compile(r"[a-z][a-z0-9-]{0,20}\.wikipedia")
NAMESPACE = re.compile(r"^(Main_Page$|Wikipedia:|Wikipédia:|Special:|Spécial:|Portal:|Help:|File:|Category:|Template:|Talk:|User:)", re.I)


def get_json(url):
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={"User-Agent": UA, "Accept": "application/json"}), timeout=35) as response:
                raw = response.read(8_000_001)
            if len(raw) > 8_000_000:
                raise ValueError("Upstream JSON exceeded 8 MB")
            return json.loads(raw)
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            delay = error.headers.get("Retry-After", "2")
            time.sleep(min(15, int(delay) if delay.isdecimal() else 2) * (attempt + 1))
    raise RuntimeError("Request exhausted")


def valid_config(config):
    if config.get("country") != "CA":
        raise ValueError("This release measures Canadian readership; country must be CA")
    for key, minimum, maximum in [("history_days", 2, 31), ("baseline_days", 7, 90), ("country_limit", 20, 500)]:
        if type(config.get(key)) is not int or not minimum <= config[key] <= maximum:
            raise ValueError(f"Invalid {key}")
    topics = config.get("topics", [])
    if not 1 <= len(topics) <= 100:
        raise ValueError("Configure between 1 and 100 topics")
    seen = set()
    for topic in topics:
        if not PROJECT.fullmatch(topic.get("project", "")) or not isinstance(topic.get("title"), str) or not 1 <= len(topic["title"]) <= 200:
            raise ValueError("Invalid topic title or Wikipedia project")
        if not isinstance(topic.get("group"), str) or not topic["group"].strip():
            raise ValueError("Every topic needs a group")
        key = (topic["project"], topic["title"].replace(" ", "_"))
        if key in seen:
            raise ValueError("Duplicate topic")
        seen.add(key)
    return config


def parse_country(raw, day, limit):
    item = raw.get("items", [{}])[0]
    if item.get("country") != "CA" or "-".join(str(item.get(k, "")).zfill(2) for k in ("year", "month", "day")) != day.isoformat():
        raise ValueError("Country/date mismatch")
    output = []
    seen = set()
    for row in item.get("articles", []):
        title, project = row.get("article"), row.get("project", "")
        views, rank = row.get("views_ceil"), row.get("rank")
        if not isinstance(title, str) or not PROJECT.fullmatch(project) or NAMESPACE.search(title):
            continue
        if type(views) is not int or views < 0 or type(rank) is not int or rank < 1:
            raise ValueError("Invalid country view count")
        if (project, title) in seen:
            raise ValueError("Duplicate country article")
        seen.add((project, title))
        output.append({"title": title.replace("_", " "), "project": project, "views_ceil": views, "rank": rank})
    if len(output) < 10:
        raise ValueError("Unexpectedly few country articles")
    return {"date": day.isoformat(), "articles": output[:limit]}


def parse_series(raw, start, end):
    values = {}
    for row in raw.get("items", []):
        stamp = str(row.get("timestamp", ""))
        if not re.fullmatch(r"\d{10}", stamp):
            raise ValueError("Invalid article date")
        day = date.fromisoformat(f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}")
        views = row.get("views")
        if type(views) is not int or views < 0 or day in values:
            raise ValueError("Invalid/duplicate article count")
        if start <= day <= end:
            values[day] = views
    expected = (end - start).days + 1
    if len(values) != expected:
        raise ValueError(f"Incomplete article history: {len(values)}/{expected} days")
    return [{"date": d.isoformat(), "views": values[d]} for d in sorted(values)]


def collect(config, target=None):
    config = valid_config(config)
    target = target or (datetime.now(timezone.utc).date() - timedelta(days=1))
    latest = None
    for offset in range(5):
        candidate = target - timedelta(days=offset)
        try:
            latest = parse_country(get_json(f"{API}/top-per-country/CA/all-access/{candidate:%Y/%m/%d}"), candidate, config["country_limit"])
            target = candidate
            break
        except HTTPError as error:
            if error.code != 404:
                raise
    if latest is None:
        raise ValueError("No complete Canadian country ranking in the last five dates")
    days = [target - timedelta(days=n) for n in range(1, config["history_days"])]
    def country(day):
        return parse_country(get_json(f"{API}/top-per-country/CA/all-access/{day:%Y/%m/%d}"), day, config["country_limit"])
    with ThreadPoolExecutor(max_workers=3) as pool:
        history = [latest, *pool.map(country, days)]
    start = target - timedelta(days=config["baseline_days"] + config["history_days"] - 1)
    def topic(item):
        title = quote(item["title"].replace(" ", "_"), safe="")
        url = f"{API}/per-article/{item['project']}/all-access/user/{title}/daily/{start:%Y%m%d}00/{target:%Y%m%d}00"
        return {**item, "history": parse_series(get_json(url), start, target), "source_url": url}
    with ThreadPoolExecutor(max_workers=3) as pool:
        topics = list(pool.map(topic, config["topics"]))
    return {"schema_version": 1, "retrieved_at": datetime.now(timezone.utc).isoformat(), "report_date": target.isoformat(), "baseline_days": config["baseline_days"], "country": "CA", "country_days": history, "topics": topics,
            "source": {"name": "Wikimedia Analytics API", "url": "https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html", "country_measure": "views_ceil: privacy-protected upper bounds, not exact counts or people", "topic_measure": "Worldwide daily user pageviews for the selected article and language", "license": "CC0 1.0 for pageview data"}}


def write_snapshot(data, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    os.replace(temporary, output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat)
    args = parser.parse_args()
    result = collect(json.loads((ROOT / "config/sources.json").read_text()), args.date)
    write_snapshot(result, ROOT / "web/data/snapshot.json")
    write_snapshot({"schema_version": 1, "checked_at": result["retrieved_at"], "report_date": result["report_date"], "topics": len(result["topics"]), "country_days": len(result["country_days"])}, ROOT / "web/data/status.json")
    print(f"Validated {len(result['country_days'])} Canadian rankings and {len(result['topics'])} complete topic histories; report date {result['report_date']}")
