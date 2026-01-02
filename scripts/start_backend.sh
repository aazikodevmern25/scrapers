#!/bin/bash

# Start Backend Server Script
# Starts the FastAPI backend with proper configuration

echo "🚀 Starting Backend Server..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "Please create it first: python3 -m venv venv"
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Check if Redis is running
if ! redis-cli ping > /dev/null 2>&1; then
    echo "⚠️  Warning: Redis is not running!"
    echo "Start Redis first: redis-server"
    exit 1
fi

# Kill any existing backend processes
echo "🧹 Cleaning up old processes..."
pkill -9 -f "gunicorn.*main:app" 2>/dev/null
pkill -9 -f "uvicorn.*main:app" 2>/dev/null
sleep 1

# Start the backend
echo "✨ Starting backend on port 1080..."
echo ""

# Use gunicorn with uvicorn workers (production-like)
gunicorn -w 2 \
  -k uvicorn.workers.UvicornWorker \
  --max-requests 1000 \
  --max-requests-jitter 50 \
  --timeout 120 \
  main:app \
  --bind 0.0.0.0:1080 \
  --access-logfile - \
  --error-logfile -

# Alternative: Use uvicorn directly (simpler, for development)
# uvicorn main:app --host 0.0.0.0 --port 1080 --reload
