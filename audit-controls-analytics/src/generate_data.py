"""
generate_data.py
-----------------
Generates a synthetic, intentionally messy "ERP export" that mimics what an
auditor would actually pull from a client system (e.g., SAP/Oracle user
access tables + a GL transaction extract).

The data is randomly generated but seeded for reproducibility, and includes
DELIBERATE, KNOWN issues so the rest of the pipeline has real things to find:
  - Segregation of Duties (SoD) conflicts (e.g., one user can both create
    AND approve AP payments)
  - Terminated employees with access that was never revoked
  - Data quality issues (duplicates, missing fields, inconsistent casing)
  - Transactions posted without a required secondary approver
  - "Threshold avoidance" transactions (suspiciously clustered just under
    the dollar amount that would trigger extra approval)
  - A seeded cluster of anomalous transactions (round dollar amounts,
    weekend postings, repeat-digit amounts) used later to validate the
    anomaly-detection model's recall.

Run: python src/generate_data.py
Outputs CSVs into data/raw/
"""

import random
import string
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
random.seed(SEED)
np.random.seed(SEED)

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
VALIDATION_DIR = ROOT / "data" / "validation"
RAW_DIR.mkdir(parents=True, exist_ok=True)
VALIDATION_DIR.mkdir(parents=True, exist_ok=True)

N_USERS = 400
N_TXNS = 6000
APPROVAL_THRESHOLD = 5000.00  # transactions >= this require a secondary approver

FIRST_NAMES = ["James", "Maria", "David", "Linda", "Robert", "Patricia", "John", "Jennifer",
               "Michael", "Elizabeth", "William", "Susan", "Carlos", "Ana", "Wei", "Priya",
               "Hassan", "Fatima", "Kevin", "Rachel", "Brian", "Emily", "Daniel", "Grace",
               "Samuel", "Nina", "Omar", "Sofia", "Tyler", "Chloe", "Anthony", "Mei",
               "Arjun", "Layla", "George", "Hannah", "Marcus", "Julia", "Victor", "Ines"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Garcia", "Miller", "Davis", "Rodriguez",
              "Martinez", "Wilson", "Anderson", "Taylor", "Thomas", "Moore", "Jackson", "Martin",
              "Lee", "Perez", "Thompson", "White", "Harris", "Clark", "Lewis", "Young", "Walker",
              "Chen", "Nguyen", "Kim", "Patel", "Khan", "Ali", "Diaz", "Reyes", "Cruz", "Torres"]

DEPARTMENTS = ["Accounts Payable", "Procurement", "General Ledger", "IT",
               "Sales", "Human Resources", "Operations"]

# role_id, role_name, department
ROLES = [
    ("R01", "AP Clerk", "Accounts Payable"),
    ("R02", "AP Approver", "Accounts Payable"),
    ("R03", "Vendor Master Maintainer", "Accounts Payable"),
    ("R04", "Purchasing Buyer", "Procurement"),
    ("R05", "Purchasing Approver", "Procurement"),
    ("R06", "GL Preparer", "General Ledger"),
    ("R07", "GL Approver", "General Ledger"),
    ("R08", "System Administrator", "IT"),
    ("R09", "Read-Only Reporting", "Operations"),
    ("R10", "HR Generalist", "Human Resources"),
    ("R11", "Sales Rep", "Sales"),
]
ROLES_DF = pd.DataFrame(ROLES, columns=["role_id", "role_name", "department"])

# Segregation of Duties conflict matrix: role pairs that should NEVER be
# held by the same active user at the same time.
SOD_CONFLICTS = [
    ("AP Clerk", "AP Approver"),
    ("Vendor Master Maintainer", "AP Approver"),
    ("Purchasing Buyer", "Purchasing Approver"),
    ("GL Preparer", "GL Approver"),
    ("System Administrator", "AP Approver"),
    ("System Administrator", "GL Approver"),
    ("System Administrator", "Purchasing Approver"),
]

