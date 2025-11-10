# 🚀 CRYPTONITA PRODUCTION

Sistema automatizado de trading de criptomonedas usando Machine Learning (XGBoost Model V3)

## 📊 Características

- **Modelo V3**: 42 features, ROI +82.7%, Win Rate 48.8%
- **Trading Automático**: Escaneo cada 12 horas, monitoreo cada 5 minutos
- **Dashboard Web**: Tiempo real con WebSocket
- **Risk Management**: Stop Loss -5%, Take Profit +15%, Max 10 posiciones
- **Testnet Ready**: Pruebas en Binance Testnet antes de producción

## 🏗️ Arquitectura

```
cryptonita-production/
├── src/
│   ├── api/           # FastAPI backend
│   ├── bot/           # Trading bot
│   ├── data/          # Feature engineering & macro data
│   ├── models/        # ML predictor
│   └── services/      # Binance integration
├── PRODUCTION_SYSTEM/
│   ├── models/        # XGBoost model V3
│   ├── configs/       # Configuración producción
│   └── docs/          # Documentación
├── scripts/           # Setup database
├── bot_config.json    # Configuración del bot
├── .env               # Variables de entorno
└── README.md
```

## 🚀 Instalación

### 1. Clonar repositorio
```bash
git clone <repo-url>
cd cryptonita-production
```

### 2. Crear entorno virtual
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# o
venv\Scripts\activate     # Windows
```

### 3. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 4. Configurar base de datos PostgreSQL

Edita el archivo `.env`:
```bash
DB_USER=cryptonita_admin
DB_PASSWORD=TIZavoltio999
DB_HOST=localhost
DB_PORT=5432
DB_NAME=cryptonita_mvp
```

Crear base de datos:
```bash
# PostgreSQL
createdb cryptonita_mvp

# Crear tablas
python scripts/setup_database.py
```

### 5. Configurar API keys de Binance

En `.env`:
```bash
# Testnet (default)
BINANCE_TESTNET_API_KEY=your_testnet_key
BINANCE_TESTNET_API_SECRET=your_testnet_secret

# Production (cuando estés listo)
BINANCE_API_KEY=your_production_key
BINANCE_API_SECRET=your_production_secret
```

## 🎮 Uso

### Opción 1: Ejecutar Bot + API juntos

```bash
# Terminal 1: API Dashboard
python run_api.py

# Terminal 2: Trading Bot
python run_bot.py
```

### Opción 2: Solo API (sin trading automático)

```bash
python run_api.py
```

Accede al dashboard: http://localhost:8000

### Opción 3: Solo Bot (sin dashboard)

```bash
python run_bot.py
```

## 📱 Dashboard

### Login
- **URL**: http://localhost:8000
- **Usuario**: admin
- **Contraseña**: cryptonita2024

### Endpoints API
- **Docs**: http://localhost:8000/api/docs
- **Stats**: http://localhost:8000/api/dashboard/stats
- **Positions**: http://localhost:8000/api/dashboard/positions
- **Signals**: http://localhost:8000/api/dashboard/signals
- **Trades**: http://localhost:8000/api/dashboard/trades

## ⚙️ Configuración

### `bot_config.json`

```json
{
  "trading": {
    "scan_interval_hours": 12,          // Escanear mercado cada 12h
    "position_monitoring_minutes": 5,    // Monitorear posiciones cada 5min
    "auto_trading_enabled": true,        // Trading automático
    "testnet_capital_usd": 5000         // Capital inicial testnet
  },
  "risk_management": {
    "max_positions": 10,
    "position_size_pct": 0.10,          // 10% por posición
    "take_profit_pct": 0.15,            // TP: +15%
    "stop_loss_pct": 0.05,              // SL: -5%
    "max_daily_loss_usd": 200           // Máx pérdida diaria
  },
  "model": {
    "threshold": 0.60                    // Probabilidad mínima
  }
}
```

### `.env` Variables

```bash
# Trading Mode
TRADING_MODE=testnet  # o production

