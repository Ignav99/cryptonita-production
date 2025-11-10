# 🎯 LISTO PARA PROBAR - Tu Setup Actual

## ✅ Lo Que YA Tienes Configurado

### Database (NO CAMBIÓ)
```env
DB_NAME: cryptonita_mvp
DB_USER: cryptonita_admin
DB_PASSWORD: TIZavoltio999
DB_HOST: localhost
DB_PORT: 5432
```
✅ **Tu base de datos se mantiene igual** - Solo necesitas iniciarla

### Binance Testnet (NO CAMBIÓ)
```env
BINANCE_TESTNET_API_KEY: m18FjcskRrNOkVqmB291WNEBsPXr3R2LWOrvtZ88TBp3RKQgQqaefzw1UB7ZUpMe
BINANCE_TESTNET_API_SECRET: qbhFNMMfnSsJINRCI3pF8ONVNtpWXX01ROh8q3F7SNEeQ4Vf1ZV3lGkZvUtSKECU
```
✅ **Listo para trading en testnet**

### Configuración de Trading (NO CAMBIÓ)
```env
TRADING_MODE: testnet
MAX_POSITION_SIZE_USD: 500
MAX_DAILY_LOSS_USD: 200
INITIAL_CAPITAL: 10000
```
✅ **Tu configuración se mantiene**

---

## 🆕 Lo Que SE AÑADIÓ (Para Web Dashboard)

Solo añadimos estas 3 variables **nuevas** al .env:

```env
JWT_SECRET_KEY=yotuVeLXjP4O4NOiZ9yQb-aPdAGBJ5KVZcKj3G5-zwc
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440
```

**Propósito:** Para la autenticación del dashboard web (login).

---

## 🚀 PASOS PARA PROBAR (5 minutos)

### 1️⃣ Iniciar PostgreSQL

```bash
sudo systemctl start postgresql
```

**Verificar:**
```bash
sudo systemctl status postgresql
```

Deberías ver: `active (running)` ✅

### 2️⃣ Crear Entorno Virtual Python

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3️⃣ Instalar Dependencias Python

```bash
pip install -r requirements.txt
```

Esto toma ~2 minutos.

### 4️⃣ Instalar Frontend

```bash
cd frontend
npm install
cd ..
```

Esto toma ~1 minuto.

---

## ▶️ EJECUTAR TODO

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
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Terminal 2: Dashboard Web

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

### Terminal 3 (Opcional): Bot

```bash
source venv/bin/activate
python run_bot.py
```

---

## 🌐 ACCEDER AL DASHBOARD

### 1. Abre el navegador:
```
http://localhost:3000
```

### 2. Login:
```
Username: admin
Password: cryptonita2025
```

### 3. ¡Ver el Dashboard! 🎉

Deberías ver:
- ✅ Stats cards (P&L, Win Rate, etc.)
- ✅ Botones START/STOP/RESTART
- ✅ Panel de posiciones
- ✅ Señales recientes
- ✅ Histórico de trades

---

## 🧪 PRUEBAS BÁSICAS

### Test 1: Login ✅
1. Ve a http://localhost:3000
2. Ingresa usuario/contraseña
3. Deberías entrar al dashboard

### Test 2: Ver API Docs ✅
1. Ve a http://localhost:8000/api/docs
2. Deberías ver Swagger UI con todos los endpoints

### Test 3: Start/Stop Bot ✅
1. En dashboard, click **START BOT**
2. Deberías ver:
   - Botón se pone verde "Running"
   - Aparece PID, CPU, RAM
3. Click **STOP BOT**
4. El bot se detiene

### Test 4: Ver Señales ✅
1. Con el bot corriendo (START)
2. Espera ~2 minutos
3. En "Recent Signals" deberían aparecer señales
4. Las señales BUY > 60% se destacan en verde

---

## 📊 TU BASE DE DATOS

**NO necesitas recrearla** - Las tablas ya existen o se crean automáticamente.

Si quieres verificar:
```bash
PGPASSWORD=TIZavoltio999 psql -h localhost -U cryptonita_admin -d cryptonita_mvp

# Dentro de psql:
\dt                              # Ver tablas
SELECT * FROM bot_status;        # Ver estado del bot
SELECT * FROM signals LIMIT 5;   # Ver señales
\q                               # Salir
```

---

## ❓ TROUBLESHOOTING

### PostgreSQL no inicia
```bash
# Ver logs
sudo journalctl -u postgresql -n 50

# Reiniciar
sudo systemctl restart postgresql
```

### Error: "ModuleNotFoundError"
```bash
# Asegúrate de activar venv
source venv/bin/activate

# Reinstalar
pip install -r requirements.txt
```

### Frontend: "Failed to fetch"
```bash
# Verifica que API esté corriendo
curl http://localhost:8000/health

# Debería responder: {"status": "healthy", ...}
```

### Bot no encuentra datos
Es normal en testnet. El bot:
- ✅ Usa Binance **PRODUCTION** para datos (read-only)
- ✅ Usa Binance **TESTNET** para trading
- No necesitas cambiar nada

---

## 📚 DOCUMENTACIÓN

| Archivo | Para Qué |
|---------|----------|
| `LOCAL_TESTING.md` | Guía completa de testing |
| `PROJECT_SUMMARY.md` | Overview del sistema |
| `DEPLOYMENT_GUIDE.md` | Deploy a producción |
| `DYNAMIC_TP_SL_SYSTEM.md` | Sistema TP/SL explicado |

---

## 🎯 SIGUIENTE PASO

**Ejecuta esto para verificar todo:**
```bash
./quick_setup.sh
```

Este script te dirá exactamente qué falta y qué hacer.

---

## ✨ Resumen

**No cambiamos nada de tu configuración original:**
- ✅ Tu base de datos `cryptonita_mvp` se mantiene
- ✅ Tu usuario `cryptonita_admin` se mantiene
- ✅ Tus API keys de Binance se mantienen
- ✅ Tus límites de trading se mantienen

**Solo añadimos:**
- JWT secret (para login web)
- API host/port (para dashboard)
- Frontend React completo
- Bot Manager (start/stop desde web)

**Todo sigue funcionando igual + ahora tienes dashboard web!** 🚀

---

**¿Listo para probar?**

1. `sudo systemctl start postgresql`
2. `./quick_setup.sh` (para verificar)
3. Seguir los pasos que te indica
4. ¡Abrir http://localhost:3000 y disfrutar! 🎉
