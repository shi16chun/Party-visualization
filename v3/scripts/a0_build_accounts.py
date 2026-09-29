#!/usr/bin/env python3
"""任务卡A0：由探测结果与核验判断生成账号总表。

输入：v3/data/audit/a0_probe.csv（a0_probe_accounts.py 的输出）
      本脚本内的 DECISIONS（每个节点×平台一条核验判断，证据见 v3/data/audit/a0_evidence.md）
输出：v3/data/accounts.csv（6个节点×4个平台=24行，不留空）
参数：无。数字字段（平台ID、创建日期、认证、粉丝数、现名）一律取自探测表，不手填；
      探测表中取不到的字段写明原因。
"""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE_CSV = ROOT / "v3" / "data" / "audit" / "a0_probe.csv"
OUT_CSV = ROOT / "v3" / "data" / "accounts.csv"

NODES = {
    "DNC": ("民主党", "党组织"),
    "Kamala HQ": ("民主党", "竞选团队"),
    "Kamala Harris": ("民主党", "候选人个人"),
    "RNC": ("共和党", "党组织"),
    "Team Trump": ("共和党", "竞选团队"),
    "Donald J. Trump": ("共和党", "候选人个人"),
}
PLATFORMS = ["youtube", "tiktok", "x", "truthsocial"]

TS_BLOCKED = "未取得（Truth Social接口被Cloudflare拦截）"
NA = "无"

