#!/bin/bash

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Quick Restart: FastAPI + ngrok"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd /home/aaziko/scrapers

# Kill existing processes
echo "1. Stopping existing FastAPI and ngrok..."
pkill -f "uvicorn.*8888" 2>/dev/null
pkill -f "ngrok" 2>/dev/null
sleep 2

# Start FastAPI
echo "2. Starting FastAPI server on port 8888..."
nohup python3 -m uvicorn core.main:app --host 0.0.0.0 --port 8888 > logs/fastapi.log 2>&1 &
FASTAPI_PID=$!
sleep 3

# Check FastAPI
if ps -p $FASTAPI_PID > /dev/null; then
    echo "   ✅ FastAPI started (PID: $FASTAPI_PID)"
else
    echo "   ❌ FastAPI failed to start"
    exit 1
fi

# Start ngrok
echo "3. Starting ngrok tunnel..."
nohup ngrok http 8888 > logs/ngrok.log 2>&1 &
NGROK_PID=$!
echo "   Waiting for ngrok to initialize..."
sleep 5

# Get ngrok URL
NGROK_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | grep -o '"public_url":"https://[^"]*"' | grep -o 'https://[^"]*' | head -1)

if [ -n "$NGROK_URL" ]; then
    echo "   ✅ ngrok started (PID: $NGROK_PID)"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  ✅ Services Running!"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "🌐 Full Tariff Form:"
    echo "   $NGROK_URL/static/macmap_full_tariff_form.html"
    echo ""
    echo "📋 Regular Tariff Form:"
    echo "   $NGROK_URL/static/macmap_tariff_form.html"
    echo ""
    echo "📊 API Docs:"
    echo "   $NGROK_URL/docs"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Save URL to file
    echo "$NGROK_URL" > current_ngrok_url.txt
else
    echo "   ❌ ngrok failed to start"
    exit 1
fi
