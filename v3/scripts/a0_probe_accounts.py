#!/usr/bin/env python3
"""任务卡A0：探测六个节点在四个平台上的账号现状。

输入：本脚本内的 CANDIDATES（大纲第三节账号表加上核验中发现的改名线索）
      与 POST_PROBES（2024年窗口期内的帖子ID，用来追踪账号改名）。
输出：
  v3/data/raw/accounts/<platform>__<key>.json  每次请求的原始返回（含抓取时间与HTTP状态）
  v3/data/audit/a0_probe.csv                    每个探测对象一行的解析结果
参数：--platforms youtube,tiktok,x,truthsocial（可选）只重跑所列平台，a0_probe.csv 中其他平台的行保留不动；
      不加参数时全部重跑并覆盖。请求之间固定间隔，不含随机过程。

说明：
  - YouTube：频道 /about 页面中的 ytInitialData（创建日期、订阅数、认证标记、handle）。
  - TikTok：用户主页中的 __UNIVERSAL_DATA_FOR_REHYDRATION__（数字ID、创建时间、认证、粉丝数、视频数）；
    单条视频页用于追踪2024年视频现在归属的账号。
  - X：第三方公开接口 api.fxtwitter.com（用户资料与单条帖子作者），未登录、未用付费接口。
  - 帖子探测（POST_PROBES）中 created 列为该帖的发布时间，不是账号创建时间。
  - Truth Social：Mastodon兼容接口 /api/v1/accounts/lookup；本环境下被Cloudflare拦截时如实记录。
"""

from __future__ import annotations

import csv
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from curl_cffi import requests

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "v3" / "data" / "raw" / "accounts"
AUDIT_CSV = ROOT / "v3" / "data" / "audit" / "a0_probe.csv"
PAUSE_SECONDS = 2.0

# (node, platform, key, kind)  kind: handle / channel_id
CANDIDATES = [
    # YouTube
    ("DNC", "youtube", "UClkO4MArT2WKWj32YDD_-Ew", "channel_id"),
    ("RNC", "youtube", "UC3o7kbpTUQ5-0WTMIp8sVwA", "channel_id"),
    ("Kamala Harris", "youtube", "UC0XBsJpPhOLg0k4x9ZwrWzw", "channel_id"),
    ("Donald J. Trump", "youtube", "UCAql2DyGU2un1Ei2nMYsqOA", "channel_id"),
    ("Kamala HQ", "youtube", "KamalaHQ", "handle"),
    ("Kamala HQ", "youtube", "HQNewsNow", "handle"),
    ("Kamala HQ", "youtube", "headquarters", "handle"),
    ("Team Trump", "youtube", "TeamTrump", "handle"),
    # TikTok
    ("DNC", "tiktok", "thedemocrats", "handle"),
    ("DNC", "tiktok", "democrats", "handle"),
    ("DNC", "tiktok", "dnc", "handle"),
    ("RNC", "tiktok", "gop", "handle"),
    ("RNC", "tiktok", "republicans", "handle"),
    ("RNC", "tiktok", "rnc", "handle"),
    ("Kamala HQ", "tiktok", "kamalahq", "handle"),
    ("Kamala HQ", "tiktok", "headquarters", "handle"),
    ("Kamala Harris", "tiktok", "kamalaharris", "handle"),
    ("Team Trump", "tiktok", "teamtrump", "handle"),
    ("Donald J. Trump", "tiktok", "realdonaldtrump", "handle"),
    # X
    ("DNC", "x", "TheDemocrats", "handle"),
    ("DNC", "x", "DNC", "handle"),
    ("RNC", "x", "GOP", "handle"),
    ("RNC", "x", "Republicans", "handle"),
    ("RNC", "x", "RNC", "handle"),
    ("Kamala HQ", "x", "KamalaHQ", "handle"),
    ("Kamala HQ", "x", "HQNewsNow", "handle"),
    ("Kamala HQ", "x", "headquarters_67", "handle"),
    ("Kamala Harris", "x", "KamalaHarris", "handle"),
    ("Team Trump", "x", "TeamTrump", "handle"),
    ("Donald J. Trump", "x", "realDonaldTrump", "handle"),
    # Truth Social
    ("Donald J. Trump", "truthsocial", "realDonaldTrump", "handle"),
    ("Team Trump", "truthsocial", "TeamTrump", "handle"),
    ("RNC", "truthsocial", "GOP", "handle"),
    ("RNC", "truthsocial", "RNC", "handle"),
]

