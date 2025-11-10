# Cryptonita Trading Bot - Dashboard Frontend

Dashboard web profesional para controlar y monitorear el bot de trading desde cualquier lugar.

## 🚀 Quick Start

### 1. Instalar Dependencias

```bash
cd frontend
npm install
```

### 2. Configurar Variables de Entorno

Copia `.env.example` a `.env`:

```bash
cp .env.example .env
```

Edita `.env` si es necesario (por defecto apunta a `localhost:8000`).

### 3. Ejecutar en Desarrollo

```bash
npm run dev
```

Abre: `http://localhost:3000`

### 4. Build para Producción

```bash
npm run build
```

Los archivos se generan en `dist/`.

---

## 📦 Características

### ✅ Control del Bot
- **START** - Inicia el bot automático
- **STOP** - Para el bot
- **RESTART** - Reinicia el bot
- **PAUSE** - Pausa el bot

### 📊 Métricas en Tiempo Real
- Total P&L
- Win Rate
- Posiciones Abiertas
- P&L del día

### 💼 Gestión de Posiciones
- Ver todas las posiciones activas
- Entry price, current price, P&L
- Take Profit y Stop Loss levels
- Duración de la posición

### 📡 Señales en Vivo
- Señales BUY recientes
- Probabilidad del modelo
- Features principales

### 📜 Histórico de Trades
- Todos los trades ejecutados
- BUY y SELL
- Precios y cantidades
- Estado (executed, pending, failed)

### ⚡ Actualizaciones en Tiempo Real
- WebSocket conectado
- Updates automáticos cada 5 segundos
- Notificaciones de nuevas señales/trades

---

## 🎨 Stack Tecnológico

- **React 18** - UI Framework
- **Vite** - Build tool
- **TailwindCSS** - Styling
- **Axios** - HTTP client
- **Lucide Icons** - Iconos
- **date-fns** - Date formatting
- **WebSocket** - Real-time updates

---

## 📁 Estructura de Archivos

```
frontend/
├── src/
│   ├── main.jsx              # Entry point
│   ├── App.jsx               # App principal con auth
│   ├── styles/
│   │   └── index.css         # Tailwind CSS
│   ├── api/
│   │   └── client.js         # API client
│   ├── hooks/
│   │   └── useWebSocket.js   # WebSocket hook
│   └── components/
│       ├── Dashboard.jsx     # Panel principal
│       ├── BotControls.jsx   # Controles ON/OFF
│       ├── Stats.jsx         # Métricas
│       ├── Positions.jsx     # Posiciones activas
│       ├── Signals.jsx       # Señales recientes
│       └── Trades.jsx        # Histórico
├── index.html
├── vite.config.js
├── tailwind.config.js
├── postcss.config.js
├── package.json
└── .env.example
```

---

## 🔐 Autenticación

### Credenciales por Defecto

```
Username: admin
Password: cryptonita2025
```

⚠️ **IMPORTANTE:** Cambia estas credenciales en producción editando `src/api/routes/auth.py`.

### Generar Nueva Contraseña

```python
from passlib.context import CryptContext

bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
hashed = bcrypt_context.hash("TU_NUEVA_PASSWORD")
print(hashed)
```

---

## 🌐 Deploy

### Opción 1: Render.com (Recomendado)

1. **Push a GitHub**
2. **Render.com** → New Static Site
3. **Build Command:** `npm install && npm run build`
4. **Publish Directory:** `dist`
5. **Environment Variables:**
   - `VITE_API_URL=https://cryptonita-api.onrender.com/api`
   - `VITE_WS_URL=wss://cryptonita-api.onrender.com/api/ws`

### Opción 2: Vercel

```bash
npm install -g vercel
vercel --prod
```

### Opción 3: Netlify

```bash
npm install -g netlify-cli
netlify deploy --prod --dir=dist
```

---

## 🔧 Configuración Avanzada

### Proxy API en Desarrollo

`vite.config.js` ya incluye proxy automático:

```javascript
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
    },
  },
}
```

### WebSocket Auto-Reconnect

El hook `useWebSocket` incluye:
- Reconexión automática (max 5 intentos)
- Intervalo de 3 segundos
- Manejo de errores

---

## 🐛 Troubleshooting

### Error: "Failed to fetch"

- Verifica que la API esté corriendo: `http://localhost:8000/health`
- Revisa las variables de entorno en `.env`

### WebSocket no conecta

- Asegúrate de que la API soporte WebSocket
- Verifica la URL en `.env` (usa `ws://` para local, `wss://` para producción)

### Build falla

```bash
# Limpia node_modules y reinstala
rm -rf node_modules package-lock.json
npm install
```

---

## 📱 Screenshots

### Dashboard Principal
- Métricas en cards
- Control del bot
- Posiciones activas
- Señales y trades

### Login
- Autenticación JWT
- Formulario responsive
- Credenciales por defecto visibles

---

## 🚀 Scripts Disponibles

```bash
npm run dev      # Desarrollo en http://localhost:3000
npm run build    # Build para producción
npm run preview  # Preview del build
```

---

## 📞 Soporte

Para ayuda con el dashboard o reportar bugs, consulta `DEPLOYMENT_GUIDE.md` en la raíz del proyecto.

---

**Cryptonita Trading Bot V3** - Dashboard Frontend
