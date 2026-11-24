"""Reproduce the analysis and figures for the pinned MineThatData experiment."""

import hashlib
import json
from contextlib import closing
from itertools import product
from math import sqrt
import os
from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd
from scipy.stats import chi2, chisquare, norm, t

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "data" / "raw" / ".matplotlib"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RAW = ROOT / "data" / "raw" / "hillstrom.csv.gz"
REPORTS = ROOT / "reports"
ALL = "All customers"
CONTROL = "No E-Mail"
MENS = "Mens E-Mail"
WOMENS = "Womens E-Mail"
CONTRASTS = [(MENS, CONTROL), (WOMENS, CONTROL), (MENS, WOMENS)]
BANDS = ["01-03 months", "04-06 months", "07-12 months"]
BUDGET_MARGINS = (0.25, 0.40, 0.60)
BUDGET_CONTACT_COSTS_USD = (0.02, 0.10, 0.20, 0.45)
BINARY = ["mens", "womens", "newbie", "visit", "conversion"]
EXPECTED_SHA = "bab6578f60db5d792f1c2372c502f029152a5249cf5ea84390f3b7f885d7234f"
EXPECTED_COLUMNS = {
    "recency", "history_segment", "history", "mens", "womens", "zip_code",
    "newbie", "channel", "segment", "visit", "conversion", "spend",
}
KEYS = ["audience", "arm"]
Z95 = norm.ppf(0.975)


def load_experiment():
    if not RAW.is_file():
        raise SystemExit(f"Missing {RAW}. See data/README.md for the download command.")
    sha256 = hashlib.sha256(RAW.read_bytes()).hexdigest()
    if sha256 != EXPECTED_SHA:
        raise ValueError(f"Unexpected dataset SHA-256: {sha256}")
    frame = pd.read_csv(RAW)
    if set(frame.columns) != EXPECTED_COLUMNS or len(frame) != 64_000:
        raise ValueError("Unexpected experiment schema or customer count.")
    if frame.isna().any().any() or set(frame.segment) != {CONTROL, MENS, WOMENS}:
        raise ValueError("Missing values or an unexpected assignment group.")
    if not frame[BINARY].isin([0, 1]).all().all():
        raise ValueError("An indicator contains values outside 0 and 1.")
    if not frame.recency.isin(range(1, 13)).all():
        raise ValueError("Recency must be an integer from 1 to 12 months.")
    cents = frame.spend * 100
    if (
        not np.isfinite(frame[["spend", "history"]]).all().all()
        or (frame[["spend", "history"]] < 0).any().any()
        or not np.allclose(cents, cents.round(), rtol=0, atol=1e-7)
        or (frame.conversion > frame.visit).any()
        or ((frame.spend > 0) != (frame.conversion == 1)).any()
    ):
        raise ValueError("Spend, history, or outcome consistency check failed.")
    duplicate_patterns = int(frame.duplicated().sum())
    frame["spend_cents"] = cents.round().astype("int64")
    return frame, duplicate_patterns


def summarize(frame):
    with closing(sqlite3.connect(":memory:")) as connection:
        frame.to_sql("experiment", connection, index=False, if_exists="fail")
        sql = pd.read_sql_query(
            (ROOT / "sql" / "summary.sql").read_text(encoding="utf-8-sig"), connection
        )

    pandas_input = frame.assign(
        recency_band=pd.cut(frame.recency, bins=[0, 3, 6, 12], labels=BANDS),
        spend_squared_cents=frame.spend_cents.pow(2),
    ).rename(columns={"segment": "arm"})
    pandas_input = pd.concat([
        pandas_input.assign(audience=ALL),
        pandas_input.assign(audience=pandas_input.recency_band.astype("string")),
    ])
    check = pandas_input.groupby(KEYS, sort=True).agg(
        customers=("conversion", "size"),
        conversions=("conversion", "sum"),
        visits=("visit", "sum"),
        spend_cents=("spend_cents", "sum"),
        spend_squared_cents=("spend_squared_cents", "sum"),
        conversion_rate=("conversion", "mean"),
    )
    sql = sql.set_index(KEYS).sort_index()
    pd.testing.assert_frame_equal(sql, check, check_index_type=False, rtol=0, atol=1e-15)
    if len(sql) != 12 or sql.loc[ALL, "customers"].sum() != len(frame):
        raise ValueError("Assignment and audience counts failed to reconcile.")
    totals = ["customers", "conversions", "visits", "spend_cents"]
    pd.testing.assert_frame_equal(sql.loc[BANDS][totals].groupby("arm").sum(), sql.loc[ALL, totals])
    sql["visit_rate"] = sql.visits / sql.customers
    sql["spend_per_customer_usd"] = sql.spend_cents / (100 * sql.customers)
    return sql


