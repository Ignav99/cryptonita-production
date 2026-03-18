#!/usr/bin/env python3
"""
CHECK COIN VOLUME AND VOLATILITY
=================================
Verifica volumen 24h y volatilidad de monedas en Binance
"""

import sys
from pathlib import Path
import requests
import pandas as pd
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def get_binance_24h_tickers():
    """Get 24h ticker data from Binance"""
    try:
        url = "https://api.binance.com/api/v3/ticker/24hr"
        response = requests.get(url, timeout=10)
        data = response.json()
        return data
    except Exception as e:
        print(f"❌ Error fetching data: {e}")
        return []


def analyze_tickers(tickers_to_check):
    """Analyze volume and volatility for given tickers"""
    print("=" * 80)
    print("📊 ANÁLISIS DE VOLUMEN Y VOLATILIDAD - BINANCE")
    print("=" * 80)

    # Get all 24h data
    print("\n⏳ Obteniendo datos de Binance...")
    all_data = get_binance_24h_tickers()

    if not all_data:
        print("❌ No se pudo obtener datos")
        return

    # Filter for our tickers
    results = []

    for ticker in tickers_to_check:
        ticker_data = next((item for item in all_data if item['symbol'] == ticker), None)

        if ticker_data:
            volume_usd = float(ticker_data['quoteVolume'])
            price_change_pct = float(ticker_data['priceChangePercent'])
            high_24h = float(ticker_data['highPrice'])
            low_24h = float(ticker_data['lowPrice'])
            last_price = float(ticker_data['lastPrice'])

            # Calculate volatility (H-L range as % of price)
            volatility = ((high_24h - low_24h) / last_price) * 100

            results.append({
                'Ticker': ticker.replace('USDT', ''),
                'Precio': f"${last_price:,.4f}",
                'Vol 24h': f"${volume_usd:,.0f}",
                'Vol (M)': f"${volume_usd/1e6:.1f}M",
                'Cambio 24h': f"{price_change_pct:+.2f}%",
                'Volatilidad': f"{volatility:.2f}%",
                'Vol_num': volume_usd,
                'Vol_pct': volatility
            })

    # Create DataFrame
    df = pd.DataFrame(results)

    # Sort by volume
    df = df.sort_values('Vol_num', ascending=False)

    print(f"\n✅ Datos obtenidos para {len(df)} monedas\n")

    # Display results
    print(df[['Ticker', 'Precio', 'Vol (M)', 'Cambio 24h', 'Volatilidad']].to_string(index=False))

    # Statistics
    print("\n" + "=" * 80)
    print("📈 ESTADÍSTICAS:")
    print("=" * 80)
    print(f"Volumen promedio: ${df['Vol_num'].mean()/1e6:.1f}M")
    print(f"Volumen mediano: ${df['Vol_num'].median()/1e6:.1f}M")
    print(f"Volatilidad promedio: {df['Vol_pct'].mean():.2f}%")
    print(f"Volatilidad mediana: {df['Vol_pct'].median():.2f}%")

    # Filter recommendations
    print("\n" + "=" * 80)
    print("💡 RECOMENDACIONES:")
    print("=" * 80)

    high_vol = df[df['Vol_num'] > 20e6]  # > $20M
    print(f"\n✅ Con volumen >$20M: {len(high_vol)} monedas")
    if len(high_vol) > 0:
        print(high_vol[['Ticker', 'Vol (M)', 'Volatilidad']].to_string(index=False))

    low_vol = df[df['Vol_num'] < 10e6]  # < $10M
    if len(low_vol) > 0:
        print(f"\n⚠️  Con volumen <$10M (EVITAR): {len(low_vol)} monedas")
        print(low_vol[['Ticker', 'Vol (M)']].to_string(index=False))

    high_volatility = df[df['Vol_pct'] > 5.0]  # > 5% volatilidad
    if len(high_volatility) > 0:
        print(f"\n🔥 Alta volatilidad (>5%): {len(high_volatility)} monedas")
        print(high_volatility[['Ticker', 'Volatilidad', 'Cambio 24h']].to_string(index=False))


if __name__ == "__main__":
    # Current tickers
    current_tickers = [
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT",
        "XRPUSDT", "DOTUSDT", "DOGEUSDT", "AVAXUSDT", "MATICUSDT",
        "LINKUSDT", "LTCUSDT", "UNIUSDT", "ATOMUSDT", "ETCUSDT",
        "XLMUSDT", "VETUSDT", "ICPUSDT", "FILUSDT", "TRXUSDT",
        "APTUSDT", "NEARUSDT", "AAVEUSDT", "ALGOUSDT", "SHIBUSDT",
        "PEPEUSDT", "ARBUSDT", "OPUSDT", "INJUSDT", "WLDUSDT"
    ]

    print("\n🔍 Analizando monedas actuales del config.py...\n")
    analyze_tickers(current_tickers)
