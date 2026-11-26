"""Durable, compact, first-observed pageview archives with atomic publication."""
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

PROJECT = re.compile(r"[a-z][a-z0-9-]{0,20}\.wikipedia")
MONTH = re.compile(r"\d{4}-\d{2}\.json")


def checked_date(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("Invalid archive date")
    return value


def identity(row):
    if not isinstance(row.get("title"), str) or not 1 <= len(row["title"]) <= 255 or not PROJECT.fullmatch(row.get("project", "")):
        raise ValueError("Invalid archived article identity")
    return row["project"], row["title"]


def prepare_days(snapshot):
    if snapshot.get("schema_version") != 1 or snapshot.get("country") != "CA":
        raise ValueError("Unknown snapshot schema/country")
    report = checked_date(snapshot.get("report_date"))
    captured = snapshot.get("retrieved_at")
    if not isinstance(captured, str) or datetime.fromisoformat(captured).tzinfo is None:
        raise ValueError("Snapshot retrieval time must include a timezone")
    baseline = snapshot.get("baseline_days")
    if type(baseline) is not int or not 7 <= baseline <= 90:
        raise ValueError("Invalid archived baseline length")
    days = {}
    def day_record(day):
        day = checked_date(day)
        if day > report:
            raise ValueError("Observation follows the snapshot report date")
        return days.setdefault(day, {"date": day, "first_saved_at": captured, "baseline_days": baseline, "topics": []})
    country_seen = set()
    for country in snapshot.get("country_days", []):
        day = country.get("date")
        if day in country_seen:
            raise ValueError("Duplicate country date")
        country_seen.add(day)
        record = day_record(day)
        articles = country.get("articles")
        if not isinstance(articles, list) or not 1 <= len(articles) <= 500:
            raise ValueError("Invalid archived country ranking")
        seen = set()
        for row in articles:
            key = identity(row)
            if key in seen or type(row.get("views_ceil")) is not int or row["views_ceil"] < 0 or type(row.get("rank")) is not int or row["rank"] < 1:
                raise ValueError("Invalid/duplicate archived country article")
            seen.add(key)
        record["country"] = {"first_saved_at": captured, "articles": deepcopy(articles)}
    if not isinstance(snapshot.get("topics"), list) or not 1 <= len(snapshot["topics"]) <= 100:
        raise ValueError("Invalid topic coverage")
    topic_seen = set()
    for topic in snapshot.get("topics", []):
        key = identity(topic)
        if key in topic_seen or not isinstance(topic.get("group"), str) or not topic["group"].strip():
            raise ValueError("Invalid/duplicate archived topic")
        topic_seen.add(key)
        seen = set()
        for point in topic.get("history", []):
            day = point.get("date")
            if day in seen or type(point.get("views")) is not int or point["views"] < 0:
                raise ValueError("Invalid/duplicate archived topic observation")
            seen.add(day)
            record = day_record(day)
            record["topics"].append({"title": topic["title"], "project": topic["project"], "group": topic["group"], "views": point["views"]})
    if not days or not topic_seen or not country_seen or report not in days:
        raise ValueError("Snapshot is missing required measured data")
    for record in days.values():
        record["topics"].sort(key=lambda row: identity(row))
    return days


def encoded(data):
    return (json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def validate_month(data, month):
    if data.get("schema_version") != 1 or data.get("month") != month or not isinstance(data.get("days"), list):
        raise ValueError("Invalid existing archive month")
    seen = set()
    for day in data["days"]:
        value = checked_date(day.get("date"))
        if value[:7] != month or value in seen or not isinstance(day.get("topics"), list):
            raise ValueError("Invalid existing archive date/coverage")
        seen.add(value)
        if len(day["topics"]) > 100:
            raise ValueError("Unexpected archived topic coverage")
        for topic in day["topics"]:
            identity(topic)
            if type(topic.get("views")) is not int or topic["views"] < 0:
                raise ValueError("Invalid archived topic count")
    return data


def merge_archive(snapshot, directory):
    """Add observed days; an existing day's topic selection/values stay immutable."""
    return merge_days(prepare_days(snapshot), directory, snapshot.get("source", {}))


def merge_days(incoming, directory, source):
    """Merge measured complete day records, including topic-only pre-2021 dates."""
    directory.mkdir(parents=True, exist_ok=True)
    months = {}
    old_manifest_path = directory / "manifest.json"
    old_manifest = json.loads(old_manifest_path.read_text()) if old_manifest_path.exists() else None
    checksums = {m["month"]: m["sha256"] for m in old_manifest.get("months", [])} if old_manifest else {}
    for path in sorted(directory.iterdir()):
        if not MONTH.fullmatch(path.name):
            continue
        raw = path.read_bytes()
        month = path.stem
        if month in checksums and hashlib.sha256(raw).hexdigest() != checksums[month]:
            raise ValueError(f"Existing archive checksum mismatch: {month}")
        months[month] = validate_month(json.loads(raw), month)
    if set(checksums) - set(months):
        raise ValueError("An existing archive month is missing")
    changed = set()
    for value, record in sorted(incoming.items()):
        month = value[:7]
        content = months.setdefault(month, {"schema_version": 1, "month": month, "source": deepcopy(source), "policy": "First observed values and topic selection are retained. Missing dates are not zero. Country rankings or absent topic coverage may be added later only when absent.", "days": []})
        existing = next((d for d in content["days"] if d["date"] == value), None)
        if existing is None:
            content["days"].append(record)
            changed.add(month)
        else:
            if "country" not in existing and "country" in record:
                existing["country"] = record["country"]
                changed.add(month)
            if not existing["topics"] and record["topics"]:
                existing["topics"] = record["topics"]
                existing["topics_saved_at"] = record.get("topics_saved_at", record["first_saved_at"])
                changed.add(month)
    for month in changed:
        months[month]["days"].sort(key=lambda d: d["date"])
        (directory / f"{month}.json").write_bytes(encoded(months[month]))
    entries = []
    for month, content in sorted(months.items(), reverse=True):
        raw = (directory / f"{month}.json").read_bytes()
        dates = [{"date": d["date"], "country": "country" in d, "topics": len(d["topics"]), "baseline_days": d["baseline_days"]} for d in sorted(content["days"], key=lambda d: d["date"], reverse=True)]
        entries.append({"month": month, "path": f"./data/history/{month}.json", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "dates": dates})
    all_dates = sorted(d["date"] for item in entries for d in item["dates"])
    manifest = {"schema_version": 1, "policy": "First observed values; no rolling deletion", "earliest_date": all_dates[0], "latest_date": all_dates[-1], "day_count": len(all_dates), "country_days": sum(d["country"] for m in entries for d in m["dates"]), "months": entries}
    (directory / "manifest.json").write_bytes(encoded(manifest))
    return manifest


def prepare_backfill(result):
    """Keep source gaps; never infer a zero or copy Canadian rankings before 2021."""
    if result.get("schema_version") != 1:
        raise ValueError("Unknown historical import schema")
    end = checked_date(result.get("requested_end"))
    topic_start = checked_date(result.get("topic_start"))
    country_start = checked_date(result.get("country_start"))
    if topic_start < "2015-07-01" or country_start < "2021-01-01" or end < topic_start:
        raise ValueError("Historical import precedes the source dataset")
    captured = result.get("completed_at")
    if not isinstance(captured, str) or datetime.fromisoformat(captured).tzinfo is None:
        raise ValueError("Historical import requires a retrieval timestamp")
    baseline = result.get("baseline_days")
    if type(baseline) is not int or not 7 <= baseline <= 90:
        raise ValueError("Invalid historical baseline")
    days, seen = {}, set()
    def record(value):
        value = checked_date(value)
        if not min(topic_start, country_start) <= value <= end:
            raise ValueError("Observation is outside the requested import range")
        return days.setdefault(value, {"date": value, "first_saved_at": captured, "topics_saved_at": captured, "baseline_days": baseline, "topics": []})
    topics = result.get("topics")
    if not isinstance(topics, list) or not 1 <= len(topics) <= 100:
        raise ValueError("Invalid historical topic selection")
    for topic in topics:
        key = identity(topic)
        if key in seen or not isinstance(topic.get("group"), str) or not topic["group"].strip():
            raise ValueError("Invalid/duplicate historical topic")
        seen.add(key)
        dates = set()
        for point in topic.get("history", []):
            value = checked_date(point.get("date"))
            if value < topic_start:
                raise ValueError("Topic observation precedes the requested topic range")
            if value in dates or type(point.get("views")) is not int or point["views"] < 0:
                raise ValueError("Invalid/duplicate historical topic observation")
            dates.add(value)
            record(value)["topics"].append({"title": topic["title"], "project": topic["project"], "group": topic["group"], "views": point["views"]})
    country_seen = set()
    for country in result.get("country_days", []):
        value = checked_date(country.get("date"))
        if value in country_seen or value < country_start:
            raise ValueError("Invalid/duplicate historical country date")
        country_seen.add(value)
        articles = country.get("articles")
        if not isinstance(articles, list) or not 1 <= len(articles) <= 500:
            raise ValueError("Invalid historical ranking coverage")
        article_seen = set()
        for article in articles:
            key = identity(article)
            if key in article_seen or type(article.get("views_ceil")) is not int or article["views_ceil"] < 0 or type(article.get("rank")) is not int or article["rank"] < 1:
                raise ValueError("Invalid/duplicate historical country article")
            article_seen.add(key)
        retrieved = country.get("retrieved_at")
        if not isinstance(retrieved, str) or datetime.fromisoformat(retrieved).tzinfo is None:
            raise ValueError("Historical ranking retrieval time is missing")
        record(value)["country"] = {"first_saved_at": retrieved, "source_url": country["source_url"], "articles": deepcopy(articles)}
    if not days:
        raise ValueError("Historical import has no observations")
    for day in days.values():
        day["topics"].sort(key=identity)
    return days


def publish_backfill(result, target):
    """Publish only verified archives; never move/re-date the live daily snapshot."""
    incoming = prepare_backfill(result)
    target = Path(target)
    snapshot = json.loads((target / "snapshot.json").read_text())
    source = {**snapshot.get("source", {}), "historical_import": "Retrospective retrieval from the same Wikimedia Analytics endpoints. Topics use the configured selection at import, not a reconstructed historical editorial selection. No absent dates are filled.", "topic_earliest_available": "2015-07-01", "country_earliest_available": "2021-01-01"}
    summary = {k: deepcopy(v) for k, v in result.items() if k not in ("topics", "country_days")}
    summary["source"] = source
    summary["topics"] = [{k: deepcopy(v) for k, v in t.items() if k != "history"} | {"observed_days": len(t["history"]), "first_date": t["history"][0]["date"] if t["history"] else None, "last_date": t["history"][-1]["date"] if t["history"] else None, "missing_days": (date.fromisoformat(result["requested_end"])-date.fromisoformat(result["topic_start"])).days+1-len(t["history"])} for t in result["topics"]]
    summary["observed_country_days"] = len(result["country_days"])
    summary["policy"] = "Existing measured values and topic selections remain unchanged. The live snapshot and its checked_at are not advanced by historical imports."
    with tempfile.TemporaryDirectory(dir=target.parent, prefix=".pulse-refresh-") as temporary:
        temporary = Path(temporary)
        stage = temporary / "data"
        shutil.copytree(target, stage)
        manifest = merge_days(incoming, stage / "history", source)
        country_dates = {d["date"] for month in manifest["months"] for d in month["dates"] if d["country"]}
        summary["upstream_unavailable_but_previously_retained"] = [d["date"] for d in result.get("unavailable_country_days", []) if d["date"] in country_dates]
        summary["unavailable_country_dates_not_archived"] = [d["date"] for d in result.get("unavailable_country_days", []) if d["date"] not in country_dates]
        summary["archive_after_import"] = {key: manifest[key] for key in ("earliest_date", "latest_date", "day_count", "country_days")}
        status = json.loads((stage / "status.json").read_text())
        status.update(archived_days=manifest["day_count"], archived_country_days=manifest["country_days"], archive_earliest=manifest["earliest_date"], archive_latest=manifest["latest_date"])
        (stage / "status.json").write_bytes(encoded(status))
        (stage / "backfill.json").write_bytes(encoded(summary))
        backup = temporary / "previous"
        os.replace(target, backup)
        try:
            os.replace(stage, target)
        except OSError:
            os.replace(backup, target)
            raise
    return manifest


def publish_snapshot(snapshot, target):
    """Publish snapshot, archive, manifest and health data as one directory swap."""
    prepare_days(snapshot)  # Reject incomplete input before touching any persisted data.
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix=".pulse-refresh-") as temporary:
        temporary = Path(temporary)
        stage = temporary / "data"
        if target.exists():
            shutil.copytree(target, stage)
        else:
            stage.mkdir()
        manifest = merge_archive(snapshot, stage / "history")
        existing_path = stage / "snapshot.json"
        active = snapshot
        if existing_path.exists():
            existing = json.loads(existing_path.read_text())
            if existing.get("report_date", "") > snapshot["report_date"]:
                active = existing  # An explicit historical import cannot move the live report backward.
        existing_path.write_bytes(encoded(active))
        status = {"schema_version": 1, "checked_at": active["retrieved_at"], "report_date": active["report_date"], "topics": len(active["topics"]), "country_days": len(active["country_days"]), "archived_days": manifest["day_count"], "archived_country_days": manifest["country_days"], "archive_earliest": manifest["earliest_date"], "archive_latest": manifest["latest_date"]}
        (stage / "status.json").write_bytes(encoded(status))
        backup = temporary / "previous"
        if target.exists():
            os.replace(target, backup)
        try:
            os.replace(stage, target)
        except OSError:
            if backup.exists():
                os.replace(backup, target)
            raise
    return manifest
