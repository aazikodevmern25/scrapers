#!/bin/bash

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║          TradeMap Scraper - Status Monitor                    ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check if services are running
echo "📊 SERVICE STATUS:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check FastAPI
if pgrep -f "uvicorn core.main:app" > /dev/null; then
    FASTAPI_PID=$(pgrep -f "uvicorn core.main:app" | head -1)
    echo "✅ FastAPI Server:    RUNNING (PID: $FASTAPI_PID)"
else
    echo "❌ FastAPI Server:    NOT RUNNING"
fi

# Check Celery
CELERY_COUNT=$(pgrep -f "celery.*trademap" | wc -l)
if [ $CELERY_COUNT -gt 0 ]; then
    echo "✅ Celery Workers:    $CELERY_COUNT processes active"
else
    echo "❌ Celery Workers:    NOT RUNNING"
fi

# Check ngrok
if pgrep ngrok > /dev/null; then
    NGROK_URL=$(grep -o 'url=https://[^[:space:]]*' logs/ngrok.log 2>/dev/null | tail -1 | cut -d= -f2)
    echo "✅ ngrok Tunnel:      ACTIVE"
    if [ ! -z "$NGROK_URL" ]; then
        echo "   URL: $NGROK_URL"
    fi
else
    echo "❌ ngrok Tunnel:      NOT RUNNING"
fi

echo ""
echo "📋 RECENT SCRAPING ACTIVITY:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check logs for recent tasks
if [ -f "logs/celery_trademap.log" ]; then
    RECENT_TASKS=$(grep -E "Task.*trademap_scraper_task|received|succeeded|failed" logs/celery_trademap.log | tail -10)
    if [ ! -z "$RECENT_TASKS" ]; then
        echo "$RECENT_TASKS"
    else
        echo "No recent tasks found"
    fi
fi

echo ""
echo "💾 MONGODB DATA:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check MongoDB for scraped data count
python3 << 'PYEOF'
try:
    from pymongo import MongoClient
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    mongo_uri = os.getenv('MONGO_URI')
    mongo_db = os.getenv('MONGO_DB', 'Dhruval')
    
    client = MongoClient(mongo_uri)
    db = client[mongo_db]
    
    # Check trademap collection
    if 'trademap' in db.list_collection_names():
        count = db.trademap.count_documents({})
        print(f"✅ TradeMap Collection: {count} records")
        
        # Get latest entry
        latest = db.trademap.find_one(sort=[('_id', -1)])
        if latest:
            print(f"   Latest entry: {latest.get('reporter', 'N/A')} → {latest.get('partner', 'N/A')}")
    else:
        print("⚠️  TradeMap collection doesn't exist yet")
    
    client.close()
except Exception as e:
    print(f"❌ Error checking MongoDB: {str(e)}")
PYEOF

echo ""
echo "🔍 LIVE LOG TAIL (Last 15 lines):"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -f "logs/celery_trademap.log" ]; then
    tail -15 logs/celery_trademap.log
else
    echo "No log file found"
fi

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  To watch live: tail -f logs/celery_trademap.log              ║"
echo "╚════════════════════════════════════════════════════════════════╝"
