"""
data_quality.py
----------------
Loads the raw ("as-exported") ERP data, runs the completeness/validity/
duplicate checks defined in sql/01_data_quality_checks.sql, cleans the
data, and scores overall data quality before vs. after cleaning.

This is the "Data Assurance" half of the project: before any control test
means anything, you have to be able to trust the data it's built on.
"""

import re
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def load_raw():
    users = pd.read_csv(RAW_DIR / "users.csv", dtype=str).fillna("")
    access = pd.read_csv(RAW_DIR / "user_access.csv", dtype=str).fillna("")
    txns = pd.read_csv(RAW_DIR / "gl_transactions.csv", dtype=str).fillna("")
    txns["amount"] = txns["amount"].astype(float)
    roles = pd.read_csv(RAW_DIR / "roles.csv", dtype=str).fillna("")
    sod = pd.read_csv(RAW_DIR / "sod_conflict_matrix.csv", dtype=str).fillna("")
    return users, access, txns, roles, sod


def run_quality_checks(users, access):
    """Runs the checks in sql/01_data_quality_checks.sql via an in-memory
    SQLite database so the results are produced by real SQL, not just
    pandas filtering."""
    conn = sqlite3.connect(":memory:")
    users.to_sql("users", conn, index=False)
    access.to_sql("user_access", conn, index=False)

    missing_department = conn.execute(
        "SELECT COUNT(*) FROM users WHERE department IS NULL OR TRIM(department) = ''"
    ).fetchone()[0]

    invalid_email = conn.execute(
        "SELECT COUNT(*) FROM users WHERE email NOT LIKE '%_@__%.__%'"
    ).fetchone()[0]

    dup_rows = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT user_id, role_id, system, granted_date, COUNT(*) c
            FROM user_access
            GROUP BY user_id, role_id, system, granted_date
            HAVING COUNT(*) > 1
        )
    """).fetchone()[0]

    missing_granted_by = conn.execute(
        "SELECT COUNT(*) FROM user_access WHERE granted_by IS NULL OR TRIM(granted_by) = ''"
    ).fetchone()[0]

    conn.close()
    return {
        "missing_department": missing_department,
        "invalid_email": invalid_email,
        "duplicate_access_groups": dup_rows,
        "missing_granted_by": missing_granted_by,
    }


def quality_score(users, access):
    """Simple composite completeness/validity score, 0-100."""
    n_users = len(users)
    n_access = len(access)

    dept_complete = (users["department"].str.strip() != "").sum() / n_users
    email_valid = users["email"].apply(lambda e: bool(EMAIL_RE.match(e))).sum() / n_users
    grantedby_complete = (access["granted_by"].str.strip() != "").sum() / n_access
    dup_key = access[["user_id", "role_id", "system", "granted_date"]]
    dup_rate = 1 - (dup_key.duplicated().sum() / n_access)

    weighted = (dept_complete + email_valid + grantedby_complete + dup_rate) / 4
    return round(weighted * 100, 1)


def clean_data(users, access, roles):
    users_clean = users.copy()
    users_clean["department"] = users_clean["department"].str.strip().replace("", "Unknown")

    # Normalize role_name against the canonical role list (case/whitespace
    # junk in the export shouldn't cause a real role to go unmatched).
    canonical = {r.strip().lower(): r.strip() for r in roles["role_name"]}
    access_clean = access.copy()
    access_clean["role_name"] = (
        access_clean["role_name"].str.strip().str.lower().map(canonical)
        .fillna(access_clean["role_name"].str.strip())
    )
    access_clean = access_clean.drop_duplicates(
        subset=["user_id", "role_id", "system", "granted_date"], keep="first"
    ).reset_index(drop=True)

    return users_clean, access_clean


def main():
    users, access, txns, roles, sod = load_raw()

    score_before = quality_score(users, access)
    raw_checks = run_quality_checks(users, access)

    users_clean, access_clean = clean_data(users, access, roles)
    score_after = quality_score(users_clean, access_clean)

    users_clean.to_csv(PROCESSED_DIR / "users_clean.csv", index=False)
    access_clean.to_csv(PROCESSED_DIR / "user_access_clean.csv", index=False)
    txns.to_csv(PROCESSED_DIR / "gl_transactions_clean.csv", index=False)
    roles.to_csv(PROCESSED_DIR / "roles.csv", index=False)
    sod.to_csv(PROCESSED_DIR / "sod_conflict_matrix.csv", index=False)

    result = {
        "records_scanned": int(n := (len(users) + len(access) + len(txns))),
        "data_quality_score_before": score_before,
        "data_quality_score_after": score_after,
        "duplicate_access_rows_removed": int(len(access) - len(access_clean)),
        **{k: int(v) for k, v in raw_checks.items()},
    }
    print(result)
    return result


if __name__ == "__main__":
    main()
