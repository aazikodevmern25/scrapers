#!/bin/bash

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     Starting TradeMap Scraper - All Services                  ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

cd /home/aaziko/scrapers

# Kill existing services
echo "🔄 Stopping old services..."
pkill -f "uvicorn core.main:app"
pkill -f "celery.*trademap"
pkill ngrok
sleep 2

# Start FastAPI
echo "🚀 Starting FastAPI Server (Port 8888)..."
nohup uvicorn core.main:app --host 0.0.0.0 --port 8888 > logs/fastapi.log 2>&1 &
FASTAPI_PID=$!
echo "   ✅ FastAPI PID: $FASTAPI_PID"
sleep 3

# Start Celery with 20 workers
echo "🚀 Starting Celery Workers (20 workers)..."
nohup celery -A celery_app.tasks worker --loglevel=info -Q trademap --concurrency=20 > logs/celery_trademap.log 2>&1 &
CELERY_PID=$!
echo "   ✅ Celery PID: $CELERY_PID"
sleep 3

# Start ngrok
echo "🌍 Starting ngrok tunnel..."
nohup /home/aaziko/ngrok http 8888 --log=stdout > logs/ngrok.log 2>&1 &
NGROK_PID=$!
echo "   ✅ ngrok PID: $NGROK_PID"
sleep 5

# Save PIDs
echo "CELERY_PID=$CELERY_PID" > .trademap_pids
echo "FASTAPI_PID=$FASTAPI_PID" >> .trademap_pids
echo "NGROK_PID=$NGROK_PID" >> .trademap_pids

# Get ngrok URL
echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                    🎉 ALL SERVICES STARTED!                   ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

NGROK_URL=$(grep -o 'url=https://[^[:space:]]*' logs/ngrok.log | tail -1 | cut -d= -f2)

if [ ! -z "$NGROK_URL" ]; then
    echo "🌍 PUBLIC ACCESS URL:"
    echo "   $NGROK_URL"
    echo ""
    echo "📋 DIRECT LINKS:"
    echo "   Dashboard:     $NGROK_URL/"
    echo "   TradeMap Form: $NGROK_URL/trademap-form"
    echo "   Health Check:  $NGROK_URL/api/v1/health"
else
    echo "⚠️  ngrok URL not ready yet. Check logs/ngrok.log in a few seconds."
fi

echo ""
echo "📊 STATUS:"
echo "   ✅ FastAPI:  Running on port 8888 (PID: $FASTAPI_PID)"
echo "   ✅ Celery:   20 workers active (PID: $CELERY_PID)"
echo "   ✅ ngrok:    Tunnel active (PID: $NGROK_PID)"
echo ""
echo "📁 LOGS:"
echo "   FastAPI: logs/fastapi.log"
echo "   Celery:  logs/celery_trademap.log"
echo "   ngrok:   logs/ngrok.log"
echo ""
echo "🛑 TO STOP ALL:"
echo "   kill $FASTAPI_PID $CELERY_PID $NGROK_PID"
echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║              Ready! Open the URL in your browser              ║"
echo "╚════════════════════════════════════════════════════════════════╝"