def wilson_interval(rate, customers):
    denominator = 1 + Z95**2 / customers
    center = (rate + Z95**2 / (2 * customers)) / denominator
    radius = Z95 * sqrt(rate * (1 - rate) / customers + Z95**2 / (4 * customers**2))
    radius /= denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def compare(summary, audience, arm, baseline):
    a, b = summary.loc[(audience, arm)], summary.loc[(audience, baseline)]
    na, nb = int(a.customers), int(b.customers)
    pa, pb = a.conversion_rate, b.conversion_rate
    difference = pa - pb
    pooled = (a.conversions + b.conversions) / (na + nb)
    se_null = sqrt(pooled * (1 - pooled) * (1 / na + 1 / nb))
    lo_a, hi_a = wilson_interval(pa, na)
    lo_b, hi_b = wilson_interval(pb, nb)
    low = difference - np.hypot(pa - lo_a, hi_b - pb)
    high = difference + np.hypot(hi_a - pa, pb - lo_b)
    return {
        "audience": audience,
        "arm": arm,
        "baseline": baseline,
        "customers": na,
        "baseline_customers": nb,
        "conversions": int(a.conversions),
        "baseline_conversions": int(b.conversions),
        "conversion_rate": pa,
        "baseline_conversion_rate": pb,
        "lift_pp": 100 * difference,
        "relative_lift_pct": 100 * difference / pb if pb > 0 else np.nan,
        "lift_low_pp": 100 * low,
        "lift_high_pp": 100 * high,
        "p_value": 2 * norm.sf(abs(difference) / se_null) if se_null > 0 else 1.0,
        "lift_variance": pa * (1 - pa) / na + pb * (1 - pb) / nb,
        "incremental_conversions": na * difference,
        "incremental_conversions_low": na * low,
        "incremental_conversions_high": na * high,
    }


def holm(p_values):
    values = np.asarray(p_values, dtype=float)
    order = np.argsort(values)
    adjusted = np.empty(len(values))
    adjusted[order] = np.minimum(1, np.maximum.accumulate(values[order] * np.arange(len(values), 0, -1)))
    return adjusted


def heterogeneity(segments):
    results = []
    for arm, rows in segments.groupby("arm"):
        effects = rows.lift_pp.to_numpy() / 100
        weights = 1 / rows.lift_variance.to_numpy()
        mean = np.average(effects, weights=weights)
        statistic = float(np.dot(weights, (effects - mean) ** 2))
        results.append({"arm": arm, "wald_chi2": statistic, "df": len(rows) - 1,
                        "p_value": chi2.sf(statistic, len(rows) - 1)})
    results = pd.DataFrame(results)
    results["p_holm"] = holm(results.p_value)
    return results


def budget_scenarios(summary):
    control = summary.loc[(ALL, CONTROL)]
    rows = []
    for arm in (MENS, WOMENS):
        treatment = summary.loc[(ALL, arm)]
        n = int(treatment.customers)
        n_control = int(control.customers)
        mean_diff = treatment.spend_per_customer_usd - control.spend_per_customer_usd

        def variance_of_mean(group):
            size = int(group.customers)
            centered_squares = group.spend_squared_cents - group.spend_cents**2 / size
            return centered_squares / (size * (size - 1) * 10_000)

        vt = variance_of_mean(treatment)
        vc = variance_of_mean(control)
        df = (vt + vc)**2 / (vt**2 / (n - 1) + vc**2 / (n_control - 1))
        radius = t.ppf(0.975, df) * sqrt(vt + vc)
        for margin, cost in product(BUDGET_MARGINS, BUDGET_CONTACT_COSTS_USD):
            rows.append({
                "arm": arm,
                "customers": n,
                "margin_assumption": margin,
                "contact_cost_assumption_usd": cost,
                "revenue_lift_per_customer_usd": mean_diff,
                "revenue_lift_low_usd": mean_diff - radius,
                "revenue_lift_high_usd": mean_diff + radius,
                "incremental_revenue_usd": mean_diff * n,
                "incremental_revenue_low_usd": (mean_diff - radius) * n,
                "incremental_revenue_high_usd": (mean_diff + radius) * n,
                "breakeven_cost_usd": margin * mean_diff,
                "breakeven_cost_low_usd": margin * (mean_diff - radius),
                "breakeven_cost_high_usd": margin * (mean_diff + radius),
                "net_per_1000_usd": 1000 * (margin * mean_diff - cost),
                "net_per_1000_low_usd": 1000 * (margin * (mean_diff - radius) - cost),
                "net_per_1000_high_usd": 1000 * (margin * (mean_diff + radius) - cost),
            })
    return pd.DataFrame(rows)


