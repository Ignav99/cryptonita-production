# Phase 5: Expansion & Scaling — Implementation Plan

**Date:** April 13, 2026
**Status:** Research complete, ready for implementation
**Prerequisite:** Phases 1-4 done and deployed

---

## Priority Matrix (All items ranked by Impact/Effort ratio)

| # | Item | Effort | Impact | ROI | Category |
|---|------|--------|--------|-----|----------|
| 1 | Wire OCO orders into trade flow | 1-2 days | CRITICAL | 10/10 | Orders |
| 2 | Telegram notifications | 2-3 hours | HIGH | 9/10 | Infra |
| 3 | Render Starter ($7/mo) | 5 min | CRITICAL | 9/10 | Infra |
| 4 | Sector allocation limits | 1-2 days | HIGH | 9/10 | Diversification |
| 5 | Correlation-based position sizing | 2-3 days | HIGH | 8/10 | Diversification |
| 6 | Enhanced regime-based allocation | 2-3 days | HIGH | 8/10 | Diversification |
| 7 | Native trailing stop fallback | 1-2 days | MEDIUM | 7/10 | Orders |
| 8 | Binance testnet → production | 1-2 hours | HIGH | 7/10 | Exchange |
| 9 | Automated coin screener script | 3-4 days | MEDIUM | 7/10 | Expansion |
| 10 | Expand to 55-60 coins | 2-3 days | MEDIUM | 7/10 | Expansion |
| 11 | Hetzner VPS migration | 8-12 hours | HIGH | 6/10 | Infra |
| 12 | Funding rate arbitrage | 1-2 weeks | HIGH | 6/10 | Arbitrage |
| 13 | Multi-timeframe (4h+1d) | 5-7 days | MEDIUM-HIGH | 5/10 | Diversification |
| 14 | Bybit as second exchange | 2-3 weeks | MEDIUM | 5/10 | Exchange |
| 15 | GitHub Actions CI | 2 hours | MEDIUM | 5/10 | Infra |
| 16 | Grid trading (sideways markets) | 2-4 weeks | MEDIUM | 4/10 | Strategy |
| SKIP | Spread arbitrage | - | LOW | - | Not viable on Render |
| SKIP | Triangular arbitrage | - | LOW | - | Needs <50ms latency |
| SKIP | Kraken | - | LOW | - | Fees too high (0.25%) |
| SKIP | TWAP/VWAP | - | LOW | - | Position sizes too small |

---

## Sprint 1: Quick Wins (Week 1) — Cost: +$7/mo

### 1.1 Wire OCO Orders (CRITICAL)
**Why:** `create_oco_order` already exists in `BinanceService` but is NOT used. Current client-side polling misses SL during Render cold starts (30-60s wake-up).

**Implementation:**
- After each buy, immediately place server-side OCO (TP limit + SL stop-limit)
- OCO fires even if bot is offline — eliminates missed stop-losses
- Keep client-side DynamicRiskManager for multi-level TP (TP1/TP2/TP3)
- Hybrid: OCO protects downside, polling manages upside

**Files:** `src/bot/trading_bot.py` (after buy execution), `src/services/binance_service.py` (already has method)

### 1.2 Telegram Notifications
**Why:** Zero visibility into what the bot is doing in production.

**Events to alert:**
| Event | Priority |
|-------|----------|
| Trade executed (buy/sell) | High |
| Stop-loss triggered | High |
| Circuit breaker activated | Critical |
| Bot crashed/restarted | Critical |
| Model retrained & promoted | Medium |
| Daily P&L summary | Low |

**Files:** New `src/services/telegram_notifier.py`, wire into `trading_bot.py`, `auto_trainer.py`
**Config:** Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` env vars

### 1.3 Render Starter Upgrade
**Why:** Free tier sleeps after 15min inactivity. Bot stops monitoring positions. Catastrophic.
**Action:** Change plan in render.yaml or dashboard. 5 minutes.

### 1.4 Uptime Monitoring
- UptimeRobot (free): Monitor `/health` every 5 min
- Healthchecks.io (free): Bot pings after each scan cycle

---

## Sprint 2: Portfolio Intelligence (Week 2-3) — Cost: $0

### 2.1 Sector Allocation Limits
**Why:** Prevents concentration risk. If all 10 positions are L1 tokens and L1 sector crashes 30%, entire portfolio gets wiped.

**Implementation:**
```
COIN_SECTORS = {
    "LINK": "L1", "DOT": "L1", "ADA": "L1", ...
    "UNI": "DeFi", "AAVE": "DeFi", "CRV": "DeFi", ...
    "FET": "AI", "WLD": "AI", "RENDER": "AI", ...
    "DOGE": "Meme", "SHIB": "Meme", ...
}

