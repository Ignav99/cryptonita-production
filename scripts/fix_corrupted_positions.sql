-- ============================================================
-- CRYPTONITA: Corrupted Positions Repair
-- Run once via: render psql --service cryptonita-db < scripts/fix_corrupted_positions.sql
-- ============================================================

BEGIN;

-- 1. Audit before
SELECT ticker, quantity, remaining_quantity, total_value, pnl
FROM positions
ORDER BY ticker;

-- 2. Clamp remaining_quantity: must be [0, quantity]
UPDATE positions
SET remaining_quantity = GREATEST(0, LEAST(quantity, remaining_quantity)),
    total_value = GREATEST(0, LEAST(quantity, remaining_quantity)) * COALESCE(current_price, avg_buy_price),
    pnl = (COALESCE(current_price, avg_buy_price) - avg_buy_price)
          * GREATEST(0, LEAST(quantity, remaining_quantity)),
    pnl_percentage = CASE
        WHEN avg_buy_price > 0 THEN
            ((COALESCE(current_price, avg_buy_price) - avg_buy_price) / avg_buy_price) * 100
        ELSE 0
    END,
    last_update = NOW()
WHERE remaining_quantity < 0
   OR remaining_quantity > quantity * 1.01;

-- 3. Audit after
SELECT ticker, quantity, remaining_quantity, total_value, pnl
FROM positions
ORDER BY ticker;

COMMIT;
