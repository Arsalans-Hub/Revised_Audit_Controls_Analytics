-- 02_sod_and_access_risk.sql
-- Core IT General Controls (ITGC) test: Segregation of Duties (SoD) and
-- terminated-user access review. These are standard tests performed in
-- SOX ITGC and access-control audit procedures.

-- Segregation of Duties conflicts: users who currently hold BOTH sides of
-- a defined incompatible-role pair (e.g., can both create AND approve an
-- AP payment).
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
  AND (a2.access_end_date IS NULL OR a2.access_end_date = '');

-- Orphaned access: terminated employees whose access was never revoked
-- (access_end_date blank despite a termination_date on file). A classic
-- ITGC exception -- and a real security exposure.
SELECT
    u.user_id, u.first_name, u.last_name, u.termination_date,
    a.role_name, a.granted_date
FROM users u
JOIN user_access_clean a ON a.user_id = u.user_id
WHERE u.status = 'Terminated'
  AND (a.access_end_date IS NULL OR a.access_end_date = '');
