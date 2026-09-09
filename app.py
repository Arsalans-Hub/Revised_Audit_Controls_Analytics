"""
app.py
------
Interactive Streamlit dashboard for the IT General Controls & Data
Assurance Analytics project.

Run locally:
    pip install -r requirements.txt
    python src/run_pipeline.py   # generates data + findings (only needed once)
    streamlit run app.py

Or deploy for free on Streamlit Community Cloud (streamlit.io/cloud) by
pointing it at this repo -- no server management required.
"""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
import charts  # noqa: E402

ROOT = Path(__file__).resolve().parent
OUTPUTS_DIR = ROOT / "outputs"
PROCESSED_DIR = ROOT / "data" / "processed"

st.set_page_config(page_title="IT Controls & Data Assurance Dashboard",
                    page_icon="🛡️", layout="wide")


@st.cache_data
def load_all():
    if not (OUTPUTS_DIR / "summary.json").exists():
        return None
    with open(OUTPUTS_DIR / "summary.json") as f:
        summary = json.load(f)
    sod_findings = pd.read_csv(OUTPUTS_DIR / "findings_sod_conflicts.csv")
    orphaned = pd.read_csv(OUTPUTS_DIR / "findings_terminated_user_access.csv")
    by_dept = pd.read_csv(OUTPUTS_DIR / "sod_conflicts_by_department.csv", index_col=0)["users_flagged"]
    benford_df = pd.read_csv(OUTPUTS_DIR / "benford_first_digit_distribution.csv")
    missing_approval = pd.read_csv(OUTPUTS_DIR / "findings_missing_approval.csv")
    threshold_avoid = pd.read_csv(OUTPUTS_DIR / "findings_threshold_avoidance.csv")
    anomalous = pd.read_csv(OUTPUTS_DIR / "findings_anomalous_transactions.csv")
    txns = pd.read_csv(PROCESSED_DIR / "gl_transactions_clean.csv", parse_dates=["txn_date"])
    anomalous["txn_date"] = pd.to_datetime(anomalous["txn_date"])
    return dict(summary=summary, sod=sod_findings, orphaned=orphaned, by_dept=by_dept,
                benford=benford_df, missing_approval=missing_approval,
                threshold_avoid=threshold_avoid, anomalous=anomalous, txns=txns)


data = load_all()

st.title("🛡️ IT General Controls & Data Assurance Dashboard")
st.caption("A simulated audit-analytics engagement: data quality review, "
           "Segregation-of-Duties testing, and GL transaction anomaly detection "
           "over a synthetic ERP export.")

if data is None:
    st.error("No pipeline output found. Run `python src/run_pipeline.py` first "
             "to generate the data and findings this dashboard reads from.")
    st.stop()

s = data["summary"]
dq, acc, txn = s["data_quality"], s["access_review"], s["transaction_testing"]

# ---- KPI row -----------------------------------------------------------
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Data Quality Score", f"{dq['data_quality_score_after']}",
          f"+{round(dq['data_quality_score_after'] - dq['data_quality_score_before'], 1)} after cleaning")
c2.metric("Active Users w/ SoD Conflict", acc["users_with_sod_conflicts"],
          f"{acc['pct_active_users_with_sod_conflict']}% of active users")
c3.metric("Terminated Users w/ Active Access", acc["terminated_users_with_active_access"],
          f"{acc['pct_terminated_users_with_orphaned_access']}% of leavers", delta_color="inverse")
c4.metric("Transactions Flagged", txn["transactions_flagged_anomalous"],
          f"of {txn['transactions_reviewed']:,} reviewed")
c5.metric("Anomaly Model Recall", f"{txn['model_recall']}%",
          f"{txn['model_precision']}% precision")

st.divider()

tab1, tab2, tab3 = st.tabs(["📊 Data Quality", "🔐 Access & Segregation of Duties", "💳 Transaction Testing"])

with tab1:
    st.subheader("Data Quality: Before vs. After Cleaning")
    left, right = st.columns([1, 1])
    with left:
        st.pyplot(charts.fig_data_quality(dq["data_quality_score_before"], dq["data_quality_score_after"]))
    with right:
        st.markdown("**Issues identified in the raw export**")
        st.write(pd.DataFrame({
            "Issue": ["Missing department field", "Invalid / malformed email",
                      "Duplicate access grant rows", "Missing 'granted by' field"],
            "Count": [dq["missing_department"], dq["invalid_email"],
                      dq["duplicate_access_groups"], dq["missing_granted_by"]],
        }))
        st.caption(f"{dq['records_scanned']:,} total records scanned across users, "
                   f"access grants, and transactions.")

with tab2:
    st.subheader("Segregation of Duties Conflicts")
    left, right = st.columns([1, 1])
    with left:
        st.pyplot(charts.fig_sod_by_department(data["by_dept"]))
    with right:
        st.markdown(f"**{acc['users_with_sod_conflicts']} active users** "
                     f"({acc['pct_active_users_with_sod_conflict']}%) hold two incompatible "
                     f"roles at the same time -- e.g. the ability to both create and approve "
                     f"the same AP payment.")
        st.dataframe(data["sod"], use_container_width=True, height=250)

    st.subheader("Terminated Users With Active Access")
    st.warning(f"{acc['terminated_users_with_active_access']} of {acc['terminated_users_reviewed']} "
               f"terminated employees ({acc['pct_terminated_users_with_orphaned_access']}%) still "
               f"had system access that was never revoked -- a classic ITGC exception and a real "
               f"security exposure.")
    st.dataframe(data["orphaned"], use_container_width=True, height=250)

with tab3:
    st.subheader("Control Exceptions")
    st.pyplot(charts.fig_control_exceptions(
        ["Missing\napproval", "Threshold\navoidance", "Anomalies\nflagged"],
        [txn["missing_required_approval"], txn["near_threshold_transactions"],
         txn["transactions_flagged_anomalous"]],
    ))

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Benford's Law Test")
        st.pyplot(charts.fig_benford(data["benford"]))
        st.caption(f"Mean Absolute Deviation: {txn['benford_mad']} -- **{txn['benford_conformity']}**")
    with right:
        st.subheader("Isolation Forest: Flagged Transactions")
        st.pyplot(charts.fig_anomaly_scatter(data["anomalous"], data["txns"]))

    st.subheader("Model Validation")
    st.info(f"To validate the anomaly-detection model without real fraud labels, "
            f"{txn['seeded_anomalies']} transactions were deliberately seeded as anomalous "
            f"during data generation. The Isolation Forest model recovered "
            f"{txn['true_positives']} of them: **{txn['model_recall']}% recall, "
            f"{txn['model_precision']}% precision.**")

    st.subheader("Flagged Transactions")
    st.dataframe(data["anomalous"], use_container_width=True, height=300)

st.divider()
st.caption("Synthetic data, generated for demonstration purposes only. "
           "See README.md for methodology and how to reproduce this analysis.")