# status 取值：存在 / 存在但窗口期无发布 / 窗口期内无可核实的官方账号 / 未发现官方账号
# active_in_window 取值：是 / 否 / 未核实
# probe：对应 a0_probe.csv 中账号探测行的 probe_key；None 表示无探测行，字段按 manual 填写
DECISIONS = [
    # ---------------- DNC ----------------
    dict(node="DNC", platform="youtube", status="存在", probe="UClkO4MArT2WKWj32YDD_-Ew",
         handle_2024="@TheDemocrats（未见改名证据）", active="是",
         window_evidence="旧稿数据窗口期Shorts 11条，如 iyxa3eCv44U（2024-08-20）",
         evidence_url="https://www.youtube.com/channel/UClkO4MArT2WKWj32YDD_-Ew",
         notes="频道名 The Democrats"),
    dict(node="DNC", platform="tiktok", status="存在", probe="democrats",
         handle_2024="待核（现名@democrats）", active="是",
         window_evidence="视频 7406055642676464939（2024-08-22，民主党全国代表大会）现归属该账号",
         evidence_url="https://www.tiktok.com/@democrats ; https://www.tiktok.com/@democrats/video/7406055642676464939",
         notes="大纲所列@thedemocrats现为无关个人账号（ID 7401714093455377454，简介非党组织）；官方账号为@democrats"),
    dict(node="DNC", platform="x", status="存在", probe="TheDemocrats",
         handle_2024="@TheDemocrats", active="是",
         window_evidence="帖子 1833680183540191305（2024-09-11）现归属该账号",
         evidence_url="https://x.com/TheDemocrats ; https://x.com/TheDemocrats/status/1833680183540191305",
         notes="@DNC为另一账号（ID 722793491059769344，9条帖子），不纳入"),
    dict(node="DNC", platform="truthsocial", status="未发现官方账号", probe=None,
         handle_2024=NA, active="否", window_evidence=NA,
         evidence_url="检索未见DNC开设Truth Social账号的报道或主页，见a0_evidence.md",
         notes="接口被拦截，无法直接查询；依检索结果判断", manual=dict(handle=NA, platform_id=NA, created=NA, verified=NA, followers=NA)),
    # ---------------- RNC ----------------
    dict(node="RNC", platform="youtube", status="存在", probe="UC3o7kbpTUQ5-0WTMIp8sVwA",
         handle_2024="待核（现名@Republicans）", active="是",
         window_evidence="旧稿数据窗口期Shorts 163条，如 qGd4-MKK5_s（2024-07-24）",
         evidence_url="https://www.youtube.com/channel/UC3o7kbpTUQ5-0WTMIp8sVwA",
         notes="频道名 GOP"),
    dict(node="RNC", platform="tiktok", status="窗口期内无可核实的官方账号", probe="gop",
         handle_2024="@gop（窗口期内是否发布无法核实）", active="否（未见窗口期发布）",
         window_evidence="RNC官方TikTok @Republicans 于2026年2月开设（Fox News、The Hill报道）",
         evidence_url="https://thehill.com/homenews/campaign/5726555-republican-party-tiktok-account/ ; https://www.tiktok.com/@republicans",
         notes="@gop账号ID编码的注册时间为2024-09-24，页面createTime为2026-01-07（与@republicans同日），已认证、现存0条视频，窗口期内是否发布过无法核实（待A5）；RNC现官方账号@republicans ID 7592735461091083278 注册于2026-01-07"),
    dict(node="RNC", platform="x", status="存在", probe="Republicans",
         handle_2024="@GOP（2026年改名@Republicans）", active="未核实",
         window_evidence="2024-05-20帖子 1792584647336931731、1792600850860327031 当时链接为x.com/GOP，现归属ID 11134252；窗口期帖子待A3",
         evidence_url="https://x.com/Republicans ; https://gop.com/commentary/palm-beach-playbook-may-20-2024/",
         notes="现@GOP为2026-04-20新注册账号（ID 2046223166461136896），不是2024年的账号；@RNC（ID 529648439）现已无帖子"),
    dict(node="RNC", platform="truthsocial", status="存在", probe=None,
         handle_2024="@RNC（依检索结果）", active="未核实",
         window_evidence="待A4",
         evidence_url="https://truthsocial.com/@RNC",
         notes="检索结果显示@RNC主页存在；接口被拦截，ID与创建日期未取得；是否另有@GOP账号未核实",
         manual=dict(handle="RNC", platform_id=TS_BLOCKED, created=TS_BLOCKED, verified=TS_BLOCKED, followers=TS_BLOCKED)),
    # ---------------- Kamala HQ ----------------
    dict(node="Kamala HQ", platform="youtube", status="存在", probe="headquarters",
         handle_2024="待核（现名@Headquarters）", active="是",
         window_evidence="视频 GsXS8WudinM（2024-10-26）、w_yGrsxNprA（2024-09-24）；频道内有2024年1月起的Biden时期内容",
         evidence_url="https://www.youtube.com/channel/UCnniIiQ9zAOjTcnct0xccig",
         notes="据内容判断为Biden-Harris HQ频道改名而来；页面未见认证标记、订阅1千余，是否官方频道需你确认；视频日期取自限流前的yt-dlp输出"),
    dict(node="Kamala HQ", platform="tiktok", status="存在", probe="headquarters",
         handle_2024="@kamalahq（原@bidenhq）", active="是",
         window_evidence="视频 7400033789335948575（2024-08-06）、7431356795391692074（2024-10-30）现归属该账号",
         evidence_url="https://www.tiktok.com/@headquarters ; https://www.cnn.com/2026/02/05/politics/kamala-hq-account-kamala-harris",
         notes="2026年2月改名Headquarters；现@kamalahq为无关新账号（ID 7576764299815027743）"),
    dict(node="Kamala HQ", platform="x", status="存在", probe="HQNewsNow",
         handle_2024="@KamalaHQ（原Biden-Harris HQ）", active="是",
         window_evidence="帖子 1815212766912803099（2024-07-22）、1834237601659703754（2024-09-12）现归属该账号",
         evidence_url="https://x.com/HQNewsNow ; https://www.cnn.com/2026/02/05/politics/kamala-hq-account-kamala-harris",
         notes="2026年2月改名@headquarters_67，后再改名@HQNewsNow；现@headquarters_67为无关账号"),
    dict(node="Kamala HQ", platform="truthsocial", status="存在", probe=None,
         handle_2024="@KamalaHQ（原@BidenHQ，2023年10月开设）", active="是",
         window_evidence="Truth Social官方账号2024-07-23发帖欢迎@KamalaHQ；Newsweek报道该账号选举期间每隔几天发帖",
         evidence_url="https://www.newsweek.com/kamala-harris-campaign-account-truth-social-1969556 ; https://www.washingtonexaminer.com/news/campaigns/presidential/3096248/truth-social-welcomes-harris-campaign/",
         notes="大纲原写无，核验后更正；现名与ID未取得（接口被拦截）",
         manual=dict(handle="待核（2024年为KamalaHQ）", platform_id=TS_BLOCKED, created="2023-10（据Forbes报道）", verified=TS_BLOCKED, followers=TS_BLOCKED)),
    # ---------------- Kamala Harris ----------------
    dict(node="Kamala Harris", platform="youtube", status="存在", probe="UC0XBsJpPhOLg0k4x9ZwrWzw",
         handle_2024="@kamalaharris（未见改名证据）", active="是",
         window_evidence="旧稿数据窗口期Shorts 156条，如 f6hcPwHIGc0（2024-07-23）",
         evidence_url="https://www.youtube.com/channel/UC0XBsJpPhOLg0k4x9ZwrWzw", notes=""),
    dict(node="Kamala Harris", platform="tiktok", status="存在", probe="kamalaharris",
         handle_2024="@kamalaharris", active="是",
         window_evidence="视频 7395695233276595487（2024-07-25）、7426486234593217838（2024-10-16）现归属该账号",
         evidence_url="https://www.tiktok.com/@kamalaharris", notes="账号注册于2024-07-23"),
    dict(node="Kamala Harris", platform="x", status="存在", probe="KamalaHarris",
         handle_2024="@KamalaHarris", active="是",
         window_evidence="帖子 1851815659144872236（2024-10-31）现归属该账号",
         evidence_url="https://x.com/KamalaHarris", notes="副总统官方账号@VP不纳入"),
    dict(node="Kamala Harris", platform="truthsocial", status="未发现官方账号", probe=None,
         handle_2024=NA, active="否", window_evidence=NA,
         evidence_url="检索未见哈里斯个人Truth Social账号，见a0_evidence.md",
         notes="接口被拦截，无法直接查询；依检索结果判断",
         manual=dict(handle=NA, platform_id=NA, created=NA, verified=NA, followers=NA)),
    # ---------------- Team Trump ----------------
    dict(node="Team Trump", platform="youtube", status="存在但窗口期无发布", probe="TeamTrump",
         handle_2024="@teamtrump", active="否",
         window_evidence="频道最新视频 vST61W4bGm8 发布于2016-11-06，共23条，均为2016年竞选内容",
         evidence_url="https://www.youtube.com/channel/UCbElcfNJQJHYiNoaV8F7E5g",
         notes="2024年特朗普竞选的YouTube发布走Donald J Trump频道（@DonaldJTrumpforPresident）；视频日期取自限流前的yt-dlp输出"),
    dict(node="Team Trump", platform="tiktok", status="存在", probe="teamtrump",
         handle_2024="@teamtrump", active="是",
         window_evidence="视频 7433202628072394030（2024-11-03）现归属该账号",
         evidence_url="https://www.tiktok.com/@teamtrump", notes="账号注册于2024-05-04"),
    dict(node="Team Trump", platform="x", status="存在", probe="TeamTrump",
         handle_2024="@TeamTrump", active="是",
         window_evidence="帖子 1835314099757916355（2024-09-15）现归属该账号",
         evidence_url="https://x.com/TeamTrump", notes="竞选快速回应账号@TrumpWarRoom另存，是否纳入待你决定"),
    dict(node="Team Trump", platform="truthsocial", status="存在", probe=None,
         handle_2024="@TeamTrump（依检索结果）", active="未核实", window_evidence="待A4",
         evidence_url="https://truthsocial.com/@TeamTrump",
         notes="检索结果显示主页存在；接口被拦截",
         manual=dict(handle="TeamTrump", platform_id=TS_BLOCKED, created=TS_BLOCKED, verified=TS_BLOCKED, followers=TS_BLOCKED)),
    # ---------------- Donald J. Trump ----------------
    dict(node="Donald J. Trump", platform="youtube", status="存在", probe="UCAql2DyGU2un1Ei2nMYsqOA",
         handle_2024="待核（现名@DonaldJTrumpforPresident）", active="是",
         window_evidence="旧稿数据窗口期Shorts 33条，如 -U3fvlYkQa4（2024-08-20）",
         evidence_url="https://www.youtube.com/channel/UCAql2DyGU2un1Ei2nMYsqOA",
         notes="频道名Donald J Trump，handle显示为竞选频道；个人节点与竞选团队节点在YouTube上合一，需你决定归属"),
    dict(node="Donald J. Trump", platform="tiktok", status="存在", probe="realdonaldtrump",
         handle_2024="@realdonaldtrump", active="是",
         window_evidence="视频 7403175874607975710（2024-08-15）、7427237451954965791（2024-10-18）现归属该账号",
         evidence_url="https://www.tiktok.com/@realdonaldtrump", notes="账号注册于2024-05-24，2024-06-01首发"),
    dict(node="Donald J. Trump", platform="x", status="存在", probe="realDonaldTrump",
         handle_2024="@realDonaldTrump", active="是",
         window_evidence="帖子 1823035759655264697（2024-08-12）现归属该账号；此前约一年未在X发帖",
         evidence_url="https://x.com/realDonaldTrump ; https://variety.com/2024/digital/news/donald-trump-returns-x-twitter-1236104163/",
         notes="窗口期内X发帖从8月12日开始"),
    dict(node="Donald J. Trump", platform="truthsocial", status="存在", probe=None,
         handle_2024="@realDonaldTrump", active="是", window_evidence="个人发布主阵地，窗口期帖子待A4",
         evidence_url="https://truthsocial.com/@realDonaldTrump",
         notes="接口被拦截，ID与创建日期未取得",
         manual=dict(handle="realDonaldTrump", platform_id=TS_BLOCKED, created=TS_BLOCKED, verified=TS_BLOCKED, followers=TS_BLOCKED)),
]

