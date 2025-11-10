# 🚀 Guía de Deployment Completo - Cryptonita Trading Bot

## 🎉 Sistema Completado

✅ Bot de trading con ML (XGBoost V3, 48 features)
✅ Sistema dinámico de TP/SL inteligente
✅ API FastAPI completa con control del bot
✅ Bot Manager para start/stop desde web
✅ WebSocket para actualizaciones en tiempo real
✅ Frontend React preparado
✅ Listo para deploy en Render.com

---

## 📦 Lo que tienes ahora

### Backend Completado:
- ✅ Bot de trading automático
- ✅ Predicción con XGBoost (42 features + OHLCV + ema_200)
- ✅ TP/SL dinámico (3 niveles, trailing stop, salidas inteligentes)
- ✅ API REST completa (auth, dashboard, controls)
- ✅ WebSocket para real-time
- ✅ PostgreSQL para datos
- ✅ Binance integration (testnet + production data)

### Frontend Preparado:
- ✅ Estructura React + Vite + TailwindCSS
- ✅ Configuración lista
- ⏳ Componentes pendientes de generar

---

## 🎯 Opciones de Deployment

### Opción A: Deploy a Render.com (⭐ RECOMENDADO)

**Lo más rápido y profesional. Todo en la nube, accesible desde cualquier lugar.**

#### Paso 1: Preparar Repositorio
```bash
# Ya está hecho! Solo push a GitHub
git push origin main
```

#### Paso 2: Configurar Render
1. Ve a https://render.com
2. Conecta tu GitHub
3. Crea nuevo "Web Service":
   - **Name:** cryptonita-api
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn src.api.main:app --host 0.0.0.0 --port $PORT`

4. Añade Base de Datos PostgreSQL:
   - Render te la da gratis
   - Auto-conecta con env var `DATABASE_URL`

5. Configura Variables de Entorno:
   ```
   BINANCE_API_KEY=tu_api_key
   BINANCE_API_SECRET=tu_api_secret
   JWT_SECRET_KEY=<genera con: python -c "import secrets; print(secrets.token_urlsafe(32))">
   ```

6. Deploy Frontend estático:
   - **Name:** cryptonita-dashboard
   - **Build Command:** `cd frontend && npm install && npm run build`
   - **Publish Directory:** `frontend/dist`

#### Resultado:
```
🌐 Dashboard: https://cryptonita-dashboard.onrender.com
📡 API: https://cryptonita-api.onrender.com
📚 Docs: https://cryptonita-api.onrender.com/api/docs
```

**Tiempo estimado: 15 minutos**

---

### Opción B: Local + ngrok (Para testing rápido)

**Útil para probar antes de deploy.**

#### Paso 1: Ejecutar Local
```bash
# Terminal 1 - PostgreSQL
sudo systemctl start postgresql

# Terminal 2 - API
cd /home/user/cryptonita-production
python -m uvicorn src.api.main:app --reload --port 8000

# Terminal 3 - Frontend (después de generar componentes)
cd frontend
npm install
npm run dev
```

#### Paso 2: Exponer con ngrok
```bash
# Terminal 4
ngrok http 8000  # Para API
ngrok http 3000  # Para Dashboard
```

#### Resultado:
```
🏠 Local Dashboard: http://localhost:3000
🏠 Local API: http://localhost:8000
🌐 Public Dashboard: https://xxx.ngrok.io
🌐 Public API: https://yyy.ngrok.io
```

**Tiempo estimado: 5 minutos**

---

### Opción C: VPS Propio (DigitalOcean, AWS, etc)

**Control total, más complejo.**

#### Requisitos:
- Ubuntu 22.04+
- Python 3.11+
- PostgreSQL 14+
- Node.js 18+
- Nginx

#### Deploy:
```bash
# 1. Clonar repo en VPS
git clone https://github.com/tuusuario/cryptonita-production
cd cryptonita-production

# 2. Setup Python
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Setup PostgreSQL
sudo -u postgres psql
CREATE DATABASE cryptonita;
CREATE USER cryptonita_user WITH PASSWORD 'password';
GRANT ALL PRIVILEGES ON DATABASE cryptonita TO cryptonita_user;

# 4. Run migrations
python scripts/init_db.py

# 5. Setup systemd service (ver abajo)

# 6. Build frontend
cd frontend
npm install
npm run build

