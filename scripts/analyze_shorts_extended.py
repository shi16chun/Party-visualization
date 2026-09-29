#!/usr/bin/env python3
"""Extended quantitative battery for the 2024 party/candidate Shorts study.

Adds, on top of scripts/analyze_shorts.py (which must be run first so that
data/processed/youtube_shorts_coded.csv exists):

A. Production-structure test (camp-level candidate share, exact OR + CI).
B. Posting-cadence statistics (active days, Fano factor, dispersion test,
   longest gap, max daily output).
C. Enriched within-party contrasts: exact conditional ML odds ratios with
   exact CIs, risk differences with Newcombe score CIs, rank-biserial with
   stratified bootstrap CIs, median ratios with bootstrap CIs. BH q-values
   are recomputed over the identical 20-test family used in the base script
   (values match results/table3_comparison_tests.csv).
D. Formal party x role interaction (RQ3): within-party permutation test of
   the difference-in-differences of proportions, plus Haldane-corrected
   ratio-of-odds-ratios with Wald CI; BH within the 7-signal family.
E. Cumulative-view models: NB2 negative binomial (MLE alpha, HC1 robust SE,
   IRRs), Poisson QMLE (HC1), OLS log(1+views) (HC3), median (quantile)
   regression. party x role saturates the four accounts, i.e. account fixed
   effects; signal coefficients are within-account associations.
F. Like-rate models: fractional logit (Papke-Wooldridge, HC3) vs the base
   empirical-logit OLS.
G. Concentration of attention: Gini, top-3 and top-10% shares, camp-level
   candidate share of cumulative views with video-level bootstrap CI.
H. Title-style metrics (all-caps, exclamation, question, quotation, word
   count) with Fisher/Mann-Whitney tests, BH within the 10-test family.
I. Dictionary sensitivity: leave-one-term-out for the opponent and negative
   dictionaries on the four key Fisher contrasts.
J. Distinctive vocabulary (Monroe-Colaresi-Quinn log-odds, informative
   Dirichlet prior): RNC vs Harris, and pooled party vs candidate accounts.
K. Minimal detectable effect simulation for the DNC (n=11) attack contrast.

Outputs go to results/extended/ plus two publication-ready tables and one
forest figure used by the manuscript builder.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy.stats import chi2, fisher_exact, mannwhitneyu, nbinom
from scipy.stats.contingency import odds_ratio as exact_odds_ratio
from statsmodels.stats.proportion import confint_proportions_2indep, proportion_confint

ROOT = Path(__file__).resolve().parents[1]
CODED = ROOT / "data" / "processed" / "youtube_shorts_coded.csv"
RESULTS = ROOT / "results"
EXT = RESULTS / "extended"
FIGURES = RESULTS / "figures"

RNG = np.random.default_rng(20260825)
N_BOOT = 5000
N_PERM = 20000

ACCOUNT_ORDER = ["dnc", "harris", "rnc", "trump"]
ACCOUNT_LABELS = {"dnc": "DNC", "harris": "Harris", "rnc": "RNC", "trump": "Trump"}
SIGNALS = [
    "opponent_reference",
    "attack_signal",
    "mobilization_signal",
    "policy_signal",
    "personal_signal",
    "endorsement_signal",
    "first_person_signal",
]
SIGNAL_LABELS = {
    "opponent_reference": "对手指涉",
    "attack_signal": "攻击",
    "mobilization_signal": "动员",
    "policy_signal": "政策",
    "personal_signal": "私人／日常",
    "endorsement_signal": "背书",
    "first_person_signal": "第一人称",
}
WINDOW_DAYS = 108
WINDOW_START = pd.Timestamp("2024-07-21")


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


def gini(values: np.ndarray) -> float:
    v = np.sort(np.asarray(values, dtype=float))
    n = len(v)
    if n == 0 or v.sum() == 0:
        return float("nan")
    cum = np.cumsum(v)
    return float((n + 1 - 2 * (cum / cum[-1]).sum()) / n)


def load() -> pd.DataFrame:
    df = pd.read_csv(CODED, encoding="utf-8-sig")
    df["upload_date"] = pd.to_datetime(df["upload_date"])
    df["title"] = df["title"].fillna("")
    return df


# ---------------------------------------------------------------- A + G ----

def production_structure(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    tab = {}
    for party in ["Democratic", "Republican"]:
        sub = df[df["party"] == party]
        n_cand = int((sub["actor_type"] == "candidate").sum())
        n_party = int((sub["actor_type"] == "party").sum())
        share = n_cand / (n_cand + n_party)
        lo, hi = proportion_confint(n_cand, n_cand + n_party, method="wilson")
        tab[party] = (n_cand, n_party)
        rows.append(
            {
                "party": party,
                "candidate_posts": n_cand,
                "party_posts": n_party,
                "candidate_share": share,
                "share_ci_low": lo,
                "share_ci_high": hi,
            }
        )
    table = [[tab["Democratic"][0], tab["Democratic"][1]], [tab["Republican"][0], tab["Republican"][1]]]
    _, p = fisher_exact(table)
    res = exact_odds_ratio(table)
    ci = res.confidence_interval(0.95)
    out = pd.DataFrame(rows)
    out["structure_diff_or"] = res.statistic
    out["structure_diff_or_ci_low"] = ci.low
    out["structure_diff_or_ci_high"] = ci.high
    out["structure_diff_fisher_p"] = p
    return out


def cadence(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    all_days = pd.date_range(WINDOW_START, periods=WINDOW_DAYS, freq="D")
    for account in ACCOUNT_ORDER:
        g = df[df["account_slug"] == account]
        daily = g.groupby("upload_date").size().reindex(all_days, fill_value=0)
        counts = daily.to_numpy()
        mean = counts.mean()
        fano = counts.var(ddof=1) / mean if mean > 0 else float("nan")
        # chi-square dispersion test against Poisson
        stat = ((counts - mean) ** 2).sum() / mean if mean > 0 else float("nan")
        dof = WINDOW_DAYS - 1
        p_disp = 2 * min(chi2.cdf(stat, dof), chi2.sf(stat, dof)) if mean > 0 else float("nan")
        active = (counts > 0).sum()
        post_days = np.flatnonzero(counts > 0)
        gaps = np.diff(post_days) if len(post_days) > 1 else np.array([np.nan])
        edge_gaps = []
        if len(post_days):
            edge_gaps = [post_days[0], WINDOW_DAYS - 1 - post_days[-1]]
        longest_gap = np.nanmax(list(gaps - 1) + edge_gaps) if len(post_days) else WINDOW_DAYS
        rows.append(
            {
                "account_slug": account,
                "account": ACCOUNT_LABELS[account],
                "n": len(g),
                "active_days": int(active),
                "active_day_share": active / WINDOW_DAYS,
                "max_per_day": int(counts.max()),
                "daily_mean": mean,
                "fano_factor": fano,
                "dispersion_p_two_sided": p_disp,
                "longest_gap_days": int(longest_gap),
            }
        )
    return pd.DataFrame(rows)


def concentration(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for account in ACCOUNT_ORDER:
        v = df.loc[df["account_slug"] == account, "view_count"].to_numpy(dtype=float)
        v_sorted = np.sort(v)[::-1]
        top3 = v_sorted[:3].sum() / v.sum()
        k10 = max(1, int(math.ceil(len(v) * 0.10)))
        top10pct = v_sorted[:k10].sum() / v.sum()
        rows.append(
            {
                "account_slug": account,
                "account": ACCOUNT_LABELS[account],
                "gini_views": gini(v),
                "top3_share": top3,
                "top10pct_share": top10pct,
                "n_top10pct": k10,
            }
        )
    out = pd.DataFrame(rows)
    # camp-level candidate share of cumulative views + video-level bootstrap CI
    camp_rows = []
    for party, cand, porg in [("Democratic", "harris", "dnc"), ("Republican", "trump", "rnc")]:
        vc = df.loc[df["account_slug"] == cand, "view_count"].to_numpy(dtype=float)
        vp = df.loc[df["account_slug"] == porg, "view_count"].to_numpy(dtype=float)
        share = vc.sum() / (vc.sum() + vp.sum())
        boots = np.empty(N_BOOT)
        for b in range(N_BOOT):
            sc = RNG.choice(vc, size=len(vc), replace=True).sum()
            sp = RNG.choice(vp, size=len(vp), replace=True).sum()
            boots[b] = sc / (sc + sp)
        lo, hi = np.percentile(boots, [2.5, 97.5])
        camp_rows.append(
            {
                "party": party,
                "candidate_view_share": share,
                "ci_low": lo,
                "ci_high": hi,
            }
        )
    return out, pd.DataFrame(camp_rows)


# -------------------------------------------------------------------- C ----

def boot_rank_biserial(left: np.ndarray, right: np.ndarray) -> tuple[float, float, float]:
    u, _ = mannwhitneyu(left, right, alternative="two-sided")
    rb = 2 * u / (len(left) * len(right)) - 1
    boots = np.empty(N_BOOT)
    for b in range(N_BOOT):
        l = RNG.choice(left, len(left), replace=True)
        r = RNG.choice(right, len(right), replace=True)
        ub, _ = mannwhitneyu(l, r, alternative="two-sided")
        boots[b] = 2 * ub / (len(l) * len(r)) - 1
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return rb, lo, hi


def boot_median_ratio(num: np.ndarray, den: np.ndarray) -> tuple[float, float, float]:
    ratio = np.median(num) / np.median(den)
    boots = np.empty(N_BOOT)
    for b in range(N_BOOT):
        n = np.median(RNG.choice(num, len(num), replace=True))
        d = np.median(RNG.choice(den, len(den), replace=True))
        boots[b] = n / d if d > 0 else np.nan
    lo, hi = np.nanpercentile(boots, [2.5, 97.5])
    return ratio, lo, hi


def enriched_contrasts(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    p_values = []
    for party in ["Democratic", "Republican"]:
        sub = df[df["party"] == party]
        pg = sub[sub["actor_type"] == "party"]
        cg = sub[sub["actor_type"] == "candidate"]
        for variable in SIGNALS:
            a, b = int(pg[variable].sum()), int((1 - pg[variable]).sum())
            c, d = int(cg[variable].sum()), int((1 - cg[variable]).sum())
            _, p = fisher_exact([[a, b], [c, d]])
            res = exact_odds_ratio([[a, b], [c, d]])
            ci = res.confidence_interval(0.95)
            rd_ci = confint_proportions_2indep(a, a + b, c, c + d, method="newcomb", compare="diff")
            rows.append(
                {
                    "party": party,
                    "variable": variable,
                    "test": "Fisher exact",
                    "party_prop": a / (a + b),
                    "candidate_prop": c / (c + d),
                    "risk_diff": a / (a + b) - c / (c + d),
                    "rd_ci_low": rd_ci[0],
                    "rd_ci_high": rd_ci[1],
                    "odds_ratio_cmle": res.statistic,
                    "or_ci_low": ci.low,
                    "or_ci_high": ci.high,
                    "effect_rb": np.nan,
                    "rb_ci_low": np.nan,
                    "rb_ci_high": np.nan,
                    "median_ratio_cand_over_party": np.nan,
                    "mr_ci_low": np.nan,
                    "mr_ci_high": np.nan,
                    "p_value": p,
                }
            )
            p_values.append(p)
        for variable in ["view_count", "like_rate", "comment_rate"]:
            left = pg[variable].dropna().to_numpy(dtype=float)
            right = cg[variable].dropna().to_numpy(dtype=float)
            _, p = mannwhitneyu(left, right, alternative="two-sided")
            rb, rb_lo, rb_hi = boot_rank_biserial(left, right)
            mr, mr_lo, mr_hi = boot_median_ratio(right, left)
            rows.append(
                {
                    "party": party,
                    "variable": variable,
                    "test": "Mann-Whitney U",
                    "party_prop": np.median(left),
                    "candidate_prop": np.median(right),
                    "risk_diff": np.nan,
                    "rd_ci_low": np.nan,
                    "rd_ci_high": np.nan,
                    "odds_ratio_cmle": np.nan,
                    "or_ci_low": np.nan,
                    "or_ci_high": np.nan,
                    "effect_rb": rb,
                    "rb_ci_low": rb_lo,
                    "rb_ci_high": rb_hi,
                    "median_ratio_cand_over_party": mr,
                    "mr_ci_low": mr_lo,
                    "mr_ci_high": mr_hi,
                    "p_value": p,
                }
            )
            p_values.append(p)
    out = pd.DataFrame(rows)
    out["p_adjust_bh"] = bh_adjust(p_values)
    return out


# -------------------------------------------------------------------- D ----

def did_interaction(df: pd.DataFrame) -> pd.DataFrame:
    """Permutation test of (p_party - p_cand)_Dem - (p_party - p_cand)_Rep."""
    rows = []
    dem = df[df["party"] == "Democratic"]
    rep = df[df["party"] == "Republican"]
    dem_role = (dem["actor_type"] == "party").to_numpy()
    rep_role = (rep["actor_type"] == "party").to_numpy()

    def did_stat(dem_vals, rep_vals, dem_mask, rep_mask):
        d = dem_vals[dem_mask].mean() - dem_vals[~dem_mask].mean()
        r = rep_vals[rep_mask].mean() - rep_vals[~rep_mask].mean()
        return d - r

    perm_ps = []
    for variable in SIGNALS:
        dv = dem[variable].to_numpy(dtype=float)
        rv = rep[variable].to_numpy(dtype=float)
        obs = did_stat(dv, rv, dem_role, rep_role)
        count = 0
        for _ in range(N_PERM):
            dm = RNG.permutation(dem_role)
            rm = RNG.permutation(rep_role)
            if abs(did_stat(dv, rv, dm, rm)) >= abs(obs) - 1e-12:
                count += 1
        p_perm = (count + 1) / (N_PERM + 1)
        # Haldane-corrected ratio of odds ratios (Wald)
        cells = []
        for sub, mask in [(dem, dem_role), (rep, rep_role)]:
            v = sub[variable].to_numpy()
            a = v[mask].sum() + 0.5
            b = (1 - v[mask]).sum() + 0.5
            c = v[~mask].sum() + 0.5
            d = (1 - v[~mask]).sum() + 0.5
            cells.append((a, b, c, d))
        (a1, b1, c1, d1), (a2, b2, c2, d2) = cells
        log_ror = math.log((a1 * d1) / (b1 * c1)) - math.log((a2 * d2) / (b2 * c2))
        se = math.sqrt(sum(1 / x for x in (a1, b1, c1, d1, a2, b2, c2, d2)))
        rows.append(
            {
                "variable": variable,
                "did_prop": obs,
                "perm_p_two_sided": p_perm,
                "ratio_of_or_haldane": math.exp(log_ror),
                "ror_ci_low": math.exp(log_ror - 1.96 * se),
                "ror_ci_high": math.exp(log_ror + 1.96 * se),
            }
        )
        perm_ps.append(p_perm)
    out = pd.DataFrame(rows)
    out["perm_p_bh"] = bh_adjust(perm_ps)
    return out


# -------------------------------------------------------------------- E ----

def view_models(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    content = (
        "opponent_reference + mobilization_signal + policy_signal + "
        "personal_signal + endorsement_signal + duration_seconds + day_index"
    )
    formula_rhs = f"C(party) * C(actor_type) + {content}"

    import patsy

    ymat, xmat = patsy.dmatrices(f"view_count ~ {formula_rhs}", data=df, return_type="dataframe")
    yv = ymat.iloc[:, 0].to_numpy()

    poisson_start = sm.GLM(yv, xmat, family=sm.families.Poisson()).fit()
    start = np.append(np.asarray(poisson_start.params), 1.0)
    nb_model = sm.NegativeBinomial(yv, xmat, loglike_method="nb2")
    nb = nb_model.fit(
        start_params=start, method="bfgs", maxiter=2000, cov_type="HC1", disp=False
    )
    if not nb.mle_retvals.get("converged", False):
        nb = nb_model.fit(
            start_params=np.asarray(nb.params), method="nm", maxiter=20000, cov_type="HC1", disp=False
        )
        nb = nb_model.fit(
            start_params=np.asarray(nb.params), method="bfgs", maxiter=5000, cov_type="HC1", disp=False
        )
    alpha = float(np.asarray(nb.params)[-1])
    alpha_se = float(np.asarray(nb.bse)[-1])
    poisson = sm.GLM(yv, xmat, family=sm.families.Poisson()).fit(cov_type="HC1")
    ols = smf.ols(f"log_views ~ {formula_rhs}", data=df).fit(cov_type="HC3")
    qreg = smf.quantreg(f"log_views ~ {formula_rhs}", data=df).fit(q=0.5)

    terms = list(xmat.columns)
    nb_params = np.asarray(nb.params)
    nb_bse = np.asarray(nb.bse)
    nb_pvals = np.asarray(nb.pvalues)
    nb_conf = np.asarray(nb.conf_int())
    po_params = np.asarray(poisson.params)
    po_pvals = np.asarray(poisson.pvalues)
    rows = []
    for i, term in enumerate(terms):
        rows.append(
            {
                "term": term,
                "nb_coef": nb_params[i],
                "nb_se": nb_bse[i],
                "nb_irr": math.exp(nb_params[i]),
                "nb_irr_ci_low": math.exp(nb_conf[i, 0]),
                "nb_irr_ci_high": math.exp(nb_conf[i, 1]),
                "nb_p": nb_pvals[i],
                "poisson_coef": po_params[i],
                "poisson_p": po_pvals[i],
                "ols_coef": ols.params[term],
                "ols_se": ols.bse[term],
                "ols_ci_low": ols.conf_int().loc[term, 0],
                "ols_ci_high": ols.conf_int().loc[term, 1],
                "ols_p": ols.pvalues[term],
                "qreg_coef": qreg.params[term],
                "qreg_p": qreg.pvalues[term],
            }
        )
    table = pd.DataFrame(rows)
    # Wald test for the interaction in the NB model
    inter_idx = [i for i, t in enumerate(terms) if "T.Republican]:C(actor_type)[T.party]" in t]
    meta = {
        "nb_alpha": alpha,
        "nb_alpha_se": alpha_se,
        "nb_alpha_ci_low": alpha - 1.96 * alpha_se,
        "nb_alpha_ci_high": alpha + 1.96 * alpha_se,
        "nb_llf": float(nb.llf),
        "poisson_llf": float(poisson.llf),
        "nb_converged": bool(nb.mle_retvals.get("converged", True)),
        "n": int(len(yv)),
        "ols_r2": float(ols.rsquared),
        "ols_adj_r2": float(ols.rsquared_adj),
        "qreg_pseudo_r2": float(1 - qreg.prsquared) if hasattr(qreg, "prsquared") else None,
        "interaction_term": terms[inter_idx[0]] if inter_idx else None,
    }
    if hasattr(qreg, "prsquared"):
        meta["qreg_pseudo_r2"] = float(qreg.prsquared)
    return table, meta


def like_rate_models(df: pd.DataFrame) -> pd.DataFrame:
    content = (
        "opponent_reference + mobilization_signal + policy_signal + "
        "personal_signal + endorsement_signal + duration_seconds + day_index"
    )
    formula_rhs = f"C(party) * C(actor_type) + {content}"
    frac = smf.glm(
        f"like_rate ~ {formula_rhs}", data=df, family=sm.families.Binomial()
    ).fit(cov_type="HC3")
    ols = smf.ols(f"logit_like_rate ~ {formula_rhs}", data=df).fit(cov_type="HC3")
    rows = []
    for term in frac.params.index:
        ci = frac.conf_int().loc[term]
        rows.append(
            {
                "term": term,
                "fraclogit_coef": frac.params[term],
                "fraclogit_se": frac.bse[term],
                "fraclogit_ci_low": ci[0],
                "fraclogit_ci_high": ci[1],
                "fraclogit_p": frac.pvalues[term],
                "elogit_ols_coef": ols.params[term],
                "elogit_ols_p": ols.pvalues[term],
            }
        )
    return pd.DataFrame(rows)


# -------------------------------------------------------------------- H ----

def style_metrics(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    t = df["title"]

    def caps_share(s: str) -> float:
        letters = [ch for ch in s if ch.isalpha()]
        if len(letters) < 3:
            return float("nan")
        return sum(ch.isupper() for ch in letters) / len(letters)

    work = df.copy()
    work["caps_share"] = t.map(caps_share)
    work["style_all_caps"] = (work["caps_share"] >= 0.8).fillna(False).astype(int)
    work["style_exclamation"] = t.str.contains("!", regex=False).astype(int)
    work["style_question"] = t.str.contains(r"\?", regex=True).astype(int)
    work["style_quote"] = t.str.contains(r'["“”]', regex=True).astype(int)
    work["style_word_count"] = t.str.split().str.len()

    desc_rows = []
    for account in ACCOUNT_ORDER:
        g = work[work["account_slug"] == account]
        desc_rows.append(
            {
                "account_slug": account,
                "account": ACCOUNT_LABELS[account],
                "all_caps_prop": g["style_all_caps"].mean(),
                "exclamation_prop": g["style_exclamation"].mean(),
                "question_prop": g["style_question"].mean(),
                "quote_prop": g["style_quote"].mean(),
                "word_count_median": g["style_word_count"].median(),
                "caps_share_mean": g["caps_share"].mean(),
            }
        )
    desc = pd.DataFrame(desc_rows)

    rows = []
    p_values = []
    for party in ["Democratic", "Republican"]:
        sub = work[work["party"] == party]
        pg = sub[sub["actor_type"] == "party"]
        cg = sub[sub["actor_type"] == "candidate"]
        for variable in ["style_all_caps", "style_exclamation", "style_question", "style_quote"]:
            a, b = int(pg[variable].sum()), int((1 - pg[variable]).sum())
            c, d = int(cg[variable].sum()), int((1 - cg[variable]).sum())
            _, p = fisher_exact([[a, b], [c, d]])
            res = exact_odds_ratio([[a, b], [c, d]])
            ci = res.confidence_interval(0.95)
            rows.append(
                {
                    "party": party,
                    "variable": variable,
                    "test": "Fisher exact",
                    "party_value": a / (a + b),
                    "candidate_value": c / (c + d),
                    "odds_ratio_cmle": res.statistic,
                    "or_ci_low": ci.low,
                    "or_ci_high": ci.high,
                    "p_value": p,
                }
            )
            p_values.append(p)
        left = pg["style_word_count"].to_numpy(dtype=float)
        right = cg["style_word_count"].to_numpy(dtype=float)
        _, p = mannwhitneyu(left, right, alternative="two-sided")
        rows.append(
            {
                "party": party,
                "variable": "style_word_count",
                "test": "Mann-Whitney U",
                "party_value": np.median(left),
                "candidate_value": np.median(right),
                "odds_ratio_cmle": np.nan,
                "or_ci_low": np.nan,
                "or_ci_high": np.nan,
                "p_value": p,
            }
        )
        p_values.append(p)
    tests = pd.DataFrame(rows)
    tests["p_adjust_bh"] = bh_adjust(p_values)
    return desc, tests, work


# -------------------------------------------------------------------- I ----

OPPONENT_TERMS = {
    "Democratic": [
        r"\bdonald trump\b", r"\btrump(?:'s|s)?\b", r"\bjd vance\b", r"\bvance(?:'s|s)?\b",
        r"\bmaga\b", r"\brepublicans?\b", r"\bgop\b", r"\bproject 2025\b",
    ],
    "Republican": [
        r"\bkamala harris\b", r"\bkamala(?:'s|s)?\b", r"\bharris(?:'s|s)?\b", r"\btim walz\b",
        r"\bwalz(?:'s|s)?\b", r"\bjoe biden\b", r"\bbiden(?:'s|s)?\b", r"\bdemocrats?\b",
        r"\bdnc\b", r"\bharris[-–—/]biden\b",
    ],
}

NEGATIVE_MARKERS = [
    r"\blie(?:s|d)?\b", r"\blying\b", r"\bliar\b", r"\bfraud\b", r"\bfail(?:ed|ure|ing)?\b",
    r"\bdangerous(?:ly)?\b", r"\bradical\b", r"\bsocialist\b", r"\bliberal\b", r"\bcrisis\b",
    r"\bdisaster\b", r"\bworst\b", r"\bcan(?:no|')t\b", r"\bwon(?:')t\b", r"\brefus(?:e|es|ed|ing)\b",
    r"\bhid(?:e|ing|den)\b", r"\bweak\b", r"\bincompetent\b", r"\bcorrupt\b", r"\bcriminals?\b",
    r"\bdestroy(?:s|ed|ing)?\b", r"\braise taxes\b", r"\btax increase\b", r"\bban(?:s|ned|ning)?\b",
    r"\btake your\b", r"\bnightmare\b", r"\bwrong\b", r"\bshame\b", r"\bopen border\b",
    r"\bborder czar\b", r"\binflation\b", r"\bunfit\b", r"\bfired\b", r"\bhypocrit(?:e|ical)\b",
    r"\bno one knows\b", r"\bdoesn(?:')t respect\b", r"\bcouldn(?:')t\b", r"\bhardship\b",
    r"\bdead\b", r"\braging\b", r"\bunhinged\b",
]


def contains_any(text: str, terms: list[str]) -> bool:
    return any(re.search(term, text, flags=re.IGNORECASE) for term in terms)


def recode_signals(df: pd.DataFrame, opp_terms: dict[str, list[str]], neg_terms: list[str]) -> pd.DataFrame:
    opp = [
        int(contains_any(text, opp_terms[party]))
        for text, party in zip(df["title_norm"], df["party"])
    ]
    neg = [int(contains_any(text, neg_terms)) for text in df["title_norm"]]
    out = df.copy()
    out["opponent_reference"] = opp
    out["attack_signal"] = np.array(opp) * np.array(neg)
    return out


def fisher_for(df: pd.DataFrame, party: str, variable: str) -> tuple[float, float]:
    sub = df[df["party"] == party]
    pg = sub[sub["actor_type"] == "party"]
    cg = sub[sub["actor_type"] == "candidate"]
    table = [
        [int(pg[variable].sum()), int((1 - pg[variable]).sum())],
        [int(cg[variable].sum()), int((1 - cg[variable]).sum())],
    ]
    orr, p = fisher_exact(table)
    return orr, p


def dictionary_sensitivity(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    base = recode_signals(df, OPPONENT_TERMS, NEGATIVE_MARKERS)
    targets = [
        ("Democratic", "opponent_reference"),
        ("Republican", "opponent_reference"),
        ("Democratic", "attack_signal"),
        ("Republican", "attack_signal"),
    ]
    for party, variable in targets:
        orr0, p0 = fisher_for(base, party, variable)
        variants = []
        # drop each opponent term of that party
        for i in range(len(OPPONENT_TERMS[party])):
            terms = {k: (v[:i] + v[i + 1:] if k == party else v) for k, v in OPPONENT_TERMS.items()}
            variants.append(recode_signals(df, terms, NEGATIVE_MARKERS))
        if variable == "attack_signal":
            for i in range(len(NEGATIVE_MARKERS)):
                neg = NEGATIVE_MARKERS[:i] + NEGATIVE_MARKERS[i + 1:]
                variants.append(recode_signals(df, OPPONENT_TERMS, neg))
        ors, ps = [], []
        for v in variants:
            orr, p = fisher_for(v, party, variable)
            ors.append(orr)
            ps.append(p)
        rows.append(
            {
                "party": party,
                "variable": variable,
                "baseline_or_sample": orr0,
                "baseline_p": p0,
                "n_variants": len(variants),
                "or_min": np.nanmin(ors),
                "or_max": np.nanmax([o for o in ors if np.isfinite(o)]),
                "p_min": min(ps),
                "p_max": max(ps),
                "n_variants_p_below_05": int(sum(p < 0.05 for p in ps)),
            }
        )
    # alternative attack definition: negative marker alone (not gated by opponent)
    alt = base.copy()
    alt["attack_signal"] = alt["negative_marker"]
    for party in ["Democratic", "Republican"]:
        orr, p = fisher_for(alt, party, "attack_signal")
        rows.append(
            {
                "party": party,
                "variable": "negative_marker_alone",
                "baseline_or_sample": orr,
                "baseline_p": p,
                "n_variants": 1,
                "or_min": orr,
                "or_max": orr,
                "p_min": p,
                "p_max": p,
                "n_variants_p_below_05": int(p < 0.05),
            }
        )
    return pd.DataFrame(rows)


# -------------------------------------------------------------------- J ----

TOKEN_RE = re.compile(r"[a-z][a-z']+")


def fightin_words(df: pd.DataFrame, mask_a, mask_b, label_a: str, label_b: str, prior_scale=500.0) -> pd.DataFrame:
    def counts(mask):
        c = Counter()
        for s in df.loc[mask, "title_norm"]:
            c.update(TOKEN_RE.findall(s))
        return c

    ca, cb = counts(mask_a), counts(mask_b)
    vocab = set(ca) | set(cb)
    total = Counter()
    for w in vocab:
        total[w] = ca[w] + cb[w]
    n_total = sum(total.values())
    na, nb_ = sum(ca.values()), sum(cb.values())
    rows = []
    a0 = prior_scale
    for w in vocab:
        aw = a0 * total[w] / n_total
        ya, yb = ca[w], cb[w]
        d = math.log((ya + aw) / (na + a0 - ya - aw)) - math.log((yb + aw) / (nb_ + a0 - yb - aw))
        var = 1 / (ya + aw) + 1 / (yb + aw)
        rows.append({"word": w, "count_a": ya, "count_b": yb, "z": d / math.sqrt(var)})
    out = pd.DataFrame(rows).sort_values("z", ascending=False)
    out["side_a"] = label_a
    out["side_b"] = label_b
    return out


# -------------------------------------------------------------------- K ----

def mde_simulation(n_small=11, n_large=156, base_rate=0.0385, alpha=0.05, n_sim=4000) -> pd.DataFrame:
    rows = []
    for or_target in [2, 3, 4, 5, 6, 8, 10, 12, 15]:
        odds = base_rate / (1 - base_rate) * or_target
        p_small = odds / (1 + odds)
        hits = 0
        for _ in range(n_sim):
            a = RNG.binomial(n_small, p_small)
            c = RNG.binomial(n_large, base_rate)
            _, p = fisher_exact([[a, n_small - a], [c, n_large - c]])
            if p < alpha:
                hits += 1
        rows.append({"odds_ratio": or_target, "p_party_account": p_small, "power": hits / n_sim})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- figure ----

def register_cjk_fonts() -> None:
    """Make a simplified-Chinese face available to matplotlib on any host."""
    import matplotlib.font_manager as fm

    for path in [
        "/usr/local/share/fonts/noto-sc/NotoSansCJKsc-Regular.otf",
        "/usr/local/share/fonts/noto-sc/NotoSansCJKsc-Bold.otf",
    ]:
        if Path(path).exists():
            fm.fontManager.addfont(path)


def forest_figure(contrasts: pd.DataFrame) -> None:
    register_cjk_fonts()
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei", "Noto Sans CJK SC", "SimHei", "WenQuanYi Zen Hei"
    ]
    plt.rcParams["axes.unicode_minus"] = False
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8), sharex=True)
    for ax, party, title, color in [
        (axes[0], "Democratic", "民主党：DNC相对哈里斯账号", "#2563eb"),
        (axes[1], "Republican", "共和党：RNC相对特朗普账号", "#dc2626"),
    ]:
        sub = contrasts[(contrasts["party"] == party) & (contrasts["test"] == "Fisher exact")]
        sub = sub.set_index("variable").loc[SIGNALS].reset_index()
        y = np.arange(len(sub))[::-1]
        or_vals = sub["odds_ratio_cmle"].to_numpy()
        lo = sub["or_ci_low"].to_numpy()
        hi = sub["or_ci_high"].to_numpy()
        floor = 0.005
        cap = 200.0
        for yi, o, l, h, q in zip(y, or_vals, lo, hi, sub["p_adjust_bh"].tolist()):
            l_plot = max(l, floor) if l > 0 else floor
            h_plot = min(h, cap) if np.isfinite(h) else cap
            o_plot = min(max(o, floor), cap) if o > 0 else floor
            lw = 2.2 if q < 0.05 else 1.2
            alpha_ = 1.0 if q < 0.05 else 0.45
            ax.plot([l_plot, h_plot], [yi, yi], color=color, lw=lw, alpha=alpha_, solid_capstyle="round")
            ax.plot([o_plot], [yi], marker="o", color=color, markersize=6 if q < 0.05 else 4.5, alpha=alpha_)
            if o == 0:
                ax.annotate("OR=0", (floor * 1.35, yi + 0.22), fontsize=7.5, va="bottom", color=color, alpha=alpha_)
        ax.axvline(1.0, color="#6b7280", lw=0.8, ls="--")
        ax.set_yticks(y)
        ax.set_yticklabels([SIGNAL_LABELS[v] for v in sub["variable"]])
        ax.set_xscale("log")
        ax.set_xlim(floor, cap)
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("条件最大似然比值比（对数坐标，95%确切置信区间）", fontsize=9)
        ax.grid(axis="x", color="#e5e7eb", lw=0.6)
        for spine in ["top", "right"]:
            ax.spines[spine].set_visible(False)
    fig.suptitle("党组织账号相对候选人账号的标题信号比值比", fontsize=12.5)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / "figure4_or_forest.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


# ------------------------------------------------------------------ main ----

def main() -> None:
    EXT.mkdir(parents=True, exist_ok=True)
    df = load()

    prod = production_structure(df)
    prod.to_csv(EXT / "ext_A_production_structure.csv", index=False, encoding="utf-8-sig")

    cad = cadence(df)
    cad.to_csv(EXT / "ext_B_cadence.csv", index=False, encoding="utf-8-sig")

    contrasts = enriched_contrasts(df)
    contrasts.to_csv(EXT / "ext_C_contrasts_enriched.csv", index=False, encoding="utf-8-sig")

    did = did_interaction(df)
    did.to_csv(EXT / "ext_D_did_interaction.csv", index=False, encoding="utf-8-sig")

    views_tab, views_meta = view_models(df)
    views_tab.to_csv(EXT / "ext_E_view_models.csv", index=False, encoding="utf-8-sig")

    likes_tab = like_rate_models(df)
    likes_tab.to_csv(EXT / "ext_F_like_rate_models.csv", index=False, encoding="utf-8-sig")

    conc, camp_share = concentration(df)
    conc.to_csv(EXT / "ext_G_concentration_accounts.csv", index=False, encoding="utf-8-sig")
    camp_share.to_csv(EXT / "ext_G_concentration_campshare.csv", index=False, encoding="utf-8-sig")

    style_desc, style_tests, style_work = style_metrics(df)
    style_desc.to_csv(EXT / "ext_H_style_descriptive.csv", index=False, encoding="utf-8-sig")
    style_tests.to_csv(EXT / "ext_H_style_tests.csv", index=False, encoding="utf-8-sig")
    style_work.to_csv(
        ROOT / "data" / "processed" / "youtube_shorts_coded_extended.csv",
        index=False,
        encoding="utf-8-sig",
    )

    sens = dictionary_sensitivity(df)
    sens.to_csv(EXT / "ext_I_dictionary_sensitivity.csv", index=False, encoding="utf-8-sig")

    fw_rnc_harris = fightin_words(
        df, df["account_slug"] == "rnc", df["account_slug"] == "harris", "RNC", "Harris"
    )
    fw_role = fightin_words(
        df, df["actor_type"] == "party", df["actor_type"] == "candidate", "party_accounts", "candidate_accounts"
    )
    pd.concat(
        [fw_rnc_harris.head(15), fw_rnc_harris.tail(15), fw_role.head(15), fw_role.tail(15)]
    ).to_csv(EXT / "ext_J_fightin_words.csv", index=False, encoding="utf-8-sig")

    mde = mde_simulation()
    mde.to_csv(EXT / "ext_K_mde_dnc_attack.csv", index=False, encoding="utf-8-sig")

    forest_figure(contrasts)

    summary = {
        "seed": 20260825,
        "n_boot": N_BOOT,
        "n_perm": N_PERM,
        "production_structure_fisher_p": float(prod["structure_diff_fisher_p"].iloc[0]),
        "production_structure_or": float(prod["structure_diff_or"].iloc[0]),
        "view_models_meta": views_meta,
    }
    (EXT / "ext_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
