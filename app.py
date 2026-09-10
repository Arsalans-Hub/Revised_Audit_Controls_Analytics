"""
app.py
------
Interactive Streamlit dashboard for the IT General Controls & Data
Assurance Analytics project.

Two modes, chosen in the sidebar:
  - Sample data (demo): reads the pre-computed results shipped in outputs/
    (fast, and matches the numbers in the README / resume bullets).
  - Upload your own data: runs the full pipeline live, in-memory, against
    CSVs you provide -- nothing is written back to disk, so it never
    touches the sample data.

Run locally:
    pip install -r requirements.txt
    streamlit run app.py
"""

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
import charts              # noqa: E402
import data_quality        # noqa: E402
import sod_analysis        # noqa: E402
import anomaly_detection   # noqa: E402

ROOT = Path(__file__).resolve().parent
OUTPUTS_DIR = ROOT / "outputs"
PROCESSED_DIR = ROOT / "data" / "processed"
TEMPLATES_DIR = ROOT / "templates"

st.set_page_config(page_title="Operational Risk & Controls Monitoring Dashboard",
                    page_icon="🛡️", layout="wide")

REQUIRED_COLUMNS = {
    "users": ["user_id", "department", "email", "status"],
    "access": ["user_id", "role_name", "access_end_date"],
    "txns": ["transaction_id", "txn_date", "preparer_id", "approver_id", "amount"],
}


# ---------------------------------------------------------------- sample data
@st.cache_data
def load_sample():
    if not (OUTPUTS_DIR / "summary.json").exists():
        return None
    with open(OUTPUTS_DIR / "summary.json") as f:
        summary = json.load(f)
    sod_findings = pd.read_csv(OUTPUTS_DIR / "findings_sod_conflicts.csv")
    orphaned = pd.read_csv(OUTPUTS_DIR / "findings_terminated_user_access.csv")
    by_dept = pd.read_csv(OUTPUTS_DIR / "sod_conflicts_by_department.csv", index_col=0)["users_flagged"]
    benford_df = pd.read_csv(OUTPUTS_DIR / "benford_first_digit_distribution.csv")
    anomalous = pd.read_csv(OUTPUTS_DIR / "findings_anomalous_transactions.csv")
    txns = pd.read_csv(PROCESSED_DIR / "gl_transactions_clean.csv", parse_dates=["txn_date"])
    anomalous["txn_date"] = pd.to_datetime(anomalous["txn_date"])
    return dict(summary=summary, sod=sod_findings, orphaned=orphaned, by_dept=by_dept,
                benford=benford_df, anomalous=anomalous, txns=txns, is_sample=True)


# ---------------------------------------------------------------- upload mode
def validate_columns(df, required, label):
    missing = [c for c in required if c not in df.columns]
    if missing:
        st.error(f"**{label}** is missing required column(s): {', '.join(missing)}. "
                 f"Download the template below to see the expected format.")
        return False
    return True


def run_on_uploaded(users_file, access_file, txns_file, roles_file, sod_file):
    users = pd.read_csv(users_file, dtype=str).fillna("")
    access = pd.read_csv(access_file, dtype=str).fillna("")
    txns = pd.read_csv(txns_file, dtype=str).fillna("")

    ok = True
    ok &= validate_columns(users, REQUIRED_COLUMNS["users"], "Users file")
    ok &= validate_columns(access, REQUIRED_COLUMNS["access"], "Access file")
    ok &= validate_columns(txns, REQUIRED_COLUMNS["txns"], "Transactions file")
    if not ok:
        return None

    txns["amount"] = pd.to_numeric(txns["amount"], errors="coerce")
    if txns["amount"].isna().any():
        st.warning(f"{txns['amount'].isna().sum()} transaction row(s) had a non-numeric amount "
                   f"and were dropped.")
        txns = txns.dropna(subset=["amount"])
    txns["txn_date"] = pd.to_datetime(txns["txn_date"], errors="coerce")
    txns = txns.dropna(subset=["txn_date"])

    roles = (pd.read_csv(roles_file, dtype=str).fillna("") if roles_file is not None
             else pd.read_csv(TEMPLATES_DIR / "roles_template.csv", dtype=str).fillna(""))
    sod = (pd.read_csv(sod_file, dtype=str).fillna("") if sod_file is not None
           else pd.read_csv(TEMPLATES_DIR / "sod_conflict_matrix_template.csv", dtype=str).fillna(""))

    with st.spinner("Running data quality checks, SoD testing, and anomaly detection..."):
        score_before = data_quality.quality_score(users, access)
        raw_checks = data_quality.run_quality_checks(users, access)
        users_clean, access_clean = data_quality.clean_data(users, access, roles)
        score_after = data_quality.quality_score(users_clean, access_clean)

        dq_summary = {
            "records_scanned": len(users) + len(access) + len(txns),
            "data_quality_score_before": score_before,
            "data_quality_score_after": score_after,
            "duplicate_access_rows_removed": len(access) - len(access_clean),
            **raw_checks,
        }

        sod_conflicts, orphaned, by_dept, acc_summary = sod_analysis.analyze(users_clean, access_clean, sod)

        # scale the anomaly-detection contamination to the size of the
        # uploaded dataset instead of the fixed 0.02 tuned for 6,000 rows
        contamination = min(0.05, max(0.01, 8 / max(len(txns), 1)))
        txn_result = anomaly_detection.analyze(txns, seeded_key_df=None, contamination=contamination)

    summary = {"data_quality": dq_summary, "access_review": acc_summary,
               "transaction_testing": txn_result["summary"]}

    return dict(summary=summary, sod=sod_conflicts, orphaned=orphaned, by_dept=by_dept,
                benford=txn_result["benford_df"], anomalous=txn_result["flagged"],
                txns=txns, is_sample=False)


