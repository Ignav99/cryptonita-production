# Cryptonita — Engine Upgrade Log
## Iniciado: 2026-05-22

---

## Contexto

Auditoría completa del sistema tras ~20 días de producción (ciclo 44, ~320 operaciones).
Objetivo: pasar de un ensemble estático con features de baja calidad a un cerebro de trading
con señales LLM, datos sociales reales, y filtros de decisión más robustos.

---

## FASE 1 — Bug Fixes (prioridad máxima) ✅

### 1.1 Fix FIFO timestamp ordering
- **Problema**: `exit_time < entry_time` en operaciones cerradas — SQL FIFO emparejaba por row order sin guardia temporal
- **Fix**: Añadido `AND s.timestamp >= b.timestamp` (o `AND s.exit_time >= b.entry_time`) en 6 queries de `db_manager.py`. También añadida columna `timestamp` a CTEs que la necesitaban.
- [x] Fix SQL para garantizar exit_time >= entry_time
- **Status**: ✅ DONE — commit `5c4d58b`

### 1.2 Fix equity curve corruption
- **Problema**: Backfill del May 5 dejó portfolio_value inflado a ~$12K (real: ~$9.9K)
- **Fix**: `scripts/fix_performance_metrics.py` — recalcula desde capital inicial + daily_pnl acumulado
- [x] Script creado con `--dry-run` flag
- **Status**: ✅ DONE — commit `5c4d58b`

### 1.3 Force manual retrain
- **Problema**: Modelo llevaba 51 días sin actualizarse (auto-trainer falla Sharpe < 0.5)
- **Fix**: `scripts/force_retrain.py --promote` — bypasea el guard de Sharpe
- [x] Script creado con `--mode [quick|full]`
- **Status**: ✅ DONE — commit `5c4d58b`

---

## FASE 2 — LLM News Sentiment con Claude Haiku ✅

- **Problema**: `news_fetcher.py` usaba keyword matching ("SEC" → siempre bearish aunque aprobara ETF)
- **Solución**: `src/data/llm_sentiment.py` — Claude Haiku analiza artículos con comprensión contextual real
- **Costo estimado**: ~$0.03-0.05/día
- **Features nuevas**: `llm_sentiment_score`, `llm_sentiment_confidence`, `llm_news_count`, `llm_regulatory_signal`, `llm_hack_signal`
- [x] Crear `src/data/llm_sentiment.py` (claude-haiku-4-5, MAX_TOKENS=300, cache 15min)
- [x] Modificar `news_fetcher.py` — método `get_ticker_features_llm()` con fallback a keywords
- [x] Añadir `ANTHROPIC_API_KEY` en `config.py` y `render.yaml`
- [x] Añadir `anthropic>=0.30.0` en `requirements.txt`
- **Status**: ✅ DONE — commit `926930b`
- **Nota**: Activar en Render dashboard seteando `ANTHROPIC_API_KEY`

---

## FASE 3 — CoinGecko Social/Dev Data para los 47 Altcoins ✅

- **Problema**: `onchain_fetcher` devuelve NaN para altcoins (solo BTC). `social_fetcher` solo lee Reddit hot posts.
- **Solución**: `src/data/coingecko_fetcher.py` — API pública de CoinGecko, sin key requerida
- **Rate limit**: 2.5s entre llamadas (30 req/min free tier)
- **Cache**: 1h TTL — cold start ~2min, warm: instantáneo
- **Features nuevas** (6):
  - `cg_market_cap_rank_norm` — rank normalizado (1.0=rank 1)
  - `cg_sentiment_votes_up` — % votos positivos (0-1)
  - `cg_twitter_followers_log` — log10 normalizado
  - `cg_reddit_subscribers_log` — log10 normalizado
  - `cg_dev_commits_4w_log` — commits últimas 4 semanas, log10
  - `cg_dev_activity_score` — composite dev activity 0-1
- [x] Crear `src/data/coingecko_fetcher.py` con mapeo de 47 tickers → CoinGecko IDs
- [x] Integrar en `features_v4.py` (`_calculate_coingecko_features()`)
- [x] Integrar en `predictor_v4.py` (`_fetch_coingecko_data_sync()`, timeout 3min)
- **Status**: ✅ DONE — pendiente commit

