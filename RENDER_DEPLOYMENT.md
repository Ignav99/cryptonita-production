# 🚀 Despliegue en Render - Guía Completa

Esta guía te llevará paso a paso para desplegar tu bot de trading en Render.

## 📋 Requisitos Previos

✅ Cuenta de GitHub con el repositorio `cryptonita-production`
✅ Cuenta en [Render.com](https://render.com) (gratis)
✅ API Keys de Binance Testnet (para pruebas seguras)

---

## 🎯 Paso 1: Preparar el Repositorio

### 1.1 Push de todos los cambios

```bash
# En tu Mac, asegúrate de que todo esté subido
git add .
git commit -m "feat: Production ready with Render configuration"
git push origin claude/proyecto-fase-d-011CUyziSCGSFJiiFCsLsnmf
```

### 1.2 Opcional: Crear rama main/master

Si quieres desplegar desde main en lugar de la rama actual:

```bash
git checkout -b main
git push origin main
```

---

## 🎯 Paso 2: Crear Cuenta en Render

1. Ve a https://render.com
2. Click en **"Get Started"**
3. Regístrate con tu cuenta de GitHub (recomendado)
4. Autoriza a Render para acceder a tus repositorios

---

## 🎯 Paso 3: Crear Base de Datos PostgreSQL

### 3.1 Crear el servicio de base de datos

1. En el dashboard de Render, click en **"New +"**
2. Selecciona **"PostgreSQL"**
3. Configura:
   - **Name**: `cryptonita-db`
   - **Database**: `cryptonita_production`
   - **User**: `cryptonita_admin`
   - **Region**: Oregon (o el más cercano)
   - **Plan**: Free (o Starter para mejor rendimiento)
4. Click en **"Create Database"**

### 3.2 Guardar credenciales

⚠️ **IMPORTANTE**: Guarda la **Internal Database URL** que aparece después de crear la DB.

Ejemplo:
```
postgresql://cryptonita_admin:xxxxx@dpg-xxxxx.oregon-postgres.render.com/cryptonita_production
```

---

## 🎯 Paso 4: Crear Web Service

### 4.1 Crear el servicio

1. Click en **"New +"** → **"Web Service"**
2. Conecta tu repositorio GitHub `cryptonita-production`
3. Selecciona la rama: `claude/proyecto-fase-d-011CUyziSCGSFJiiFCsLsnmf` (o `main`)

### 4.2 Configuración básica

- **Name**: `cryptonita-bot`
- **Region**: Oregon (mismo que la DB)
- **Branch**: `claude/proyecto-fase-d-011CUyziSCGSFJiiFCsLsnmf`
- **Runtime**: Python 3
- **Build Command**: `./scripts/render_build.sh`
- **Start Command**: `./scripts/render_start.sh`

### 4.3 Plan

- **Free**: El servicio se duerme después de 15 minutos de inactividad
- **Starter ($7/mes)**: ✅ **RECOMENDADO** - Corre 24/7 sin dormir

---

## 🎯 Paso 5: Configurar Variables de Entorno

En la sección **"Environment Variables"**, agrega:

### Variables OBLIGATORIAS:

```bash
# Binance Testnet (para pruebas)
BINANCE_TESTNET_API_KEY=tu_testnet_api_key
BINANCE_TESTNET_API_SECRET=tu_testnet_secret

# Database (copia del paso 3.2)
DATABASE_URL=postgresql://cryptonita_admin:xxxxx@dpg-xxxxx.oregon-postgres.render.com/cryptonita_production

# Trading Mode
TRADING_MODE=testnet

# JWT (Render puede auto-generar SECRET_KEY)
SECRET_KEY=<auto-generate o pon el de tu .env>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# System
ENVIRONMENT=production
LOG_LEVEL=INFO
API_HOST=0.0.0.0
API_PORT=8000
```

### Variables OPCIONALES (Trading Config):

```bash
INITIAL_CAPITAL=10000
MAX_POSITION_SIZE_USD=500
MAX_DAILY_LOSS_USD=200
MAX_TOTAL_RISK_PERCENT=2.0
REQUIRE_MANUAL_APPROVAL=false
```

### Para Trading REAL (solo cuando estés listo):

```bash
BINANCE_API_KEY=tu_production_api_key
BINANCE_API_SECRET=tu_production_secret
TRADING_MODE=production  # Cambiar de testnet a production
```

---

## 🎯 Paso 6: Desplegar

1. Después de configurar todo, click en **"Create Web Service"**
2. Render empezará a:
   - ✅ Clonar el repositorio
   - ✅ Ejecutar `render_build.sh` (instalar Python deps, construir frontend)
   - ✅ Ejecutar `render_start.sh` (setup DB, iniciar API)

3. **Espera 5-10 minutos** para el primer deploy

---

## 🎯 Paso 7: Verificar Despliegue

### 7.1 Ver logs

En el dashboard de Render, ve a **"Logs"** y verifica que veas:

```
✅ Positions table migration completed successfully!
🌐 Starting API server...
📍 API will be available at: https://cryptonita-bot.onrender.com
```

### 7.2 Acceder al dashboard

1. Abre: `https://cryptonita-bot.onrender.com`
2. Deberías ver el dashboard de Cryptonita
3. Login con:
   - Usuario: `admin`
   - Password: `cryptonita2024`

### 7.3 Health Check

Visita: `https://cryptonita-bot.onrender.com/health`

Deberías ver:
```json
{
  "status": "healthy",
  "version": "3.0",
  "environment": "production",
  "trading_mode": "testnet"
}
```

---

## 🎯 Paso 8: Controlar el Bot

### Desde el Dashboard Web:

1. Ve a `https://cryptonita-bot.onrender.com`
2. Haz login
3. Click en **"Start Bot"** para iniciar el trading
4. Click en **"Stop Bot"** para detenerlo
5. Monitorea:
   - Posiciones activas
   - Señales de trading
   - P&L total
   - Win rate

### El bot se quedará corriendo siempre si:

✅ Elegiste el plan **Starter** ($7/mes)
✅ El bot está iniciado desde el dashboard
✅ No hay errores críticos

---

## 🔧 Troubleshooting

### Problema: Build falla

**Solución**: Revisa los logs en Render. Común:
- Falta alguna variable de entorno
- Error en `render_build.sh` - verifica permisos

```bash
# Localmente, da permisos de ejecución:
chmod +x scripts/render_build.sh scripts/render_start.sh
git add scripts/*.sh
git commit -m "fix: Add execute permissions to render scripts"
git push
```

### Problema: Base de datos no conecta

**Solución**:
- Verifica que `DATABASE_URL` esté bien configurada
- Asegúrate de que la DB y el Web Service estén en la **misma región**

### Problema: Bot no inicia desde dashboard

**Solución**:
- Revisa logs del servicio en Render
- Verifica que las API keys de Binance Testnet sean correctas
- Prueba las keys en: https://testnet.binance.vision/

### Problema: El servicio se duerme

**Solución**:
- Esto es normal con el plan **Free**
- Upgrade a plan **Starter** ($7/mes) para que corra 24/7
- O usa un servicio de "ping" externo (ej: UptimeRobot) para mantenerlo despierto

---

## 📊 Monitoreo

### Logs en tiempo real:

```bash
# Desde Render dashboard → Logs
# O usando Render CLI:
render logs -f cryptonita-bot
```

### Métricas:

- Render dashboard muestra CPU, RAM, bandwidth
- Tu dashboard custom muestra P&L, trades, win rate

---

## 🔒 Seguridad

### Cambiar password del dashboard:

Edita `src/api/auth.py` línea 119:

```python
"hashed_password": get_password_hash("TU_NUEVO_PASSWORD"),
```

Luego:
```bash
git add src/api/auth.py
git commit -m "security: Update dashboard password"
git push
```

Render hará auto-deploy.

### Rotar API Keys:

1. En Render dashboard → Environment
2. Actualiza `BINANCE_TESTNET_API_KEY` y `SECRET`
3. Click "Save Changes"
4. Render reiniciará automáticamente

---

## 💰 Costos

| Servicio | Plan Free | Plan Starter |
|----------|-----------|--------------|
| PostgreSQL | ✅ 1GB storage | ✅ 10GB storage |
| Web Service | ⚠️ Se duerme tras 15min | ✅ Corre 24/7 |
| Costo | $0/mes | $7/mes |

**Recomendación**: Empieza con Free para probar, luego upgrade a Starter cuando estés listo para trading automático 24/7.

---

## 📝 Siguiente Pasos

✅ Prueba el bot en testnet durante 1-2 semanas
✅ Monitorea win rate, P&L, drawdown
✅ Ajusta parámetros en Environment Variables
✅ Cuando estés seguro, cambia a `TRADING_MODE=production`
✅ Usa cantidades pequeñas al principio

---

## 🆘 Soporte

- **Logs de Render**: Dashboard → Logs
- **Logs del bot**: Dashboard → Ver consola en `/api/docs`
- **Health status**: `https://cryptonita-bot.onrender.com/health`

---

¡Listo! Tu bot está en la nube y listo para operar 24/7 🚀
