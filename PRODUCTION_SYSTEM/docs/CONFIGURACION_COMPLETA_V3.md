# 📋 CONFIGURACIÓN COMPLETA - SISTEMA V3

**Fecha:** 2025-11-01 12:19:20  
**Versión:** 3.0  
**Estado:** Producción Activa  

---

## 🎯 INFORMACIÓN DEL SISTEMA

- **Nombre:** Crypto Trading System V3
- **Descripción:** Sistema de trading automatizado con ML (XGBoost)
- **Objetivo:** Detectar pumps >20% en cryptos con 15 días de anticipación
- **Performance:** +82.7% ROI en test set (julio-octubre 2024)

---

## 🤖 MODELO

### Algoritmo
- **Framework:** XGBoost 3.1.1
- **Tipo:** Clasificación Binaria
- **Archivo:** `models/production_model_v3.json`

### Hiperparámetros
```python
{
  "n_estimators": 300,
  "max_depth": 6,
  "learning_rate": 0.05,
  "subsample": 0.8,
  "colsample_bytree": 0.8,
  "min_child_weight": 1,
  "gamma": 0,
  "scale_pos_weight": 1.52,
  "random_state": 42,
  "eval_metric": "logloss",
  "tree_method": "hist",
  "objective": "binary:logistic"
}
```

---

## 📊 FEATURES (42 TOTAL)

### Categoría 1: Originales V1 (14 features)
1. price_to_ema200
2. atr_pct
3. price_change_14d
4. obv
5. obv_ratio
6. hl_ratio
7. volume_ratio_20
8. stoch_k
9. lower_shadow_ratio
10. upper_shadow_ratio
11. bullish_candles_3d
12. body_ratio
13. close_position
14. body_trend

### Categoría 2: Tendencia V2 (15 features)
1. momentum_3d
2. momentum_5d
3. momentum_7d
4. price_acceleration
5. volume_trend_ratio
6. volume_acceleration
7. atr_compression
8. hl_compression
9. green_candles_5d
10. green_candles_10d
11. higher_highs_5d
12. higher_lows_5d
13. price_position_20d
14. momentum_strength
15. body_trend_ratio

### Categoría 3: Macro V2 (5 features)
1. fear_greed_value
2. funding_rate
3. spx
4. spx_change_7d
5. vix

### Categoría 4: Momentum Avanzado V3 (8 features)
1. price_jerk_3d
2. volume_jerk_3d
3. price_explosion_ratio
4. volume_explosion_ratio
5. momentum_vs_btc_3d
6. beta_acceleration
7. volatility_spike_ratio
8. hl_expansion_rate

### Top 15 Features Más Importantes
1. spx: 6.3
2. fear_greed_value: 5.1
3. atr_pct: 4.7
4. hl_ratio: 4.7
5. spx_change_7d: 4.6
6. vix: 4.1
7. price_explosion_ratio: 3.9
8. obv: 3.7
9. funding_rate: 3.6
10. price_position_20d: 3.6
11. price_to_ema200: 2.8
12. atr_compression: 2.7
13. stoch_k: 2.5
14. volume_trend_ratio: 2.4
15. price_change_14d: 2.4

---

## 🎯 TARGET

- **Variable:** `target_v2`
- **Definición:** Pump >20% en próximos 15 días
- **Cálculo:** `max_return_15d >= 0.20`

---

## 💼 REGLAS DE TRADING
```python
{
  "position_size_pct": 0.1,
  "max_position_size_pct": 15,
  "take_profit_pct": 0.15,
  "stop_loss_pct": 0.05,
  "max_portfolio_risk_pct": 30,
  "max_positions": 10,
  "threshold": 0.6,
  "max_portfolio_risk": 0.3
}
```

### Explicación
- **Threshold (0.60):** Solo entrar si probabilidad >60%
- **Position Size (10%):** Cada posición = 10% del capital
- **Take Profit (+15%):** Cerrar con ganancia del 15%
- **Stop Loss (-5%):** Cortar pérdidas al 5%
- **Max Risk (30%):** Máximo 30% del capital en riesgo
- **Max Positions (10):** Diversificar en máximo 10 cryptos

---

## 📈 PERFORMANCE

### Test Set (2024-07-01 → 2025-10-28)
- **test_period:** 2024-07-01 to 2025-10-28
- **roi:** 82.7
- **win_rate:** 48.8
- **total_trades:** 43
- **sharpe_ratio:** 3.43
- **max_drawdown:** 6.3
- **profit_factor:** 3.1
- **avg_days_held:** TBD

### Comparación Histórica
| Versión | ROI | Win Rate | Trades |
|---------|-----|----------|--------|
| V1 | 18.1% | 32.5% | N/A |
| V2 | 45.7% | 50.0% | 23 |
| V3 | 82.7% | 48.8% | 43 |

---

## 📊 DATOS

### Dataset
- **Archivo:** `data/production_dataset_v3.csv`
- **Registros:** 49,184
- **Periodo:** 2019-01-01 → 2025-10-28
- **Cryptos:** 25

### Train/Test Split
- **Train:** 2019-01-01 → 2024-06-30 (39,509 registros)
- **Test:** 2024-07-01 → 2025-10-28 (9,675 registros)

### Cryptos Soportadas (25)
1. AAVE-USD
2. ADA-USD
3. ALGO-USD
4. APT-USD
5. ARB-USD
6. ATOM-USD
7. AVAX-USD
8. DOGE-USD
9. DOT-USD
10. FIL-USD
11. FTM-USD
12. GRT-USD
13. INJ-USD
14. LINK-USD
15. MANA-USD
16. MATIC-USD
17. NEAR-USD
18. OP-USD
19. RNDR-USD
20. RUNE-USD
21. SAND-USD
22. SOL-USD
23. STX-USD
24. SUI-USD
25. UNI-USD

---

## 🔄 WORKFLOW DE PRODUCCIÓN

1. **Recolección Diaria:** Obtener OHLCV + datos macro
2. **Preprocesamiento:** Calcular 42 features
3. **Predicción:** Generar probabilidades con V3
4. **Trading:** Abrir/cerrar posiciones según reglas
5. **Reentrenamiento Mensual:** Actualizar modelo con datos nuevos

---

## 📁 ARCHIVOS CLAVE

- `models/production_model_v3.json` - Modelo entrenado
- `configs/PRODUCTION_MASTER_CONFIG.json` - Configuración completa
- `configs/production_features_config_v3.json` - Definición features
- `data/production_dataset_v3.csv` - Dataset
- `docs/README_V3.md` - Documentación

---

**Última actualización:** 2025-11-01 12:19:20