# Risk Parameters
MAX_POSITION_SIZE_USD=500
MAX_DAILY_LOSS_USD=200
MAX_POSITIONS=10
REQUIRE_MANUAL_APPROVAL=false
```

## 🔄 Flujo del Bot

### Escaneo (cada 12 horas)
1. Obtener datos OHLCV de 30 criptomonedas
2. Obtener datos macro (Fear & Greed, VIX, SPX)
3. Calcular 42 features por moneda
4. Hacer predicciones con modelo V3
5. Filtrar señales (threshold 0.60)
6. Ejecutar trades automáticamente

### Monitoreo (cada 5 minutos)
1. Verificar precio actual de posiciones abiertas
2. Comprobar si se alcanzó TP (+15%) o SL (-5%)
3. Actualizar P&L en base de datos
4. Enviar actualizaciones a dashboard via WebSocket

## 🛡️ Risk Management

- **Max Positions**: 10 simultáneas
- **Position Size**: 10% del capital ($500 max)
- **Take Profit**: +15%
- **Stop Loss**: -5%
- **Max Daily Loss**: $200 (bot se detiene)
- **Portfolio Risk**: Máx 30% en riesgo

## 📊 Modelo V3

- **Features**: 42 (14 original + 15 tendencia + 5 macro + 8 momentum avanzado)
- **Algoritmo**: XGBoost
- **Target**: Pumps >20% en 15 días
- **Threshold**: 0.60
- **ROI (test)**: +82.7%
- **Win Rate**: 48.8%
- **Sharpe Ratio**: 3.43

## 🧪 Testing (Testnet)

1. Configura `.env`:
```bash
TRADING_MODE=testnet
```

2. Ejecuta bot:
```bash
python run_bot.py
```

3. Monitorea en dashboard:
```bash
python run_api.py
```

4. Observa trades en Binance Testnet

## 🚀 Producción

⚠️ **IMPORTANTE**: Antes de pasar a producción:

1. ✅ Testea al menos 1 mes en testnet
2. ✅ Verifica que Win Rate > 40%
3. ✅ Confirma que respeta límites de pérdida
4. ✅ Revisa logs de errores

Cambiar a producción:
```bash
# .env
TRADING_MODE=production
BINANCE_API_KEY=your_real_key
BINANCE_API_SECRET=your_real_secret
INITIAL_CAPITAL=10000
```

## 📝 Logs

Los logs se guardan en:
```
logs/cryptonita.log
```

Niveles:
- **INFO**: Operaciones normales
- **DEBUG**: Detalles de features y predicciones
- **WARNING**: Trades bloqueados, límites alcanzados
- **ERROR**: Fallos de conexión, errores de Binance

## 🔧 Troubleshooting

### Error: "Could not connect to database"
```bash
# Verifica PostgreSQL
pg_isready
# Verifica credenciales en .env
```

### Error: "Binance API error"
```bash
# Verifica API keys en .env
# Verifica que estés en testnet si usas testnet keys
```

### Bot no ejecuta trades
```bash
# Verifica bot_config.json:
"auto_trading_enabled": true

# Verifica .env:
REQUIRE_MANUAL_APPROVAL=false
```

## 📚 Documentación

- **Modelo V3**: `PRODUCTION_SYSTEM/docs/README_V3.md`
- **Config Completa**: `PRODUCTION_SYSTEM/docs/CONFIGURACION_COMPLETA_V3.md`
- **Features**: `PRODUCTION_SYSTEM/configs/production_features_config_v3.json`

## 🤝 Soporte

Para consultas sobre el sistema:
1. Revisa logs en `logs/cryptonita.log`
2. Consulta documentación en `PRODUCTION_SYSTEM/docs/`
3. Verifica configuración en `bot_config.json`

## 📄 Licencia

Proyecto privado - Todos los derechos reservados

---

**Versión**: 3.0
**Última actualización**: 2025-11-10