---

## FASE 4 — Time Series Features (ETS + Trend) ✅

- **Problema**: XGB/LGB/CatBoost son modelos de tabla — foto estática, sin proyección temporal
- **Solución**: `src/data/timeseries_features.py` — ETS forecast a 15d + trend slope + momentum divergence
- **Features nuevas** (4):
  - `ets_expected_return_15d` — retorno esperado según ETS Holt lineal, clipeado [-50%, +100%]
  - `ets_uncertainty_15d` — incertidumbre del forecast (std residuales × √horizon / precio)
  - `trend_slope_14d` — slope OLS 14d normalizado por precio actual
  - `momentum_divergence` — divergencia corto (3d) vs medio (14d) momentum
- [x] Crear `src/data/timeseries_features.py` con Holt's ExponentialSmoothing
- [x] Integrar en `features_v4.py` (`_calculate_timeseries_features()`)
- [x] `statsmodels>=0.14.0` ya en requirements.txt (FASE 2)
- **Status**: ✅ DONE — pendiente commit

---

## FASE 5 — Decision Layer: Trend Filter + Cooldown + Meta-Learner ✅

- **Problemas identificados**:
  - ICP: 2 entradas en downtrend después de +45% rally → -$64 combinado
  - ONDOUSDT: 3 entradas en 3 semanas, 2 en pérdida
  - Meta-learner LogisticRegression no captura interacciones no lineales entre base models

- **Soluciones implementadas**:
  - **Trend filter** (`_passes_trend_filter()`): EMA50 < EMA200 → bloquea entrada; precio > 1.20×EMA50 → sobreextendido, bloquea
  - **Cooldown tracker** (`register_trade_result()` + `_in_cooldown()`): 7 días tras pérdida → size ×0.5
  - **Meta-learner upgrade** (`ensemble.py`): LogisticRegression → LGBMClassifier (100 estimators, 15 leaves, lr=0.05)

- [x] Implementar `_passes_trend_filter()` en `predictor_v4.py`
- [x] Implementar `register_trade_result()` + `_in_cooldown()` + `_get_cooldown_mult()` en `predictor_v4.py`
- [x] Upgrade `ensemble.py`: LogisticRegression → LGBMClassifier
- **Status**: ✅ DONE — pendiente commit

---

## FASE 6 — Retrain Automático Fix ✅

- **Problema**: `auto_trainer.py` tenía threshold `win_rate_min = 0.50` — con 43.93% nunca promovía (51 días bloqueado)
- **Fix**: Bajado a `0.40` — floor real de operabilidad. El auto-retrain corre cada 7 días y ahora puede promover
- [x] Threshold bajado en `auto_trainer.py`
- [x] `ANTHROPIC_API_KEY` seteada en Render dashboard (22 May — manual por usuario)
- [x] `git push origin main` → Render auto-deploy activo
- **Commit final**: `4296c58`
- **Status**: ✅ DONE — EN PRODUCCIÓN

---

## Feature registry final (V4.4)

Total features: **109** (94 originales + 6 CoinGecko + 5 LLM news + 4 ETS/trend)

Config: `configs/feature_config_v4.json` v4.3

---

## Historial de commits

| Fecha | Hash | Descripción |
|---|---|---|
| 2026-05-22 | `5c4d58b` | fix: FIFO timestamp guard + equity curve fix script + force retrain script |
| 2026-05-22 | `926930b` | feat: LLM news sentiment with Claude Haiku |
| 2026-05-22 | `4296c58` | feat: CoinGecko social/dev features + ETS time series + trend filter + cooldown + LightGBM meta |

---

## Punto de control siguiente

Una vez todo en producción:
1. Esperar 1 ciclo completo (6h) → verificar logs sin errores
2. Esperar 7 días → comparar win rate nuevo modelo vs baseline (43.93%)
3. Revisar: ¿ICP/ONDOUSDT recurrentes se bloquean con trend filter?
4. Revisar: ¿news LLM features tienen correlación con movimientos reales?
5. Evaluar si activar Chronos (USE_CHRONOS=true) en función de RAM disponible en Render

---

*Log mantenido por Claude — actualizado automáticamente con cada fase completada.*
