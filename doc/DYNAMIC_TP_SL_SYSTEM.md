# 🎯 Sistema Dinámico de Take Profit y Stop Loss

## Descripción General

El bot ahora incluye un **sistema inteligente de gestión de riesgo** que ajusta automáticamente los niveles de Take Profit (TP) y Stop Loss (SL) según las condiciones del mercado, volatilidad y momentum de cada moneda.

---

## 🚀 Características Principales

### 1. **Take Profit Parcial por Niveles**

En lugar de vender toda la posición a un solo precio, el sistema vende en 3 etapas:

| Nivel | % Posición | Ganancia Target | Descripción |
|-------|-----------|----------------|-------------|
| **TP1** | 30% | +10-20% | Asegurar ganancia rápida |
| **TP2** | 40% | +20-35% | Objetivo medio |
| **TP3** | 30% | +40-60% | Capturar pumps grandes |

**Ventajas:**
- ✅ Aseguras ganancias progresivamente
- ✅ No pierdes todo el potencial si sigue subiendo
- ✅ Reduces riesgo manteniendo menos exposición

---

### 2. **Trailing Stop Loss (TSL)**

El Stop Loss **sube automáticamente** con el precio, pero nunca baja.

**Cómo funciona:**
1. Se activa cuando la ganancia > **5%**
2. Mantiene distancia de **1.5 x ATR** del precio actual
3. Si precio sube → SL sube
4. Si precio baja → SL se queda donde está
5. **Lock profit:** Garantiza mínimo +1% de ganancia una vez activado

**Ejemplo:**
```
Entrada:     $100
Precio sube: $110 (+10%) → TSL se activa
SL inicial:  $95 (-5%)
TSL nuevo:   $106 (+6% profit locked)

Precio sube: $120 (+20%)
TSL nuevo:   $115 (+15% profit locked)

Precio baja: $118 → TSL se mantiene en $115
```

---

### 3. **Ajuste Dinámico Según Volatilidad (ATR)**

El sistema ajusta TP/SL basándose en la **volatilidad real** de cada moneda:

| ATR | Volatilidad | Multiplicador TP/SL |
|-----|------------|-------------------|
| < 2% | Muy baja | 0.8x (más ajustado) |
| 2-3% | Baja | 0.9x |
| 3-5% | Normal | 1.0x (base) |
| 5-8% | Alta | 1.2x (más amplio) |
| > 8% | Muy alta | 1.5x |

**Por qué es importante:**
- Monedas volátiles (ej: PEPE, FLOKI) necesitan TP/SL más amplios
- Evita stop-outs prematuros por volatilidad normal
- Maximiza ganancias en monedas de bajo riesgo

---

### 4. **Ajuste Según Momentum**

El sistema detecta la **fuerza del movimiento** y ajusta:

| Momentum | Multiplicador | Estrategia |
|----------|-------------|------------|
| Muy fuerte (+5%/3d) | 1.3x | TP más amplio, esperar más |
| Fuerte (+2%/3d) | 1.15x | Ligeramente optimista |
| Normal | 1.0x | Base |
| Débil | 0.9x | TP más cercano |
| Negativo | 0.8x | Tomar ganancias rápido |

**Lógica:**
- Momentum fuerte → Probable que continúe → Esperar más
- Momentum débil → Puede revertir → Salir antes

---

### 5. **Ajuste Según Fear & Greed Index**

El índice de miedo/codicia del mercado influye en la agresividad:

| Índice | Condición | Ajuste | Razón |
|--------|-----------|--------|-------|
| 0-25 | Extreme Fear | +15% TP | Aprovechar rebotes |
| 25-40 | Fear | +5% TP | Ligeramente optimista |
| 40-60 | Neutral | Base | Sin ajuste |
| 60-75 | Greed | -5% TP | Tomar ganancias |
| 75-100 | Extreme Greed | -15% TP | Salir antes del crash |

---

### 6. **Condiciones de Salida Inteligente**

El bot monitorea constantemente y puede salir **antes** de TP/SL si detecta:

#### 🔴 **Reversión de Momentum**
```
Entrada:  Momentum +4% (fuerte subida)
Actual:   Momentum -2% (se invierte)
Acción:   Salir 100% si ganancia > 3%
```

#### 📉 **Pérdida de Fuerza**
```
Entrada:  Momentum Strength 0.7 (fuerte)
Actual:   Momentum Strength 0.2 (débil)
Acción:   Salir 50% si ganancia > 5%
```

#### 📊 **Colapso de Volumen**
```
Entrada:  Volume Ratio 2.5x (alto volumen)
Actual:   Volume Ratio 0.5x (volumen cae 80%)
Acción:   Salir 50% (fin del pump)
```

#### 🕯️ **Patrones Bajistas**
```
Velas rojas: >80% en últimos 5 días
Lower lows: Patrón de mínimos decrecientes
Acción:     Salir 30% preventivo
```

---

## 📊 Ejemplo Completo

### Entrada: DOGEUSDT

**Señal:** Probabilidad 0.75 (alta confianza)