GL_ACCOUNTS = ["6010-Office Supplies", "6020-Travel & Entertainment", "6030-Professional Fees",
               "6040-IT Software", "6050-Facilities", "6060-Marketing", "6070-Utilities",
               "6080-Consulting", "6090-Equipment", "6100-Freight & Shipping"]


def random_date(start, end):
    delta = end - start
    return start + timedelta(days=random.randint(0, delta.days))


def build_users():
    users = []
    dept_roles = {d: [r for r in ROLES if r[2] == d] for d in DEPARTMENTS}
    hire_start = datetime(2018, 1, 1)
    hire_end = datetime(2026, 6, 1)

    for i in range(1, N_USERS + 1):
        uid = f"U{i:04d}"
        fname, lname = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
        dept = random.choice(DEPARTMENTS)
        hire_date = random_date(hire_start, hire_end)

        # ~12% of the population is terminated
        is_terminated = random.random() < 0.12
        term_date = None
        status = "Active"
        if is_terminated:
            status = "Terminated"
            term_date = random_date(hire_date + timedelta(days=30), datetime(2026, 9, 1))

        email = f"{fname.lower()}.{lname.lower()}@northfieldindustries.com"
        # ~3% malformed emails (missing domain) -- realistic export junk
        if random.random() < 0.03:
            email = f"{fname.lower()}.{lname.lower()}"

        # ~3% missing department (blank field in source export)
        dept_out = dept if random.random() > 0.03 else ""

        users.append({
            "user_id": uid, "first_name": fname, "last_name": lname,
            "department": dept_out, "email": email,
            "hire_date": hire_date.strftime("%Y-%m-%d"),
            "status": status,
            "termination_date": term_date.strftime("%Y-%m-%d") if term_date else "",
            "true_department": dept,  # kept for internal role-assignment logic only
        })
    return pd.DataFrame(users)


def build_access(users_df):
    rows = []
    conflict_pool = [u for u in users_df.itertuples() if random.random() < 0.11]  # ~11% seeded conflicts
    conflict_ids = {u.user_id for u in conflict_pool}
    role_lookup = {r[1]: r for r in ROLES}

    for u in users_df.itertuples():
        dept = u.true_department
        primary_roles = [r for r in ROLES if r[2] == dept]
        if not primary_roles:
            primary_roles = [random.choice(ROLES)]
        chosen = [random.choice(primary_roles)]

        # Seed a genuine, verifiable SoD conflict: assign BOTH sides of a
        # randomly chosen incompatible-role pair, regardless of the user's
        # home department (realistic -- e.g., legacy access from a prior
        # role that was never cleaned up).
        if u.user_id in conflict_ids:
            pair = random.choice(SOD_CONFLICTS)
            role_a, role_b = role_lookup[pair[0]], role_lookup[pair[1]]
            chosen = [role_a, role_b]

        for role_id, role_name, role_dept in chosen:
            granted_date = random_date(datetime.strptime(u.hire_date, "%Y-%m-%d"), datetime(2026, 8, 1))
            granted_by = f"U{random.randint(1, N_USERS):04d}"
            # ~5% missing granted_by (incomplete export field)
            if random.random() < 0.05:
                granted_by = ""

            # Access end date: revoked at termination UNLESS this is a seeded
            # "orphaned access" finding (~35% of terminated users keep access)
            access_end = ""
            if u.status == "Terminated":
                if random.random() > 0.35:
                    access_end = u.termination_date  # properly revoked

            role_name_out = role_name
            # ~4% inconsistent casing/whitespace junk from source system
            if random.random() < 0.04:
                role_name_out = f"  {role_name.lower()}"

            rows.append({
                "user_id": u.user_id, "role_id": role_id, "role_name": role_name_out,
                "system": "ERP-PROD", "granted_date": granted_date.strftime("%Y-%m-%d"),
                "granted_by": granted_by, "access_end_date": access_end,
            })

    access_df = pd.DataFrame(rows)
    # ~2% exact duplicate rows (common export artifact)
    dupes = access_df.sample(frac=0.02, random_state=SEED)
    access_df = pd.concat([access_df, dupes], ignore_index=True)
    return access_df.sample(frac=1, random_state=SEED).reset_index(drop=True)


