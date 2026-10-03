#!/usr/bin/env python3
"""任务卡A3准备：从USC公开的2024大选X数据集中筛出本研究账号的帖子，评估覆盖率。

数据集：Balasubramanian, Zou, Narayana, You, Luceri & Ferrara，
  A Public Dataset Tracking Social Media Discourse about the 2024 U.S. Presidential Election on Twitter/X
  （arXiv:2411.00376），https://github.com/sinking8/x-24-us-election ，CC BY-NC-SA 4.0。
  按关键词收集，覆盖2024-05-01至2024-11-30，约4400万条，分881个数据块（每块约5万条）。

用法：python v3/scripts/a3_usc24_filter.py [--workers 4] [--limit N]
输入：数据块清单（由本脚本从仓库文件树读取，需先执行
      git clone --filter=blob:none --no-checkout --depth 1 https://github.com/sinking8/x-24-us-election
      到 /home/user/sinking8/x-24-us-election，或用 --tree-file 指定一份文件清单）
输出：
  v3/data/raw/x/usc24_matches.csv.gz   作者为本研究账号的全部帖子（数据集原字段，附来源数据块）
  v3/data/audit/x_usc24_chunks.csv     每个数据块的行数、日期范围、各账号命中数、处理状态
参数：账号按2024年的账号名匹配（数据集的username字段为抓取时的账号名），并以user字段中的数字ID复核。
      数据块逐个下载、筛选后即删除，不保留原始数据块。无随机过程。
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import re
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "v3" / "data" / "raw" / "x" / "usc24_matches.csv.gz"
LOG = ROOT / "v3" / "data" / "audit" / "x_usc24_chunks.csv"
REPO = Path("/home/user/sinking8/x-24-us-election")
RAW_URL = "https://raw.githubusercontent.com/sinking8/x-24-us-election/main/{}"

# 2024年的账号名 -> (节点, 数字ID)，数字ID来自A0核验
ACCOUNTS = {
    "thedemocrats": ("DNC", "14377605"),
    "gop": ("RNC", "11134252"),
    "kamalahq": ("Kamala HQ", "3315264553"),
    "kamalaharris": ("Kamala Harris", "30354991"),
    "teamtrump": ("Team Trump", "729676086632656900"),
    "trumpwarroom": ("Trump War Room", "1108472017144201216"),
    "realdonaldtrump": ("Donald J. Trump", "25073877"),
}
USER_ID_RE = re.compile(r"'id':\s*(\d+)")


def list_chunks(tree_file: str | None) -> list[str]:
    if tree_file:
        names = Path(tree_file).read_text(encoding="utf-8").split()
    else:
        names = subprocess.run(["git", "-C", str(REPO), "ls-tree", "-r", "--name-only", "HEAD"],
                               capture_output=True, text=True, check=True).stdout.split()
    return sorted([n for n in names if n.endswith(".csv.gz")], key=lambda x: [int(t) if t.isdigit() else t
                                                                              for t in re.split(r"(\d+)", x)])


def process(name: str) -> tuple[dict, list[dict]]:
    import pandas as pd
    from curl_cffi import requests

    log = {"chunk": name, "rows": "", "date_min": "", "date_max": "", "hits": 0, "status": ""}
    for h in ACCOUNTS:
        log[f"hit_{h}"] = 0
    data = None
    for attempt in range(4):
        try:
            resp = requests.get(RAW_URL.format(name), timeout=300)
            if resp.status_code == 200:
                data = resp.content
                break
            log["status"] = f"http {resp.status_code}"
        except Exception as exc:
            log["status"] = f"{type(exc).__name__}"
        time.sleep(3 * (attempt + 1))
    if data is None:
        return log, []
    try:
        df = pd.read_csv(io.BytesIO(data), compression="gzip", dtype=str, low_memory=False)
    except Exception as exc:
        log["status"] = f"parse error: {str(exc)[:80]}"
        return log, []
    log["rows"] = len(df)
    if "date" in df:
        log["date_min"], log["date_max"] = df["date"].min(), df["date"].max()
    uname = df["username"].fillna("").str.lower() if "username" in df else pd.Series([""] * len(df))
    hit = df[uname.isin(ACCOUNTS)].copy()
    rows = []
    for _, r in hit.iterrows():
        h = str(r["username"]).lower()
        m = USER_ID_RE.search(str(r.get("user", "")))
        uid = m.group(1) if m else ""
        rec = {k: ("" if pd.isna(v) else v) for k, v in r.items() if not str(k).startswith("Unnamed")}
        rec.update({"_handle_2024": h, "_node": ACCOUNTS[h][0], "_user_id_parsed": uid,
                    "_id_match": uid == ACCOUNTS[h][1], "_chunk": name})
        rows.append(rec)
        log[f"hit_{h}"] += 1
    log["hits"] = len(rows)
    log["status"] = "ok"
    return log, rows


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--tree-file", default=None)
    a = p.parse_args()
    chunks = list_chunks(a.tree_file)
    if a.limit:
        chunks = chunks[: a.limit]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    logs, matches = [], []
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(process, c): c for c in chunks}
        for i, f in enumerate(as_completed(futs), 1):
            log, rows = f.result()
            logs.append(log)
            matches.extend(rows)
            if i % 25 == 0 or i == len(chunks):
                print(f"{i}/{len(chunks)} chunks, matches so far {len(matches)}", flush=True)
    order = {c: i for i, c in enumerate(chunks)}
    logs.sort(key=lambda r: order[r["chunk"]])
    with LOG.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(logs[0].keys()))
        w.writeheader()
        w.writerows(logs)
    fields = sorted({k for r in matches for k in r}, key=lambda k: (k.startswith("_"), k))
    with gzip.open(OUT, "wt", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(sorted(matches, key=lambda r: (r["_handle_2024"], r.get("id", ""))))
    bad = sum(1 for l in logs if l["status"] != "ok")
    print(f"done: {len(chunks)} chunks, {bad} not ok, {len(matches)} matched rows -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