**Features:**
- ATR: 6% (alta volatilidad) → Multiplicador 1.2x
- Momentum 3d: +4% (fuerte) → Multiplicador 1.3x
- Fear & Greed: 45 (neutral) → Multiplicador 1.0x
- Volatility Total: 1.2 × 1.3 × 1.0 = **1.56x**

**TP/SL Calculados:**
```
Entrada: $0.100

SL Base: -5% × 1.2 (ATR) = -6%
SL Final: $0.094 (-6%)

TP1 Base: +10% × 1.56 = +15.6%
TP1 Final: $0.116 (+16%) | 30% posición

TP2 Base: +20% × 1.56 = +31.2%
TP2 Final: $0.131 (+31%) | 40% posición

TP3 Base: +40% × 1.56 = +62.4%
TP3 Final: $0.162 (+62%) | 30% posición
```

### Evolución de la Posición

**Día 1:**
```
Precio: $0.106 (+6%)
Acción: Trailing Stop se activa
TSL:    $0.102 (+2% profit locked)
```

**Día 3:**
```
Precio: $0.116 (+16%)
Acción: TP1 HIT → Vende 30%
TSL:    $0.112 (+12% profit locked)
Quedan: 70% posición
```

**Día 5:**
```
Precio: $0.132 (+32%)
Acción: TP2 HIT → Vende 40%
TSL:    $0.127 (+27% profit locked)
Quedan: 30% posición
```

**Día 7:**
```
Precio: $0.145 (+45%)
Momentum: -2% (se invierte)
Volumen:  Cae 70%
Acción:   SALIDA INTELIGENTE → Vende 30% restante
Razón:    Momentum reversal + volume collapse
```

### Resultado Final

| Salida | % Posición | Precio | Ganancia | Ganancia Total |
|--------|-----------|--------|----------|---------------|
| TP1 | 30% | $0.116 | +16% | +4.8% |
| TP2 | 40% | $0.132 | +32% | +12.8% |
| Exit | 30% | $0.145 | +45% | +13.5% |
| **TOTAL** | **100%** | - | - | **+31.1%** |

**Comparación con TP Fijo (+15%):**
- TP Fijo: +15% en toda la posición
- Sistema Dinámico: **+31.1%** (más del doble!)

---

## 🎮 Configuración

Los parámetros pueden ajustarse en `src/trading/dynamic_risk_manager.py`:

```python
# Niveles de Take Profit parcial
self.tp_levels = [
    {'name': 'TP1', 'pct': 0.10, 'size': 0.30},  # 30% a +10%
    {'name': 'TP2', 'pct': 0.20, 'size': 0.40},  # 40% a +20%
    {'name': 'TP3', 'pct': 0.40, 'size': 0.30},  # 30% a +40%
]

# Trailing Stop Loss
self.trailing_stop_activation = 0.05  # Activa con +5%
self.trailing_stop_distance_atr_mult = 1.5  # 1.5 × ATR
```

---

## 📈 Ventajas del Sistema

1. **Maximiza Ganancias**
   - Captura pumps grandes sin salir demasiado pronto
   - TP parcial asegura profit mientras mantiene exposición

2. **Reduce Riesgo**
   - Trailing Stop protege ganancias automáticamente
   - Salidas inteligentes detectan reversiones

3. **Se Adapta al Mercado**
   - Volatilidad alta → Más espacio para moverse
   - Momentum fuerte → Espera más
   - Mercado codicia → Toma ganancias antes

4. **Evita Emociones**
   - Todo automatizado, sin decisiones emocionales
   - Reglas claras basadas en datos

---

## 🔍 Monitoreo

El bot muestra toda la información en los logs:

```
📊 SOLUSDT | SL: -6.2% | TP1: +15.8% | TP2: +31.5% | TP3: +63.1% |
   Vol: 1.24x | Mom: 1.35x

🔼 SOLUSDT Trailing SL: $95.40 → $102.50 (+2.5% profit locked)

📤 SOLUSDT PARTIAL EXIT: tp1_hit (30%)
✅ SELL executed: 12.5 SOLUSDT @ $115.80 | Reason: tp1_hit

🚪 SOLUSDT FULL EXIT: momentum_reversal
✅ SELL executed: 29.1 SOLUSDT @ $142.30 | Reason: momentum_reversal
```

---

## 🧪 Próximos Pasos para Probar

1. **Ejecuta el bot:**
   ```bash
   python run_bot.py
   ```

2. **Espera señales BUY** con probabilidad > 0.60

3. **Observa los logs** para ver cómo se calculan los TP/SL dinámicos

4. **Si se abre una posición**, el monitoreo cada 5 minutos mostrará:
   - Precio actual y P&L
   - Trailing Stop ajustes
   - Salidas parciales
   - Condiciones de salida inteligente

---

## ⚠️ Notas Importantes

- El sistema está diseñado para **testnet** primero
- Todos los cálculos son automáticos, no requieren intervención
- Los logs muestran toda la lógica en tiempo real
- Puedes ajustar los multiplicadores según tu tolerancia al riesgo

---

**Sistema creado:** 2025-11-10
**Versión:** 1.0 - Dynamic TP/SL
**Estado:** Ready for testing ✅
