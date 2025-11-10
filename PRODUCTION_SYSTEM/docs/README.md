# 🚀 CRYPTO TRADING SYSTEM V2 - PRODUCTION

**Versión:** 2.0.0  
**Fecha:** 2025-10-30  
**Estado:** ✅ PRODUCCIÓN

---

## 📊 RENDIMIENTO

| Métrica | Valor |
|---------|-------|
| **ROI (16 meses)** | **+45.7%** |
| **Win Rate** | 50.0% |
| **Total Trades** | 22.0 |
| **Max Drawdown** | 2.7% |
| **Sharpe Ratio** | 5.47 |
| **Profit Factor** | 4.46 |

---

## 🏗️ ARQUITECTURA

### Modelo Principal
- **Tipo:** HYBRID_V2
- **Archivo:** `production_model_hybrid.json`
- **Features:** 34
- **Threshold:** 0.70
- **Target:** Pumps >20% en 15 días

### Features (29 técnicas + 5 macro)

#### 📈 Originales (14)
Indicadores técnicos básicos: price_to_ema200, ATR, volumen, momentum, etc.

#### 🎯 Tendencia (15) - NUEVO EN V2
- **Momentum multi-timeframe:** momentum_3d, 5d, 7d
- **Aceleración:** price_acceleration, volume_acceleration
- **Estructura alcista:** green_candles, higher_highs/lows
- **Volatilidad:** atr_compression, hl_compression
- **Posición:** price_position_20d, momentum_strength

#### 🌍 Macro (5)
Fear & Greed, Funding Rate, S&P 500, VIX

---

## 🎯 REGLAS DE TRADING
```python
CONFIGURACIÓN:
├── Threshold:           0.70
├── Posición:            10% del capital
├── Take Profit:         +15%
├── Stop Loss:           -5%
├── Max riesgo total:    30%
└── Max posiciones:      10 simultáneas
```

---

## 📁 ESTRUCTURA DE ARCHIVOS
```
PRODUCTION_SYSTEM/
├── configs/
│   ├── PRODUCTION_MASTER_CONFIG.json    ← ⭐ Config principal
│   ├── production_models_config.json
│   └── production_features_config.json
├── models/
│   ├── production_model.json            ← Modelo principal
│   └── production_model_hybrid.json     ← Modelo híbrido
├── data/
│   ├── production_dataset.csv           ← Dataset completo
│   └── test_dataset.csv                 ← Test set
├── analysis/
│   ├── v2_backtest_comparison.json      ← Resultados backtest
│   └── pumps_detected.csv               ← Pumps históricos
└── docs/
    └── README.md                         ← Esta documentación
```

---

## 🚀 USO RÁPIDO

### 1. Cargar Sistema
```python
import xgboost as xgb
import pandas as pd
import json

# Cargar configuración
with open('configs/PRODUCTION_MASTER_CONFIG.json', 'r') as f:
    config = json.load(f)

# Cargar modelo
model = xgb.XGBClassifier()
model.load_model(f"models/{config['model']['file']}")

# Cargar features
with open('configs/production_features_config.json', 'r') as f:
    features_config = json.load(f)
    features = features_config['features']['all_v2']  # o hybrid_v2

print(f"✅ Sistema V2 cargado")
print(f"   Modelo: {config['model']['name']}")
print(f"   Features: {len(features)}")
print(f"   Threshold: {config['model']['threshold']}")
```

### 2. Generar Señal
```python
def get_signal(row, model, features, threshold=0.70):
    """Genera señal de trading"""

    # Preparar features
    X = row[features].values.reshape(1, -1)
    X = np.nan_to_num(X, nan=0, posinf=0, neginf=0)

    # Predecir
    prob = model.predict_proba(X)[0, 1]

    # Señal
    if prob >= threshold:
        return {
            'signal': True,
            'probability': prob,
            'position_size': 0.10,  # 10%
            'take_profit': 0.15,    # 15%
            'stop_loss': 0.05       # 5%
        }

    return {'signal': False}

# Uso
signal = get_signal(today_data, model, features)
if signal['signal']:
    print(f"🎯 SEÑAL! Probabilidad: {signal['probability']:.2%}")
```

---

## 📈 HISTORIAL DE MEJORAS

| Versión | ROI | Mejora Principal |
|---------|-----|------------------|
| **V1.0** | +18.1% | Sistema base con ensemble |
| **V1.5** | +37.7% | Optimización thresholds (0.85→0.70) |
| **V2.0** | **+45.7%** | **Features tendencia + target >20%** |

---

## 🎯 PRÓXIMAS MEJORAS PLANIFICADAS

### 🔥 Alta Prioridad
1. **Sistema de Review Manual**
   - Herramienta para etiquetar pumps manualmente
   - Mejorar dataset con feedback experto
   - Impacto esperado: +5-10% win rate

2. **Optimización Hiperparámetros**
   - Grid search: max_depth, learning_rate, n_estimators
   - Validación cruzada temporal
   - Impacto esperado: +5-10% ROI

### 📊 Media Prioridad
3. **Sentiment Analysis**
   - Integrar noticias (CoinGecko/NewsAPI)
   - Features de Twitter/Reddit
   - Detectar pumps por eventos

4. **Ensemble Avanzado**
   - Stacking con meta-modelo
   - Combinar múltiples algoritmos
   - Impacto: +3-5% ROI

### 💡 Baja Prioridad
5. **Features Temporales**
   - Estacionalidad mensual
   - Ciclos de Bitcoin
   - Impacto: +2-3% ROI

---

## ⚠️ MONITOREO Y MANTENIMIENTO

### ✅ Revisión Semanal
- [ ] Win rate actual vs esperado
- [ ] Drawdown actual
- [ ] Número de trades
- [ ] Features calculándose correctamente

### ✅ Revisión Mensual
- [ ] ROI mensual vs target
- [ ] Profit factor
- [ ] Trades ganadores/perdedores
- [ ] Ajustar thresholds si es necesario

### ✅ Revisión Trimestral
- [ ] Reentrenar modelos con datos nuevos
- [ ] Evaluar nuevas features
- [ ] Optimizar hiperparámetros
- [ ] Actualizar documentación

### 🚨 Alertas Automáticas
- **PAUSAR trading si:**
  - Drawdown > 15%
  - Win rate < 30% en última semana
  - 5 pérdidas consecutivas

---

## 📞 SOPORTE Y LOGS

### Logs Importantes
- `analysis/v2_backtest_comparison.json` - Resultados completos
- `configs/PRODUCTION_MASTER_CONFIG.json` - Config actual
- `BACKUP_20251030_155736/` - Backup de versión anterior

### Troubleshooting

**Problema:** Modelo no predice
- Verificar que todas las features existen
- Revisar NaN/Inf en datos
- Confirmar threshold correcto

**Problema:** Win rate bajo
- Revisar threshold (subir si WR < 30%)
- Verificar calidad de datos
- Considerar reentrenamiento

---

## 📄 LICENCIA

Uso personal/educativo. Trading implica riesgos.

**DISCLAIMER:** Este sistema no garantiza ganancias. Usa bajo tu propio riesgo.

---

**Sistema creado con ❤️ y Machine Learning**

*Última actualización: 2025-10-30 15:57:36*
