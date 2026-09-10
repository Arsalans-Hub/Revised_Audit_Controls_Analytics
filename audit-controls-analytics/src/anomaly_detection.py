"""
anomaly_detection.py
---------------------
Substantive testing over the GL transaction population:

  1. Control-exception SQL checks (sql/03_transaction_control_exceptions.sql):
     missing required approvals, self-approved transactions, and
     "threshold avoidance" (amounts clustered just under the approval
     trigger).
  2. Benford's Law first-digit test -- a standard forensic-accounting
     technique to spot unnatural transaction populations.
  3. An Isolation Forest anomaly-detection model, whose recall is measured
     against a held-out set of transactions that were deliberately seeded
     as anomalous during data generation (a lightweight way to validate a
     detection model's performance without real labeled fraud data).
"""

import sqlite3
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
VALIDATION_DIR = ROOT / "data" / "validation"
OUTPUTS_DIR = ROOT / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

APPROVAL_THRESHOLD = 5000.00

# Benford's Law expected first-digit frequencies
BENFORD_EXPECTED = {d: np.log10(1 + 1 / d) for d in range(1, 10)}


def load():
    txns = pd.read_csv(PROCESSED_DIR / "gl_transactions_clean.csv", dtype=str).fillna("")
    txns["amount"] = txns["amount"].astype(float)
    txns["txn_date"] = pd.to_datetime(txns["txn_date"])
    return txns


def control_exception_checks(txns):
    conn = sqlite3.connect(":memory:")
    txns.to_sql("gl_transactions", conn, index=False)

    missing_approval = pd.read_sql_query("""
        SELECT transaction_id, txn_date, preparer_id, amount, account
        FROM gl_transactions
        WHERE amount >= 5000.00 AND (approver_id IS NULL OR TRIM(approver_id) = '')
    """, conn)

    self_approved = pd.read_sql_query("""
        SELECT transaction_id, txn_date, preparer_id, amount
        FROM gl_transactions
        WHERE preparer_id = approver_id AND TRIM(approver_id) <> ''
    """, conn)

    near_threshold = pd.read_sql_query("""
        SELECT transaction_id, txn_date, preparer_id, amount
        FROM gl_transactions
        WHERE amount BETWEEN 4500.00 AND 4999.99
    """, conn)
    conn.close()

    missing_approval.to_csv(OUTPUTS_DIR / "findings_missing_approval.csv", index=False)
    near_threshold.to_csv(OUTPUTS_DIR / "findings_threshold_avoidance.csv", index=False)

    return missing_approval, self_approved, near_threshold


def benfords_law_test(txns):
    first_digits = txns["amount"].apply(lambda x: int(str(x)[0]) if str(x)[0] != '0' else None).dropna()
    observed_counts = Counter(int(d) for d in first_digits)
    total = sum(observed_counts.values())
    observed_pct = {d: observed_counts.get(d, 0) / total for d in range(1, 10)}
    expected_pct = BENFORD_EXPECTED

    mad = np.mean([abs(observed_pct[d] - expected_pct[d]) for d in range(1, 10)])
    # Standard MAD conformity bands (Nigrini, 2012)
    if mad < 0.006:
        conformity = "Close conformity"
    elif mad < 0.012:
        conformity = "Acceptable conformity"
    elif mad < 0.015:
        conformity = "Marginally acceptable conformity"
    else:
        conformity = "Nonconformity"

    benford_df = pd.DataFrame({
        "digit": list(range(1, 10)),
        "observed_pct": [round(observed_pct[d] * 100, 2) for d in range(1, 10)],
        "expected_pct": [round(expected_pct[d] * 100, 2) for d in range(1, 10)],
    })
    benford_df.to_csv(OUTPUTS_DIR / "benford_first_digit_distribution.csv", index=False)

    return {"mean_absolute_deviation": round(mad, 4), "conformity": conformity}, benford_df


def isolation_forest_scan(txns):
    features = txns.copy()
    features["day_of_week"] = features["txn_date"].dt.dayofweek
    features["is_weekend"] = (features["day_of_week"] >= 5).astype(int)
    features["has_approver"] = (features["approver_id"].str.strip() != "").astype(int)
    features["log_amount"] = np.log1p(features["amount"])
    features["is_round_amount"] = (features["amount"] % 100 == 0).astype(int)

    X = features[["log_amount", "is_weekend", "has_approver", "is_round_amount"]]

    model = IsolationForest(n_estimators=300, contamination=0.02, random_state=42)
    features["anomaly_score"] = model.fit_predict(X)  # -1 = anomaly, 1 = normal
    features["anomaly_raw_score"] = model.decision_function(X)

    flagged = features[features["anomaly_score"] == -1].sort_values("anomaly_raw_score")
    flagged[["transaction_id", "txn_date", "preparer_id", "amount", "account",
             "is_weekend", "has_approver", "is_round_amount", "anomaly_raw_score"]].to_csv(
        OUTPUTS_DIR / "findings_anomalous_transactions.csv", index=False
    )
    return flagged, len(features)


def validate_against_seeded_anomalies(flagged):
    """Measures the Isolation Forest's recall against the known set of
    transactions that were deliberately seeded as anomalous during data
    generation -- a way to sanity-check the model without real fraud
    labels."""
    key = pd.read_csv(VALIDATION_DIR / "seeded_anomaly_key.csv")
    seeded_ids = set(key[key["_seeded_anomaly"]]["transaction_id"])
    flagged_ids = set(flagged["transaction_id"])

    true_positives = seeded_ids & flagged_ids
    recall = len(true_positives) / len(seeded_ids) if seeded_ids else 0.0
    precision = len(true_positives) / len(flagged_ids) if flagged_ids else 0.0

    return {
        "seeded_anomalies": len(seeded_ids),
        "flagged_by_model": len(flagged_ids),
        "true_positives": len(true_positives),
        "model_recall": round(recall * 100, 1),
        "model_precision": round(precision * 100, 1),
    }


def main():
    txns = load()
    missing_approval, self_approved, near_threshold = control_exception_checks(txns)
    benford_stats, benford_df = benfords_law_test(txns)
    flagged, n_total = isolation_forest_scan(txns)
    validation = validate_against_seeded_anomalies(flagged)

    summary = {
        "transactions_reviewed": n_total,
        "missing_required_approval": len(missing_approval),
        "self_approved_transactions": len(self_approved),
        "near_threshold_transactions": len(near_threshold),
        "benford_mad": benford_stats["mean_absolute_deviation"],
        "benford_conformity": benford_stats["conformity"],
        "transactions_flagged_anomalous": len(flagged),
        **validation,
    }
    print(summary)
    return summary


if __name__ == "__main__":
    main()