# ---------------------------------------------------------------------- sidebar
st.sidebar.title("🛡️ Data Source")
mode = st.sidebar.radio("Choose what to explore", ["Sample data (demo)", "Upload your own data"])

data = None
if mode == "Sample data (demo)":
    data = load_sample()
else:
    st.sidebar.markdown("**Required files**")
    users_file = st.sidebar.file_uploader("Users (CSV)", type="csv", key="users")
    access_file = st.sidebar.file_uploader("User access grants (CSV)", type="csv", key="access")
    txns_file = st.sidebar.file_uploader("GL transactions (CSV)", type="csv", key="txns")

    with st.sidebar.expander("Optional: roles & SoD conflict matrix"):
        st.caption("If skipped, a default role list and Segregation-of-Duties "
                   "conflict matrix (matching the sample data) is used.")
        roles_file = st.file_uploader("Roles (CSV)", type="csv", key="roles")
        sod_file = st.file_uploader("SoD conflict matrix (CSV)", type="csv", key="sod")

    with st.sidebar.expander("📥 Download CSV templates"):
        for fname in ["users_template.csv", "user_access_template.csv",
                       "gl_transactions_template.csv", "roles_template.csv",
                       "sod_conflict_matrix_template.csv"]:
            fpath = TEMPLATES_DIR / fname
            if fpath.exists():
                st.download_button(fname, data=fpath.read_bytes(), file_name=fname, key=f"dl_{fname}")

    if users_file and access_file and txns_file:
        data = run_on_uploaded(users_file, access_file, txns_file, roles_file, sod_file)
    else:
        st.info("👈 Upload a **users**, **access**, and **transactions** CSV in the sidebar to "
                "run this dashboard on your own data. Download the templates there first if "
                "you want to see the expected format.")

st.title("🛡️ IT General Controls & Data Assurance Dashboard")
st.caption("Data quality review, Segregation-of-Duties testing, and GL transaction "
           "anomaly detection -- run on the sample dataset or on your own upload.")

if data is None:
    st.stop()

s = data["summary"]
dq, acc, txn = s["data_quality"], s["access_review"], s["transaction_testing"]
has_validation = "model_recall" in txn

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
if has_validation:
    c5.metric("Anomaly Model Recall", f"{txn['model_recall']}%", f"{txn['model_precision']}% precision")
else:
    c5.metric("Anomaly Model", "Unsupervised", "no seeded ground truth to score against")

st.divider()

tab1, tab2, tab3 = st.tabs(["📊 Data Quality", "🔐 Access & Segregation of Duties", "💳 Transaction Testing"])

with tab1:
    st.subheader("Data Quality: Before vs. After Cleaning")
    left, right = st.columns([1, 1])
    with left:
        st.pyplot(charts.fig_data_quality(dq["data_quality_score_before"], dq["data_quality_score_after"]))
    with right:
        st.markdown("**Issues identified in the raw data**")
        st.dataframe(pd.DataFrame({
            "Issue": ["Missing department field", "Invalid / malformed email",
                      "Duplicate access grant rows", "Missing 'granted by' field"],
            "Count": [dq["missing_department"], dq["invalid_email"],
                      dq["duplicate_access_groups"], dq["missing_granted_by"]],
        }), hide_index=True, use_container_width=True)
        st.caption(f"{dq['records_scanned']:,} total records scanned across users, "
                   f"access grants, and transactions.")

with tab2:
    st.subheader("Segregation of Duties Conflicts")
    if len(data["by_dept"]) > 0:
        left, right = st.columns([1, 1])
        with left:
            st.pyplot(charts.fig_sod_by_department(data["by_dept"]))
        with right:
            st.markdown(f"**{acc['users_with_sod_conflicts']} active users** "
                         f"({acc['pct_active_users_with_sod_conflict']}%) hold two incompatible "
                         f"roles at the same time.")
            st.dataframe(data["sod"], use_container_width=True, height=250)
    else:
        st.success("No Segregation of Duties conflicts found in this dataset.")

    st.subheader("Terminated Users With Active Access")
    if acc["terminated_users_with_active_access"] > 0:
        st.warning(f"{acc['terminated_users_with_active_access']} of {acc['terminated_users_reviewed']} "
                   f"terminated employees ({acc['pct_terminated_users_with_orphaned_access']}%) still "
                   f"had system access that was never revoked.")
        st.dataframe(data["orphaned"], use_container_width=True, height=250)
    else:
        st.success("No terminated users with lingering access were found.")

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

    if has_validation:
        st.subheader("Model Validation")
        st.info(f"To validate the anomaly-detection model without real fraud labels, "
                f"{txn['seeded_anomalies']} transactions were deliberately seeded as anomalous "
                f"during data generation. The Isolation Forest model recovered "
                f"{txn['true_positives']} of them: **{txn['model_recall']}% recall, "
                f"{txn['model_precision']}% precision.**")
    else:
        st.caption("This is your own data, so there's no seeded ground truth to score the "
                   "model's recall/precision against -- the flagged transactions above are "
                   "the model's raw, unsupervised output for manual review.")

    st.subheader("Flagged Transactions")
    st.dataframe(data["anomalous"], use_container_width=True, height=300)

st.divider()
if data.get("is_sample", True):
    st.caption("Synthetic sample data, generated for demonstration purposes. "
               "See README.md for methodology, or switch to 'Upload your own data' in the sidebar.")
else:
    st.caption("Results computed live from your uploaded files. Nothing you upload is saved or written to disk.")
