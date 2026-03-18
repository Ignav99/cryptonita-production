# 📊 SELECCIÓN DE MONEDAS PARA EL BOT

## ❌ PROBLEMA CON LA LISTA ANTERIOR

La lista original incluía monedas **demasiado estables** para el objetivo del modelo V3:

### Monedas eliminadas y por qué:

1. **BTCUSDT** ❌
   - Volatilidad: ~2-3% diario
   - Market cap: >$1T (demasiado grande)
   - **Problema**: NO genera pumps de +20% en 15 días

2. **ETHUSDT** ❌
   - Volatilidad: ~2-4% diario
   - Market cap: >$400B (muy grande)
   - **Problema**: Movimientos lentos, poca volatilidad

3. **BNBUSDT** ❌
   - Volatilidad: ~3-5% diario
   - **Problema**: Coin de exchange, movimientos predecibles

4. **LTCUSDT, XRPUSDT, ETCUSDT** ❌
   - Monedas "viejas" con baja volatilidad
   - Poco volumen comparado con nuevas altcoins

5. **XLMUSDT, VETUSDT, TRXUSDT** ⚠️
   - Volumen bajo (<$10M algunos días)
   - Riesgo de liquidez

---

## ✅ NUEVA LISTA OPTIMIZADA (42 monedas)

### Criterios de Selección:

1. **Alta Volatilidad**: >5% movimiento diario típico
2. **Buen Volumen**: >$20M USD/día
3. **Market Cap**: $100M - $15B (sweet spot para pumps)
4. **Categorías diversas**: Layer 1, DeFi, Gaming, AI, Memes

### Distribución por Categoría:

#### 🔹 Layer 1 / Layer 2 (10 monedas)
Blockchains alternativos con alta volatilidad:
- **SOL, AVAX, NEAR, APT, SUI, SEI** - Nuevas L1 con mucho hype
- **ARB, OP** - L2 de Ethereum con buen volumen
- **INJ, FTM** - DeFi chains volátiles

**Por qué funcionan**: Noticias frecuentes, actualizaciones, partnerships → pumps súbitos

#### 🔹 DeFi (8 monedas)
Protocolos DeFi con volatilidad por noticias:
- **UNI, AAVE, MKR** - DeFi blue chips volátiles
- **LDO, RUNE, CRV, GMX, DYDX** - Protocolos emergentes

**Por qué funcionan**: Lanzamientos de productos, TVL changes, governance → pumps de 20-50%

#### 🔹 Gaming / Metaverse (5 monedas)
Juegos blockchain muy volátiles:
- **SAND, MANA, AXS, IMX, GALA**

**Por qué funcionan**: Lanzamientos de juegos, partnerships, eventos → pumps masivos

#### 🔹 AI / Compute (4 monedas)
Tendencia 2024-2025, altísima volatilidad:
- **FET, AGIX, WLD, RENDER**

**Por qué funcionan**: Narrativa de AI muy fuerte → pumps de 30-100% en días

#### 🔹 Memecoins (5 monedas)
Volatilidad extrema, alto volumen:
- **DOGE, SHIB** - Memes establecidos con volumen
- **PEPE, FLOKI, BONK** - Nuevos memes volátiles

**Por qué funcionan**: Hype en redes sociales → pumps de 50-200% en horas

#### 🔹 Otros Altcoins Sólidos (10 monedas)
Altcoins de media-alta capitalización:
- **DOT, ATOM, ADA, MATIC, LINK** - Altcoins probados
- **ICP, FIL, HBAR, VET, ALGO** - Proyectos sólidos volátiles

**Por qué funcionan**: Balance entre volumen y volatilidad

---

## 📊 COMPARACIÓN

| Métrica | Lista Anterior | Nueva Lista |
|---------|---------------|-------------|
| **Monedas** | 30 | 42 |
| **Incluye BTC/ETH** | ✅ (problema) | ❌ (correcto) |
| **Volatilidad promedio** | ~4% | ~7% |
| **Potencial pump >20%** | Bajo | Alto |
| **Volumen mínimo** | Variable | >$20M |
| **Enfoque** | Mix general | Altcoins volátiles |

---

## 🎯 EJEMPLOS DE PUMPS REALES

Estas monedas de la nueva lista han tenido pumps >20% en 15 días:

- **WLD**: +150% (Enero 2024)
- **PEPE**: +200% (Abril 2024)
- **INJ**: +80% (Diciembre 2023)
- **RENDER**: +120% (Febrero 2024)
- **BONK**: +300% (Diciembre 2023)
- **SOL**: +50% (Octubre 2024)

**VS** monedas eliminadas:
- **BTC**: Máximo ~15% en 15 días
- **ETH**: Máximo ~12% en 15 días
- **BNB**: Máximo ~18% en 15 días

---

## ⚙️ CÓMO VER LA LISTA

```bash
# Ver lista formateada
python scripts/show_tickers.py

# Ver en config.py
grep "TICKERS" config.py -A 15
```

---

## 🔄 ACTUALIZACIONES FUTURAS

La lista se puede ajustar basado en:
1. **Volumen real** (eliminar monedas <$10M/día)
2. **Performance del modelo** (eliminar monedas con 0% win rate)
3. **Nuevas altcoins** (agregar nuevos proyectos volátiles)
4. **Categorías emergentes** (RWA, SocialFi, etc.)

---

## ✅ CONCLUSIÓN

**Antes**: Lista genérica con BTC/ETH (estables)
**Ahora**: Lista optimizada para buscar pumps de +20% en altcoins volátiles

**Resultado esperado**: Mayor tasa de detección de pumps, mejor ROI
