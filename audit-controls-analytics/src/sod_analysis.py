"""
sod_analysis.py
----------------
Runs the two core ITGC access-control tests defined in
sql/02_sod_and_access_risk.sql:

  1. Segregation of Duties (SoD) conflicts -- active users holding both
     sides of a defined incompatible-role pair.
  2. Orphaned access -- terminated users whose system access was never
     revoked.

Both are executed as real SQL against an in-memory SQLite database built
from the cleaned data produced by data_quality.py.
"""

import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
OUTPUTS_DIR = ROOT / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

SOD_QUERY = """
SELECT
    a1.user_id,
    a1.role_name AS role_a,
    a2.role_name AS role_b
FROM user_access_clean a1
JOIN user_access_clean a2
    ON a1.user_id = a2.user_id
    AND a1.role_name < a2.role_name
JOIN sod_conflict_matrix m
    ON (m.role_a = a1.role_name AND m.role_b = a2.role_name)
    OR (m.role_b = a1.role_name AND m.role_a = a2.role_name)
JOIN users u
    ON u.user_id = a1.user_id
WHERE u.status = 'Active'
  AND (a1.access_end_date IS NULL OR a1.access_end_date = '')
  AND (a2.access_end_date IS NULL OR a2.access_end_date = '')
"""

ORPHANED_ACCESS_QUERY = """
SELECT
    u.user_id, u.first_name, u.last_name, u.department, u.termination_date,
    a.role_name, a.granted_date
FROM users u
JOIN user_access_clean a ON a.user_id = u.user_id
WHERE u.status = 'Terminated'
  AND (a.access_end_date IS NULL OR a.access_end_date = '')
"""


def load_clean():
    users = pd.read_csv(PROCESSED_DIR / "users_clean.csv", dtype=str).fillna("")
    access = pd.read_csv(PROCESSED_DIR / "user_access_clean.csv", dtype=str).fillna("")
    sod = pd.read_csv(PROCESSED_DIR / "sod_conflict_matrix.csv", dtype=str).fillna("")
    return users, access, sod


def run():
    users, access, sod = load_clean()

    conn = sqlite3.connect(":memory:")
    users.to_sql("users", conn, index=False)
    access.to_sql("user_access_clean", conn, index=False)
    sod.to_sql("sod_conflict_matrix", conn, index=False)

    sod_conflicts = pd.read_sql_query(SOD_QUERY, conn)
    orphaned_access = pd.read_sql_query(ORPHANED_ACCESS_QUERY, conn)
    conn.close()

    sod_conflicts.to_csv(OUTPUTS_DIR / "findings_sod_conflicts.csv", index=False)
    orphaned_access.to_csv(OUTPUTS_DIR / "findings_terminated_user_access.csv", index=False)

    active_users = (users["status"] == "Active").sum()
    terminated_users = (users["status"] == "Terminated").sum()

    n_conflict_users = sod_conflicts["user_id"].nunique()
    n_orphaned_users = orphaned_access["user_id"].nunique()

    # SoD conflicts by department, for the dashboard chart
    dept_lookup = users.set_index("user_id")["department"].to_dict()
    sod_conflicts["department"] = sod_conflicts["user_id"].map(dept_lookup)
    by_dept = sod_conflicts.groupby("department")["user_id"].nunique().sort_values(ascending=False)
    by_dept.to_csv(OUTPUTS_DIR / "sod_conflicts_by_department.csv", header=["users_flagged"])

    summary = {
        "active_users_reviewed": int(active_users),
        "terminated_users_reviewed": int(terminated_users),
        "users_with_sod_conflicts": int(n_conflict_users),
        "pct_active_users_with_sod_conflict": round(100 * n_conflict_users / active_users, 1),
        "terminated_users_with_active_access": int(n_orphaned_users),
        "pct_terminated_users_with_orphaned_access": round(100 * n_orphaned_users / terminated_users, 1)
            if terminated_users else 0.0,
    }
    print(summary)
    return summary


if __name__ == "__main__":
    run()