# 7. Configure Nginx (ver abajo)
```

#### systemd service (`/etc/systemd/system/cryptonita-api.service`):
```ini
[Unit]
Description=Cryptonita Trading Bot API
After=network.target postgresql.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/cryptonita-production
Environment="PATH=/home/ubuntu/cryptonita-production/venv/bin"
ExecStart=/home/ubuntu/cryptonita-production/venv/bin/uvicorn src.api.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable cryptonita-api
sudo systemctl start cryptonita-api
```

#### Nginx config (`/etc/nginx/sites-available/cryptonita`):
```nginx
server {
    listen 80;
    server_name tudominio.com;

    # Frontend
    location / {
        root /home/ubuntu/cryptonita-production/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # API
    location /api {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # WebSocket
    location /api/ws {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
    }
}
```

**Tiempo estimado: 1-2 horas**

---

## 📝 Siguiente Paso: Generar Frontend

El frontend está configurado pero faltan los componentes React. Tengo 2 opciones:

### Opción 1: Script Automático
```bash
cd /home/user/cryptonita-production
./scripts/generate_frontend.sh
```

Esto creará automáticamente:
- `src/main.jsx` - Entry point
- `src/App.jsx` - App principal
- `src/styles/index.css` - Styles
- `src/api/client.js` - API client
- `src/components/*` - Todos los componentes
- `src/hooks/*` - WebSocket hook

### Opción 2: Manual (te doy el código)
Te proporciono cada archivo uno por uno para que los revises.

---

## 🎮 Cómo Usar el Dashboard (Post-Deploy)

1. **Accede al dashboard:**
   ```
   https://cryptonita-dashboard.onrender.com
   ```

2. **Login:**
   ```
   Username: admin
   Password: cryptonita2025
   ```
   ⚠️ Cámbialo en producción!

3. **Panel de Control:**
   - Click **START** → Inicia el bot
   - Click **STOP** → Para el bot
   - Click **RESTART** → Reinicia el bot

4. **Monitorea en tiempo real:**
   - Posiciones activas
   - P&L actual
   - Señales BUY recientes
   - Histórico de trades
   - Estado del proceso (PID, CPU, RAM)

---

## ⚙️ Configuración de Producción

### Variables de Entorno Importantes:

```env
# Trading
TRADING_MODE=testnet          # testnet o production
BINANCE_API_KEY=xxx
BINANCE_API_SECRET=xxx

# Database
DATABASE_URL=postgresql://user:pass@host:5432/cryptonita

# Security
JWT_SECRET_KEY=xxx            # Genera uno nuevo!
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440       # 24 horas

# Bot
MAX_POSITIONS=10
PREDICTION_THRESHOLD=0.60
POSITION_SIZE_PCT=0.10        # 10% por trade
TAKE_PROFIT_PCT=0.15          # Base TP (será ajustado dinámicamente)
STOP_LOSS_PCT=0.05            # Base SL (será ajustado dinámicamente)
MAX_DAILY_LOSS_USD=200
```

---

## 🔒 Seguridad

### 1. Cambia las credenciales por defecto

En `src/api/auth.py`, línea 15:
```python
USERS_DB = {
    "admin": {
        "username": "admin",
        "hashed_password": bcrypt_context.hash("TU_PASSWORD_AQUI"),  # CAMBIAR!
        "email": "admin@cryptonita.com"
    }
}
```

### 2. Genera JWT Secret nuevo
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 3. Activa HTTPS en producción

Render lo da automáticamente. Si usas VPS, usa Let's Encrypt:
```bash
sudo certbot --nginx -d tudominio.com
```

---

## 📊 Monitoreo y Logs

### Ver logs del bot (Render):
```
Dashboard → Services → cryptonita-api → Logs
```

### Ver logs local:
```bash
tail -f logs/bot.log
```

### Métricas en dashboard:
- Total P&L
- Win rate %
- Trades ejecutados
- Posiciones activas
- Señales generadas
- Estado del proceso

---

## 🐛 Troubleshooting

### Bot no inicia:
```bash
# Verifica que PostgreSQL esté corriendo
sudo systemctl status postgresql

# Verifica credenciales de Binance
python -c "from binance.client import Client; c = Client('KEY', 'SECRET'); print(c.ping())"

# Verifica permisos
chmod +x run_bot.py
```

### Error de features:
```bash
# El modelo necesita exactamente 48 features
# Verifica que esté usando la versión correcta
python -c "from src.data.features import FeatureEngineer; fe = FeatureEngineer(); print(len(fe.required_features))"
# Debe mostrar: 48
```

### WebSocket no conecta:
```bash
# Verifica que la API esté corriendo
curl http://localhost:8000/health

# Test WebSocket
wscat -c ws://localhost:8000/api/ws/dashboard
```

---

## 🎯 Próximos Pasos

- [ ] Decidir método de deploy (Render recomendado)
- [ ] Generar componentes del frontend
- [ ] Configurar PostgreSQL
- [ ] Configurar variables de entorno
- [ ] Deploy backend
- [ ] Deploy frontend
- [ ] Cambiar credenciales por defecto
- [ ] Probar start/stop desde dashboard
- [ ] Activar trading automático
- [ ] ¡Monitor y profit! 🚀

---

**¿Qué prefieres hacer ahora?**

A) Deploy a Render (más rápido, recomendado)
B) Generar frontend completo primero
C) Probar localmente antes de deploy
D) Configurar VPS propio

¡Dime y continuamos! 🚀
