#!/bin/bash
# Render Build Script
set -e

echo "🚀 Starting Render build process..."

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Build frontend
echo "🎨 Building frontend..."
cd frontend

# Install Node.js dependencies
npm install

# Build the frontend
npm run build

cd ..

echo "✅ Build completed successfully!"
