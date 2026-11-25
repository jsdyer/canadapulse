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
    if not isinstance(row.get("title"), str) or not 1 <= len(row["title"]) <= 200 or not PROJECT.fullmatch(row.get("project", "")):
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
    incoming = prepare_days(snapshot)
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
        content = months.setdefault(month, {"schema_version": 1, "month": month, "source": deepcopy(snapshot.get("source", {})), "policy": "First observed values and topic selection are retained. Missing dates are not zero. Country rankings may be added later only when absent.", "days": []})
        existing = next((d for d in content["days"] if d["date"] == value), None)
        if existing is None:
            content["days"].append(record)
            changed.add(month)
        elif "country" not in existing and "country" in record:
            existing["country"] = record["country"]
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
