# Cryptonita V5 — Next Results Check

> **Fecha de inicio**: 2026-06-03 | **Capital inicial**: $3,000 | **Modelo**: V5 Ternary (LONG/SHORT/HOLD)
> **Commit deployado**: `059a0c3`

---

## Antes de revisar resultados: verificación del arranque

```bash
# 1. Obtener token
curl -s -X POST https://<TU_URL>.onrender.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<PASSWORD>"}' | python3 -m json.tool
# → guarda el access_token

# 2. Verificar portfolio en $3,000
curl -s https://<TU_URL>.onrender.com/api/stats \
  -H "Authorization: Bearer <TOKEN>" | python3 -m json.tool

# 3. Verificar modelo V5
# En los logs de Render debe aparecer: "Using V5 Ternary Predictor (LONG/SHORT/HOLD)"
```

---

## Checklist de resultados por timeframe

### Después de 1 día (check mínimo)
- [ ] Bot arrancó sin errores (ver logs Render)
- [ ] Aparece "V5 Ternary Predictor" en logs
- [ ] Al menos 1 ciclo completado (`cycle_number > 0`)
- [ ] No hay posiciones abiertas de antes (balance ≈ $3,000)

### Después de 3 días
- [ ] Al menos 5-10 señales generadas
- [ ] La tabla de Signals muestra badgets ▲ LONG o ▼ SHORT
- [ ] Balance: entre $2,800 y $3,400 es normal

### Después de 1 semana (primera evaluación real)
- [ ] **Win rate SHORT > 37.5%** (break-even con R/R +5%/-3%)
- [ ] **Win rate LONG > 37.5%**
- [ ] Balance esperado: $3,090–$3,360 (+3% a +12%)
- [ ] Si balance < $2,700 → STOP e investigar (ver sección Red Flags)

---

## Resultados esperados (calibrado en backtest de 25 coins)

| Timeframe | Conservador | Base case | Bull market |
|-----------|------------|-----------|-------------|
| 1 semana | +3–8% | +5–12% | +8–20% |
| 1 mes | +12–25% | +20–40% | +30–60% |
| 3 meses | +40–80% | +60–120% | +100–200% |
| 1 año | +100% | +200% | +400% |

**Descuentos de producción aplicados**: -0.3%/trade comisiones+slippage, -30% degradación del modelo.

---

## Red Flags → investigar inmediatamente

| Síntoma | Causa probable | Acción |
|---------|---------------|--------|
| 0 trades tras 48h | Bot no arrancó o modelos no cargados | Ver logs Render, reiniciar |
| Solo señales HOLD | Threshold muy alto o modelos vacíos | Verificar `PRODUCTION_SYSTEM/models/v5/` |
| Solo LONG (nunca SHORT) | `USE_V4_MODEL=true` aún activo | Verificar render.yaml commit |
| Pérdida > 5% en 1 trade | SL no funcionando | Revisar `binance_futures_service.py` |
| Balance < $2,700 en 1 semana | LONG signals destruyendo valor | Deshabilitar LONG en per_coin_config.py |

---

## Cómo ejecutar el soft-reset (si necesitás empezar de cero)

```bash
# Guarda historial de trades pero borra posiciones abiertas y pone $3,000
curl -s -X POST https://<TU_URL>.onrender.com/api/controls/soft-reset \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" | python3 -m json.tool
# → "Soft reset complete. Portfolio set to $3,000. Historical trades preserved."
```

---

## Qué cambió en V5 vs V4

| | V4 (antes) | V5 (ahora) |
|--|--|--|
| Señales SHORT | ❌ imposible — bug estructural | ✅ Binance Futures |
| Clasificación | Binario (BUY/HOLD) | Ternario (LONG/SHORT/HOLD) |
| Modelos | 1 modelo global | 1 modelo por moneda |
| LONG win rate | ~27% | ~30% |
| SHORT win rate | N/A | ~47–51% |
| Break-even real | 50% | **37.5%** (R/R asimétrico) |
| Sharpe (backtest) | desconocido | 5.5 avg (25 coins) |
| Tickers positivos | desconocido | 96% de 25 coins testeadas |

---

## Archivos clave para diagnóstico

```
src/models/predictor_v5.py         → thresholds, should_trade() logic
src/config/per_coin_config.py      → coins con LONG deshabilitado
src/services/binance_futures_service.py → ejecución SHORT
docs/BACKTEST_V5_2026-06-03_pass2.md   → métricas baseline backtest
```

---

## Optimizaciones pendientes para la próxima sesión

1. **Per-coin SHORT threshold** — igual que ya existe para LONG (algunos coins como STX tienen SHORT WR de solo 10%)
2. **Reentrenamiento mensual** — POST /api/controls/trigger-training (ya automatizado cada 7 días)
3. **Filtro macro BTC SMA200** — solo operar LONG cuando BTC está en tendencia alcista
4. **Deshabilitar LONG para más coins** — ADA (19% WR), RUNE (0% WR) deberían operar solo SHORT