# 2024年的帖子，用来确认原账号现在的ID与名称，以及窗口期内是否发布。来源见 v3/data/audit/a0_evidence.md。
POST_PROBES = [
    # X（帖子ID）
    ("Kamala HQ", "x", "1815212766912803099"),
    ("Kamala HQ", "x", "1834237601659703754"),
    ("RNC", "x", "1792584647336931731"),
    ("RNC", "x", "1792600850860327031"),
    ("DNC", "x", "1833680183540191305"),
    ("Team Trump", "x", "1835314099757916355"),
    ("Kamala Harris", "x", "1851815659144872236"),
    ("Donald J. Trump", "x", "1823035759655264697"),
    # TikTok（视频ID）
    ("DNC", "tiktok", "7406055642676464939"),
    ("Kamala HQ", "tiktok", "7400033789335948575"),
    ("Kamala HQ", "tiktok", "7431356795391692074"),
    ("Kamala Harris", "tiktok", "7395695233276595487"),
    ("Kamala Harris", "tiktok", "7426486234593217838"),
    ("Team Trump", "tiktok", "7433202628072394030"),
    ("Donald J. Trump", "tiktok", "7403175874607975710"),
    ("Donald J. Trump", "tiktok", "7427237451954965791"),
    # YouTube（视频ID）
    ("DNC", "youtube", "iyxa3eCv44U"),
    ("RNC", "youtube", "qGd4-MKK5_s"),
    ("Kamala Harris", "youtube", "f6hcPwHIGc0"),
    ("Donald J. Trump", "youtube", "-U3fvlYkQa4"),
    ("Kamala HQ", "youtube", "GsXS8WudinM"),
    ("Kamala HQ", "youtube", "w_yGrsxNprA"),
    ("Team Trump", "youtube", "vST61W4bGm8"),
]

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fetch(url: str, attempts: int = 3) -> tuple[int, str]:
    last = (0, "")
    for i in range(attempts):
        try:
            resp = requests.get(url, headers=HEADERS, impersonate="chrome", timeout=40)
            last = (resp.status_code, resp.text)
            if resp.status_code == 200:
                return last
        except Exception as exc:  # 网络错误照样记录
            last = (0, f"REQUEST_ERROR: {exc}")
        time.sleep(PAUSE_SECONDS * (i + 1))
    return last


def save_raw(platform: str, key: str, payload: dict) -> str:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", key)
    path = RAW_DIR / f"{platform}__{safe}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return str(path.relative_to(ROOT))


def parse_count(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"([0-9][0-9,.]*)\s*([KMB])?", text)
    if not m:
        return None
    num = float(m.group(1).replace(",", ""))
    mult = {None: 1, "K": 1e3, "M": 1e6, "B": 1e9}[m.group(2)]
    return int(round(num * mult))


def probe_youtube(key: str, kind: str) -> dict:
    base = f"https://www.youtube.com/channel/{key}" if kind == "channel_id" else f"https://www.youtube.com/@{key}"
    url = base + "/about"
    status, html = fetch(url)
    out = {"url": url, "http_status": status}
    ext = {}
    if status == 200:
        pats = {
            "joined": r'"joinedDateText":\{"content":"Joined ([^"]+)"',
            "subscribers_text": r'"subscriberCountText":"([^"]+)"',
            "video_count_text": r'"videoCountText":"([^"]+)"',
            "canonical_url": r'"canonicalChannelUrl":"([^"]+)"',
            # 页面里的 "channelId" 可能属于推荐频道，频道自身ID取 canonical 链接
            "channel_id": r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[A-Za-z0-9_-]{22})"',
            "title": r'<meta property="og:title" content="([^"]+)"',
        }
        for name, pat in pats.items():
            m = re.search(pat, html)
            ext[name] = m.group(1) if m else None
        ext["verified_badge"] = "BADGE_STYLE_TYPE_VERIFIED" in html or "CHECK_CIRCLE_FILLED" in html
    out["extracted"] = ext
    out["raw_excerpt"] = html[:500] if status != 200 else None
    row = {
        "exists": status == 200 and bool(ext.get("channel_id")),
        "platform_id": ext.get("channel_id"),
        "handle_now": (ext.get("canonical_url") or "").rsplit("/", 1)[-1] or None,
        "display_name": ext.get("title"),
        "created": _yt_date(ext.get("joined")),
        "verified": ext.get("verified_badge"),
        "followers_now": parse_count(ext.get("subscribers_text")),
        "posts_now": parse_count(ext.get("video_count_text")),
    }
    return out, row


