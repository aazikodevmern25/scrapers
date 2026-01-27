#!/bin/bash
# Restart All Scraper Services - FastAPI, ngrok (generates new URL)
# Uses port 8001 (avoiding 8000 used by Cloudflare)
# For Eximpedia, TradeMap, and MacMap scrapers

echo "======================================================================"
echo "Restarting All Scraper Services (Port 8001)"
echo "Eximpedia | TradeMap | MacMap"
echo "======================================================================"
echo ""

cd /home/aaziko/scrapers

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# 1. Stop existing services
echo "1. Stopping existing services..."
pkill -9 -f "uvicorn.*main:app"
pkill -9 -f "ngrok"
sleep 3
echo "   ✅ Old services stopped"

# 2. Start FastAPI on port 8001
echo ""
echo "2. Starting FastAPI on port 8001..."
nohup python3 -m uvicorn core.main:app --host 0.0.0.0 --port 8001 > logs/fastapi.log 2>&1 &
sleep 10

# Check if FastAPI is running
if curl -s http://localhost:8001/api/v1/health > /dev/null 2>&1; then
    echo "   ✅ FastAPI is running on port 8001"
else
    echo "   ❌ FastAPI failed to start - check logs/fastapi.log"
    exit 1
fi

# 3. Start ngrok on port 8001
echo ""
echo "3. Starting ngrok tunnel..."
nohup ~/ngrok http 8001 --log=stdout > logs/ngrok.log 2>&1 &
sleep 8

# 4. Get new ngrok URL
echo ""
echo "4. Getting new ngrok URL..."
sleep 5
NEW_URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | python3 -c "import sys, json; data = json.load(sys.stdin); print(data['tunnels'][0]['public_url'])" 2>/dev/null)

if [ -z "$NEW_URL" ]; then
    echo "   ⏳ Waiting for ngrok to start..."
    sleep 10
    NEW_URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | python3 -c "import sys, json; data = json.load(sys.stdin); print(data['tunnels'][0]['public_url'])" 2>/dev/null)
fi

if [ -z "$NEW_URL" ]; then
    echo "   ❌ Failed to get ngrok URL - check logs/ngrok.log"
    exit 1
fi

echo "   ✅ New ngrok URL: $NEW_URL"

# 5. Check workers
echo ""
echo "5. Checking workers..."
EXIMPEDIA_WORKERS=$(ps aux | grep "celery.*eximpedia" | grep -v grep | wc -l)
TRADEMAP_WORKERS=$(ps aux | grep "celery.*trademap" | grep -v grep | wc -l)
MACMAP_WORKERS=$(ps aux | grep "celery.*macmap_tariff" | grep -v grep | wc -l)

echo "   Eximpedia Workers: $EXIMPEDIA_WORKERS running"
echo "   TradeMap Workers: $TRADEMAP_WORKERS running"
echo "   MacMap Workers: $MACMAP_WORKERS running"

if [ "$EXIMPEDIA_WORKERS" -eq 0 ] || [ "$TRADEMAP_WORKERS" -eq 0 ] || [ "$MACMAP_WORKERS" -eq 0 ]; then
    echo ""
    echo "   ⚠️  WARNING: Some workers are not running!"
    echo "   Run: bash start_all_scrapers.sh"
fi

echo ""
echo "======================================================================"
echo "✅ SERVICES RESTARTED SUCCESSFULLY"
echo "======================================================================"
echo ""
echo "📋 NEW URLS:"
echo ""
echo "EXIMPEDIA:"
echo "   • Form: ${NEW_URL}/eximpedia-form"
echo "   • Mirror Data: ${NEW_URL}/eximpedia-mirror-data-form"
echo ""
echo "TRADEMAP:"
echo "   • Form: ${NEW_URL}/trademap-form"
echo ""
echo "MACMAP:"
echo "   • Tariff Form: ${NEW_URL}/static/macmap_tariff_form.html"
echo "   • Trade Agreements: ${NEW_URL}/static/macmap_trade_agreements_form.html"
echo ""
echo "API:"
echo "   • Docs: ${NEW_URL}/docs"
echo "   • Health: ${NEW_URL}/api/v1/health"
echo ""

# Save to file
cat > CURRENT_NGROK_URL.txt << EOF
====================================================================
CURRENT NGROK URL (Updated: $(date))
====================================================================

Base URL: $NEW_URL
Port: 8001 (FastAPI)

EXIMPEDIA:
  • Form: ${NEW_URL}/eximpedia-form
  • Mirror Data: ${NEW_URL}/eximpedia-mirror-data-form

TRADEMAP:
  • Form: ${NEW_URL}/trademap-form

MACMAP:
  • Tariff Form: ${NEW_URL}/static/macmap_tariff_form.html
  • Trade Agreements: ${NEW_URL}/static/macmap_trade_agreements_form.html

API:
  • Docs: ${NEW_URL}/docs
  • Health Check: ${NEW_URL}/api/v1/health

====================================================================
Services Status:
  ✅ FastAPI: Running on localhost:8001
  ✅ Ngrok: Tunneling to public URL
  ✅ Eximpedia Workers: $EXIMPEDIA_WORKERS
  ✅ TradeMap Workers: $TRADEMAP_WORKERS
  ✅ MacMap Workers: $MACMAP_WORKERS
====================================================================
EOF

# Save individual URLs
echo "$NEW_URL" > EXIMPEDIA_NGROK_URL.txt
echo "$NEW_URL" > TRADEMAP_NGROK_URL.txt
echo "$NEW_URL" > MACMAP_NGROK_URL.txt

echo "📄 URLs saved to:"
echo "   • CURRENT_NGROK_URL.txt (all scrapers)"
echo "   • EXIMPEDIA_NGROK_URL.txt"
echo "   • TRADEMAP_NGROK_URL.txt"
echo "   • MACMAP_NGROK_URL.txt"
echo ""
echo "======================================================================"
echo "Done! Use the new URLs above to access forms."
echo "======================================================================"
echo ""
