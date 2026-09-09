"""
run_pipeline.py
----------------
Runs the full pipeline end to end:
  1. generate_data   -> data/raw/*.csv
  2. data_quality     -> data/processed/*.csv  (+ quality scores)
  3. sod_analysis      -> outputs/findings_*.csv (access risk)
  4. anomaly_detection -> outputs/findings_*.csv (transaction risk)
  5. charts             -> outputs/charts/*.png (for the README)
  6. summary.json       -> every headline statistic in one place

Run: python src/run_pipeline.py
"""

import json
from pathlib import Path

import pandas as pd

import generate_data
import data_quality
import sod_analysis
import anomaly_detection
import charts

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = ROOT / "outputs"
CHARTS_DIR = OUTPUTS_DIR / "charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)


def main():
    print("1/5  Generating synthetic ERP export...")
    generate_data.main()

    print("2/5  Running data quality checks + cleaning...")
    dq_summary = data_quality.main()

    print("3/5  Running SoD / access-risk analysis...")
    sod_summary = sod_analysis.run()

    print("4/5  Running transaction control-exception + anomaly analysis...")
    anomaly_summary = anomaly_detection.main()

    print("5/5  Building charts...")
    by_dept = pd.read_csv(OUTPUTS_DIR / "sod_conflicts_by_department.csv", index_col=0)["users_flagged"]
    fig1 = charts.fig_data_quality(dq_summary["data_quality_score_before"], dq_summary["data_quality_score_after"])
    fig1.savefig(CHARTS_DIR / "data_quality.png", dpi=150)

    fig2 = charts.fig_sod_by_department(by_dept)
    fig2.savefig(CHARTS_DIR / "sod_by_department.png", dpi=150)

    benford_df = pd.read_csv(OUTPUTS_DIR / "benford_first_digit_distribution.csv")
    fig3 = charts.fig_benford(benford_df)
    fig3.savefig(CHARTS_DIR / "benford_distribution.png", dpi=150)

    txns = pd.read_csv(ROOT / "data" / "processed" / "gl_transactions_clean.csv", parse_dates=["txn_date"])
    flagged = pd.read_csv(OUTPUTS_DIR / "findings_anomalous_transactions.csv", parse_dates=["txn_date"])
    fig4 = charts.fig_anomaly_scatter(flagged, txns)
    fig4.savefig(CHARTS_DIR / "anomaly_scatter.png", dpi=150)

    fig5 = charts.fig_control_exceptions(
        ["Missing\napproval", "Threshold\navoidance", "Anomalies\nflagged"],
        [anomaly_summary["missing_required_approval"], anomaly_summary["near_threshold_transactions"],
         anomaly_summary["transactions_flagged_anomalous"]],
    )
    fig5.savefig(CHARTS_DIR / "control_exceptions.png", dpi=150)

    summary = {
        "data_quality": dq_summary,
        "access_review": sod_summary,
        "transaction_testing": anomaly_summary,
    }
    with open(OUTPUTS_DIR / "summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)

    print("\nDone. Full summary written to outputs/summary.json\n")
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
