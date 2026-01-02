#!/bin/bash

echo "🔄 Restarting Backend..."
echo ""

# Stop all backend services
echo "Stopping services..."
pkill -f "python core/main.py"
pkill -f "indiamart_categories_worker"
sleep 2

# Check prerequisites
echo "Checking prerequisites..."
redis-cli ping > /dev/null 2>&1 || { echo "❌ Redis not running!"; exit 1; }
mongosh --eval "db.adminCommand('ping')" > /dev/null 2>&1 || { echo "❌ MongoDB not running!"; exit 1; }
echo "✅ Prerequisites OK"
echo ""

# Start FastAPI
echo "Starting FastAPI server..."
if [ -d "venv" ]; then
    PYTHONPATH=$(pwd) nohup ./venv/bin/python core/main.py > logs/fastapi.log 2>&1 &
else
    PYTHONPATH=$(pwd) nohup python3 core/main.py > logs/fastapi.log 2>&1 &
fi
BACKEND_PID=$!
echo "✅ FastAPI started (PID: $BACKEND_PID)"
echo ""

# Wait and verify
sleep 3
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ Backend is ready!"
    echo ""
    echo "API: http://localhost:8000"
    echo "Logs: tail -f logs/fastapi.log"
    echo ""
    echo "Now click 'Start' on your homepage!"
else
    echo "❌ Backend failed to start. Check logs/fastapi.log"
    exit 1
fi
