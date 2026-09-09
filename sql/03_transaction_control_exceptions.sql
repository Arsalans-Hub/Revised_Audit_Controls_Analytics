-- 03_transaction_control_exceptions.sql
-- Substantive test over GL transactions: control exceptions and
-- "threshold avoidance" (amounts suspiciously clustered just under the
-- dollar threshold that would trigger mandatory secondary approval).

-- Missing required approval: transactions at/above the approval threshold
-- with no approver on file.
SELECT transaction_id, txn_date, preparer_id, amount, account
FROM gl_transactions
WHERE amount >= 5000.00
  AND (approver_id IS NULL OR TRIM(approver_id) = '');

-- Self-approval: the same person prepared and approved their own
-- transaction (should never happen if SoD is enforced).
SELECT transaction_id, txn_date, preparer_id, amount
FROM gl_transactions
WHERE preparer_id = approver_id;

-- Threshold avoidance: transactions priced between $4,500-$4,999.99, just
-- under the $5,000 approval trigger. An unusually high concentration here
-- (versus the surrounding range) suggests possible policy circumvention.
SELECT COUNT(*) AS near_threshold_txns
FROM gl_transactions
WHERE amount BETWEEN 4500.00 AND 4999.99;