def build_transactions(users_df):
    active_users = users_df[users_df["status"] == "Active"]["user_id"].tolist()
    rows = []
    start = datetime(2025, 9, 1)
    end = datetime(2026, 8, 31)

    # small "seeded anomaly ring": a handful of users used to inject a
    # detectable pattern of suspicious transactions
    anomaly_ring = random.sample(active_users, 6)

    for i in range(1, N_TXNS + 1):
        tid = f"T{i:06d}"
        preparer = random.choice(active_users)
        txn_date = random_date(start, end)
        account = random.choice(GL_ACCOUNTS)

        seeded_anomaly = False
        if random.random() < 0.018:  # ~1.8% seeded anomalous transactions
            preparer = random.choice(anomaly_ring)
            amount = round(random.choice([4900, 4950, 4995, 9800, 9900, 4999, 2000, 5000]) +
                            random.choice([0, 0, 0.00]), 2)
            txn_date = random_date(start, end)
            # push toward weekend postings for the anomaly ring
            while txn_date.weekday() < 5 and random.random() < 0.6:
                txn_date += timedelta(days=(5 - txn_date.weekday()))
            seeded_anomaly = True
        else:
            # normal transactions: lognormal distribution approximates
            # naturally-occurring Benford's Law behavior
            amount = round(float(np.random.lognormal(mean=6.2, sigma=1.1)), 2)
            amount = max(15.00, min(amount, 48000.00))

        approver = ""
        if amount >= APPROVAL_THRESHOLD:
            # ~2.5% of required approvals are missing (control exception)
            if random.random() > 0.025:
                pool = [u for u in active_users if u != preparer]
                approver = random.choice(pool)
        else:
            if random.random() < 0.3:
                pool = [u for u in active_users if u != preparer]
                approver = random.choice(pool)

        rows.append({
            "transaction_id": tid, "txn_date": txn_date.strftime("%Y-%m-%d"),
            "preparer_id": preparer, "approver_id": approver,
            "account": account, "amount": amount,
            "description": f"{account.split('-')[1]} charge",
            "_seeded_anomaly": seeded_anomaly,
        })

    return pd.DataFrame(rows)


def main():
    users_df = build_users()
    access_df = build_access(users_df)
    txns_df = build_transactions(users_df)

    # Keep a hidden validation copy of seeded anomalies in a separate folder
    # (NOT part of the "raw ERP export" -- a real export would never
    # contain this column; it exists only to score the detection model).
    txns_df[["transaction_id", "_seeded_anomaly"]].to_csv(
        VALIDATION_DIR / "seeded_anomaly_key.csv", index=False)

    users_out = users_df.drop(columns=["true_department"])
    txns_out = txns_df.drop(columns=["_seeded_anomaly"])

    users_out.to_csv(RAW_DIR / "users.csv", index=False)
    ROLES_DF.to_csv(RAW_DIR / "roles.csv", index=False)
    access_df.to_csv(RAW_DIR / "user_access.csv", index=False)
    txns_out.to_csv(RAW_DIR / "gl_transactions.csv", index=False)

    sod_df = pd.DataFrame(SOD_CONFLICTS, columns=["role_a", "role_b"])
    sod_df.to_csv(RAW_DIR / "sod_conflict_matrix.csv", index=False)

    print(f"Generated {len(users_out)} users, {len(access_df)} access records, "
          f"{len(txns_out)} GL transactions -> {RAW_DIR}")


if __name__ == "__main__":
    main()
