#!/usr/bin/env python3
"""
1-YEAR REALISTIC SIMULATION — Cryptonita V4.1 Optimized
=========================================================
Focused Monte Carlo for realistic 1-year projection with:
- Optimized TP/SL from 30yr simulation (TP1=12%, TP2=25%, TP3=50%)
- Tier-aware position sizing and risk management
- Progressive trailing stop (tightens as profit grows)
- Monthly breakdown with contribution tracking
- 3 scenarios: Conservative (Sideways), Normal (Mixed), Aggressive (Bull)

Usage: python scripts/simulation_1year.py
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Tuple


# ═══════════════════════════════════════════════════════════════
# MARKET SCENARIOS
# ═══════════════════════════════════════════════════════════════

@dataclass
class Scenario:
    name: str
    description: str
    # Regime probabilities [bull, sideways, bear] for starting weights
    regime_weights: List[float]
    # Signal quality modifier
    signal_quality: float

SCENARIOS = [
    Scenario("BEAR/SIDEWAYS", "Mercado lateral/bajista (peor caso razonable)",
             [0.15, 0.45, 0.40], 0.90),
    Scenario("NORMAL/MIXED", "Mercado mixto típico (caso base)",
             [0.30, 0.45, 0.25], 1.00),
    Scenario("BULL", "Mercado alcista (mejor caso razonable)",
             [0.55, 0.35, 0.10], 1.10),
]


# ═══════════════════════════════════════════════════════════════
# SIMULATION CONFIG
# ═══════════════════════════════════════════════════════════════

INITIAL_EUR = 2500.0
MONTHLY_EUR = 400.0
EUR_USD = 1.08
N_SIMS = 5000
DAYS = 365

# Costs
FEE = 0.001
SLIPPAGE = 0.0005

# Risk management — OPTIMIZED
MAX_POSITIONS = 10
MAX_PORTFOLIO_RISK = 0.30

# Optimized multi-level TP (from Monte Carlo analysis)
TP_LEVELS = [
    {"name": "TP1", "pct": 0.12, "sell_frac": 0.25},  # Sell 25% at +12%
    {"name": "TP2", "pct": 0.25, "sell_frac": 0.35},  # Sell 35% at +25%
    {"name": "TP3", "pct": 0.50, "sell_frac": 1.00},  # Sell 100% at +50%
]

# Regimes
REGIME_TRANSITION = np.array([
    [0.985, 0.012, 0.003],
    [0.008, 0.987, 0.005],
    [0.004, 0.016, 0.980],
])

@dataclass
class Regime:
    name: str
    daily_ret: float
    daily_vol: float
    signal_rate: float  # high-confidence signals per day across all tickers
    base_wr: float

REGIMES = [
    Regime("Bull",     +0.0020, 0.035, 0.12, 0.60),
    Regime("Sideways", +0.0003, 0.028, 0.07, 0.48),
    Regime("Bear",    -0.0012, 0.042, 0.04, 0.35),
]

# Tiers
@dataclass
class Tier:
    name: str
    threshold: float
    max_pos: float
    kelly_m: float
    n_coins: int
    vol_mult: float
    wr_bonus: float
    # Optimized: tier-specific TP/SL multipliers
    sl_mult: float
    tp_mult: float
    trailing_activation: float

TIERS = [
    Tier("BlueChip", 0.93, 0.15, 1.2, 5,  0.8, 0.03, 1.2, 1.3, 0.04),
    Tier("LargeCap", 0.95, 0.12, 1.0, 7,  1.0, 0.02, 1.0, 1.1, 0.05),
    Tier("MidCap",   0.97, 0.08, 0.8, 20, 1.3, 0.01, 1.0, 1.0, 0.05),
    Tier("Meme",     0.99, 0.04, 0.5, 5,  1.8, 0.00, 0.7, 0.8, 0.03),
]

TOTAL_COINS = sum(t.n_coins for t in TIERS)


def kelly(wr, b=4.0, frac=0.25):
    """Fractional Kelly. b = TP/SL ratio (20%/5% = 4.0)"""
    full = (wr * b - (1 - wr)) / b
    return max(0.0, frac * full)


def sim_one_year(rng, scenario):
    """Simulate 1 year with multi-level TP, trailing stop, tier-aware sizing."""
    cash = INITIAL_EUR * EUR_USD
    contributions_eur = INITIAL_EUR
    positions = []  # (norm_price, peak_norm, size_usd, tier_idx, day, tp1_hit, tp2_hit)

    monthly_values = []
    total_trades = 0
    total_wins = 0
    total_fees = 0.0
    peak = cash
    max_dd = 0.0

    # Build tier boundaries
    boundaries = []
    cum = 0
    for t in TIERS:
        boundaries.append((cum, cum + t.n_coins))
        cum += t.n_coins

    regime_idx = rng.choice(3, p=scenario.regime_weights)

    for day in range(DAYS):
        # Monthly contribution
        if day > 0 and day % 30 == 0:
            contrib = MONTHLY_EUR * EUR_USD
            cash += contrib
            contributions_eur += MONTHLY_EUR

        # Regime
        regime_idx = rng.choice(3, p=REGIME_TRANSITION[regime_idx])
        regime = REGIMES[regime_idx]

        # Update positions
        new_positions = []
        for norm, peak_n, sz, ti, entry_day, tp1h, tp2h in positions:
            tier = TIERS[ti]
            ret = rng.normal(regime.daily_ret, regime.daily_vol * tier.vol_mult)
            norm *= (1 + ret)
            peak_n = max(peak_n, norm)
            pnl_pct = norm - 1.0

            # Dynamic SL (tier-adjusted)
            base_sl = 0.05 * tier.sl_mult
            sl_pct = max(0.03, min(0.12, base_sl))

            # Trailing stop logic
            trailing_active = pnl_pct > tier.trailing_activation
            if trailing_active:
                # Progressive tightening
                if tp2h:
                    trail_dist = 0.015
                elif tp1h:
                    trail_dist = 0.025
                elif pnl_pct > 0.30:
                    trail_dist = 0.02
                elif pnl_pct > 0.15:
                    trail_dist = 0.03
                else:
                    trail_dist = 0.04

                # Trailing stop = peak - distance
                trailing_sl = peak_n - trail_dist - 1.0  # Relative to entry
                # If trailing stop triggers
                if norm < (1.0 + trailing_sl) and trailing_sl > 0:
                    exit_pnl = sz * trailing_sl
                    fee = (sz + exit_pnl) * (FEE + SLIPPAGE)
                    cash += sz + exit_pnl - fee
                    total_fees += fee
                    total_trades += 1
                    if trailing_sl > 0:
                        total_wins += 1
                    continue

            # Stop loss
            if pnl_pct <= -sl_pct:
                loss = sz * sl_pct
                fee = sz * (FEE + SLIPPAGE)
                cash += sz - loss - fee
                total_fees += fee
                total_trades += 1
                continue

            # TP levels (tier-adjusted)
            tp1_target = TP_LEVELS[0]["pct"] * tier.tp_mult
            tp2_target = TP_LEVELS[1]["pct"] * tier.tp_mult
            tp3_target = TP_LEVELS[2]["pct"] * tier.tp_mult

            # TP1 hit
            if pnl_pct >= tp1_target and not tp1h:
                sell_frac = TP_LEVELS[0]["sell_frac"]
                sell_usd = sz * sell_frac
                gain = sell_usd * pnl_pct
                fee = (sell_usd + gain) * (FEE + SLIPPAGE)
                cash += sell_usd + gain - fee
                total_fees += fee
                total_trades += 1
                total_wins += 1
                sz *= (1 - sell_frac)  # Remaining position
                tp1h = True

            # TP2 hit
            if pnl_pct >= tp2_target and not tp2h and tp1h:
                sell_frac = TP_LEVELS[1]["sell_frac"]
                sell_usd = sz * sell_frac
                gain = sell_usd * pnl_pct
                fee = (sell_usd + gain) * (FEE + SLIPPAGE)
                cash += sell_usd + gain - fee
                total_fees += fee
                total_trades += 1
                total_wins += 1
                sz *= (1 - sell_frac)
                tp2h = True

            # TP3 hit — exit all remaining
            if pnl_pct >= tp3_target and tp2h:
                gain = sz * pnl_pct
                fee = (sz + gain) * (FEE + SLIPPAGE)
                cash += sz + gain - fee
                total_fees += fee
                total_trades += 1
                total_wins += 1
                continue

            # Time exit (21 days max hold)
            if (day - entry_day) >= 21:
                val = sz * norm
                fee = val * (FEE + SLIPPAGE)
                cash += val - fee
                total_fees += fee
                total_trades += 1
                if norm > 1.0:
                    total_wins += 1
                continue

            new_positions.append((norm, peak_n, sz, ti, entry_day, tp1h, tp2h))

        positions = new_positions

        # Generate new signals
        scores = np.zeros(TOTAL_COINS)
        signal_rate = regime.signal_rate * scenario.signal_quality
        is_signal = rng.random(TOTAL_COINS) < signal_rate
        n_noise = (~is_signal).sum()
        n_sig = is_signal.sum()
        scores[~is_signal] = rng.uniform(0.30, 0.88, n_noise)
        if n_sig > 0:
            scores[is_signal] = 0.85 + rng.beta(8, 2, n_sig) * 0.15

        for ci in range(TOTAL_COINS):
            if len(positions) >= MAX_POSITIONS:
                break

            ti = 0
            for idx, (lo, hi) in enumerate(boundaries):
                if lo <= ci < hi:
                    ti = idx
                    break
            tier = TIERS[ti]

            if scores[ci] < tier.threshold:
                continue

            portfolio_now = cash + sum(p[2] * p[0] for p in positions)
            if portfolio_now <= 0:
                break

            wr = min(0.80, regime.base_wr + tier.wr_bonus + (scores[ci] - 0.90) * 0.5)
            k = kelly(wr, b=4.0, frac=0.25)
            pos_pct = k * tier.kelly_m
            pos_pct = max(0.02, min(tier.max_pos, pos_pct))
            regime_scale = [1.0, 0.7, 0.5][regime_idx]
            pos_pct *= regime_scale
            pos_pct = max(0.02, min(tier.max_pos, pos_pct))

            pos_usd = cash * pos_pct
            if pos_usd < 10:
                continue

            total_pos = sum(p[2] for p in positions)
            if (total_pos + pos_usd) / max(1, portfolio_now) > MAX_PORTFOLIO_RISK:
                continue

            fee = pos_usd * (FEE + SLIPPAGE)
            cash -= pos_usd
            total_fees += fee
            positions.append((1.0, 1.0, pos_usd - fee, ti, day, False, False))

        # Portfolio value
        pos_val = sum(p[2] * p[0] for p in positions)
        portfolio = cash + pos_val

        if portfolio > peak:
            peak = portfolio
        dd = (peak - portfolio) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)

        # Monthly snapshot
        if (day + 1) % 30 == 0 or day == DAYS - 1:
            monthly_values.append(portfolio / EUR_USD)

    final_usd = cash + sum(p[2] * p[0] for p in positions)
    final_eur = final_usd / EUR_USD
    profit_eur = final_eur - contributions_eur
    wr = total_wins / total_trades * 100 if total_trades > 0 else 0

    return {
        "final_eur": final_eur,
        "contributed_eur": contributions_eur,
        "profit_eur": profit_eur,
        "roi_pct": profit_eur / contributions_eur * 100 if contributions_eur > 0 else 0,
        "max_dd": max_dd * 100,
        "trades": total_trades,
        "win_rate": wr,
        "fees_eur": total_fees / EUR_USD,
        "monthly": monthly_values,
    }


def run_scenario(scenario, n_sims=N_SIMS, seed=42):
    rng = np.random.default_rng(seed)
    results = []
    for _ in range(n_sims):
        results.append(sim_one_year(rng, scenario))
    return results


def main():
    total_contributed = INITIAL_EUR + MONTHLY_EUR * 12
    print(f"""
{'█'*70}
  CRYPTONITA V4.1 — SIMULACIÓN 1 AÑO REALISTA
  {N_SIMS:,} simulaciones por escenario
  Capital inicial: €{INITIAL_EUR:,.0f} + €{MONTHLY_EUR}/mes = €{total_contributed:,.0f} invertidos
  TP multinivel: +12% / +25% / +50% (con trailing stop progresivo)
  SL dinámico: 3-12% según tier y volatilidad
{'█'*70}
""")

    all_results = {}

    for scenario in SCENARIOS:
        print(f"  Simulando: {scenario.name} ({scenario.description})...", flush=True)
        results = run_scenario(scenario)
        all_results[scenario.name] = results

        finals = np.array([r["final_eur"] for r in results])
        profits = np.array([r["profit_eur"] for r in results])
        rois = np.array([r["roi_pct"] for r in results])
        dds = np.array([r["max_dd"] for r in results])
        wrs = np.array([r["win_rate"] for r in results])
        trades = np.array([r["trades"] for r in results])
        fees = np.array([r["fees_eur"] for r in results])

        # Monthly progression
        all_monthly = np.array([r["monthly"] for r in results])
        n_months = all_monthly.shape[1]
        monthly_med = np.median(all_monthly, axis=0)
        monthly_p10 = np.percentile(all_monthly, 10, axis=0)
        monthly_p90 = np.percentile(all_monthly, 90, axis=0)

        print(f"""
{'─'*70}
  ESCENARIO: {scenario.name}
  {scenario.description}
{'─'*70}

  Invertido: €{total_contributed:,.0f} en 12 meses

  ╔═══════════════════════════════════════════════════════════════╗
  ║  PORTFOLIO A 1 AÑO                                         ║
  ╠═══════════════════════════════════════════════════════════════╣
  ║  P5  (peor caso):    €{np.percentile(finals,5):>10,.0f}  (ROI: {np.percentile(rois,5):>+6.1f}%)    ║
  ║  P10:                €{np.percentile(finals,10):>10,.0f}  (ROI: {np.percentile(rois,10):>+6.1f}%)    ║
  ║  P25:                €{np.percentile(finals,25):>10,.0f}  (ROI: {np.percentile(rois,25):>+6.1f}%)    ║
  ║  ► MEDIANA:          €{np.median(finals):>10,.0f}  (ROI: {np.median(rois):>+6.1f}%)    ║
  ║  P75:                €{np.percentile(finals,75):>10,.0f}  (ROI: {np.percentile(rois,75):>+6.1f}%)    ║
  ║  P90:                €{np.percentile(finals,90):>10,.0f}  (ROI: {np.percentile(rois,90):>+6.1f}%)    ║
  ║  P95 (mejor caso):   €{np.percentile(finals,95):>10,.0f}  (ROI: {np.percentile(rois,95):>+6.1f}%)    ║
  ╚═══════════════════════════════════════════════════════════════╝

  Métricas:
  │  Max Drawdown:  {np.percentile(dds,10):>5.1f}%  /  {np.median(dds):>5.1f}%  /  {np.percentile(dds,90):>5.1f}%  (P10/Med/P90)
  │  Win Rate:      {np.percentile(wrs,10):>5.1f}%  /  {np.median(wrs):>5.1f}%  /  {np.percentile(wrs,90):>5.1f}%
  │  Trades:        {np.median(trades):>5.0f} mediana / {np.mean(trades):>5.0f} media
  │  Fees pagadas:  €{np.median(fees):>6.0f} mediana

  Evolución mensual (€):
  {'Mes':>5} │ {'P10':>10} │ {'Mediana':>10} │ {'P90':>10} │ {'Aportado':>10}
  {'─'*5}─┼─{'─'*10}─┼─{'─'*10}─┼─{'─'*10}─┼─{'─'*10}""")

        for m in range(n_months):
            month_num = m + 1
            aportado = INITIAL_EUR + MONTHLY_EUR * month_num
            print(f"  {month_num:>5} │ €{monthly_p10[m]:>8,.0f} │ €{monthly_med[m]:>8,.0f} │ €{monthly_p90[m]:>8,.0f} │ €{aportado:>8,.0f}")

    # Summary comparison
    print(f"""
{'█'*70}
  RESUMEN COMPARATIVO — 1 AÑO
  (Invertidos: €{total_contributed:,.0f})
{'█'*70}

  {'Escenario':<20} │ {'P10':>10} │ {'Mediana':>10} │ {'P90':>10} │ {'ROI Med':>8} │ {'WR Med':>7}
  {'─'*20}─┼─{'─'*10}─┼─{'─'*10}─┼─{'─'*10}─┼─{'─'*8}─┼─{'─'*7}""")

    for scenario in SCENARIOS:
        res = all_results[scenario.name]
        f = np.array([r["final_eur"] for r in res])
        roi = np.array([r["roi_pct"] for r in res])
        wr = np.array([r["win_rate"] for r in res])
        print(f"  {scenario.name:<20} │ €{np.percentile(f,10):>8,.0f} │ €{np.median(f):>8,.0f} │ €{np.percentile(f,90):>8,.0f} │ {np.median(roi):>+6.1f}% │ {np.median(wr):>5.1f}%")

    # Realistic expectations
    normal = all_results["NORMAL/MIXED"]
    n_finals = np.array([r["final_eur"] for r in normal])
    n_profits = np.array([r["profit_eur"] for r in normal])
    n_rois = np.array([r["roi_pct"] for r in normal])
    n_trades = np.array([r["trades"] for r in normal])
    n_wrs = np.array([r["win_rate"] for r in normal])

    prob_profit = np.mean(n_profits > 0) * 100
    prob_10pct = np.mean(n_rois > 10) * 100
    prob_loss_5 = np.mean(n_rois < -5) * 100
    avg_monthly_profit = np.median(n_profits) / 12

    print(f"""
{'═'*70}
  QUÉ ESPERAR EN UN AÑO NORMAL (escenario mixto)
{'═'*70}

  Inviertes: €{total_contributed:,.0f} (€2,500 + 12 × €400)

  ┌─────────────────────────────────────────────────────────────┐
  │  Resultado más probable:                                    │
  │  Portfolio: €{np.median(n_finals):,.0f} → Ganancia: €{np.median(n_profits):,.0f}        │
  │  Eso son ~€{avg_monthly_profit:,.0f}/mes de beneficio medio                 │
  │                                                             │
  │  Trades: ~{np.median(n_trades):.0f} operaciones en el año                   │
  │  Win rate: {np.median(n_wrs):.0f}% (normal en estrategias de ratio alto)    │
  │  Max drawdown: {np.median(np.array([r['max_dd'] for r in normal])):.1f}% (temporal, se recupera)            │
  └─────────────────────────────────────────────────────────────┘

  Probabilidades:
  │  P(acabar en positivo):  {prob_profit:>5.1f}%
  │  P(ganar > 10%):         {prob_10pct:>5.1f}%
  │  P(perder > 5%):         {prob_loss_5:>5.1f}%

  REALIDAD: Con ratio TP/SL de 4:1, puedes perder 63% de trades
  y aún ganar dinero. 1 trade ganador (+20%) compensa 4 perdedores (-5%).
""")


if __name__ == "__main__":
    main()
