#!/usr/bin/env python3
"""任务卡A3准备：评估USC 2024大选X数据集对本研究账号的覆盖程度。

输入：v3/data/raw/x/usc24_matches.csv.gz（a3_usc24_filter.py 的输出）
输出：v3/data/audit/x_usc24_coverage.csv
方法：
  1. 按帖子ID去重（同一帖子因匹配不同关键词被多次收录），每条保留一行。
  2. 帖子类型：retweetedTweet为True记转发，in_reply_to_status_id_str非空记回复，quotedTweet为True记引用，其余为原创。
  3. 覆盖率上限：user字段中的statusesCount是抓取时刻的账号累计发帖数，数据集未记录抓取时间，
     无法据此还原窗口期的发帖总数。但同一账号最大与最小statusesCount之差，是两次抓取之间实际
     新增的发帖数（含回复、转发，扣除删帖），必然不大于收集期（2024-05-01至11-30）内的发帖总数。
     因此 数据集收录的去重条数 / 该差值 是覆盖率的上限。
参数：窗口按美国东部时间计（2024-07-21至2024-11-05）。无随机过程。
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "v3" / "data" / "raw" / "x" / "usc24_matches.csv.gz"
OUT = ROOT / "v3" / "data" / "audit" / "x_usc24_coverage.csv"
STATUSES_RE = re.compile(r"'statusesCount':\s*(\d+)")


def kind(r: pd.Series) -> str:
    if str(r.get("retweetedTweet")) == "True":
        return "retweet"
    if str(r.get("in_reply_to_status_id_str")) not in ("", "nan", "None"):
        return "reply"
    if str(r.get("quotedTweet")) == "True":
        return "quote"
    return "original"


def main() -> None:
    m = pd.read_csv(SRC, dtype=str, low_memory=False)
    m["ts"] = pd.to_datetime(m["epoch"].astype(float), unit="s", utc=True)
    m["et"] = m["ts"].dt.tz_convert("America/New_York")
    m["statuses"] = m["user"].map(lambda u: int(x.group(1)) if (x := STATUSES_RE.search(str(u))) else None)
    m["post_id"] = m["url"].str.extract(r"/status/(\d+)")[0]
    m["kind"] = m.apply(kind, axis=1)
    uniq = m.drop_duplicates("post_id")
    win = uniq[(uniq["et"] >= "2024-07-21") & (uniq["et"] < "2024-11-06")]
    rows = []
    for h, g in m.groupby("_handle_2024"):
        u_all = uniq[uniq["_handle_2024"] == h]
        u_win = win[win["_handle_2024"] == h]
        delta = g["statuses"].max() - g["statuses"].min()
        kinds = u_win["kind"].value_counts()
        rows.append({
            "handle_2024": h, "node": g["_node"].iloc[0],
            "rows_with_duplicates": len(g), "unique_posts_all": len(u_all), "unique_posts_window": len(u_win),
            "window_original": int(kinds.get("original", 0)), "window_quote": int(kinds.get("quote", 0)),
            "window_reply": int(kinds.get("reply", 0)), "window_retweet": int(kinds.get("retweet", 0)),
            "window_days_with_posts": u_win["et"].dt.date.nunique(),
            "statuses_min": g["statuses"].min(), "statuses_max": g["statuses"].max(),
            "statuses_delta_lower_bound": delta,
            "coverage_upper_bound": round(len(u_all) / delta, 3) if delta > 0 else None,
        })
    out = pd.DataFrame(rows).sort_values("node")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
