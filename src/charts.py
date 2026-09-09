"""
charts.py
---------
Chart-building functions shared by generate_report.py (static PNGs for the
README) and app.py (the interactive Streamlit dashboard). Keeping the
plotting logic in one place means both use exactly the same figures.
"""

import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.edgecolor": "#333333",
    "axes.labelcolor": "#222222",
    "text.color": "#222222",
    "xtick.color": "#333333",
    "ytick.color": "#333333",
    "font.size": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
})

NAVY = "#1f3b57"
ORANGE = "#d97828"
GRAY = "#9aa5b1"
RED = "#b33f3f"


def fig_data_quality(score_before, score_after):
    fig, ax = plt.subplots(figsize=(5.5, 3))
    bars = ax.barh(["After cleaning", "Before cleaning"], [score_after, score_before],
                    color=[NAVY, GRAY], height=0.5)
    ax.set_xlim(90, 100)
    ax.set_xlabel("Data quality score (completeness + validity)")
    ax.set_title("Data Quality Score: Before vs. After Cleaning", fontweight="bold")
    for b in bars:
        ax.text(b.get_width() + 0.1, b.get_y() + b.get_height() / 2,
                 f"{b.get_width():.1f}", va="center", fontsize=10)
    fig.tight_layout()
    return fig


def fig_sod_by_department(by_dept_series):
    fig, ax = plt.subplots(figsize=(6, 3.5))
    by_dept_series = by_dept_series.sort_values(ascending=True)
    ax.barh(by_dept_series.index, by_dept_series.values, color=NAVY)
    ax.set_xlabel("Active users flagged with an SoD conflict")
    ax.set_title("Segregation of Duties Conflicts by Department", fontweight="bold")
    fig.tight_layout()
    return fig


def fig_benford(benford_df):
    fig, ax = plt.subplots(figsize=(6, 3.5))
    width = 0.38
    x = np.arange(1, 10)
    ax.bar(x - width / 2, benford_df["observed_pct"], width, label="Observed", color=NAVY)
    ax.bar(x + width / 2, benford_df["expected_pct"], width, label="Benford Expected", color=ORANGE)
    ax.set_xticks(x)
    ax.set_xlabel("Leading digit")
    ax.set_ylabel("% of transactions")
    ax.set_title("Benford's Law: Leading-Digit Distribution", fontweight="bold")
    ax.legend(frameon=False)
    fig.tight_layout()
    return fig


def fig_anomaly_scatter(flagged_df, all_txns_df):
    fig, ax = plt.subplots(figsize=(6.5, 4))
    ax.scatter(all_txns_df["txn_date"], all_txns_df["amount"],
               s=8, color=GRAY, alpha=0.35, label="Normal")
    ax.scatter(flagged_df["txn_date"], flagged_df["amount"],
               s=22, color=RED, alpha=0.85, label="Flagged anomalous")
    ax.set_ylabel("Transaction amount ($)")
    ax.set_title("Isolation Forest: Flagged Transactions Over Time", fontweight="bold")
    ax.legend(frameon=False)
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def fig_control_exceptions(labels, values):
    fig, ax = plt.subplots(figsize=(5.5, 3.2))
    ax.bar(labels, values, color=[RED, ORANGE, NAVY][:len(labels)])
    ax.set_title("Transaction Control Exceptions Identified", fontweight="bold")
    for i, v in enumerate(values):
        ax.text(i, v + max(values) * 0.02, str(v), ha="center", fontweight="bold")
    fig.tight_layout()
    return fig
