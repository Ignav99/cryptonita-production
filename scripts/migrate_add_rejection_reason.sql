-- ============================================================
-- CRYPTONITA: Add rejection_reason column to signals table
-- Run once via: render psql --service cryptonita-db < scripts/migrate_add_rejection_reason.sql
-- ============================================================

BEGIN;

-- 1. Add column (idempotent)
ALTER TABLE signals
ADD COLUMN IF NOT EXISTS rejection_reason VARCHAR(50) DEFAULT NULL;

-- 2. Backfill existing HOLDs: above_ceiling if prob >= 0.42, below_floor otherwise
UPDATE signals
SET rejection_reason = CASE
    WHEN probability >= 0.42 THEN 'above_ceiling'
    ELSE 'below_floor'
END
WHERE signal_type = 'HOLD'
  AND rejection_reason IS NULL;

-- 3. Verify
SELECT
    signal_type,
    rejection_reason,
    COUNT(*) as count,
    ROUND(AVG(probability)::numeric, 4) as avg_probability
FROM signals
GROUP BY signal_type, rejection_reason
ORDER BY signal_type, rejection_reason;

COMMIT;