SECTOR_LIMITS = {  # Max positions per sector (out of MAX_POSITIONS=10)
    "L1": 4, "DeFi": 3, "AI": 3, "Gaming": 2, "Meme": 2,
    "RWA": 2, "DePIN": 2, "L2": 3
}
```

**Files:** `config.py` (add mappings), `trading_bot.py` (check before opening position)

### 2.2 Correlation-Based Position Sizing
**Why:** SOL, AVAX, NEAR (all L1s, correlation ~0.85) in portfolio = effectively one big position. If they all dump, Kelly sizing doesn't account for the correlation.

**Implementation:**
- Compute 30d rolling correlation between candidate and held positions
- Penalty multiplier: avg_corr < 0.3 → 1.0x, avg_corr = 0.6 → 0.85x, avg_corr = 0.8 → 0.65x, avg_corr > 0.95 → 0.50x
- Apply after Kelly calculation
- Cheap: 30d x 10 correlations = 0.002 seconds

**Files:** New `src/models/correlation_engine.py`, modify `position_sizer.py`, `trading_bot.py`

### 2.3 Enhanced Regime-Based Allocation
**Why:** `RegimeDetector` already exists but only adjusts position size multiplier. Should also adjust thresholds, max positions, TP/SL.

**Regime parameter overrides:**
| Parameter | Bull | Sideways | Bear |
|-----------|------|----------|------|
| Position Size Mult | 1.0x | 0.7x | 0.4x |
| MAX_POSITIONS | 10 | 7 | 4 |
| Threshold adjust | -0.02 | 0 | +0.05 |
| STOP_LOSS_PCT | 5% | 5% | 4% |
| TAKE_PROFIT | 25% | 20% | 12% |

**Add fast regime detector** (7d BTC returns + vol) to supplement slow HMM (14d window).

**Files:** `config.py` (REGIME_ADJUSTMENTS dict), `regime_detector.py` (fast check), `trading_bot.py` (apply at scan start)

---

## Sprint 3: Expansion (Week 3-5) — Cost: $0

### 3.1 Automated Coin Screener
**Screening funnel:**
1. All Binance USDT pairs with TRADING status
2. 24h volume > $10M
3. Bid-ask spread < 0.10%
4. Listed > 6 months, market cap $50M-$50B
5. BTC correlation < 0.85
6. Average daily volatility > 3%

**Output:** Ranked JSON of candidates. Manual review before adding.
**Files:** New `scripts/coin_screener.py`

### 3.2 Expand to 55-60 Coins
**Priority sectors to add:**
| Sector | Candidates | Count |
|--------|-----------|-------|
| AI | TAO, ARKM, POND | +3 |
| RWA | ONDO, POLYX, CFX | +3 |
| DePIN | IOTA, IOTX, AR | +3 |
| New L2 | STX, TIA, MANTA, ZK, STRK | +5 |
| Gaming | PIXEL, PORTAL, BEAM | +3 |

**Files:** `config.py` (expand TICKERS, COIN_RISK_PROFILES), retrain model with expanded universe

### 3.3 Binance Production Migration
**Checklist:**
- [ ] Complete KYC on binance.com
- [ ] Create Ed25519 API key with "Spot & Margin Trading" permission
- [ ] IP-restrict to Render/VPS static IP
- [ ] Update env vars: BINANCE_API_KEY, BINANCE_API_SECRET
- [ ] Set TRADING_MODE=production
- [ ] Test with minimum order sizes first
- [ ] Update python-binance (Jan 2026 percent-encoding change)

---

## Sprint 4: Infrastructure (Month 2) — Cost: $4.10/mo

### 4.1 Hetzner CX22 Singapore VPS
- 4GB RAM, 2 vCPU, 40GB NVMe — $4.10/mo
- 8x RAM and 4x CPU vs Render Starter at 60% cost
- ~60ms latency to Binance (vs ~100ms from Render Oregon)

### 4.2 Docker Deployment
```yaml
services:
  api:
    command: python run_api.py
    mem_limit: 512m
  bot:
    command: python run_bot.py
    mem_limit: 1g
  db:
    image: postgres:16-alpine
    mem_limit: 512m
```

### 4.3 Self-hosted PostgreSQL
- No more 30-day expiry or 1GB storage limit
- Daily pg_dump backups to cloud storage

---

## Sprint 5: New Revenue Streams (Month 2-3) — Cost: $0

### 5.1 Funding Rate Arbitrage
**How:** Buy spot + short perpetual (same exchange). Collect funding fee every 8h. Delta-neutral.
- Expected APY: 15-25% (normal), 30-70% (bull market)
- Minimum capital: $2,000-$5,000
- Works on Render (slow polling OK, rates change every 8h)
- **Requires:** Binance Futures account, separate capital pool

### 5.2 Native Trailing Stop (Safety Net)
- Add `trailingDelta` parameter to Binance stop orders
- Set wider than client-side trailing (2.5x ATR vs 1.5x ATR)
- If bot goes offline, native trailing still protects gains

---

## Sprint 6: Advanced (Month 3+)

### 6.1 Bybit Integration
- Build exchange adapter abstraction (`ExchangeService` ABC)
- Unified V5 API, full ccxt support
- Same trading logic, different venue
- Enables cross-exchange redundancy

### 6.2 Multi-Timeframe (4h + 1d)
- Daily model for trend direction (strategic)
- 4h model for entry timing (tactical)
- Both aligned → 15% confidence boost
- Reduces false entries by filtering 4h-bearish setups

### 6.3 Grid Trading (Sideways Regime)
- Only when HMM regime = "ranging"
- 10-20% of portfolio allocated
- BTC/ETH only (deep liquidity)
- Expected: 2-5% monthly in ranging markets

---

## What We SKIP and Why

| Strategy | Why Skip |
|----------|----------|
| **Spread Arbitrage** | Needs <50ms latency + $50K+ capital. Render = 200-500ms. |
| **Triangular Arbitrage** | Needs WebSocket + sub-second execution. Margins razor-thin. |
| **Kraken** | 0.25%/0.40% fees = devastating for bot margins |
| **dYdX** | Perpetuals only, no spot. Irrelevant until adding derivatives. |
| **TWAP/VWAP** | Position sizes ($500) too small to cause meaningful slippage |
| **Full VWAP** | Overkill for current scale |

---

## Cost Projection

| Month | Infrastructure | Monthly Cost | Cumulative |
|-------|---------------|-------------|------------|
| 1 | Render Starter | $7 | $7 |
| 2 | Hetzner CX22 (replace Render) | $4.10 | $11.10 |
| 3+ | Hetzner CX22 (steady state) | $4.10 | $4.10/mo |

**Total first-year cost: ~$54** for production-grade 24/7 infrastructure.
