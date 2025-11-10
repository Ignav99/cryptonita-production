#!/usr/bin/env python3
"""
SHOW CONFIGURED TICKERS
=======================
Muestra la lista de monedas configuradas para el bot
"""

print("=" * 70)
print("📊 MONEDAS CONFIGURADAS PARA CRYPTONITA BOT V3")
print("=" * 70)
print()

# Nueva lista optimizada para altcoins volátiles
tickers = [
    # Layer 1 / Layer 2 (Alta volatilidad, buen volumen)
    "SOLUSDT", "AVAXUSDT", "NEARUSDT", "APTUSDT", "SUIUSDT",
    "SEIUSDT", "ARBUSDT", "OPUSDT", "INJUSDT", "FTMUSDT",

    # DeFi (Alto potencial de pumps por noticias)
    "UNIUSDT", "AAVEUSDT", "MKRUSDT", "LDOUSDT", "RUNEUSDT",
    "CRVUSDT", "GMXUSDT", "DYDXUSDT",

    # Gaming / Metaverse (Muy volátiles, eventos frecuentes)
    "SANDUSDT", "MANAUSDT", "AXSUSDT", "IMXUSDT", "GALAUSDT",

    # AI / Compute (Tendencia 2024-2025, alta volatilidad)
    "FETUSDT", "AGIXUSDT", "WLDUSDT", "RENDERUSDT",

    # Memecoins (Alto volumen y volatilidad extrema)
    "DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "FLOKIUSDT", "BONKUSDT",

    # Otros altcoins sólidos (volatilidad media-alta)
    "DOTUSDT", "ATOMUSDT", "ADAUSDT", "MATICUSDT", "LINKUSDT",
    "ICPUSDT", "FILUSDT", "HBARUSDT", "VETUSDT", "ALGOUSDT"
]

categories = {
    "Layer 1/2": ["SOL", "AVAX", "NEAR", "APT", "SUI", "SEI", "ARB", "OP", "INJ", "FTM"],
    "DeFi": ["UNI", "AAVE", "MKR", "LDO", "RUNE", "CRV", "GMX", "DYDX"],
    "Gaming/Metaverse": ["SAND", "MANA", "AXS", "IMX", "GALA"],
    "AI/Compute": ["FET", "AGIX", "WLD", "RENDER"],
    "Memecoins": ["DOGE", "SHIB", "PEPE", "FLOKI", "BONK"],
    "Otros Altcoins": ["DOT", "ATOM", "ADA", "MATIC", "LINK", "ICP", "FIL", "HBAR", "VET", "ALGO"]
}

for category, coins in categories.items():
    print(f"\n🔹 {category} ({len(coins)} monedas):")
    print("   " + ", ".join(coins))

print()
print("=" * 70)
print(f"✅ TOTAL: {len(tickers)} monedas")
print("=" * 70)
print()
print("💡 CARACTERÍSTICAS:")
print("   ✅ Alta volatilidad (>5% movimiento diario)")
print("   ✅ Volumen >$20M USD/día")
print("   ✅ Market cap: $100M - $15B")
print("   ❌ EXCLUIDAS: BTC, ETH, BNB (muy estables)")
print()
print("🎯 OBJETIVO: Detectar pumps de +20% en 15 días")
print()
