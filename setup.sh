#!/bin/bash
# =================================================================
# CRYPTONITA PRODUCTION - SETUP SCRIPT
# =================================================================
# Este script configura todo el entorno automáticamente

set -e  # Exit on error

echo "========================================================================="
echo "🚀 CRYPTONITA PRODUCTION - SETUP"
echo "========================================================================="
echo ""

# 1. Verificar Python
echo "📋 Verificando Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 no encontrado. Instala Python 3.8+ primero."
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo "✅ $PYTHON_VERSION encontrado"
echo ""

# 2. Crear entorno virtual
echo "📦 Creando entorno virtual..."
if [ -d "venv" ]; then
    echo "⚠️  Entorno virtual ya existe. ¿Recrear? (y/N)"
    read -r response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo "🗑️  Eliminando entorno anterior..."
        rm -rf venv
        python3 -m venv venv
        echo "✅ Entorno virtual recreado"
    else
        echo "✅ Usando entorno existente"
    fi
else
    python3 -m venv venv
    echo "✅ Entorno virtual creado en ./venv"
fi
echo ""

# 3. Activar entorno virtual
echo "🔌 Activando entorno virtual..."
source venv/bin/activate
echo "✅ Entorno virtual activado"
echo ""

# 4. Actualizar pip
echo "⬆️  Actualizando pip..."
pip install --upgrade pip > /dev/null 2>&1
echo "✅ pip actualizado"
echo ""

# 5. Instalar dependencias
echo "📥 Instalando dependencias desde requirements.txt..."
echo "   (Esto puede tardar 2-3 minutos...)"
pip install -r requirements.txt
echo "✅ Dependencias instaladas"
echo ""

# 6. Crear directorio de logs
echo "📁 Creando directorios necesarios..."
mkdir -p logs
echo "✅ Directorio de logs creado"
echo ""

# 7. Verificar PostgreSQL
echo "🐘 Verificando PostgreSQL..."
if command -v psql &> /dev/null; then
    echo "✅ PostgreSQL encontrado"

    # Preguntar si crear base de datos
    echo ""
    echo "¿Crear base de datos 'cryptonita_mvp'? (y/N)"
    read -r response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo "📊 Creando base de datos..."
        createdb cryptonita_mvp 2>/dev/null || echo "⚠️  Base de datos ya existe"

        echo "📋 Creando tablas..."
        python scripts/setup_database.py
        echo "✅ Base de datos configurada"
    else
        echo "⏭️  Saltando creación de base de datos"
        echo "   Ejecuta manualmente: createdb cryptonita_mvp"
        echo "   Luego: python scripts/setup_database.py"
    fi
else
    echo "⚠️  PostgreSQL no encontrado"
    echo "   Instala PostgreSQL antes de continuar"
    echo "   macOS: brew install postgresql"
    echo "   Ubuntu: sudo apt-get install postgresql postgresql-contrib"
fi
echo ""

# 8. Verificar .env
echo "⚙️  Verificando archivo .env..."
if [ -f ".env" ]; then
    echo "✅ Archivo .env encontrado"
else
    echo "⚠️  Archivo .env NO encontrado"
    echo "   Asegúrate de tener configurado el archivo .env"
fi
echo ""

# 9. Resumen
echo "========================================================================="
echo "✅ SETUP COMPLETADO"
echo "========================================================================="
echo ""
echo "📋 PRÓXIMOS PASOS:"
echo ""
echo "1. Activar entorno virtual (si no está activado):"
echo "   source venv/bin/activate"
echo ""
echo "2. Verificar configuración:"
echo "   cat .env"
echo ""
echo "3. Ver lista de monedas:"
echo "   python scripts/show_tickers.py"
echo ""
echo "4. OPCIÓN A - Ejecutar API Dashboard:"
echo "   python run_api.py"
echo "   Luego visita: http://localhost:8000"
echo ""
echo "5. OPCIÓN B - Ejecutar Trading Bot:"
echo "   python run_bot.py"
echo ""
echo "6. OPCIÓN C - Ejecutar ambos (en terminales separadas):"
echo "   Terminal 1: python run_api.py"
echo "   Terminal 2: python run_bot.py"
echo ""
echo "========================================================================="
echo "🎯 CREDENCIALES DEL DASHBOARD:"
echo "   URL: http://localhost:8000"
echo "   Usuario: admin"
echo "   Contraseña: cryptonita2024"
echo "========================================================================="
echo ""
