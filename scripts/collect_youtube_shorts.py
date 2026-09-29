#!/usr/bin/env python3
"""Collect a time-bounded census of public YouTube Shorts metadata.

The script first uses the already-collected, reverse-chronological Shorts index to
locate the date window, then retrieves only the public watch pages needed for the
study. It does not download video or audio files.
"""

from __future__ import annotations

import csv
import json
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
START_DATE = "2024-07-21"
END_DATE = "2024-11-05"
PADDING = 30
MAX_WORKERS = 10
CLIENT_VERSION = "2.20260708.00.00"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class Channel:
    slug: str
    party: str
    actor_type: str
    display_name: str
    channel_id: str
    flat_file: str


CHANNELS = [
    Channel(
        "dnc",
        "Democratic",
        "party",
        "The Democrats",
        "UClkO4MArT2WKWj32YDD_-Ew",
        "dnc_shorts_flat.jsonl",
    ),
    Channel(
        "rnc",
        "Republican",
        "party",
        "GOP",
        "UC3o7kbpTUQ5-0WTMIp8sVwA",
        "rnc_shorts_flat.jsonl",
    ),
    Channel(
        "harris",
        "Democratic",
        "candidate",
        "Kamala Harris",
        "UC0XBsJpPhOLg0k4x9ZwrWzw",
        "harris_shorts_flat.jsonl",
    ),
    Channel(
        "trump",
        "Republican",
        "candidate",
        "Donald J Trump",
        "UCAql2DyGU2un1Ei2nMYsqOA",
        "trump_shorts_flat.jsonl",
    ),
]


def parse_compact_count(value: str | None) -> int | None:
    if not value:
        return None
    cleaned = value.strip().replace(",", "").upper()
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)([KMB])?", cleaned)
    if not match:
        return None
    number = float(match.group(1))
    multiplier = {None: 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[
        match.group(2)
    ]
    return int(round(number * multiplier))


def first_match(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1)
    return None


def innertube_request(endpoint: str, video_id: str, attempts: int = 4) -> dict[str, Any]:
    url = f"https://www.youtube.com/youtubei/v1/{endpoint}"
    payload = json.dumps(
        {
            "context": {
                "client": {
                    "clientName": "WEB",
                    "clientVersion": CLIENT_VERSION,
                    "hl": "en",
                    "gl": "US",
                }
            },
            "videoId": video_id,
        }
    ).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(
                url,
                data=payload,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept-Language": "en-US,en;q=0.9",
                    "Content-Type": "application/json",
                    "X-Youtube-Client-Name": "1",
                    "X-Youtube-Client-Version": CLIENT_VERSION,
                },
                method="POST",
            )
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8", errors="replace"))
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep((2 ** attempt) + random.random())
    raise RuntimeError(f"{type(last_error).__name__}: {last_error}")


def fetch_video_metadata(video_id: str, include_engagement: bool = False) -> dict[str, Any]:
    source_url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        player = innertube_request("player", video_id)
        details = player.get("videoDetails", {})
        micro = player.get("microformat", {}).get("playerMicroformatRenderer", {})
        status = player.get("playabilityStatus", {})
        upload_date = micro.get("uploadDate") or micro.get("publishDate")
        if upload_date:
            upload_date = upload_date[:10]

        like_count = None
        comment_count = None
        if include_engagement:
            next_response = innertube_request("next", video_id)
            next_text = json.dumps(next_response, ensure_ascii=False, separators=(",", ":"))
            like_text = first_match(
                next_text,
                [
                    r"like this video along with ([0-9,.]+) other (?:people|person)",
                    r"([0-9,.]+) (?:people have|person has) liked this video",
                ],
            )
            comment_text = first_match(
                next_text,
                [
                    r'"engagementPanelTitleHeaderRenderer"\s*:\s*\{.{0,700}?'
                    r'"text"\s*:\s*"Comments".{0,500}?"contextualInfo"\s*:\s*'
                    r'\{.{0,250}?"text"\s*:\s*"([0-9,.KMB]+)"',
                    r'"contextualInfo"\s*:\s*\{.{0,250}?"text"\s*:\s*'
                    r'"([0-9,.KMB]+)".{0,500}?"text"\s*:\s*"Comments"',
                ],
            )
            like_count = parse_compact_count(like_text)
            comment_count = parse_compact_count(comment_text)

        return {
            "video_id": video_id,
            "source_url": source_url,
            "title": details.get("title"),
            "description": details.get("shortDescription"),
            "upload_date": upload_date,
            "duration_seconds": int(details.get("lengthSeconds") or 0) or None,
            "view_count": int(details.get("viewCount") or 0) or None,
            "like_count": like_count,
            "comment_count": comment_count,
            "channel_name": details.get("author") or micro.get("ownerChannelName"),
            "channel_id_observed": details.get("channelId") or micro.get("externalChannelId"),
            "is_live_content": details.get("isLiveContent"),
            "playability_status": status.get("status"),
            "playability_reason": status.get("reason"),
            "keywords": details.get("keywords") or [],
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "error": None,
        }
    except RuntimeError as exc:
        return {
            "video_id": video_id,
            "source_url": source_url,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "error": str(exc),
        }


