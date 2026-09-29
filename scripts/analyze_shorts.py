#!/usr/bin/env python3
"""Reproducible descriptive, lexical-signal, and association analyses."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import statsmodels.formula.api as smf
from scipy.stats import fisher_exact, mannwhitneyu


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed" / "youtube_shorts_2024_general_election.csv"
RESULTS = ROOT / "results"
FIGURES = RESULTS / "figures"

ACCOUNT_ORDER = ["dnc", "harris", "rnc", "trump"]
ACCOUNT_LABELS = {
    "dnc": "DNC",
    "harris": "Harris",
    "rnc": "RNC",
    "trump": "Trump",
}


def contains_any(text: str, terms: list[str]) -> bool:
    return any(re.search(term, text, flags=re.IGNORECASE) for term in terms)


OPPONENT_TERMS = {
    "Democratic": [
        r"\bdonald trump\b",
        r"\btrump(?:'s|s)?\b",
        r"\bjd vance\b",
        r"\bvance(?:'s|s)?\b",
        r"\bmaga\b",
        r"\brepublicans?\b",
        r"\bgop\b",
        r"\bproject 2025\b",
    ],
    "Republican": [
        r"\bkamala harris\b",
        r"\bkamala(?:'s|s)?\b",
        r"\bharris(?:'s|s)?\b",
        r"\btim walz\b",
        r"\bwalz(?:'s|s)?\b",
        r"\bjoe biden\b",
        r"\bbiden(?:'s|s)?\b",
        r"\bdemocrats?\b",
        r"\bdnc\b",
        r"\bharris[-–—/]biden\b",
    ],
}

OWN_TERMS = {
    "Democratic": [
        r"\bkamala harris\b",
        r"\bkamala\b",
        r"\bharris(?:[-–—/]walz)?\b",
        r"\btim walz\b",
        r"\bwalz\b",
        r"\bdemocrats?\b",
        r"\bpresident biden\b",
        r"\bvice president\b",
    ],
    "Republican": [
        r"\bdonald (?:j\.? )?trump\b",
        r"\bpresident trump\b",
        r"\btrump\b",
        r"\bjd vance\b",
        r"\bvance\b",
        r"\brepublicans?\b",
        r"\bgop\b",
        r"\bmaga\b",
    ],
}

NEGATIVE_MARKERS = [
    r"\blie(?:s|d)?\b",
    r"\blying\b",
    r"\bliar\b",
    r"\bfraud\b",
    r"\bfail(?:ed|ure|ing)?\b",
    r"\bdangerous(?:ly)?\b",
    r"\bradical\b",
    r"\bsocialist\b",
    r"\bliberal\b",
    r"\bcrisis\b",
    r"\bdisaster\b",
    r"\bworst\b",
    r"\bcan(?:no|')t\b",
    r"\bwon(?:')t\b",
    r"\brefus(?:e|es|ed|ing)\b",
    r"\bhid(?:e|ing|den)\b",
    r"\bweak\b",
    r"\bincompetent\b",
    r"\bcorrupt\b",
    r"\bcriminals?\b",
    r"\bdestroy(?:s|ed|ing)?\b",
    r"\braise taxes\b",
    r"\btax increase\b",
    r"\bban(?:s|ned|ning)?\b",
    r"\btake your\b",
    r"\bnightmare\b",
    r"\bwrong\b",
    r"\bshame\b",
    r"\bopen border\b",
    r"\bborder czar\b",
    r"\binflation\b",
    r"\bunfit\b",
    r"\bfired\b",
    r"\bhypocrit(?:e|ical)\b",
    r"\bno one knows\b",
    r"\bdoesn(?:')t respect\b",
    r"\bcouldn(?:')t\b",
    r"\bhardship\b",
    r"\bdead\b",
    r"\braging\b",
    r"\bunhinged\b",
]

MOBILIZATION_TERMS = [
    r"\bvote\b",
    r"\bvoting\b",
    r"\bregister(?:ed)?\b",
    r"\bmake your plan\b",
    r"\bplan to vote\b",
    r"\bget out and vote\b",
    r"\bjoin us\b",
    r"\bdonate\b",
    r"\bchip in\b",
    r"\btext\b.{0,20}\bto\b",
    r"\blet(?:')s win\b",
    r"\btoo big to rig\b",
    r"\belection is going to be close\b",
]

POLICY_TERMS = [
    r"\beconom(?:y|ic|ics)\b",
    r"\bprices?\b",
    r"\bcosts?\b",
    r"\bwages?\b",
    r"\btax(?:es|ation)?\b",
    r"\btips\b",
    r"\bjobs?\b",
    r"\bbusiness\b",
    r"\bmedicare\b",
    r"\bsocial security\b",
    r"\bhealth(?:care| care)?\b",
    r"\babortion\b",
    r"\breproductive\b",
    r"\bfreedom\b",
    r"\bborder\b",
    r"\bimmigra(?:tion|nts?)\b",
    r"\bsanctuary cit(?:y|ies)\b",
    r"\bcrime\b",
    r"\bguns?\b",
    r"\bfracking\b",
    r"\benergy\b",
    r"\bdemocracy\b",
    r"\bcannabis\b",
    r"\blegalize\b",
    r"\bproject 2025\b",
    r"\bforeign policy\b",
    r"\bukraine\b",
    r"\bisrael\b",
]

PERSONAL_TERMS = [
    r"\bfamil(?:y|ies)\b",
    r"\bgrandpa\b",
    r"\bgranddaughter\b",
    r"\bgrandchildren\b",
    r"\bmom(?:ala)?\b",
    r"\bdad\b",
    r"\bhusband\b",
    r"\bdoug\b",
    r"\bbaby\b",
    r"\blove you\b",
    r"\bsweet treat\b",
    r"\bgreens\b",
    r"\btabasco\b",
    r"\bpretzels?\b",
    r"\brecipe\b",
    r"\bfood\b",
    r"\bdottie(?:')s\b",
    r"\bwholesome\b",
]

ENDORSEMENT_TERMS = [
    r"\bendorse(?:s|d|ment)?\b",
    r"\bbacks?\b",
    r"\bsupport(?:s|ed)?\b",
    r"\blisten to\b",
    r"\bbarack obama\b",
    r"\bpresident obama\b",
    r"\bmichelle obama\b",
    r"\bmichelle\b",
    r"\bjennifer lopez\b",
    r"\bj lo\b",
    r"\bbruce springsteen\b",
    r"\banuel aa\b",
    r"\btulsi\b",
    r"\brfk\b",
]

HUMOR_TERMS = [
    r"\blol\b",
    r"\bmeme\b",
    r"\bjoke\b",
    r"\bbeing jd vance\b",
    r"\bmerry christmas kamala\b",
    r"\bthis is so rich\b",
    r"\bword salad\b",
    r"\braging\b",
]


def bh_adjust(p_values: list[float]) -> list[float]:
    n = len(p_values)
    order = np.argsort(p_values)
    adjusted = np.empty(n, dtype=float)
    running = 1.0
    for rank_from_end, index in enumerate(order[::-1], start=1):
        rank = n - rank_from_end + 1
        value = min(running, p_values[index] * n / rank)
        adjusted[index] = value
        running = value
    return adjusted.tolist()


def rank_biserial(u_stat: float, n1: int, n2: int) -> float:
    return 2 * u_stat / (n1 * n2) - 1


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["title"] = df["title"].fillna("")
    df["description"] = df["description"].fillna("")
    df["title_norm"] = (
        df["title"]
        .str.normalize("NFKC")
        .str.replace("’", "'", regex=False)
        .str.replace("–", "-", regex=False)
        .str.replace("—", "-", regex=False)
        .str.lower()
    )
    df["opponent_reference"] = [
        int(contains_any(text, OPPONENT_TERMS[party]))
        for text, party in zip(df["title_norm"], df["party"])
    ]
    df["own_reference"] = [
        int(contains_any(text, OWN_TERMS[party]))
        for text, party in zip(df["title_norm"], df["party"])
    ]
    df["negative_marker"] = df["title_norm"].map(lambda text: int(contains_any(text, NEGATIVE_MARKERS)))
    df["attack_signal"] = df["opponent_reference"] * df["negative_marker"]
    df["mobilization_signal"] = df["title_norm"].map(lambda text: int(contains_any(text, MOBILIZATION_TERMS)))
    df["policy_signal"] = df["title_norm"].map(lambda text: int(contains_any(text, POLICY_TERMS)))
    df["personal_signal"] = df["title_norm"].map(lambda text: int(contains_any(text, PERSONAL_TERMS)))
    df["endorsement_signal"] = df["title_norm"].map(lambda text: int(contains_any(text, ENDORSEMENT_TERMS)))
    df["humor_signal"] = df["title_norm"].map(lambda text: int(contains_any(text, HUMOR_TERMS)))
    df["first_person_signal"] = df["title_norm"].map(
        lambda text: int(bool(re.search(r"\b(?:i|i'm|i've|me|my|we|we're|our|us)\b", text)))
    )
    df["upload_date"] = pd.to_datetime(df["upload_date"])
    df["day_index"] = (df["upload_date"] - pd.Timestamp("2024-07-21")).dt.days
    df["week_start"] = df["upload_date"] - pd.to_timedelta(df["upload_date"].dt.weekday, unit="D")
    df["view_count"] = pd.to_numeric(df["view_count"], errors="coerce")
    df["like_count"] = pd.to_numeric(df["like_count"], errors="coerce")
    df["comment_count"] = pd.to_numeric(df["comment_count"], errors="coerce")
    df["duration_seconds"] = pd.to_numeric(df["duration_seconds"], errors="coerce")
    df["like_rate"] = df["like_count"] / df["view_count"]
    df["comment_rate"] = df["comment_count"] / df["view_count"]
    df["log_views"] = np.log1p(df["view_count"])
    eps = 0.5
    df["logit_like_rate"] = np.log((df["like_count"] + eps) / (df["view_count"] - df["like_count"] + eps))
    return df


def descriptive_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for account in ACCOUNT_ORDER:
        group = df[df["account_slug"] == account]
        rows.append(
            {
                "account_slug": account,
                "account": ACCOUNT_LABELS[account],
                "party": group["party"].iloc[0],
                "actor_type": group["actor_type"].iloc[0],
                "n": len(group),
                "posts_per_day": len(group) / 108,
                "duration_median": group["duration_seconds"].median(),
                "views_total": group["view_count"].sum(),
                "views_median": group["view_count"].median(),
                "views_q1": group["view_count"].quantile(0.25),
                "views_q3": group["view_count"].quantile(0.75),
                "likes_median": group["like_count"].median(),
                "like_rate_median": group["like_rate"].median(),
                "comment_rate_median": group["comment_rate"].median(),
            }
        )
    return pd.DataFrame(rows)


def signal_table(df: pd.DataFrame) -> pd.DataFrame:
    signals = [
        "opponent_reference",
        "attack_signal",
        "own_reference",
        "mobilization_signal",
        "policy_signal",
        "personal_signal",
        "endorsement_signal",
        "humor_signal",
        "first_person_signal",
    ]
    rows = []
    for account in ACCOUNT_ORDER:
        group = df[df["account_slug"] == account]
        for signal in signals:
            rows.append(
                {
                    "account_slug": account,
                    "account": ACCOUNT_LABELS[account],
                    "signal": signal,
                    "count": int(group[signal].sum()),
                    "n": len(group),
                    "proportion": group[signal].mean(),
                }
            )
    return pd.DataFrame(rows)


def comparison_tests(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    binary_vars = [
        "opponent_reference",
        "attack_signal",
        "mobilization_signal",
        "policy_signal",
        "personal_signal",
        "endorsement_signal",
        "first_person_signal",
    ]
    for party in ["Democratic", "Republican"]:
        sub = df[df["party"] == party]
        party_group = sub[sub["actor_type"] == "party"]
        candidate_group = sub[sub["actor_type"] == "candidate"]
        for variable in binary_vars:
            table = [
                [int(party_group[variable].sum()), int((1 - party_group[variable]).sum())],
                [int(candidate_group[variable].sum()), int((1 - candidate_group[variable]).sum())],
            ]
            odds_ratio, p_value = fisher_exact(table)
            rows.append(
                {
                    "party": party,
                    "variable": variable,
                    "test": "Fisher exact",
                    "party_account_value": party_group[variable].mean(),
                    "candidate_account_value": candidate_group[variable].mean(),
                    "effect": odds_ratio,
                    "p_value": p_value,
                }
            )
        for variable in ["view_count", "like_rate", "comment_rate"]:
            left = party_group[variable].dropna()
            right = candidate_group[variable].dropna()
            u_stat, p_value = mannwhitneyu(left, right, alternative="two-sided")
            rows.append(
                {
                    "party": party,
                    "variable": variable,
                    "test": "Mann-Whitney U",
                    "party_account_value": left.median(),
                    "candidate_account_value": right.median(),
                    "effect": rank_biserial(u_stat, len(left), len(right)),
                    "p_value": p_value,
                }
            )
    result = pd.DataFrame(rows)
    result["p_adjust_bh"] = bh_adjust(result["p_value"].tolist())
    return result


def regression_table(df: pd.DataFrame, outcome: str) -> tuple[pd.DataFrame, dict]:
    formula = (
        f"{outcome} ~ C(party) * C(actor_type) + opponent_reference + "
        "mobilization_signal + policy_signal + personal_signal + "
        "endorsement_signal + duration_seconds + day_index"
    )
    model = smf.ols(formula, data=df).fit(cov_type="HC3")
    conf = model.conf_int()
    table = pd.DataFrame(
        {
            "term": model.params.index,
            "coefficient": model.params.values,
            "robust_se": model.bse.values,
            "p_value": model.pvalues.values,
            "ci_low": conf[0].values,
            "ci_high": conf[1].values,
        }
    )
    if outcome == "log_views":
        table["multiplicative_factor"] = np.exp(table["coefficient"])
    summary = {
        "outcome": outcome,
        "n": int(model.nobs),
        "r_squared": model.rsquared,
        "adjusted_r_squared": model.rsquared_adj,
        "f_pvalue": model.f_pvalue,
        "formula": formula,
    }
    return table, summary


def make_figures(df: pd.DataFrame, descriptive: pd.DataFrame, signals: pd.DataFrame) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False
    sns.set_theme(style="whitegrid", font="Microsoft YaHei")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    colors = ["#3b82f6", "#60a5fa", "#ef4444", "#f87171"]
    axes[0].bar(descriptive["account"], descriptive["n"], color=colors)
    axes[0].set_title("样本期Shorts发布量")
    axes[0].set_ylabel("视频条数")
    for idx, value in enumerate(descriptive["n"]):
        axes[0].text(idx, value + 3, f"{int(value)}", ha="center", fontsize=10)

    axes[1].bar(descriptive["account"], descriptive["views_median"], color=colors)
    axes[1].set_yscale("log")
    axes[1].set_title("单条累计观看数中位数（对数坐标）")
    axes[1].set_ylabel("累计观看数")
    fig.tight_layout()
    fig.savefig(FIGURES / "figure1_output_and_attention.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    selected = [
        "opponent_reference",
        "attack_signal",
        "mobilization_signal",
        "policy_signal",
        "personal_signal",
        "endorsement_signal",
        "first_person_signal",
    ]
    labels = {
        "opponent_reference": "提及对手",
        "attack_signal": "攻击信号",
        "mobilization_signal": "动员信号",
        "policy_signal": "政策信号",
        "personal_signal": "私人/生活信号",
        "endorsement_signal": "背书信号",
        "first_person_signal": "第一人称",
    }
    heat = (
        signals[signals["signal"].isin(selected)]
        .pivot(index="account", columns="signal", values="proportion")
        .reindex(index=[ACCOUNT_LABELS[a] for a in ACCOUNT_ORDER], columns=selected)
    )
    heat.columns = [labels[col] for col in heat.columns]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    sns.heatmap(heat * 100, annot=True, fmt=".1f", cmap="YlOrRd", cbar_kws={"label": "%"}, ax=ax)
    ax.set_title("标题中的可复核传播信号（%）")
    ax.set_xlabel("")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(FIGURES / "figure2_lexical_signal_heatmap.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    weekly = (
        df.groupby(["week_start", "account_slug"]).size().rename("n").reset_index()
    )
    weekly.to_csv(RESULTS / "weekly_counts.csv", index=False, encoding="utf-8-sig")
    fig, ax = plt.subplots(figsize=(11, 4.8))
    for account, color in zip(ACCOUNT_ORDER, colors):
        group = weekly[weekly["account_slug"] == account]
        ax.plot(group["week_start"], group["n"], marker="o", label=ACCOUNT_LABELS[account], color=color)
    ax.set_title("竞选期官方Shorts周度发布节奏")
    ax.set_ylabel("视频条数")
    ax.set_xlabel("")
    ax.legend(ncol=4, frameon=False)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(FIGURES / "figure3_weekly_output.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(DATA, encoding="utf-8-sig")
    if df["video_id"].duplicated().any():
        raise ValueError("Duplicate video IDs found")
    if not df["upload_date"].between("2024-07-21", "2024-11-05").all():
        raise ValueError("Out-of-window rows found")
    df = enrich(df)

    coded_path = ROOT / "data" / "processed" / "youtube_shorts_coded.csv"
    df.to_csv(coded_path, index=False, encoding="utf-8-sig")

    descriptive = descriptive_table(df)
    signals = signal_table(df)
    tests = comparison_tests(df)
    reg_views, summary_views = regression_table(df, "log_views")
    reg_likes, summary_likes = regression_table(df, "logit_like_rate")

    descriptive.to_csv(RESULTS / "table1_descriptive.csv", index=False, encoding="utf-8-sig")
    signals.to_csv(RESULTS / "table2_text_signals.csv", index=False, encoding="utf-8-sig")
    tests.to_csv(RESULTS / "table3_comparison_tests.csv", index=False, encoding="utf-8-sig")
    reg_views.to_csv(RESULTS / "table4_regression_log_views.csv", index=False, encoding="utf-8-sig")
    reg_likes.to_csv(RESULTS / "table5_regression_like_rate.csv", index=False, encoding="utf-8-sig")

    top_cases = (
        df.sort_values(["account_slug", "view_count"], ascending=[True, False])
        .groupby("account_slug", group_keys=False)
        .head(10)
    )
    top_cases[
        [
            "account_slug",
            "upload_date",
            "video_id",
            "title",
            "view_count",
            "like_count",
            "comment_count",
            "opponent_reference",
            "attack_signal",
            "mobilization_signal",
            "policy_signal",
            "personal_signal",
            "endorsement_signal",
            "source_url",
        ]
    ].to_csv(RESULTS / "top_cases_by_account.csv", index=False, encoding="utf-8-sig")

    make_figures(df, descriptive, signals)

    summary = {
        "rows": len(df),
        "accounts": df.groupby("account_slug").size().to_dict(),
        "retrieval_time_min": df["retrieved_at_utc"].min(),
        "retrieval_time_max": df["retrieved_at_utc"].max(),
        "missing_comment_count": int(df["comment_count"].isna().sum()),
        "view_model": summary_views,
        "like_rate_model": summary_likes,
    }
    (RESULTS / "analysis_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
