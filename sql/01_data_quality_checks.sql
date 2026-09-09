-- 01_data_quality_checks.sql
-- Data quality / completeness checks run against the raw ERP export before
-- it is trusted for control testing. Mirrors the kind of checks an auditor
-- runs before relying on client-provided data ("data assurance").

-- Completeness: how many user records are missing a department (a required
-- field for routing access reviews to the right business owner)?
SELECT COUNT(*) AS missing_department
FROM users
WHERE department IS NULL OR TRIM(department) = '';

-- Validity: how many user emails don't match a basic email pattern?
SELECT COUNT(*) AS invalid_email
FROM users
WHERE email NOT LIKE '%_@__%.__%';

-- Duplicate access grant records (same user/role/system granted twice --
-- an export artifact that would double-count access if not de-duplicated).
SELECT user_id, role_id, system, granted_date, COUNT(*) AS occurrences
FROM user_access
GROUP BY user_id, role_id, system, granted_date
HAVING COUNT(*) > 1;

-- Incomplete access records: missing "granted_by" means we cannot verify
-- who authorized the access -- itself a control gap worth flagging.
SELECT COUNT(*) AS missing_granted_by
FROM user_access
WHERE granted_by IS NULL OR TRIM(granted_by) = '';

-- Inconsistent formatting: role names with stray casing/whitespace that
-- would break any exact-match logic downstream if not normalized first.
SELECT DISTINCT role_name
FROM user_access
WHERE role_name <> TRIM(role_name)
   OR role_name <> UPPER(SUBSTR(role_name,1,1)) || SUBSTR(role_name,2);
