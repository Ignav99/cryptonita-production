# 🚀 QUICK START - CRYPTONITA PRODUCTION

Guía rápida para poner en marcha el bot de trading.

---

## 📦 OPCIÓN 1: Setup Automático (RECOMENDADO)

```bash
# 1. Hacer ejecutable el script de setup
chmod +x setup.sh

# 2. Ejecutar setup automático
./setup.sh

# 3. Seguir las instrucciones en pantalla
```

El script automático hará:
- ✅ Verificar Python
- ✅ Crear entorno virtual
- ✅ Instalar todas las dependencias
- ✅ Crear base de datos (opcional)
- ✅ Configurar todo

---

## 🛠️ OPCIÓN 2: Setup Manual

### Paso 1: Crear entorno virtual

```bash
# Crear entorno virtual
python3 -m venv venv

# Activar entorno virtual
source venv/bin/activate  # Linux/Mac
# o
venv\Scripts\activate     # Windows
```

### Paso 2: Instalar dependencias

```bash
# Actualizar pip
pip install --upgrade pip

# Instalar todas las dependencias
pip install -r requirements.txt
```

Esto instalará:
- FastAPI, Uvicorn (API)
- SQLAlchemy, psycopg2 (Database)
- XGBoost, scikit-learn (ML)
- python-binance (Trading)
- Y más... (~50 paquetes)

### Paso 3: Configurar PostgreSQL

```bash
# Crear base de datos
createdb cryptonita_mvp

# Crear tablas
python scripts/setup_database.py
```

### Paso 4: Verificar configuración

```bash
# Ver archivo .env
cat .env

# Verificar que tengas:
# - DB credentials
# - Binance API keys (testnet)
# - Trading mode = testnet
```

---

## 🧪 TESTING INICIAL

### Test 1: Ver lista de monedas

```bash
python scripts/show_tickers.py
```

Debería mostrar:
```
📊 MONEDAS CONFIGURADAS PARA CRYPTONITA BOT V3
...
✅ TOTAL: 42 monedas
```

### Test 2: Verificar base de datos

```bash
python scripts/setup_database.py
```

Debería mostrar:
```
✅ crypto_prices - OK
✅ signals - OK
✅ trades - OK
✅ bot_status - OK
✅ positions - OK
✅ performance_metrics - OK
```

### Test 3: Probar API (sin bot)

```bash
# Terminal 1: Ejecutar API
python run_api.py

# Terminal 2: Probar endpoint
curl http://localhost:8000/health

# Debería responder:
# {"status":"healthy","version":"3.0","environment":"development","trading_mode":"testnet"}
```

Luego visita: http://localhost:8000

---

## 🤖 EJECUTAR EL BOT

### Opción A: Solo API (Dashboard sin trading)

```bash
python run_api.py
```

Visita: http://localhost:8000
- Usuario: `admin`
- Contraseña: `cryptonita2024`

### Opción B: Solo Bot (Trading sin dashboard)

```bash
python run_bot.py
```

El bot:
- Escaneará mercado cada 12 horas
- Monitoreará posiciones cada 5 minutos
- Ejecutará trades automáticamente (si `AUTO_TRADING=true`)

### Opción C: Bot + API juntos (RECOMENDADO)

```bash
# Terminal 1: API
python run_api.py

# Terminal 2: Bot
python run_bot.py
```

Así puedes:
- Ver el dashboard en tiempo real
- Monitorear las operaciones del bot
- Controlar el bot desde la UI

---

## 📊 VERIFICAR QUE TODO FUNCIONA

### 1. Base de datos
```bash
psql cryptonita_mvp -c "SELECT COUNT(*) FROM bot_status;"
# Debería retornar 1
```

### 2. API
```bash
curl http://localhost:8000/health
# Debería retornar: {"status":"healthy",...}
```

### 3. Binance (testnet)
El bot verificará la conexión automáticamente al iniciar.

---

## 🔧 CONFIGURACIÓN IMPORTANTE

### Archivo: `.env`

```bash
# Trading mode (IMPORTANTE)
TRADING_MODE=testnet  # Usar testnet primero!

# Binance Testnet
BINANCE_TESTNET_API_KEY=tu_key_aquí
BINANCE_TESTNET_API_SECRET=tu_secret_aquí

# Risk management
MAX_POSITION_SIZE_USD=500
MAX_DAILY_LOSS_USD=200
MAX_POSITIONS=10
```

### Archivo: `bot_config.json`

```json
{
  "trading": {
    "scan_interval_hours": 12,
    "position_monitoring_minutes": 5,
    "auto_trading_enabled": true
  }
}
```

---

## 📝 LOGS

Ver logs del bot:
```bash
tail -f logs/cryptonita.log
```

O en tiempo real durante ejecución:
```bash
python run_bot.py
# Los logs aparecerán en consola
```

---

## ⚠️ TROUBLESHOOTING

### Error: "ModuleNotFoundError"
```bash
# Asegúrate de que el entorno virtual esté activado
source venv/bin/activate

# Reinstala dependencias
pip install -r requirements.txt
```

### Error: "Database connection failed"
```bash
# Verifica que PostgreSQL esté corriendo
pg_isready

# Verifica credenciales en .env
cat .env | grep DB_
```

### Error: "Binance API error"
```bash
# Verifica que uses las keys de TESTNET
# Verifica que TRADING_MODE=testnet en .env
```

---

## 🎯 WORKFLOW RECOMENDADO

### Primera vez:
1. ✅ Setup completo (entorno virtual + dependencias)
2. ✅ Configurar base de datos
3. ✅ Probar API sola
4. ✅ Ejecutar bot en modo testnet
5. ✅ Observar logs y resultados
6. ✅ Monitorear durante 1 semana

### Después de testing:
1. Cambiar a production en `.env`
2. Actualizar API keys de Binance (reales)
3. Ejecutar en producción

---

## 📚 RECURSOS

- **README completo**: `README.md`
- **Documentación modelo**: `PRODUCTION_SYSTEM/docs/README_V3.md`
- **Lista monedas**: `python scripts/show_tickers.py`
- **Explicación monedas**: `TICKERS_EXPLANATION.md`
- **API docs**: http://localhost:8000/api/docs (cuando API esté corriendo)

---

## ✅ CHECKLIST ANTES DE PRODUCCIÓN

- [ ] Bot corriendo en testnet por 1+ mes
- [ ] Win rate > 40%
- [ ] Max drawdown < 10%
- [ ] Trades ejecutándose correctamente
- [ ] TP/SL funcionando
- [ ] Logs sin errores críticos
- [ ] Database actualizándose correctamente

Solo después de verificar todo ✅, cambiar a production.

---

**¿Dudas? Revisa los logs en `logs/cryptonita.log`**
