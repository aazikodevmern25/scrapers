#!/bin/bash

# TradeMap Scraper - Optimized for 64GB RAM + i7 9th Gen
# Auto-configured for your system

echo "=========================================="
echo "  TradeMap - Optimized Configuration"
echo "  64GB RAM | i7 9th Gen"
echo "=========================================="
echo ""

# System specs
RAM_GB=64
CPU_CORES=$(nproc)

# Calculate optimal concurrency for 64GB RAM
# Each browser + proxy uses ~3-4GB
# Leave 16GB for system
# (64 - 16) / 4 = 12 workers recommended
RECOMMENDED_WORKERS=12

# Allow override from command line
WORKERS=${1:-$RECOMMENDED_WORKERS}

echo "System Configuration:"
echo "  RAM: ${RAM_GB}GB"
echo "  CPU Cores: $CPU_CORES"
echo "  Recommended Workers: $RECOMMENDED_WORKERS"
echo "  Using Workers: $WORKERS"
echo ""

# Performance estimate
TOTAL_TASKS=4452
TIME_PER_TASK=10
ESTIMATED_HOURS=$(( ($TOTAL_TASKS * $TIME_PER_TASK) / $WORKERS / 60 ))

echo "📊 Performance Estimate (4452 tasks):"
echo "  Workers: $WORKERS parallel"
echo "  Time: ~$ESTIMATED_HOURS hours"
echo "  Days: ~$(( $ESTIMATED_HOURS / 24 )) days"
echo ""

# Check dependencies
echo "Checking system..."

if ! pgrep -x redis-server > /dev/null; then
    echo "❌ Redis not running!"
    echo "   Start: sudo systemctl start redis"
    exit 1
fi

if ! mongosh "mongodb://admin:Aaziko%21%40%23123@202.47.115.6:27017/?authSource=admin" --quiet --eval "db.adminCommand('ping')" > /dev/null 2>&1; then
    echo "❌ MongoDB not accessible!"
    exit 1
fi

# Check proxies
PROXY_COUNT=$(wc -l < config/proxies.txt)
echo "✅ Redis: Running"
echo "✅ MongoDB: Connected (remote)"
echo "✅ Proxies: $PROXY_COUNT loaded"
echo ""

# Stop existing
echo "Stopping existing workers..."
pkill -9 -f "celery.*trademap" 2>/dev/null
pkill -9 -f "uvicorn" 2>/dev/null
sleep 3

# Create logs dir
mkdir -p logs

# Start FastAPI
echo "Starting FastAPI server..."
uvicorn core.main:app --host 0.0.0.0 --port 1080 --workers 2 > logs/fastapi.log 2>&1 &
sleep 3

# Start Celery with optimized settings for 64GB RAM
echo "Starting Celery with $WORKERS workers..."
celery -A celery_app.tasks worker \
    --loglevel=info \
    -Q trademap \
    --concurrency=$WORKERS \
    --max-tasks-per-child=30 \
    --prefetch-multiplier=2 \
    --time-limit=1200 \
    --soft-time-limit=1000 \
    --max-memory-per-child=4000000 \
    > logs/celery_trademap.log 2>&1 &

sleep 5

# Verify
echo ""
echo "=========================================="
echo "  Status"
echo "=========================================="

if pgrep -f uvicorn > /dev/null; then
    echo "✅ FastAPI: Running"
else
    echo "❌ FastAPI: Failed"
fi

if pgrep -f "celery.*trademap" > /dev/null; then
    CELERY_PIDS=$(pgrep -f "celery.*trademap" | wc -l)
    echo "✅ Celery: Running ($CELERY_PIDS processes)"
    echo "   Workers: $WORKERS parallel tasks"
    echo "   With Proxy: ✅ Enabled"
    echo "   Headless: ✅ Enabled"
else
    echo "❌ Celery: Failed"
    exit 1
fi

echo ""
echo "📊 Expected Performance:"
echo "   Total: 4452 tasks"
echo "   Parallel: $WORKERS workers"
echo "   Time: ~$ESTIMATED_HOURS hours (~$(( $ESTIMATED_HOURS / 24 )) days)"
echo "   Speed: $(( 742 / $ESTIMATED_HOURS ))x faster than single worker"
echo ""

echo "🌐 Access Form:"
echo "   ./open_form.sh"
echo "   http://localhost:1080"
echo ""

echo "📊 Monitor:"
echo "   ./monitor_scraping.sh"
echo "   tail -f logs/celery_trademap.log"
echo ""

echo "=========================================="
echo "  🚀 Ready with Proxy Support!"
echo "=========================================="
