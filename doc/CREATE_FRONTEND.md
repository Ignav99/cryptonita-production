# 🎨 Dashboard Frontend - Guía Completa

## Sistema ya configurado

✅ API Backend con control del bot
✅ Bot Manager para start/stop
✅ Endpoints completos
✅ WebSocket ready

---

## 📦 Estructura del Dashboard

```
frontend/
├── package.json          ✅ Creado
├── vite.config.js        ✅ Creado
├── tailwind.config.js    ✅ Creado
├── index.html            ✅ Creado
├── src/
│   ├── main.jsx          → Entrada de la app
│   ├── App.jsx           → Componente principal
│   ├── styles/
│   │   └── index.css     → Tailwind CSS
│   ├── api/
│   │   └── client.js     → Axios configurado
│   ├── components/
│   │   ├── Dashboard.jsx     → Panel principal
│   │   ├── BotControls.jsx   → ON/OFF/Restart
│   │   ├── Positions.jsx     → Posiciones activas
│   │   ├── Signals.jsx       → Señales recientes
│   │   ├── Trades.jsx        → Histórico trades
│   │   └── Stats.jsx         → Métricas tiempo real
│   └── hooks/
│       └── useWebSocket.js   → Real-time updates
```

---

## 🚀 Opción 1: Deploy Rápido en Render (Recomendado)

### Configuración para Render

Crea `render.yaml`:

```yaml
services:
  # Backend API
  - type: web
    name: cryptonita-api
    env: python
    buildCommand: "pip install -r requirements.txt"
    startCommand: "uvicorn src.api.main:app --host 0.0.0.0 --port $PORT"
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: cryptonita-db
          property: connectionString
      - key: BINANCE_API_KEY
        sync: false
      - key: BINANCE_API_SECRET
        sync: false

  # Frontend Dashboard
  - type: web
    name: cryptonita-dashboard
    env: static
    buildCommand: "cd frontend && npm install && npm run build"
    staticPublishPath: frontend/dist
    routes:
      - type: rewrite
        source: /api/*
        destination: https://cryptonita-api.onrender.com/api/*

databases:
  - name: cryptonita-db
    databaseName: cryptonita
    user: cryptonita_user
```

### Deploy Steps:

1. **Push a GitHub:**
   ```bash
   git add -A
   git commit -m "feat: Add complete dashboard frontend structure"
   git push origin main
   ```

2. **Render.com:**
   - Conecta tu repo de GitHub
   - Auto-detecta `render.yaml`
   - Deploy automático! ✅

3. **Acceso:**
   ```
   Dashboard: https://cryptonita-dashboard.onrender.com
   API: https://cryptonita-api.onrender.com/api/docs
   ```

---

## 🎯 Opción 2: Setup Local para Desarrollo

### 1. Instalar Dependencias

```bash
cd frontend
npm install
```

### 2. Variables de Entorno

Crea `frontend/.env`:

```env
VITE_API_URL=http://localhost:8000/api
VITE_WS_URL=ws://localhost:8000/api/ws
```

### 3. Ejecutar Dashboard

Terminal 1 - Backend:
```bash
cd /ruta/cryptonita-production
python -m uvicorn src.api.main:app --reload --port 8000
```

Terminal 2 - Frontend:
```bash
cd frontend
npm run dev
```

Abre: `http://localhost:3000`

---

## 📱 Features del Dashboard

### 🎮 Panel de Control
- Botón **START/STOP** bot
- Botón **RESTART** bot
- Modo Auto/Manual
- Estado en tiempo real (PID, CPU, RAM, Uptime)

### 📊 Vista Principal
- **Total P&L** en tiempo real
- **Posiciones activas** (entrada, actual, TP/SL, %gain)
- **Señales BUY recientes** (ticker, probabilidad)
- **Trades ejecutados** (historial completo)

### 📈 Gráficos
- Performance diaria (últimos 30 días)
- Win rate %
- Distribución de ganancias
- Señales por día

### ⚡ Actualizaciones en Tiempo Real
- WebSocket conectado
- Updates cada 5 segundos
- Notificaciones de trades
- Estado del bot live

---

## 🛠️ Script de Generación del Frontend

Ejecuta esto para generar TODOS los archivos del frontend:

```bash
cd /home/user/cryptonita-production
bash scripts/generate_frontend.sh
```

Este script creará:
- ✅ src/main.jsx
- ✅ src/App.jsx
- ✅ src/styles/index.css
- ✅ src/api/client.js
- ✅ src/components/Dashboard.jsx
- ✅ src/components/BotControls.jsx
- ✅ src/components/Positions.jsx
- ✅ src/components/Signals.jsx
- ✅ src/components/Trades.jsx
- ✅ src/components/Stats.jsx
- ✅ src/hooks/useWebSocket.js

---

## 🌐 URLs Finales (Post-Deploy)

**Producción en Render:**
```
Dashboard: https://cryptonita-dashboard.onrender.com
API Docs:  https://cryptonita-api.onrender.com/api/docs
WebSocket: wss://cryptonita-api.onrender.com/api/ws/dashboard
```

**Local (Desarrollo):**
```
Dashboard: http://localhost:3000
API:       http://localhost:8000/api
API Docs:  http://localhost:8000/api/docs
```

---

## 🔐 Configuración de Seguridad

1. **Genera token JWT:**
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Añade a `.env`:**
   ```env
   JWT_SECRET_KEY=<tu-token-generado>
   JWT_ALGORITHM=HS256
   JWT_EXPIRE_MINUTES=60
   ```

3. **Usuario por defecto:**
   ```
   Username: admin
   Password: cryptonita2025
   ```

   ⚠️ Cambia esto en producción!

---

## 📝 Próximos Pasos

1. [ ] Generar frontend completo
2. [ ] Probar localmente
3. [ ] Configurar PostgreSQL en Render
4. [ ] Deploy a Render
5. [ ] Configurar variables de entorno (API keys)
6. [ ] Activar bot en producción
7. [ ] Monitor desde dashboard! 🚀

---

**¿Quieres que genere todos los archivos del frontend ahora?**

Te daré código completo y funcional listo para deploy.
