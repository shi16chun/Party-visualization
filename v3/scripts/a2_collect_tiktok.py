#!/usr/bin/env python3
"""任务卡A2：TikTok采集。

用法：
  python v3/scripts/a2_collect_tiktok.py list   [--nodes democrats,kamalaharris] [--profile-dir DIR] [--headless] [--chrome-path PATH]
  python v3/scripts/a2_collect_tiktok.py detail [--nodes ...] [--ids-file FILE]
  python v3/scripts/a2_collect_tiktok.py build

三步分工：
  list    用浏览器打开账号主页，模拟手机访问并持续下滑，截取页面加载的视频列表接口返回，
          直到列表早于窗口起点或没有更多内容。本步骤在作者本地电脑运行（云端环境被TikTok拦截）。
          浏览器窗口默认可见；出现验证码或登录提示时手动处理，脚本会等待。
          --profile-dir 指定一个本地文件夹保存浏览器登录状态，在窗口中登录TikTok一次后，后续运行沿用。
          抓取只读取公开页面上的视频元数据，不采集评论与用户信息。
  detail  逐条读取视频页，取得单条视频的完整元数据。用于补全、核对列表结果，云端与本地均可运行。
  build   合并为窗口期总表，并生成审计表。

输入：v3/data/accounts.csv（A0产出，取TikTok上in_scope为“纳入”的账号）
输出：
  v3/data/raw/tiktok/<handle>__list.jsonl     列表接口返回的逐条视频（原样保存，附抓取时间）
  v3/data/raw/tiktok/<handle>__list_log.jsonl 每一页列表请求的状态
  v3/data/raw/tiktok/<handle>__detail.jsonl   单条视频页解析结果
  v3/data/raw/tiktok/<handle>.jsonl           窗口期逐条记录（合并后）
  v3/data/processed/tiktok_window.csv         窗口期总表
  v3/data/audit/tiktok_pull_log.csv           每个账号每一步的拉取日志
参数：窗口按美国东部时间计，2024-07-21 00:00 至 2024-11-05 23:59:59，与A1一致。无随机过程。

本地运行前的准备（Windows命令行）：
  pip install playwright curl_cffi tzdata
  python -m playwright install chromium
TikTok公开页面给出的播放、点赞、评论、分享数为4位有效数字的近似值（收藏数为精确值），表中照原样记录。
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "v3" / "data" / "raw" / "tiktok"
AUDIT = ROOT / "v3" / "data" / "audit"
PROCESSED = ROOT / "v3" / "data" / "processed"
ACCOUNTS = ROOT / "v3" / "data" / "accounts.csv"

ET = ZoneInfo("America/New_York")
WINDOW_START = datetime(2024, 7, 21, 0, 0, 0, tzinfo=ET)
WINDOW_END = datetime(2024, 11, 5, 23, 59, 59, tzinfo=ET)
START_TS = int(WINDOW_START.timestamp())
END_TS = int(WINDOW_END.timestamp())
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_accounts(only: set[str] | None) -> list[dict]:
    out = []
    with ACCOUNTS.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["platform"] == "tiktok" and r["in_scope"] == "纳入" and (not only or r["handle"] in only):
                out.append({"node": r["node"], "camp": r["camp"], "role": r["role"], "handle": r["handle"],
                            "user_id": r["platform_id"]})
    return out


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def append_log(rows: list[dict]) -> None:
    path = AUDIT / "tiktok_pull_log.csv"
    fields = ["handle", "step", "items", "in_window", "errors", "detail", "retrieved_at"]
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        if new:
            w.writeheader()
        w.writerows(rows)


# ------------------------------------------------------------------ list
async def list_account(acc: dict, headless: bool, chrome_path: str | None, max_scrolls: int,
                       profile_dir: str | None = None) -> None:
    from playwright.async_api import async_playwright

    RAW.mkdir(parents=True, exist_ok=True)
    items: dict[str, dict] = {r["id"]: r for r in read_jsonl(RAW / f"{acc['handle']}__list.jsonl")}
    page_log: list[dict] = []
    started = now_iso()

    async with async_playwright() as p:
        launch = {"headless": headless, "args": ["--disable-blink-features=AutomationControlled"]}
        if chrome_path:
            launch["executable_path"] = chrome_path
        if os.environ.get("HTTPS_PROXY"):
            launch["proxy"] = {"server": os.environ["HTTPS_PROXY"]}
        device = {k: v for k, v in p.devices["iPhone 13"].items() if k != "default_browser_type"}
        if profile_dir:
            ctx = await p.chromium.launch_persistent_context(profile_dir, **launch, **device)
            browser = ctx
        else:
            browser = await p.chromium.launch(**launch)
            ctx = await browser.new_context(**device)
        page = await ctx.new_page()

        async def on_response(resp):
            if "/api/post/item_list" not in resp.url:
                return
            entry = {"status": resp.status, "retrieved_at": now_iso()}
            try:
                data = json.loads(await resp.body())
                lst = data.get("itemList") or []
                entry.update({"n": len(lst), "hasMore": data.get("hasMore"), "cursor": data.get("cursor")})
                for it in lst:
                    it["_retrieved_at"] = entry["retrieved_at"]
                    items[it["id"]] = it
            except Exception as exc:  # 空返回即被拦截
                entry["error"] = f"{type(exc).__name__}: {str(exc)[:80]}"
            page_log.append(entry)

        page.on("response", on_response)
        await page.goto(f"https://www.tiktok.com/@{acc['handle']}", wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(6000)
        if not headless:
            print(f"[{acc['handle']}] 浏览器已打开。如出现验证码或登录提示，请在窗口中手动完成；脚本最多等待60秒。")
        for _ in range(12):
            if any(e.get("n") for e in page_log):
                break
            try:
                await page.get_by_role("button", name="Refresh").first.click(timeout=3000)
            except Exception:
                pass
            await page.wait_for_timeout(5000)

        stall = 0
        for _ in range(max_scrolls):
            before = len(items)
            await page.evaluate("window.scrollBy(0, 3000)")
            await page.mouse.wheel(0, 3000)
            await page.wait_for_timeout(2500)
            unpinned = [int(v["createTime"]) for v in items.values() if not v.get("isPinnedItem")]
            if unpinned and min(unpinned) < START_TS - 86400:
                break  # 已早于窗口起点
            if page_log and page_log[-1].get("hasMore") is False:
                break
            stall = stall + 1 if len(items) == before else 0
            if stall >= 10:
                break
        await browser.close()

    with (RAW / f"{acc['handle']}__list.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for it in sorted(items.values(), key=lambda v: -int(v["createTime"])):
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    with (RAW / f"{acc['handle']}__list_log.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
        for e in page_log:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    wrong_author = sum(1 for v in items.values() if (v.get("author") or {}).get("id") not in (None, acc["user_id"]))
    in_win = sum(1 for v in items.values() if START_TS <= int(v["createTime"]) <= END_TS)
    errs = sum(1 for e in page_log if e.get("error"))
    oldest = min((int(v["createTime"]) for v in items.values()), default=None)
    detail = (f"pages={len(page_log)} blocked_pages={errs} wrong_author={wrong_author} "
              f"oldest={datetime.fromtimestamp(oldest, timezone.utc).date() if oldest else None}")
    append_log([{"handle": acc["handle"], "step": "list", "items": len(items), "in_window": in_win,
                 "errors": errs, "detail": detail, "retrieved_at": started}])
    print(acc["handle"], "items", len(items), "in_window", in_win, detail)


# ------------------------------------------------------------------ detail
def fetch_detail(video_id: str) -> dict:
    from curl_cffi import requests

    url = f"https://www.tiktok.com/@_/video/{video_id}"
    for attempt in range(3):
        try:
            resp = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
                                impersonate="chrome", timeout=40)
            m = re.search(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', resp.text, re.S)
            scope = json.loads(m.group(1)).get("__DEFAULT_SCOPE__", {}) if m else {}
            det = scope.get("webapp.video-detail", {})
            item = (det.get("itemInfo") or {}).get("itemStruct")
            if item:
                item["_retrieved_at"] = now_iso()
                return item
            last = {"id": video_id, "error": f"http {resp.status_code} statusCode {det.get('statusCode')} {det.get('statusMsg')}"}
        except Exception as exc:
            last = {"id": video_id, "error": f"{type(exc).__name__}: {str(exc)[:120]}"}
        time.sleep(2 * (attempt + 1))
    last["_retrieved_at"] = now_iso()
    return last


def step_detail(accounts: list[dict], ids_file: str | None) -> None:
    extra = []
    if ids_file:
        extra = [x.strip() for x in Path(ids_file).read_text(encoding="utf-8").split() if x.strip()]
    for acc in accounts:
        listed = [r["id"] for r in read_jsonl(RAW / f"{acc['handle']}__list.jsonl")
                  if START_TS - 86400 <= int(r["createTime"]) <= END_TS + 86400]
        ids = sorted(set(listed) | set(extra)) if not ids_file else extra
        done = {r["id"]: r for r in read_jsonl(RAW / f"{acc['handle']}__detail.jsonl") if not r.get("error")}
        started, out, errs = now_iso(), [], 0
        for vid in ids:
            rec = done.get(vid) or fetch_detail(vid)
            if rec.get("error"):
                errs += 1
            elif (rec.get("author") or {}).get("id") != acc["user_id"]:
                continue  # 指定ID清单时，只保留属于该账号的视频
            out.append(rec)
            time.sleep(1.0)
        with (RAW / f"{acc['handle']}__detail.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
            for r in out:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        append_log([{"handle": acc["handle"], "step": "detail", "items": len(out) - errs, "in_window": "",
                     "errors": errs, "detail": f"{len(ids)} ids requested", "retrieved_at": started}])
        print(acc["handle"], "detail", len(out), "errors", errs)


# ------------------------------------------------------------------ build
def flatten(it: dict, source: str) -> dict:
    st = it.get("stats") or {}
    st2 = it.get("statsV2") or {}
    vid = it.get("video") or {}
    music = it.get("music") or {}
    ct = int(it["createTime"])
    ts = datetime.fromtimestamp(ct, timezone.utc)
    return {
        "post_id": it["id"], "published_at_utc": ts.isoformat(), "date_et": ts.astimezone(ET).date().isoformat(),
        "type": "image" if it.get("imagePost") else "video",
        "duration": vid.get("duration"), "desc": it.get("desc"),
        "views_now": st2.get("playCount", st.get("playCount")), "likes_now": st2.get("diggCount", st.get("diggCount")),
        "comments_now": st2.get("commentCount", st.get("commentCount")),
        "shares_now": st2.get("shareCount", st.get("shareCount")),
        "collects_now": st2.get("collectCount", st.get("collectCount")),
        "is_pinned": bool(it.get("isPinnedItem")), "is_ad": bool(it.get("isAd")),
        "music_title": music.get("title"), "music_original": music.get("original"),
        "author_id": (it.get("author") or {}).get("id"),
        "source": source, "retrieved_at": it.get("_retrieved_at"),
    }


def step_build(accounts: list[dict]) -> None:
    rows = []
    for acc in accounts:
        merged: dict[str, dict] = {}
        for it in read_jsonl(RAW / f"{acc['handle']}__list.jsonl"):
            merged[it["id"]] = flatten(it, "list")
        for it in read_jsonl(RAW / f"{acc['handle']}__detail.jsonl"):
            if not it.get("error"):
                merged[it["id"]] = flatten(it, "detail")  # 单条视频页更新，覆盖列表值
        node_rows = []
        for r in merged.values():
            ts = int(datetime.fromisoformat(r["published_at_utc"]).timestamp())
            if START_TS <= ts <= END_TS and r["author_id"] == acc["user_id"]:
                r.update({"node": acc["node"], "camp": acc["camp"], "role": acc["role"], "platform": "tiktok",
                          "handle": acc["handle"], "url": f"https://www.tiktok.com/@{acc['handle']}/video/{r['post_id']}"})
                node_rows.append(r)
        with (RAW / f"{acc['handle']}.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
            for r in sorted(node_rows, key=lambda x: x["published_at_utc"]):
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        rows.extend(node_rows)
        print(acc["handle"], "window", len(node_rows))
    fields = ["node", "camp", "role", "platform", "handle", "post_id", "published_at_utc", "date_et", "type",
              "duration", "desc", "views_now", "likes_now", "comments_now", "shares_now", "collects_now",
              "is_pinned", "is_ad", "music_title", "music_original", "url", "source", "retrieved_at"]
    PROCESSED.mkdir(parents=True, exist_ok=True)
    with (PROCESSED / "tiktok_window.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda x: (x["handle"], x["published_at_utc"])))
    print("tiktok_window.csv", len(rows))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("step", choices=["list", "detail", "build"])
    p.add_argument("--nodes", default="", help="账号handle，逗号分隔；默认全部纳入账号")
    p.add_argument("--headless", action="store_true", help="无界面运行（云端用；本地建议不加）")
    p.add_argument("--chrome-path", default=None, help="指定浏览器可执行文件路径")
    p.add_argument("--max-scrolls", type=int, default=400)
    p.add_argument("--profile-dir", default=None, help="保存浏览器登录状态的本地文件夹（本地运行时建议使用）")
    p.add_argument("--ids-file", default=None, help="detail步骤只读取此文件中的视频ID")
    a = p.parse_args()
    only = set(x for x in a.nodes.split(",") if x) or None
    accounts = load_accounts(only)
    if a.step == "list":
        for acc in accounts:
            asyncio.run(list_account(acc, a.headless, a.chrome_path, a.max_scrolls, a.profile_dir))
    elif a.step == "detail":
        step_detail(accounts, a.ids_file)
    else:
        step_build(load_accounts(None))


if __name__ == "__main__":
    main()
