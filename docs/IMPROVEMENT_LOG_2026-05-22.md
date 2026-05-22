# Cryptonita — Engine Upgrade Log
## Iniciado: 2026-05-22

---

## Contexto

Auditoría completa del sistema tras ~20 días de producción (ciclo 44, ~320 operaciones).
Objetivo: pasar de un ensemble estático con features de baja calidad a un cerebro de trading
con señales LLM, datos sociales reales, y filtros de decisión más robustos.

---

## FASE 1 — Bug Fixes (prioridad máxima)

### 1.1 Fix FIFO timestamp ordering
- **Problema**: `exit_time < entry_time` en operaciones cerradas — SQL FIFO empareja por row order no por timestamp
- **Afecta**: `db_manager.get_closed_positions()` y todas las funciones con `ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY timestamp)`
- **Fix**: El SQL ya usa `ORDER BY timestamp` en el `ROW_NUMBER()` — el bug real está en que no hay un JOIN con condición `s.timestamp >= b.timestamp`. Añadir sanity check en la query.
- [ ] Identificar query exacta con timestamps incorrectos
- [ ] Fix SQL para garantizar exit_time >= entry_time
- **Status**: 🔄 IN PROGRESS

### 1.2 Fix equity curve corruption
- **Problema**: Backfill del May 5 dejó portfolio_value inflado a ~$12K (real: ~$9.9K)
- **Fix**: Script `scripts/fix_performance_metrics.py` — recalcula portfolio_value desde capital inicial + daily_pnl acumulado
- [ ] Crear script
- [ ] Verificar: SELECT date, portfolio_value FROM performance_metrics ORDER BY date → final ~$9.865K
- **Status**: ⏳ PENDING

### 1.3 Force manual retrain
- **Problema**: Modelo lleva 51 días sin actualizarse (auto-trainer falla Sharpe < 0.5)
- **Fix**: Script `scripts/force_retrain.py --force-promote`
- [ ] Crear script
- **Status**: ⏳ PENDING

---

## FASE 2 — LLM News Sentiment con Claude Haiku

- **Problema**: `news_fetcher.py` usa keyword matching ("SEC" → siempre bearish aunque sea positivo)
- **Solución**: `src/data/llm_sentiment.py` — Claude Haiku analiza artículos con comprensión real
- **Costo estimado**: ~$0.03-0.05/día
- **Features nuevas**: `llm_sentiment_score`, `llm_sentiment_confidence`, `llm_news_count`, `llm_regulatory_signal`
- [ ] Crear `src/data/llm_sentiment.py`
- [ ] Modificar `news_fetcher.py` para integrar LLM (async, con fallback a keywords)
- [ ] Añadir `ANTHROPIC_API_KEY` en `config.py` y `render.yaml`
- [ ] Añadir `anthropic>=0.30.0` en `requirements.txt`
- **Status**: ⏳ PENDING

---

## FASE 3 — CoinGecko Social/Dev Data para los 47 Altcoins

- **Problema**: `onchain_fetcher` devuelve NaN para altcoins (solo funciona para BTC). `social_fetcher` solo lee r/cryptocurrency hot posts.
- **Solución**: `src/data/coingecko_fetcher.py` — API pública de CoinGecko, sin key requerida
- **Features nuevas**: `cg_twitter_followers`, `cg_reddit_subscribers`, `cg_sentiment_votes_up`, `cg_dev_commits_4w`, `cg_dev_activity_score`, `cg_market_cap_rank`
- [ ] Crear `src/data/coingecko_fetcher.py` con rate limiting (2.5s entre llamadas)
- [ ] Integrar en `predictor_v4.py` (cache 1h)
- [ ] Añadir features a `features_v4.py`
- **Status**: ⏳ PENDING

---

## FASE 4 — Time Series Features (ETS + Trend)

- **Problema**: XGB/LGB/CatBoost son modelos de tabla — foto estática, sin proyección temporal
- **Solución**: `src/data/timeseries_features.py` — ETS forecast a 15d + trend slope + momentum divergence
- **Features nuevas**: `ets_expected_return_15d`, `ets_uncertainty_15d`, `trend_slope_14d`, `momentum_divergence`
- **Opcional** (USE_CHRONOS=true): `chronos_expected_return_15d`, `chronos_uncertainty_15d`
- [ ] Crear `src/data/timeseries_features.py`
- [ ] Integrar en `predictor_v4.py`
- [ ] Añadir `statsmodels>=0.14.0` en `requirements.txt`
- **Status**: ⏳ PENDING

---

## FASE 5 — Decision Layer: Trend Filter + Cooldown + Meta-Learner

- **Problemas identificados**:
  - ICP: 2 entradas en downtrend después de +45% rally → -$64 combinado
  - ONDOUSDT: 3 entradas en 3 semanas, 2 en pérdida
  - Meta-learner LogisticRegression no captura interacciones no lineales entre base models

- **Soluciones**:
  - Trend filter: EMA50 < EMA200 → skip entrada (anti-downtrend guard)
  - Over-extended guard: precio >20% sobre EMA50 → entrada tardía, skip
  - Cooldown: 7 días tras cierre con pérdida en ese ticker → reducir size 50%
  - Meta-learner: LogisticRegression → LightGBM (100 estimators, 15 leaves)

- [ ] Implementar `_passes_trend_filter()` en `predictor_v4.py`
- [ ] Implementar `register_trade_result()` + `_in_cooldown()` en `predictor_v4.py`
- [ ] Upgrade `ensemble.py`: `from sklearn.linear_model import LogisticRegression` → `lgb.LGBMClassifier`
- **Status**: ⏳ PENDING

---

## FASE 6 — Retrain + Deploy

- [ ] `python scripts/force_retrain.py --force-promote`
- [ ] Verificar métricas: AUC-ROC CV >= 0.67, std < 0.15, Sharpe >= 0.6
- [ ] `git push origin main` → Render auto-deploy
- [ ] Verificar: GET /health → 200, dashboard equity curve correcto (~$9.9K)
- **Status**: ⏳ PENDING

---

## Historial de commits

| Fecha | Hash | Descripción |
|---|---|---|
| 2026-05-22 | TBD | fix: FIFO timestamp ordering + equity curve fix script + force retrain script |
| 2026-05-22 | TBD | feat: LLM news sentiment with Claude Haiku |
| 2026-05-22 | TBD | feat: CoinGecko social/dev features for all 47 tickers |
| 2026-05-22 | TBD | feat: time series forward-looking features (ETS + trend) |
| 2026-05-22 | TBD | feat: trend filter + cooldown tracker + LightGBM meta-learner |

---

## Punto de control siguiente

Una vez todas las fases estén completas y en producción:
1. Esperar 1 ciclo completo (6h) → verificar logs sin errores
2. Esperar 7 días → comparar win rate nuevo modelo vs baseline (43.93%)
3. Revisar: ¿ICP/ONDOUSDT recurrentes se bloquean con trend filter?
4. Revisar: ¿news LLM features tienen correlación con movimientos reales?
5. Evaluar si activar Chronos (USE_CHRONOS=true) en función de RAM disponible en Render

---

*Log mantenido por Claude — actualizado automáticamente con cada fase completada.*
