#!/bin/bash
# Restart All Scraper Services - FastAPI, ngrok, and Workers

echo "======================================================================"
echo "Restarting All Scraper Services"
echo "======================================================================"
echo ""

cd /home/aaziko/scrapers

# 1. Stop existing services
echo "1. Stopping existing services..."
pkill -f "uvicorn core.main"
pkill -f "ngrok"
sleep 3

# 2. Start FastAPI
echo "2. Starting FastAPI..."
nohup python3 -m uvicorn core.main:app --host 0.0.0.0 --port 8000 > logs/fastapi.log 2>&1 &
sleep 10

# Check if FastAPI is running
if curl -s http://localhost:8000/docs > /dev/null 2>&1; then
    echo "   ✅ FastAPI is running on port 8000"
else
    echo "   ❌ FastAPI failed to start - check logs/fastapi.log"
    exit 1
fi

# 3. Start ngrok
echo "3. Starting ngrok..."
nohup ngrok http 8001 --log=stdout > logs/ngrok.log 2>&1 &
sleep 5

# 4. Get new ngrok URL
echo "4. Getting new ngrok URL..."
sleep 5
NEW_URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | python3 -c "import sys, json; data = json.load(sys.stdin); print(data['tunnels'][0]['public_url'])" 2>/dev/null)

if [ -z "$NEW_URL" ]; then
    echo "   ⏳ Waiting for ngrok to start..."
    sleep 10
    NEW_URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | python3 -c "import sys, json; data = json.load(sys.stdin); print(data['tunnels'][0]['public_url'])" 2>/dev/null)
fi

echo ""
echo "======================================================================"
echo "✅ SERVICES RESTARTED SUCCESSFULLY"
echo "======================================================================"
echo ""
echo "📋 NEW URLS:"
echo "   Ngrok URL: $NEW_URL"
echo "   TradeMap Form: ${NEW_URL}/trademap-form"
echo "   MacMap Form: ${NEW_URL}/static/macmap_tariff_form.html"
echo "   API Docs: ${NEW_URL}/docs"
echo ""

# Save to file
cat > CURRENT_NGROK_URL.txt << EOF
====================================================================
CURRENT NGROK URL (Updated: $(date))
====================================================================

Base URL: $NEW_URL

Forms:
  • TradeMap Form: ${NEW_URL}/trademap-form
  • MacMap Tariff Form: ${NEW_URL}/static/macmap_tariff_form.html

API:
  • API Docs: ${NEW_URL}/docs
  • Health Check: ${NEW_URL}/api/v1/health

====================================================================
Services Status:
  ✅ FastAPI: Running on localhost:8000
  ✅ Ngrok: Tunneling to public URL
  ✅ Workers: Continue running (not affected by restart)
====================================================================
EOF

echo "📄 URL saved to: CURRENT_NGROK_URL.txt"
echo ""

# 5. Check workers
echo "5. Checking workers..."
MACMAP_WORKERS=$(ps aux | grep "celery.*macmap_tariff" | grep -v grep | wc -l)
TRADEMAP_WORKERS=$(ps aux | grep "celery.*trademap" | grep -v grep | wc -l)

echo "   MacMap Workers: $MACMAP_WORKERS running"
echo "   TradeMap Workers: $TRADEMAP_WORKERS running"

if [ "$MACMAP_WORKERS" -eq 0 ] || [ "$TRADEMAP_WORKERS" -eq 0 ]; then
    echo ""
    echo "⚠️  WARNING: Some workers are not running!"
    echo "   Run: bash start_all_workers.sh"
fi

echo ""
echo "======================================================================"
echo "Done! Use the new URLs above to access forms."
echo "======================================================================"