def _yt_date(text: str | None) -> str | None:
    if not text:
        return None
    try:
        return datetime.strptime(text, "%b %d, %Y").date().isoformat()
    except ValueError:
        return text


def tiktok_state(html: str) -> dict:
    m = re.search(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(m.group(1)).get("__DEFAULT_SCOPE__", {}) if m else {}


def probe_tiktok(key: str, kind: str) -> dict:
    url = f"https://www.tiktok.com/@{key}"
    status, html = fetch(url)
    scope = tiktok_state(html) if status == 200 else {}
    detail = scope.get("webapp.user-detail", {})
    info = detail.get("userInfo", {})
    user, stats = info.get("user", {}), info.get("stats", {})
    out = {"url": url, "http_status": status, "statusCode": detail.get("statusCode"),
           "user": user, "stats": stats}
    ct = user.get("createTime")
    row = {
        "exists": bool(user.get("id")),
        "platform_id": user.get("id"),
        "handle_now": user.get("uniqueId"),
        "display_name": user.get("nickname"),
        "created": datetime.fromtimestamp(ct, timezone.utc).date().isoformat() if ct else None,
        "verified": user.get("verified"),
        "followers_now": stats.get("followerCount"),
        "posts_now": stats.get("videoCount"),
    }
    return out, row


def probe_x(key: str, kind: str) -> dict:
    url = f"https://api.fxtwitter.com/{key}"
    status, text = fetch(url)
    try:
        data = json.loads(text)
    except ValueError:
        data = {"unparsed": text[:500]}
    user = data.get("user") or {}
    ver = user.get("verification") or {}
    joined = user.get("joined")
    row = {
        "exists": bool(user.get("id")),
        "platform_id": user.get("id"),
        "handle_now": user.get("screen_name"),
        "display_name": user.get("name"),
        "created": datetime.strptime(joined, "%a %b %d %H:%M:%S %z %Y").date().isoformat() if joined else None,
        "verified": f"{ver.get('verified')}:{ver.get('type')}" if ver else None,
        "followers_now": user.get("followers"),
        "posts_now": user.get("tweets"),
    }
    return {"url": url, "http_status": status, "response": data}, row


def probe_x_post(post_id: str) -> tuple[dict, dict]:
    url = f"https://api.fxtwitter.com/status/{post_id}"
    status, text = fetch(url)
    try:
        data = json.loads(text)
    except ValueError:
        data = {"unparsed": text[:500]}
    tweet = data.get("tweet") or {}
    author = tweet.get("author") or {}
    row = {
        "exists": bool(author.get("id")),
        "platform_id": author.get("id"),
        "handle_now": author.get("screen_name"),
        "display_name": author.get("name"),
        "created": tweet.get("created_at"),
        "verified": None,
        "followers_now": author.get("followers"),
        "posts_now": None,
    }
    return {"url": url, "http_status": status, "response": data}, row


def probe_tiktok_post(post_id: str) -> tuple[dict, dict]:
    # TikTok视频页的路径里 @ 后的名字不参与解析，作者以页面返回为准
    url = f"https://www.tiktok.com/@_/video/{post_id}"
    status, html = fetch(url)
    scope = tiktok_state(html) if status == 200 else {}
    detail = scope.get("webapp.video-detail", {})
    item = (detail.get("itemInfo") or {}).get("itemStruct") or {}
    author = item.get("author") or {}
    ct = item.get("createTime")
    row = {
        "exists": bool(author.get("id")),
        "platform_id": author.get("id"),
        "handle_now": author.get("uniqueId"),
        "display_name": author.get("nickname"),
        "created": datetime.fromtimestamp(int(ct), timezone.utc).isoformat() if ct else None,
        "verified": author.get("verified"),
        "followers_now": None,
        "posts_now": None,
    }
    out = {"url": url, "http_status": status, "statusCode": detail.get("statusCode"),
           "desc": item.get("desc"), "author": author, "createTime": ct}
    return out, row


def probe_youtube_post(video_id: str) -> tuple[dict, dict]:
    import yt_dlp

    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(url, download=False)
        status = 200
    except Exception as exc:
        info, status = {"error": str(exc)}, 0
    keep = {k: info.get(k) for k in ["id", "title", "upload_date", "duration", "channel", "channel_id",
                                     "uploader_id", "channel_follower_count", "error"]}
    ud = info.get("upload_date")
    row = {
        "exists": bool(info.get("channel_id")),
        "platform_id": info.get("channel_id"),
        "handle_now": info.get("uploader_id"),
        "display_name": info.get("channel"),
        "created": f"{ud[:4]}-{ud[4:6]}-{ud[6:]}" if ud else None,
        "verified": info.get("channel_is_verified"),
        "followers_now": info.get("channel_follower_count"),
        "posts_now": None,
    }
    return {"url": url, "http_status": status, "info": keep}, row


POST_PROBERS = {"x": probe_x_post, "tiktok": probe_tiktok_post, "youtube": probe_youtube_post}


def probe_truthsocial(key: str, kind: str) -> dict:
    url = f"https://truthsocial.com/api/v1/accounts/lookup?acct={key}"
    status, text = fetch(url, attempts=2)
    blocked = "cloudflare" in text.lower() or "just a moment" in text.lower()
    try:
        data = json.loads(text) if not blocked else {}
    except ValueError:
        data = {}
    row = {
        "exists": bool(data.get("id")) if data else None,
        "platform_id": data.get("id"),
        "handle_now": data.get("username"),
        "display_name": data.get("display_name"),
        "created": (data.get("created_at") or "")[:10] or None,
        "verified": data.get("verified"),
        "followers_now": data.get("followers_count"),
        "posts_now": data.get("statuses_count"),
    }
    out = {"url": url, "http_status": status, "blocked_by_cloudflare": blocked,
           "response": data if data else text[:300]}
    return out, row


PROBERS = {"youtube": probe_youtube, "tiktok": probe_tiktok, "x": probe_x, "truthsocial": probe_truthsocial}
FIELDS = ["node", "platform", "probe_type", "probe_key", "http_status", "exists", "platform_id",
          "handle_now", "display_name", "created", "verified", "followers_now", "posts_now",
          "raw_file", "retrieved_at"]


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--platforms", default=",".join(PROBERS))
    only = set(parser.parse_args().platforms.split(","))
    rows = []
    for node, platform, key, kind in CANDIDATES:
        if platform not in only:
            continue
        out, row = PROBERS[platform](key, kind)
        out["retrieved_at"] = now_iso()
        raw = save_raw(platform, key, out)
        rows.append({"node": node, "platform": platform, "probe_type": kind, "probe_key": key,
                     "http_status": out["http_status"], **row, "raw_file": raw,
                     "retrieved_at": out["retrieved_at"]})
        print(platform, key, out["http_status"], row.get("handle_now"), row.get("platform_id"))
        time.sleep(PAUSE_SECONDS)
    for node, platform, post_id in POST_PROBES:
        if platform not in only:
            continue
        out, row = POST_PROBERS[platform](post_id)
        out["retrieved_at"] = now_iso()
        raw = save_raw(platform, f"post_{post_id}", out)
        rows.append({"node": node, "platform": platform, "probe_type": "post_2024", "probe_key": post_id,
                     "http_status": out["http_status"], **row, "raw_file": raw,
                     "retrieved_at": out["retrieved_at"]})
        print(platform, "post", post_id, out["http_status"], row.get("handle_now"), row.get("platform_id"))
        time.sleep(PAUSE_SECONDS)
    if only != set(PROBERS) and AUDIT_CSV.exists():
        with AUDIT_CSV.open(encoding="utf-8") as fh:
            kept = [r for r in csv.DictReader(fh) if r["platform"] not in only]
        rows = kept + rows
    AUDIT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {AUDIT_CSV.relative_to(ROOT)} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