def load_flat_index(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    records.sort(key=lambda row: int(row["playlist_index"]))
    return records


def locate_window(
    records: list[dict[str, Any]], cache: dict[str, dict[str, Any]]
) -> tuple[int, int, list[dict[str, Any]]]:
    """Return a padded, zero-based slice containing the requested date window."""

    probes: list[dict[str, Any]] = []

    def date_at(position: int) -> str:
        video_id = records[position]["id"]
        if video_id not in cache:
            cache[video_id] = fetch_video_metadata(video_id)
            probes.append(cache[video_id])
        date_value = cache[video_id].get("upload_date")
        if not date_value:
            raise ValueError(f"No upload date for probe {video_id}: {cache[video_id].get('error')}")
        return date_value

    def first_position(predicate) -> int:
        lo, hi = 0, len(records)
        while lo < hi:
            mid = (lo + hi) // 2
            if predicate(date_at(mid)):
                hi = mid
            else:
                lo = mid + 1
        return lo

    # The Shorts tab is reverse chronological. Locate the first item at or before
    # the end date, then the first item older than the start date.
    first = first_position(lambda date: date <= END_DATE)
    after_last = first_position(lambda date: date < START_DATE)
    if first >= len(records) or after_last <= first:
        return 0, len(records), probes
    return max(0, first - PADDING), min(len(records), after_last + PADDING), probes


def collect_channel(channel: Channel) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records = load_flat_index(RAW_DIR / channel.flat_file)
    cache: dict[str, dict[str, Any]] = {}
    try:
        start, stop, probes = locate_window(records, cache)
        boundary_mode = "binary_window_with_padding"
    except ValueError:
        start, stop, probes = 0, len(records), []
        boundary_mode = "full_index_fallback"

    selected = records[start:stop]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(fetch_video_metadata, row["id"]): row
            for row in selected
            if row["id"] not in cache
        }
        for future in as_completed(futures):
            row = futures[future]
            cache[row["id"]] = future.result()

    in_window_ids = [
        row["id"]
        for row in selected
        if cache[row["id"]].get("upload_date")
        and START_DATE <= cache[row["id"]]["upload_date"] <= END_DATE
    ]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(fetch_video_metadata, video_id, True): video_id
            for video_id in in_window_ids
        }
        for future in as_completed(futures):
            video_id = futures[future]
            cache[video_id] = future.result()

    output: list[dict[str, Any]] = []
    raw_output: list[dict[str, Any]] = []
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
                "format": "YouTube Shorts",
            }
        )
        raw_output.append(item)
        if item.get("upload_date") and START_DATE <= item["upload_date"] <= END_DATE:
            output.append(item)

    raw_path = RAW_DIR / f"{channel.slug}_shorts_watch_{START_DATE.replace('-', '')}_{END_DATE.replace('-', '')}.jsonl"
    with raw_path.open("w", encoding="utf-8", newline="\n") as handle:
        for item in sorted(raw_output, key=lambda value: int(value["playlist_index"])):
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    audit = {
        "account_slug": channel.slug,
        "account_name": channel.display_name,
        "party": channel.party,
        "actor_type": channel.actor_type,
        "flat_index_size": len(records),
        "retrieved_slice_start_1based": start + 1,
        "retrieved_slice_end_1based": stop,
        "retrieved_watch_pages": len(raw_output),
        "in_window_items": len(output),
        "retrieval_errors": sum(bool(item.get("error")) for item in raw_output),
        "missing_like_count": sum(item.get("like_count") is None for item in output),
        "missing_comment_count": sum(item.get("comment_count") is None for item in output),
        "boundary_mode": boundary_mode,
        "probe_count": len(probes),
    }
    return output, audit


def write_processed(rows: list[dict[str, Any]], audits: list[dict[str, Any]]) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
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
    csv_path = PROCESSED_DIR / "youtube_shorts_2024_general_election.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: (row["upload_date"], row["account_slug"], row["video_id"])))

    audit_path = PROCESSED_DIR / "collection_audit.csv"
    with audit_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(audits[0]))
        writer.writeheader()
        writer.writerows(audits)


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []
    for channel in CHANNELS:
        rows, audit = collect_channel(channel)
        all_rows.extend(rows)
        audits.append(audit)
        print(json.dumps(audit, ensure_ascii=False), flush=True)
    write_processed(all_rows, audits)
    print(
        json.dumps(
            {
                "status": "complete",
                "study_rows": len(all_rows),
                "start_date": START_DATE,
                "end_date": END_DATE,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