def quality_summary(frame, summary, duplicate_patterns):
    group_counts = summary.loc[ALL, "customers"]
    srm = chisquare(group_counts)
    features = ["recency", "history", "mens", "womens", "newbie"]
    control = frame.loc[frame.segment == CONTROL, features]
    smd = {}
    for arm in (MENS, WOMENS):
        group = frame.loc[frame.segment == arm, features]
        standardized = (group.mean() - control.mean()) / np.sqrt((group.var() + control.var()) / 2)
        smd[arm] = standardized.to_dict()
    return {
        "source_sha256": EXPECTED_SHA,
        "customers": len(frame),
        "raw_columns": len(EXPECTED_COLUMNS),
        "missing_values": int(frame.isna().sum().sum()),
        "duplicate_attribute_rows_retained": duplicate_patterns,
        "assignment_counts": group_counts.to_dict(),
        "srm_chi2": float(srm.statistic),
        "srm_p_value_equal_thirds": float(srm.pvalue),
        "baseline_standardized_mean_differences": smd,
    }


def plot_effects(overall, segments):
    palette = {MENS: "#12665e", WOMENS: "#935213"}
    groups = [
        (overall[overall.baseline == CONTROL], "Overall assignment effect"),
        (segments, "Effect by months since last purchase"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.3), layout="constrained", sharex=True)
    for ax, (data, title), audiences in zip(axes, groups, [[ALL], BANDS]):
        ax.axvline(0, color="#576273", linestyle="--", linewidth=1, zorder=1)
        for arm, dot, offset in [(MENS, "o", -0.12), (WOMENS, "s", 0.12)]:
            rows = data.loc[data.arm == arm].set_index("audience").loc[audiences]
            ax.errorbar(
                rows.lift_pp, np.arange(len(audiences)) + offset,
                xerr=[rows.lift_pp - rows.lift_low_pp, rows.lift_high_pp - rows.lift_pp],
                fmt=dot, color=palette[arm], capsize=3, linewidth=1.7, label=arm,
            )
        ax.set_title(title, loc="left", fontsize=12, fontweight="bold", color="#172532", pad=13)
        ax.set(xlabel="Conversion lift vs no email (percentage points)",
               yticks=range(len(audiences)), yticklabels=audiences, ylim=(len(audiences) - 0.48, -0.52))
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.spines["bottom"].set_color("#b1bac6")
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="x", color="#e9edf1")
        ax.set_axisbelow(True)
    fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncol=2, frameon=False)
    fig.get_layout_engine().set(rect=(0.01, 0.10, 0.98, 0.86))
    fig.savefig(REPORTS / "conversion_lift.png", dpi=160, facecolor="white")
    plt.close(fig)


def main():
    frame, duplicate_patterns = load_experiment()
    summary = summarize(frame)
    overall = pd.DataFrame([compare(summary, ALL, arm, base) for arm, base in CONTRASTS])
    overall["p_holm"] = holm(overall.p_value)
    segments = pd.DataFrame([
        compare(summary, band, arm, CONTROL) for band in BANDS for arm in (MENS, WOMENS)
    ])
    segments["p_holm"] = holm(segments.p_value)

    REPORTS.mkdir(exist_ok=True)
    tables = {
        "arm_summary": summary.reset_index(),
        "overall_effects": overall,
        "segment_effects": segments,
        "heterogeneity": heterogeneity(segments),
        "budget_scenarios": budget_scenarios(summary),
    }
    for name, table in tables.items():
        table.drop(columns=["lift_variance"], errors="ignore").to_csv(
            REPORTS / f"{name}.csv", index=False, float_format="%.12g"
        )
    checks = quality_summary(frame, summary, duplicate_patterns)
    (REPORTS / "quality_checks.json").write_text(json.dumps(checks, indent=2) + "\n", encoding="utf-8")
    plot_effects(overall, segments)
    print(f"Analyzed {len(frame):,} customers. SQL and Pandas summaries reconcile.")
    print(overall[["arm", "baseline", "lift_pp", "p_holm"]].to_string(index=False))


if __name__ == "__main__":
    main()


