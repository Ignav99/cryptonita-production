# Walk-Forward Backtest V5 — 2026-06-03

> **Method:** Train on first 75% of each coin's history, predict on last 25%. Zero lookahead. Triple-barrier P&L simulation.

- **TP return:** +5%  |  **SL loss:** -3%
- **Long threshold:** per-coin (disabled=1.0, optimized=0.40-0.45, default=0.65)  |  **Short threshold:** 0.35
- **Train split:** 75% / Test: 25%
- **Tickers tested:** 25

---

## Per-Ticker Results

| Ticker | Test Period | Long Win% | Short Win% | Overall Win% | Return% | Avg/Trade% | Sharpe | MaxDD% | N Long | N Short | OOS Acc |
|--------|-------------|-----------|------------|--------------|---------|------------|--------|--------|--------|---------|---------|
| ATOM-USD   | 2024-03-02 → 2025-10-28 | 26.1% | 60.9% | 59.0% | +1062.0% | +2.4% | 9.33 | -37.4% |     23 |     419 | 0.540 |
| ARB-USD    | 2024-02-13 → 2025-10-28 | 58.4% | 33.3% | 58.3% | +1007.0% | +2.2% | 8.21 | -71.1% |    457 |       3 | 0.572 |
| ADA-USD    | 2024-02-13 → 2025-10-28 | N/A | 56.0% | 56.0% | +958.0% | +2.1% | 7.90 | -42.2% |      0 |     459 | 0.506 |
| NEAR-USD   | 2024-07-25 → 2025-10-28 | 30.8% | 55.1% | 54.4% | +903.0% | +2.0% | 9.12 | -44.6% |     13 |     439 | 0.542 |
| MATIC-USD  | 2023-10-02 → 2025-03-24 | 34.0% | 52.0% | 50.2% | +883.0% | +1.7% | 7.60 | -67.0% |     53 |     465 | 0.487 |
| DOT-USD    | 2024-07-12 → 2025-10-28 | 22.2% | 51.5% | 51.0% | +865.0% | +1.8% | 8.59 | -49.1% |      9 |     460 | 0.508 |
| RUNE-USD   | 2024-04-04 → 2025-10-28 | N/A | 49.4% | 49.4% | +839.0% | +1.7% | 7.10 | -45.6% |      0 |     500 | 0.466 |
| MANA-USD   | 2024-02-13 → 2025-10-28 | 40.0% | 50.9% | 50.8% | +810.0% | +1.8% | 6.78 | -36.7% |      5 |     450 | 0.413 |
| SAND-USD   | 2024-07-10 → 2025-10-28 | 15.2% | 54.0% | 51.1% | +797.0% | +1.8% | 7.87 | -45.6% |     33 |     415 | 0.498 |
| APT-USD    | 2024-08-01 → 2025-06-24 | N/A | 53.4% | 53.4% | +701.0% | +2.1% | 10.54 | -37.4% |      0 |     328 | 0.534 |
| AVAX-USD   | 2024-07-19 → 2025-10-28 | 29.1% | 58.7% | 50.7% | +681.0% | +1.7% | 6.91 | -51.6% |    110 |     298 | 0.482 |
| OP-USD     | 2024-12-01 → 2025-10-28 | 11.1% | 60.0% | 55.6% | +651.0% | +2.2% | 9.77 | -44.6% |     27 |     270 | 0.548 |
| FTM-USD    | 2023-07-12 → 2025-01-13 | 27.0% | 50.4% | 45.2% | +615.0% | +1.2% | 5.12 | -39.3% |    111 |     393 | 0.437 |
| SOL-USD    | 2024-06-09 → 2025-10-28 | 32.7% | 48.0% | 46.1% | +526.0% | +1.3% | 5.11 | -36.7% |     49 |     352 | 0.396 |
| AAVE-USD   | 2024-07-22 → 2025-10-28 | N/A | 45.0% | 45.0% | +522.0% | +1.2% | 5.07 | -65.6% |      0 |     440 | 0.427 |
| INJ-USD    | 2024-07-27 → 2025-10-28 | 26.8% | 49.7% | 42.9% | +521.0% | +1.2% | 5.35 | -38.6% |    127 |     302 | 0.423 |
| ALGO-USD   | 2024-03-27 → 2025-10-28 | N/A | 56.2% | 56.2% | +456.0% | +2.2% | 5.53 | -24.9% |      0 |     208 | 0.356 |
| LINK-USD   | 2024-02-13 → 2025-10-28 | N/A | 48.0% | 48.0% | +369.0% | +1.5% | 4.05 | -35.5% |      0 |     244 | 0.308 |
| DOGE-USD   | 2024-02-13 → 2025-10-28 | N/A | 51.6% | 51.6% | +340.0% | +1.5% | 3.69 | -29.3% |      0 |     225 | 0.356 |
| FIL-USD    | 2024-02-13 → 2025-10-28 | N/A | 35.7% | 35.7% | +261.0% | +1.4% | 3.97 | -11.5% |      0 |     185 | 0.245 |
| SUI-USD    | 2023-11-15 → 2024-06-04 | 44.4% | 33.3% | 34.1% | +45.0% | +0.3% | 1.23 | -49.1% |      9 |     123 | 0.355 |
| GRT-USD    | 2021-10-21 → 2022-04-01 | 33.3% | 39.2% | 38.3% | +43.0% | +0.7% | 1.91 | -23.5% |      9 |      51 | 0.331 |
| RNDR-USD   | 2023-07-12 → 2024-07-21 | N/A | 50.0% | 50.0% | +16.0% | +1.6% | 1.06 | -5.9% |      0 |      10 | 0.263 |
| UNI-USD    | 2023-12-03 → 2025-04-17 | N/A | 35.8% | 35.8% | +10.0% | +0.1% | 0.21 | -62.3% |      0 |      81 | 0.373 |
| STX-USD    | 2023-12-09 → 2025-04-23 | N/A | 10.6% | 10.6% | -28.0% | -0.2% | -0.68 | -63.6% |      0 |     179 | 0.211 |

---

## Aggregate Summary

| Metric | Value |
|--------|-------|
| Tickers in report | 25 |
| Total signals (LONG+SHORT) | 8,334 |
| Total LONG signals | 1,035 |
| Total SHORT signals | 7,299 |
| Avg Long Win Rate | 30.8% |
| Avg Short Win Rate | 47.5% |
| Avg Overall Win Rate | 47.2% |
| Median Return% | +615.0% |
| Mean Return% | +554.1% |
| Best Return% | +1062.0% |
| Worst Return% | -28.0% |
| Median Sharpe | 5.53 |
| Mean Sharpe | 5.65 |
| Avg Max Drawdown | -42.3% |
| Avg OOS Accuracy | 0.423 |
| % Tickers with positive return | 96% |
| % Tickers with Sharpe > 0.5 | 92% |

---

## Interpretation

### Is V5 learning something real?

**Verdict: POSITIVE — Win rate exceeds asymmetric break-even. Genuine edge present.**

- Asymmetric break-even win rate: 37.5%  (TP=+5% / SL=-3%)
- Observed avg overall win rate: 47.2%
- Positive-return tickers: 96% of 25
- Avg Sharpe ratio: 5.65 (>0.5 = acceptable, >1.0 = good)

### Caveats

- Triple-barrier TP/SL returns are approximations (ATR-based, not exact fill prices)
- No transaction costs or slippage modeled
- SHORT signals assume frictionless shorting
- Past performance does not guarantee future results

*Generated: 2026-06-03 00:32:42*