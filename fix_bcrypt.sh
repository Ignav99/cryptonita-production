#!/bin/bash
# Fix bcrypt compatibility issues

echo "🔧 Fixing bcrypt compatibility..."

# Activate virtual environment
source venv/bin/activate

# Upgrade bcrypt and passlib to compatible versions
pip install --upgrade bcrypt==4.1.2 passlib==1.7.4

echo "✅ bcrypt and passlib updated!"
echo ""
echo "Now you can start the API:"
echo "  uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload"
