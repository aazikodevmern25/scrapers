#!/bin/bash

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                                                                ║"
echo "║         🗑️  CLEAR CELERY TASK QUEUE                          ║"
echo "║                                                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

echo "⚠️  WARNING: This will delete ALL pending tasks in the queue!"
echo ""
read -p "Are you sure you want to clear the queue? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "❌ Cancelled"
    exit 1
fi

echo ""
echo "Stopping workers..."
pkill -9 -f "celery.*trademap"

echo "Clearing Redis queue..."
cd /home/aaziko/scrapers
python3 << 'EOF'
import redis
import os
from dotenv import load_dotenv

load_dotenv()

# Connect to Redis
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Clear the celery queue
keys_deleted = 0
for key in r.scan_iter("celery*"):
    r.delete(key)
    keys_deleted += 1

print(f"✅ Cleared {keys_deleted} keys from Redis")
EOF

echo ""
echo "Restarting workers..."
nohup celery -A celery_app.tasks worker --loglevel=info -Q trademap --concurrency=10 > logs/celery_trademap.log 2>&1 &

sleep 3

WORKERS=$(ps aux | grep "celery.*trademap" | grep -v grep | wc -l)
echo "✅ Workers restarted: $WORKERS active"

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "✅ Queue cleared! You can now submit NEW tasks."
echo "═══════════════════════════════════════════════════════════════"