FIELDS = ["node", "camp", "platform", "handle", "platform_id", "created", "verified", "evidence_url",
          "checked_on", "role", "status", "handle_2024", "active_in_window", "window_evidence",
          "followers_now", "display_name_now", "notes"]


def load_probes() -> tuple[dict, dict]:
    accounts, posts = {}, {}
    with PROBE_CSV.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["probe_type"] == "post_2024":
                posts[(row["platform"], row["probe_key"])] = row
            else:
                accounts[(row["platform"], row["probe_key"])] = row
    return accounts, posts


def main() -> None:
    accounts, posts = load_probes()
    seen = set()
    out = []
    for d in DECISIONS:
        camp, role = NODES[d["node"]]
        key = (d["node"], d["platform"])
        assert key not in seen, key
        seen.add(key)
        if d["probe"]:
            p = accounts[(d["platform"], d["probe"])]
            assert p["http_status"] == "200" and p["platform_id"], (d["platform"], d["probe"])
            row = dict(handle=p["handle_now"].lstrip("@"), platform_id=p["platform_id"], created=p["created"],
                       verified=p["verified"], followers=p["followers_now"], display_name=p["display_name"],
                       checked_on=p["retrieved_at"][:10])
        else:
            m = d["manual"]
            row = dict(handle=m["handle"], platform_id=m["platform_id"], created=m["created"],
                       verified=m["verified"], followers=m["followers"], display_name=NA,
                       checked_on="2026-09-29")
        out.append({
            "node": d["node"], "camp": camp, "platform": d["platform"], "handle": row["handle"],
            "platform_id": row["platform_id"], "created": row["created"], "verified": row["verified"],
            "evidence_url": d["evidence_url"], "checked_on": row["checked_on"], "role": role,
            "status": d["status"], "handle_2024": d["handle_2024"], "active_in_window": d["active"],
            "window_evidence": d["window_evidence"], "followers_now": row["followers"],
            "display_name_now": row["display_name"], "notes": d["notes"] or NA,
        })
    expected = {(n, p) for n in NODES for p in PLATFORMS}
    missing = expected - seen
    assert not missing, f"缺少节点×平台：{missing}"
    for r in out:
        blanks = [k for k in FIELDS if r[k] in ("", None)]
        assert not blanks, (r["node"], r["platform"], blanks)
    order = {n: i for i, n in enumerate(NODES)}
    out.sort(key=lambda r: (order[r["node"]], PLATFORMS.index(r["platform"])))
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(out)
    print(f"wrote {OUT_CSV.relative_to(ROOT)} ({len(out)} rows)")


if __name__ == "__main__":
    main()
