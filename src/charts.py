"""
charts.py
---------
Chart-building functions shared by run_pipeline.py (static PNGs for the
README) and app.py (the interactive Streamlit dashboard). Keeping the
plotting logic in one place means both use exactly the same figures.
"""

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

sns.set_theme(style="whitegrid", context="talk", font_scale=0.52)

NAVY = "#16324f"
NAVY_LIGHT = "#3f6690"
AMBER = "#e0912b"
RED = "#b8433a"
SLATE = "#9aa7b6"
INK = "#1c2733"
SUBTLE = "#6b7684"

plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "savefig.facecolor": "white",
    "axes.edgecolor": "#d7dde3",
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": SUBTLE,
    "ytick.color": SUBTLE,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.spines.left": False,
    "grid.color": "#e7ebef",
    "grid.linewidth": 0.9,
    "font.family": "DejaVu Sans",
})


def _title(ax, title, subtitle=None):
    ax.set_title(title, fontsize=13.5, fontweight="bold", color=INK, pad=28, loc="left")
    if subtitle:
        ax.text(0.0, 1.10, subtitle, transform=ax.transAxes,
                 fontsize=10.5, color=SUBTLE, ha="left")


def fig_data_quality(score_before, score_after):
    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    cats = ["Before cleaning", "After cleaning"]
    vals = [score_before, score_after]
    colors = [SLATE, NAVY]
    bars = ax.barh(cats, vals, color=colors, height=0.48, zorder=3,
                    edgecolor="white", linewidth=0.5)
    ax.set_xlim(90, 100)
    ax.grid(axis="x", zorder=0)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Data quality score (completeness + validity, out of 100)", fontsize=10.5)
    _title(ax, "Data Quality: Before vs. After Cleaning",
           "Composite score across department, email, and access-grant fields")
    for b, v in zip(bars, vals):
        ax.text(b.get_width() + 0.15, b.get_y() + b.get_height() / 2,
                 f"{v:.1f}", va="center", fontsize=12, fontweight="bold", color=INK)
    fig.tight_layout()
    return fig


def fig_sod_by_department(by_dept_series):
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    by_dept_series = by_dept_series.sort_values(ascending=True)
    bars = ax.barh(by_dept_series.index, by_dept_series.values, color=NAVY, height=0.6,
                    zorder=3, edgecolor="white", linewidth=0.5)
    ax.grid(axis="x", zorder=0)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Active users flagged with an SoD conflict", fontsize=10.5)
    _title(ax, "Segregation of Duties Conflicts by Department",
           "Users currently holding two incompatible roles at once")
    for b in bars:
        ax.text(b.get_width() + 0.08, b.get_y() + b.get_height() / 2,
                 f"{int(b.get_width())}", va="center", fontsize=10.5, fontweight="bold", color=INK)
    fig.tight_layout()
    return fig


def fig_benford(benford_df):
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    width = 0.36
    x = np.arange(1, 10)
    ax.bar(x - width / 2, benford_df["observed_pct"], width, label="Observed",
           color=NAVY, zorder=3, edgecolor="white", linewidth=0.4)
    ax.bar(x + width / 2, benford_df["expected_pct"], width, label="Benford Expected",
           color=AMBER, zorder=3, edgecolor="white", linewidth=0.4)
    ax.set_xticks(x)
    ax.grid(axis="x", visible=False)
    ax.set_xlabel("Leading digit", fontsize=10.5)
    ax.set_ylabel("% of transactions", fontsize=10.5)
    _title(ax, "Benford's Law: Leading-Digit Distribution",
           "Natural transaction populations should track the expected curve")
    ax.legend(frameon=False, loc="upper right", fontsize=10)
    fig.tight_layout()
    return fig


def fig_anomaly_scatter(flagged_df, all_txns_df):
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.scatter(all_txns_df["txn_date"], all_txns_df["amount"],
               s=10, color=SLATE, alpha=0.35, label="Normal", zorder=2, linewidths=0)
    ax.scatter(flagged_df["txn_date"], flagged_df["amount"],
               s=32, color=RED, alpha=0.9, label="Flagged anomalous", zorder=3,
               edgecolor="white", linewidth=0.4)
    ax.set_ylabel("Transaction amount ($)", fontsize=10.5)
    _title(ax, "Isolation Forest: Flagged Transactions Over Time",
           "Amount, weekend timing, and round-dollar patterns drive the score")
    ax.legend(frameon=True, framealpha=0.9, edgecolor="none", loc="upper right", fontsize=10)
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def fig_control_exceptions(labels, values):
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    colors = [RED, AMBER, NAVY][:len(labels)]
    bars = ax.bar(labels, values, color=colors, width=0.55, zorder=3,
                   edgecolor="white", linewidth=0.5)
    ax.grid(axis="y", zorder=0)
    ax.grid(axis="x", visible=False)
    _title(ax, "Transaction Control Exceptions Identified",
           "Missing approvals, threshold avoidance, and model-flagged anomalies")
    for i, v in enumerate(values):
        ax.text(i, v + max(values) * 0.025, str(v), ha="center", fontweight="bold",
                 fontsize=12, color=INK)
    fig.tight_layout()
    return fig
