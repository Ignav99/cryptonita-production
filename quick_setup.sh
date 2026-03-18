#!/bin/bash
# Cryptonita Production - Quick Setup Script
# This script will verify and setup everything needed for local testing

echo "=============================================="
echo "🚀 CRYPTONITA PRODUCTION - QUICK SETUP"
echo "=============================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check PostgreSQL
echo "1. Checking PostgreSQL..."
if command -v psql &> /dev/null; then
    echo -e "${GREEN}✅ PostgreSQL client installed${NC}"

    # Try to connect
    PGPASSWORD=TIZavoltio999 psql -h localhost -U cryptonita_admin -d cryptonita_mvp -c "SELECT 1;" &> /dev/null
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Database connection successful${NC}"

        # Check tables
        TABLES=$(PGPASSWORD=TIZavoltio999 psql -h localhost -U cryptonita_admin -d cryptonita_mvp -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")
        echo -e "${GREEN}✅ Database has $TABLES tables${NC}"
    else
        echo -e "${RED}❌ Cannot connect to database${NC}"
        echo -e "${YELLOW}   PostgreSQL might not be running${NC}"
        echo -e "${YELLOW}   Start it with: sudo systemctl start postgresql${NC}"
    fi
else
    echo -e "${RED}❌ PostgreSQL not found${NC}"
fi

echo ""

# Check Python
echo "2. Checking Python environment..."
if [ -d "venv" ]; then
    echo -e "${GREEN}✅ Virtual environment exists${NC}"
else
    echo -e "${YELLOW}⚠️  No virtual environment found${NC}"
    echo -e "${YELLOW}   Create it with: python3 -m venv venv${NC}"
fi

echo ""

# Check .env
echo "3. Checking configuration..."
if [ -f ".env" ]; then
    echo -e "${GREEN}✅ .env file exists${NC}"

    # Check important variables
    if grep -q "JWT_SECRET_KEY" .env; then
        echo -e "${GREEN}✅ JWT secret configured${NC}"
    else
        echo -e "${YELLOW}⚠️  JWT secret missing (just added it)${NC}"
    fi

    if grep -q "BINANCE_TESTNET_API_KEY" .env; then
        echo -e "${GREEN}✅ Binance Testnet keys configured${NC}"
    fi
else
    echo -e "${RED}❌ .env file not found${NC}"
fi

echo ""

# Check Node.js (for frontend)
echo "4. Checking Node.js (for dashboard)..."
if command -v node &> /dev/null; then
    NODE_VERSION=$(node -v)
    echo -e "${GREEN}✅ Node.js installed: $NODE_VERSION${NC}"

    if [ -d "frontend/node_modules" ]; then
        echo -e "${GREEN}✅ Frontend dependencies installed${NC}"
    else
        echo -e "${YELLOW}⚠️  Frontend dependencies not installed${NC}"
        echo -e "${YELLOW}   Install with: cd frontend && npm install${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Node.js not found (needed for dashboard)${NC}"
fi

echo ""
echo "=============================================="
echo "📋 NEXT STEPS:"
echo "=============================================="
echo ""

# Determine what needs to be done
NEEDS_VENV=false
NEEDS_DEPS=false
NEEDS_FRONTEND=false
NEEDS_DB=false

if [ ! -d "venv" ]; then
    NEEDS_VENV=true
fi

if [ -d "venv" ] && [ ! -f "venv/bin/uvicorn" ]; then
    NEEDS_DEPS=true
fi

if command -v node &> /dev/null && [ ! -d "frontend/node_modules" ]; then
    NEEDS_FRONTEND=true
fi

PGPASSWORD=TIZavoltio999 psql -h localhost -U cryptonita_admin -d cryptonita_mvp -c "SELECT 1;" &> /dev/null
if [ $? -ne 0 ]; then
    NEEDS_DB=true
fi

# Show instructions
STEP=1

if [ "$NEEDS_DB" = true ]; then
    echo "${STEP}. Start PostgreSQL:"
    echo "   sudo systemctl start postgresql"
    echo ""
    STEP=$((STEP+1))
fi

if [ "$NEEDS_VENV" = true ]; then
    echo "${STEP}. Create virtual environment:"
    echo "   python3 -m venv venv"
    echo ""
    STEP=$((STEP+1))
fi

if [ "$NEEDS_DEPS" = true ] || [ "$NEEDS_VENV" = true ]; then
    echo "${STEP}. Install Python dependencies:"
    echo "   source venv/bin/activate"
    echo "   pip install -r requirements.txt"
    echo ""
    STEP=$((STEP+1))
fi

if [ "$NEEDS_FRONTEND" = true ]; then
    echo "${STEP}. Install frontend dependencies:"
    echo "   cd frontend"
    echo "   npm install"
    echo "   cd .."
    echo ""
    STEP=$((STEP+1))
fi

echo "${STEP}. Run the system:"
echo "   # Terminal 1 - API"
echo "   source venv/bin/activate"
echo "   python -m uvicorn src.api.main:app --reload --port 8000"
echo ""
echo "   # Terminal 2 - Dashboard"
echo "   cd frontend && npm run dev"
echo ""
echo "   # Terminal 3 - Bot (optional)"
echo "   source venv/bin/activate"
echo "   python run_bot.py"
echo ""

echo "=============================================="
echo "📚 DOCUMENTATION:"
echo "=============================================="
echo "- LOCAL_TESTING.md    - Complete testing guide"
echo "- PROJECT_SUMMARY.md  - Full system overview"
echo "- DEPLOYMENT_GUIDE.md - Deploy to production"
echo ""

echo "=============================================="
echo "🌐 ACCESS URLS (after running):"
echo "=============================================="
echo "- Dashboard:  http://localhost:3000"
echo "- API:        http://localhost:8000"
echo "- API Docs:   http://localhost:8000/api/docs"
echo ""
echo "Login: admin / cryptonita2025"
echo ""

echo "✨ Setup check complete!"
