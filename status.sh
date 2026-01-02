#!/bin/bash

# Quick Status Check

echo "=========================================="
echo "  TradeMap Scraper - Status"
echo "=========================================="
echo ""

# Workers
WORKERS=$(pgrep -af celery | wc -l)
if [ $WORKERS -gt 0 ]; then
    echo "✅ Celery Workers: $WORKERS running (12 parallel workers)"
else
    echo "❌ Celery Workers: NOT RUNNING"
fi

# FastAPI
if curl -s http://localhost:1080 > /dev/null 2>&1; then
    echo "✅ FastAPI Server: Running on port 1080"
else
    echo "❌ FastAPI Server: NOT RUNNING"
fi

# Chrome
CHROME=$(pgrep chrome | wc -l)
echo "✅ Chrome Browsers: $CHROME (hidden/headless)"

# Queue
QUEUE=$(redis-cli llen trademap 2>/dev/null)
echo "✅ Tasks in Queue: $QUEUE remaining"

# MongoDB
DOCS=$(mongosh "mongodb://admin:Aaziko%21%40%23123@202.47.115.6:27017/Dhruval?authSource=admin" --quiet --eval "db.trademap.countDocuments()" 2>/dev/null)
echo "✅ Documents Saved: $DOCS"

# Progress
if [ ! -z "$DOCS" ]; then
    PROGRESS=$(echo "scale=2; ($DOCS / 8904) * 100" | bc)
    echo "✅ Progress: ${PROGRESS}%"
fi

echo ""
echo "=========================================="
echo "  Form URL: http://localhost:1080"
echo "  Monitor: ./watch_progress.sh"
echo "=========================================="
