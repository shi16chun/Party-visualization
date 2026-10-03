#!/usr/bin/env python3
"""任务卡A1：YouTube全量采集（普通视频、Shorts、直播回放）。

用法：
  python v3/scripts/a1_collect_youtube.py index   # 频道各页面平面索引，不需要API密钥
  python v3/scripts/a1_collect_youtube.py api     # 官方Data API：上传列表、窗口期视频元数据
  python v3/scripts/a1_collect_youtube.py build   # 合并为窗口期总表，与旧稿363条比对
  python v3/scripts/a1_collect_youtube.py all     # 依次执行以上三步
可选参数：--nodes dnc,rnc 只处理所列频道（index、api两步有效）。

输入：
  v3/data/accounts.csv                                   YouTube频道清单（A0产出）
  data/processed/youtube_shorts_2024_general_election.csv 旧稿363条（只读）
输出：
  v3/data/raw/youtube/<slug>__index_<tab>.jsonl   频道页面平面索引（tab = videos/shorts/streams）
  v3/data/raw/youtube/<slug>__uploads_api.jsonl   上传列表（全部公开视频的ID与发布时间）
  v3/data/raw/youtube/<slug>__videos_api.jsonl    窗口期视频的完整元数据（API原始返回）
  v3/data/raw/youtube/<slug>.jsonl                窗口期逐条记录（合并后，每行一条视频）
  v3/data/audit/youtube_pull_log.csv              每个频道每一步的拉取日志
  v3/data/processed/youtube_window.csv            窗口期总表
  v3/data/audit/youtube_vs_v1.csv                 与旧稿363条逐条比对
参数：
  窗口按美国东部时间计：2024-07-21 00:00 至 2024-11-05 23:59:59（America/New_York）。
  旧稿按YouTube页面给出的发布日期（太平洋时间）计，边界附近的差异在比对表中单列。
  API密钥不写入代码与文件：由环境的API credentials在代理处附加 X-Goog-Api-Key 请求头；
  若设置了环境变量 YOUTUBE_API_KEY，则改以查询参数传入。
  无随机过程。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "v3" / "data" / "raw" / "youtube"
AUDIT = ROOT / "v3" / "data" / "audit"
PROCESSED = ROOT / "v3" / "data" / "processed"
ACCOUNTS = ROOT / "v3" / "data" / "accounts.csv"
V1_CSV = ROOT / "data" / "processed" / "youtube_shorts_2024_general_election.csv"

ET = ZoneInfo("America/New_York")
WINDOW_START = datetime(2024, 7, 21, 0, 0, 0, tzinfo=ET)
WINDOW_END = datetime(2024, 11, 5, 23, 59, 59, tzinfo=ET)
TABS = ["videos", "shorts", "streams"]
API = "https://www.googleapis.com/youtube/v3"
PAUSE = 0.5

SLUGS = {
    "DNC": "dnc",
    "RNC": "rnc",
    "Kamala HQ": "kamalahq",
    "Kamala Harris": "harris",
    "Team Trump": "teamtrump",
    "Trump War Room": "trumpwarroom",
    "Donald J. Trump": "trump",
}
V1_SLUG = {"dnc": "dnc", "rnc": "rnc", "harris": "harris", "trump": "trump"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_channels(only: set[str] | None) -> list[dict]:
    """A0账号表中YouTube上存在的频道；窗口期无发布的频道也拉索引，用于核验。"""
    out = []
    with ACCOUNTS.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["platform"] != "youtube" or not row["platform_id"].startswith("UC"):
                continue
            slug = SLUGS[row["node"]]
            if only and slug not in only:
                continue
            out.append({"slug": slug, "node": row["node"], "camp": row["camp"], "role": row["role"],
                        "channel_id": row["platform_id"], "in_scope": row["in_scope"]})
    return out


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def append_log(rows: list[dict]) -> None:
    path = AUDIT / "youtube_pull_log.csv"
    fields = ["slug", "step", "target", "items", "errors", "detail", "retrieved_at"]
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        if new:
            w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------- index
def step_index(channels: list[dict]) -> None:
    import yt_dlp

    opts = {"extract_flat": "in_playlist", "quiet": True, "no_warnings": True,
            "skip_download": True, "sleep_interval_requests": PAUSE, "ignoreerrors": False}
    for ch in channels:
        logs = []
        for tab in TABS:
            url = f"https://www.youtube.com/channel/{ch['channel_id']}/{tab}"
            started = now_iso()
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                entries = list(info.get("entries") or [])
                rows = [{"playlist_index": i + 1, "id": e.get("id"), "title": e.get("title"),
                         "duration": e.get("duration"), "view_count": e.get("view_count"),
                         "url": e.get("url"), "tab": tab, "channel_id": ch["channel_id"],
                         "retrieved_at": started} for i, e in enumerate(entries)]
                write_jsonl(RAW / f"{ch['slug']}__index_{tab}.jsonl", rows)
                logs.append({"slug": ch["slug"], "step": "index", "target": tab, "items": len(rows),
                             "errors": 0, "detail": url, "retrieved_at": started})
            except Exception as exc:  # 该页面不存在（如无直播）或请求失败，均如实记录
                msg = str(exc).splitlines()[0][:300]
                no_tab = "does not have a" in msg  # 频道本无此页面，不计为抓取失败
                write_jsonl(RAW / f"{ch['slug']}__index_{tab}.jsonl", [])
                logs.append({"slug": ch["slug"], "step": "index", "target": tab, "items": 0,
                             "errors": 0 if no_tab else 1,
                             "detail": f"{url} :: {'无此页面' if no_tab else '抓取失败'} :: {msg}",
                             "retrieved_at": started})
            print(ch["slug"], tab, logs[-1]["items"], logs[-1]["detail"][-120:])
            time.sleep(PAUSE)
        append_log(logs)


# ---------------------------------------------------------------- api
def api_get(endpoint: str, params: dict) -> dict:
    from curl_cffi import requests

    params = dict(params)
    key = os.environ.get("YOUTUBE_API_KEY")
    if key:
        params["key"] = key
    last = None
    for attempt in range(4):
        try:
            resp = requests.get(f"{API}/{endpoint}", params=params, timeout=60)
            if resp.status_code == 200:
                return resp.json()
            last = f"HTTP {resp.status_code}: {resp.text[:300]}"
            if resp.status_code in (400, 401, 403, 404):
                break
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"
        time.sleep(2 ** attempt)
    raise RuntimeError(last)


def check_api() -> None:
    try:
        api_get("videos", {"part": "id", "id": "GsXS8WudinM"})
    except RuntimeError as exc:
        sys.exit(f"YouTube Data API 不可用，api步骤中止：{exc}")


def iso_duration_seconds(text: str | None) -> int | None:
    if not text:
        return None
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", text)
    if not m:
        return None
    d, h, mi, s = (int(x) if x else 0 for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def in_window(published_at: str) -> bool:
    ts = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    return WINDOW_START <= ts <= WINDOW_END


def step_api(channels: list[dict]) -> None:
    check_api()
    for ch in channels:
        logs = []
        started = now_iso()
        uploads = "UU" + ch["channel_id"][2:]
        items, token = [], None
        try:
            while True:
                params = {"part": "contentDetails,snippet", "playlistId": uploads, "maxResults": 50}
                if token:
                    params["pageToken"] = token
                data = api_get("playlistItems", params)
                for it in data.get("items", []):
                    cd, sn = it.get("contentDetails", {}), it.get("snippet", {})
                    items.append({"video_id": cd.get("videoId"),
                                  "published_at": cd.get("videoPublishedAt") or sn.get("publishedAt"),
                                  "position": sn.get("position"), "title": sn.get("title"),
                                  "retrieved_at": started})
                token = data.get("nextPageToken")
                if not token:
                    break
                time.sleep(PAUSE)
            err = 0
            detail = uploads
        except RuntimeError as exc:
            err, detail = 1, f"{uploads} :: {exc}"
        write_jsonl(RAW / f"{ch['slug']}__uploads_api.jsonl", items)
        logs.append({"slug": ch["slug"], "step": "api_uploads", "target": uploads, "items": len(items),
                     "errors": err, "detail": detail, "retrieved_at": started})

        window_ids = [r["video_id"] for r in items if r.get("published_at") and in_window(r["published_at"])]
        records, failed = [], 0
        started = now_iso()
        for i in range(0, len(window_ids), 50):
            batch = window_ids[i:i + 50]
            try:
                data = api_get("videos", {"part": "snippet,contentDetails,statistics,liveStreamingDetails,status",
                                          "id": ",".join(batch), "maxResults": 50})
                got = {it["id"]: it for it in data.get("items", [])}
                for vid in batch:
                    rec = got.get(vid)
                    if rec is None:
                        failed += 1
                        records.append({"id": vid, "error": "not returned by videos.list", "retrieved_at": started})
                    else:
                        rec["retrieved_at"] = started
                        records.append(rec)
            except RuntimeError as exc:
                failed += len(batch)
                records.extend({"id": vid, "error": str(exc)[:300], "retrieved_at": started} for vid in batch)
            time.sleep(PAUSE)
        write_jsonl(RAW / f"{ch['slug']}__videos_api.jsonl", records)
        logs.append({"slug": ch["slug"], "step": "api_videos", "target": "window", "items": len(records) - failed,
                     "errors": failed, "detail": f"{len(window_ids)} ids in window", "retrieved_at": started})
        append_log(logs)
        print(ch["slug"], "uploads", len(items), "window", len(window_ids), "failed", failed)


# ---------------------------------------------------------------- build
def step_build(channels: list[dict]) -> None:
    out_rows = []
    for ch in channels:
        tab_of: dict[str, str] = {}
        for tab in TABS:
            for r in read_jsonl(RAW / f"{ch['slug']}__index_{tab}.jsonl"):
                tab_of.setdefault(r["id"], tab)
        node_rows = []
        for rec in read_jsonl(RAW / f"{ch['slug']}__videos_api.jsonl"):
            if rec.get("error"):
                node_rows.append({"post_id": rec["id"], "error": rec["error"]})
                continue
            sn, cd, st = rec.get("snippet", {}), rec.get("contentDetails", {}), rec.get("statistics", {})
            live = rec.get("liveStreamingDetails") or {}
            pub = datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
            node_rows.append({
                "node": ch["node"], "camp": ch["camp"], "role": ch["role"], "platform": "youtube",
                "slug": ch["slug"], "channel_id": sn.get("channelId"), "post_id": rec["id"],
                "published_at_utc": pub.astimezone(timezone.utc).isoformat(),
                "date_et": pub.astimezone(ET).date().isoformat(),
                "tab": tab_of.get(rec["id"], "not_in_index"),
                "is_live_broadcast": bool(live),
                "duration": iso_duration_seconds(cd.get("duration")),
                "title": sn.get("title"), "description": sn.get("description"),
                "views_now": st.get("viewCount"), "likes_now": st.get("likeCount"),
                "comments_now": st.get("commentCount"),
                "privacy_status": (rec.get("status") or {}).get("privacyStatus"),
                "url": f"https://www.youtube.com/watch?v={rec['id']}",
                "retrieved_at": rec.get("retrieved_at"), "error": "",
            })
        write_jsonl(RAW / f"{ch['slug']}.jsonl", node_rows)
        out_rows.extend(r for r in node_rows if not r.get("error"))
    fields = ["node", "camp", "role", "platform", "slug", "channel_id", "post_id", "published_at_utc", "date_et",
              "tab", "is_live_broadcast", "duration", "title", "description", "views_now", "likes_now",
              "comments_now", "privacy_status", "url", "retrieved_at"]
    PROCESSED.mkdir(parents=True, exist_ok=True)
    with (PROCESSED / "youtube_window.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(out_rows, key=lambda r: (r["slug"], r["published_at_utc"])))
    print("youtube_window.csv", len(out_rows))
    compare_v1(out_rows)


def compare_v1(v3_rows: list[dict]) -> None:
    """旧稿363条逐条比对：是否仍在线、窗口与页面归属是否一致、指标变化。"""
    v3 = {r["post_id"]: r for r in v3_rows}
    uploads: dict[str, dict] = {}
    for slug in V1_SLUG.values():
        for r in read_jsonl(RAW / f"{slug}__uploads_api.jsonl"):
            uploads[r["video_id"]] = r
    rows = []
    with V1_CSV.open(encoding="utf-8-sig") as fh:
        for old in csv.DictReader(fh):
            vid = old["video_id"]
            new = v3.get(vid)
            if new:
                status = "仍在线，在v3窗口内" + ("" if new["tab"] == "shorts" else f"（现归{new['tab']}页）")
            elif vid in uploads:
                status = "仍在线，不在v3窗口内（时区边界）"
            else:
                status = "不在现上传列表（下线、删除或转为非公开）"

            def delta(a, b):
                try:
                    return int(b) - int(a)
                except (TypeError, ValueError):
                    return ""

            rows.append({
                "source": "v1", "slug": old["account_slug"], "post_id": vid, "status": status,
                "v1_upload_date": old["upload_date"], "v3_date_et": new["date_et"] if new else "",
                "v1_duration": old["duration_seconds"], "v3_duration": new["duration"] if new else "",
                "v1_views": old["view_count"], "v3_views": new["views_now"] if new else "",
                "views_change": delta(old["view_count"], new["views_now"]) if new else "",
                "v1_likes": old["like_count"], "v3_likes": new["likes_now"] if new else "",
                "v1_comments": old["comment_count"], "v3_comments": new["comments_now"] if new else "",
            })
    v1_ids = {r["post_id"] for r in rows}
    for r in v3_rows:
        if r["slug"] in V1_SLUG and r["tab"] == "shorts" and r["post_id"] not in v1_ids:
            rows.append({"source": "v3", "slug": r["slug"], "post_id": r["post_id"],
                         "status": "v3新增（旧稿未收录的Shorts）", "v1_upload_date": "", "v3_date_et": r["date_et"],
                         "v1_duration": "", "v3_duration": r["duration"], "v1_views": "", "v3_views": r["views_now"],
                         "views_change": "", "v1_likes": "", "v3_likes": r["likes_now"], "v1_comments": "",
                         "v3_comments": r["comments_now"]})
    fields = list(rows[0].keys())
    with (AUDIT / "youtube_vs_v1.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    print(Counter(r["status"] for r in rows))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("step", choices=["index", "api", "build", "all"])
    p.add_argument("--nodes", default="")
    a = p.parse_args()
    only = set(x for x in a.nodes.split(",") if x) or None
    channels = load_channels(only)
    if a.step in ("index", "all"):
        step_index(channels)
    if a.step in ("api", "all"):
        step_api(channels)
    if a.step in ("build", "all"):
        step_build(load_channels(None))


if __name__ == "__main__":
    main()
