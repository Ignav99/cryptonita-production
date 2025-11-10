# 🧪 Testing Local - Guía Completa

Todo el sistema está listo! Ahora vamos a probarlo localmente antes de hacer deploy.

---

## 📋 Checklist Previo

✅ Bot de trading implementado
✅ Sistema dinámico de TP/SL
✅ API FastAPI completa
✅ Bot Manager (start/stop desde API)
✅ Frontend React completo
✅ WebSocket real-time
✅ Autenticación JWT

---

## 🚀 Setup Local en 5 Pasos

### Paso 1: Configurar Base de Datos PostgreSQL

```bash
# Opción A: Instalar PostgreSQL (si no lo tienes)
sudo apt update
sudo apt install postgresql postgresql-contrib

# Opción B: Usar Docker (más rápido)
docker run --name cryptonita-db \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=cryptonita \
  -p 5432:5432 \
  -d postgres:16

# Crear base de datos
psql -U postgres -h localhost
CREATE DATABASE cryptonita;
CREATE USER cryptonita_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE cryptonita TO cryptonita_user;
\q
```

### Paso 2: Configurar Variables de Entorno

Crea `.env` en la raíz:

```bash
cat > .env << 'EOF'
# Database
DATABASE_URL=postgresql://cryptonita_user:your_password@localhost:5432/cryptonita

# Binance API (Testnet)
BINANCE_API_KEY=your_testnet_api_key
BINANCE_API_SECRET=your_testnet_secret

# Trading
TRADING_MODE=testnet
MAX_POSITIONS=10
PREDICTION_THRESHOLD=0.60
POSITION_SIZE_PCT=0.10

# Security
JWT_SECRET_KEY=your-super-secret-key-change-this-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440

# API
API_HOST=0.0.0.0
API_PORT=8000
EOF
```

**Genera JWT Secret:**
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Paso 3: Instalar Dependencias Python

```bash
# Crear entorno virtual
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

### Paso 4: Inicializar Base de Datos

```bash
# Crear tablas
python3 << 'EOF'
from config import settings
from src.data.storage.db_manager import DatabaseManager

db = DatabaseManager(settings.get_database_url())
print("✅ Database initialized successfully!")
EOF
```

### Paso 5: Instalar Frontend

```bash
cd frontend
npm install
cd ..
```

---

## ⚡ Ejecutar Todo

### Terminal 1: API Backend

```bash
source venv/bin/activate
python -m uvicorn src.api.main:app --reload --port 8000
```

**Deberías ver:**
```
🚀 CRYPTONITA TRADING BOT API - STARTING
Version: 3.0
Environment: development
Trading Mode: testnet
API running on: http://0.0.0.0:8000
```

**Prueba:** Abre http://localhost:8000/health

### Terminal 2: Frontend Dashboard

```bash
cd frontend
npm run dev
```

**Deberías ver:**
```
  VITE v5.0.8  ready in 500 ms

  ➜  Local:   http://localhost:3000/
  ➜  Network: http://192.168.x.x:3000/
