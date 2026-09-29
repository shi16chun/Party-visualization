#!/usr/bin/env python3
"""Collect short-form items (<=180s) that YouTube lists on each Videos tab."""

from __future__ import annotations

import csv
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path

import collect_youtube_shorts as base


CHANNELS = [
    replace(channel, flat_file=f"{channel.slug}_flat.jsonl")
    for channel in base.CHANNELS
]


def collect_channel(channel: base.Channel):
    records = base.load_flat_index(base.RAW_DIR / channel.flat_file)
    cache = {}
    try:
        start, stop, probes = base.locate_window(records, cache)
        boundary_mode = "binary_window_with_padding"
    except ValueError:
        start, stop, probes = 0, len(records), []
        boundary_mode = "full_index_fallback"

    selected = records[start:stop]
    with ThreadPoolExecutor(max_workers=base.MAX_WORKERS) as executor:
        futures = {
            executor.submit(base.fetch_video_metadata, row["id"]): row
            for row in selected
            if row["id"] not in cache
        }
        for future in as_completed(futures):
            row = futures[future]
            cache[row["id"]] = future.result()

    study_ids = [
        row["id"]
        for row in selected
        if cache[row["id"]].get("upload_date")
        and base.START_DATE <= cache[row["id"]]["upload_date"] <= base.END_DATE
        and (cache[row["id"]].get("duration_seconds") or 10**9) <= 180
    ]
    with ThreadPoolExecutor(max_workers=base.MAX_WORKERS) as executor:
        futures = {
            executor.submit(base.fetch_video_metadata, video_id, True): video_id
            for video_id in study_ids
        }
        for future in as_completed(futures):
            video_id = futures[future]
            cache[video_id] = future.result()

    raw_rows = []
    study_rows = []
    for row in selected:
        item = dict(cache[row["id"]])
        item.update(
            {
                "account_slug": channel.slug,
                "party": channel.party,
                "actor_type": channel.actor_type,
                "account_name": channel.display_name,
                "channel_id_expected": channel.channel_id,
                "playlist_index": row["playlist_index"],
                "format": "YouTube Videos tab",
            }
        )
        raw_rows.append(item)
        if item["video_id"] in study_ids:
            study_rows.append(item)

    raw_path = base.RAW_DIR / (
        f"{channel.slug}_videos_tab_watch_"
        f"{base.START_DATE.replace('-', '')}_{base.END_DATE.replace('-', '')}.jsonl"
    )
    with raw_path.open("w", encoding="utf-8", newline="\n") as handle:
        for item in sorted(raw_rows, key=lambda value: int(value["playlist_index"])):
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    audit = {
        "account_slug": channel.slug,
        "account_name": channel.display_name,
        "party": channel.party,
        "actor_type": channel.actor_type,
        "flat_index_size": len(records),
        "retrieved_slice_start_1based": start + 1,
        "retrieved_slice_end_1based": stop,
        "retrieved_watch_pages": len(raw_rows),
        "in_window_items_all_durations": sum(
            bool(item.get("upload_date"))
            and base.START_DATE <= item["upload_date"] <= base.END_DATE
            for item in raw_rows
        ),
        "in_window_items_le_180s": len(study_rows),
        "retrieval_errors": sum(bool(item.get("error")) for item in raw_rows),
        "missing_like_count": sum(item.get("like_count") is None for item in study_rows),
        "missing_comment_count": sum(item.get("comment_count") is None for item in study_rows),
        "boundary_mode": boundary_mode,
        "probe_count": len(probes),
    }
    return study_rows, audit


def write_outputs(rows, audits):
    base.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    fields = [
        "video_id",
        "upload_date",
        "party",
        "actor_type",
        "account_slug",
        "account_name",
        "channel_id_expected",
        "channel_id_observed",
        "playlist_index",
        "format",
        "title",
        "description",
        "duration_seconds",
        "view_count",
        "like_count",
        "comment_count",
        "is_live_content",
        "playability_status",
        "source_url",
        "retrieved_at_utc",
        "error",
    ]
    csv_path = base.PROCESSED_DIR / "youtube_videos_tab_shortform_2024_general_election.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(
            sorted(rows, key=lambda row: (row["upload_date"], row["account_slug"], row["video_id"]))
        )

    audit_path = base.PROCESSED_DIR / "collection_audit_videos_tab.csv"
    with audit_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(audits[0]))
        writer.writeheader()
        writer.writerows(audits)


def main():
    all_rows = []
    audits = []
    for channel in CHANNELS:
        rows, audit = collect_channel(channel)
        all_rows.extend(rows)
        audits.append(audit)
        print(json.dumps(audit, ensure_ascii=False), flush=True)
    write_outputs(all_rows, audits)
    print(json.dumps({"status": "complete", "study_rows": len(all_rows)}), flush=True)


if __name__ == "__main__":
    main()
