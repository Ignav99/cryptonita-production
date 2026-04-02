# Threshold Calibration — 2 April 2026

## Context
- Model V4 retrained on 2 April 2026 with data up to 1 April 2026
- 39 tickers, 89 features, XGBoost+LightGBM+CatBoost ensemble
- Training metrics: AUC 0.9923, F1 0.80, CV AUC 0.6721
- Analysis based on 10 days of data (March 23 - April 1, 2026)

## Probability Distribution (model output)
```
Min:    0.0555
P25:    0.0827
Median: 0.1067
P75:    0.1395
P90:    0.2062
P95:    0.2579
Max:    0.8997
```
Most signals (75%) produce probabilities below 0.14. Only 5% exceed 0.26.

## Previous Configuration (before this change)
3 confidence levels per tier:

| Tier | HIGH | MEDIUM | EXPLORATORY |
|------|------|--------|-------------|
| T1 Blue Chip | >= 0.50 | >= 0.35 | >= 0.20 |
| T2 Large Cap | >= 0.45 | >= 0.30 | >= 0.18 |
| T3 Mid Cap   | >= 0.40 | >= 0.25 | >= 0.15 |
| T4 Meme      | >= 0.55 | >= 0.40 | >= 0.25 |

## Win Rate Analysis (TP 3% vs SL 3%, 10 days)

| Level | Signals | Win Rate | Avg Prob | Avg Max Gain | Avg Max Loss | PnL (sized) |
|-------|---------|----------|----------|-------------|-------------|-------------|
| HIGH | 5 (0.5/day) | **25%** (1/4) | 0.602 | +17.4% | -7.9% | -$60 |
| MEDIUM | 14 (1.4/day) | **54.5%** (6/11) | 0.312 | +22.2% | -7.8% | +$15 |
| EXPLORATORY | 45 (4.5/day) | **48.7%** (19/39) | 0.206 | +11.4% | -7.8% | -$7.50 |
| HOLD | 326 | — | — | — | — | — |

**Total simulated PnL: -$52.50 (-0.53% on $10K portfolio)**

## Key Findings

1. **EXPLORATORY is pure noise**: 48.7% WR is essentially a coin flip. Generated 45 signals
   in 10 days (4.5/day) with zero statistical edge. Loses money after commissions.

2. **MEDIUM has edge**: 54.5% WR with 6 wins vs 5 losses. The only profitable level.
   Average probability of winning MEDIUM signals: 0.31. This is the minimum entry point.

3. **HIGH has too few samples**: Only 4 completed trades (1 win / 3 losses = 25% WR).
   Cannot draw conclusions from 4 trades. Need 30+ for statistical significance.
   The one winning HIGH signal (ALGOUSDT, prob=0.90) gained +9.6%.

4. **Edge starts at ~0.30 probability**: Below 0.30, win rates cluster around 48-49%.
   Above 0.30, win rates jump to 54%+. This is the empirical threshold for positive edge.

5. **Top performing tickers**: ALGOUSDT (62% WR, avg prob 0.39), DYDXUSDT (67% WR),
   RENDERUSDT (62% WR), ICPUSDT (67% WR), LDOUSDT (67% WR), NEARUSDT (67% WR).

6. **Worst tickers**: APTUSDT (0% WR on 4 signals), SANDUSDT (0% WR), MANAUSDT (0% WR),
   VETUSDT (0% WR). These may need higher thresholds or exclusion.

## New Configuration (applied 2 April 2026)

### Decision: Eliminate EXPLORATORY, raise thresholds

| Tier | HIGH | MEDIUM | EXPLORATORY |
|------|------|--------|-------------|
| T1 Blue Chip | >= 0.55 (+0.05) | >= 0.38 (+0.03) | DISABLED |
| T2 Large Cap | >= 0.50 (+0.05) | >= 0.35 (+0.05) | DISABLED |
| T3 Mid Cap   | >= 0.45 (+0.05) | >= 0.30 (+0.05) | DISABLED |
| T4 Meme      | >= 0.60 (+0.05) | >= 0.42 (+0.02) | DISABLED |

### Position Sizing (testing phase)
| Level | Position Mult | TP Mult | SL Mult | Max Positions |
|-------|-------------|---------|---------|---------------|
| HIGH | 75% Kelly | 1.0x | 1.0x | 8 |
| MEDIUM | 40% Kelly | 0.70x | 0.75x | 5 |
| EXPLORATORY | 0% (disabled) | — | — | 0 |

### Rationale
- **EXPLORATORY disabled**: 48.7% WR = no edge = random trades = loss after fees.
  Setting `threshold_low = threshold_medium` and `position_mult = 0.0` means the code
  path exists but will never execute a trade.
- **MEDIUM raised to 0.30-0.38**: The empirical edge boundary is ~0.30. We add margin
  per tier (higher risk tiers get higher minimum).
- **HIGH raised to 0.45-0.60**: More conservative. Only truly strong signals get full
  position. We need more data before trusting HIGH signals (only 4 samples so far).
- **Testing phase sizing**: HIGH at 75% instead of 100%, MEDIUM at 40% instead of 50%.
  After 15-20 days of data collection, we'll calibrate to final values.

### Expected Signal Volume (per 10 days, estimated)
- OLD config: ~64 signals (6 HIGH + 14 MEDIUM + 45 EXPLORATORY)
- NEW config: ~15-19 signals (5 HIGH + 10-14 MEDIUM + 0 EXPLORATORY)
- Reduction: ~70% fewer trades, all with demonstrated edge

## Next Steps (review around April 17-20, 2026)
1. Collect 15-20 more days of production data with new thresholds
2. Auto-retrain model around April 9 (7-day cycle)
3. After 30 total days:
   - Re-analyze win rates per level with larger sample sizes
   - Decide if HIGH threshold needs adjustment (need 30+ trades)
   - Decide if MEDIUM threshold is optimal or should be tightened/loosened
   - Consider per-ticker threshold overrides for consistently bad performers
   - Calibrate final position sizing (remove "testing phase" reduction)
   - Evaluate if commission structure supports the trade frequency