```

**Prueba:** Abre http://localhost:3000

### Terminal 3: Bot (Opcional - para probar)

```bash
source venv/bin/activate
python run_bot.py
```

---

## 🧪 Testing Paso a Paso

### 1. Probar Login

1. Ve a http://localhost:3000
2. Login con:
   ```
   Username: admin
   Password: cryptonita2025
   ```
3. ✅ Deberías ver el dashboard

### 2. Probar API Docs

1. Ve a http://localhost:8000/api/docs
2. Autoriza con token JWT
3. Prueba endpoint `/api/dashboard/stats`
4. ✅ Deberías ver datos del bot

### 3. Probar Control del Bot

**Desde el Dashboard:**

1. Click en **START BOT**
   - ✅ Botón se pone verde "Running"
   - ✅ Aparece PID, CPU, RAM
   - ✅ Bot empieza a scanear

2. Observa logs en Terminal 3:
   ```
   🔍 MARKET SCAN - CYCLE #1
   📊 Fetching macro data...
   📊 Fetching BTC data...
   🔮 Making predictions...
   ```

3. Click en **STOP BOT**
   - ✅ Bot se detiene
   - ✅ PID desaparece
   - ✅ Status cambia a "Stopped"

### 4. Probar Datos en Dashboard

**Stats Cards:**
- Total P&L (debe estar en $0.00 inicialmente)
- Win Rate (0% sin trades)
- Open Positions (0)
- Today P&L ($0.00)

**Recent Signals:**
- Después del primer scan, deberían aparecer señales
- Verás tickers con probabilidades
- Las señales BUY > 0.60 se destacan en verde

**Positions:**
- Vacío hasta que se ejecute un trade

**Trades:**
- Vacío hasta que se ejecute un trade

### 5. Probar WebSocket

1. Abre la consola del navegador (F12)
2. Deberías ver:
   ```
   ✅ WebSocket connected
   📡 WebSocket update: {...}
   ```
3. El indicador "Live" debe estar verde
4. Los datos se actualizan automáticamente

### 6. Probar Ejecución de Trade (Testnet)

**Pre-requisito:** Tener API keys de Binance Testnet configuradas.

1. Asegúrate de que el bot esté corriendo
2. Espera a que encuentre una señal BUY > 0.60
3. Si `auto_trading_enabled: true` en `bot_config.json`:
   - ✅ Bot ejecutará trade automáticamente
   - ✅ Aparecerá en "Open Positions"
   - ✅ Aparecerá en "Trade History"
   - ✅ TP/SL se colocarán automáticamente

4. Monitorea la posición:
   - Cada 5 minutos, el bot verifica TP/SL
   - Trailing Stop se activa con +5% profit
   - Salidas inteligentes si detecta reversión

---

## 🔍 Verificar Funcionamiento

### Checklist de Funcionalidades

**Backend API:**
- [ ] `/health` responde OK
- [ ] `/api/docs` muestra Swagger
- [ ] Login genera JWT token
- [ ] Dashboard endpoints retornan datos
- [ ] Controls start/stop funcionan
- [ ] Process status muestra PID/CPU/RAM

**Frontend:**
- [ ] Login funciona
- [ ] Dashboard carga sin errores
- [ ] Stats cards muestran datos
- [ ] Botones Start/Stop funcionan
- [ ] WebSocket conecta (indicador verde)
- [ ] Auto-refresh funciona
- [ ] Responsive en móvil

**Bot:**
- [ ] Inicia correctamente
- [ ] Fetch de datos de Binance funciona
- [ ] Cálculo de 48 features sin errores
- [ ] Predicciones con XGBoost funcionan
- [ ] Guarda señales en DB
- [ ] TP/SL dinámico se calcula
- [ ] Trailing stop funciona

---

## 🐛 Problemas Comunes

### Error: "ModuleNotFoundError: No module named 'pydantic_settings'"

```bash
source venv/bin/activate
pip install -r requirements.txt
```

### Error: "Database connection failed"

```bash
# Verifica que PostgreSQL esté corriendo
sudo systemctl status postgresql

# O si usas Docker:
docker ps | grep cryptonita-db

# Verifica la URL en .env
echo $DATABASE_URL
```

### Error: "Binance API error"

```bash
# Para testnet, obtén API keys en:
# https://testnet.binance.vision/

# Verifica las keys en .env
grep BINANCE .env
```

### Frontend: "Failed to fetch"

```bash
# Verifica que la API esté corriendo
curl http://localhost:8000/health

# Verifica VITE_API_URL en frontend/.env
cat frontend/.env
```

### Bot no encuentra suficientes datos

```bash
# Esto es normal en testnet
# El bot usa producción para datos históricos (read-only)
# y testnet solo para trading
```

---

## 📊 Logs y Debugging

### Ver logs del bot:
```bash
tail -f logs/bot.log
```

### Ver logs de la API:
```bash
# Los logs aparecen en la terminal donde ejecutaste uvicorn
```

### Ver logs del frontend:
```bash
# Consola del navegador (F12)
```

### Revisar base de datos:
```bash
psql -U cryptonita_user -d cryptonita -h localhost

# Ver señales
SELECT * FROM signals ORDER BY timestamp DESC LIMIT 10;

# Ver trades
SELECT * FROM trades ORDER BY timestamp DESC LIMIT 10;

# Ver posiciones
SELECT * FROM positions WHERE status = 'open';

# Ver estado del bot
SELECT * FROM bot_status ORDER BY last_update DESC LIMIT 1;
```

---

## ✅ Todo Funciona? Próximos Pasos

Si todo funciona localmente:

### Opción A: Deploy a Render

1. Lee `DEPLOYMENT_GUIDE.md`
2. Configura PostgreSQL en Render
3. Deploy backend y frontend
4. Configura variables de entorno
5. ¡Listo! Accede desde cualquier lugar

### Opción B: Seguir Probando Local

1. Déjalo corriendo 24 horas
2. Monitorea señales y trades
3. Verifica que el TP/SL dinámico funcione
4. Prueba el trailing stop
5. Revisa las salidas inteligentes

---

## 📞 Ayuda

Si encuentras problemas:

1. Revisa los logs
2. Consulta `DEPLOYMENT_GUIDE.md`
3. Verifica `DYNAMIC_TP_SL_SYSTEM.md` para el sistema de TP/SL
4. Lee `frontend/README.md` para el dashboard

---

**Sistema Completo Ready for Testing!** 🚀
