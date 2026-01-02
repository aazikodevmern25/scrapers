#!/bin/bash

# TradeMap Scraper - POWERFUL SERVER DEPLOYMENT
# For servers with 128GB RAM and 80 cores

echo "=========================================="
echo "  TradeMap - Powerful Server Setup"
echo "  128GB RAM | 80 Cores"
echo "=========================================="
echo ""

# Automatic concurrency based on CPU cores
AVAILABLE_CORES=$(nproc)
AVAILABLE_RAM_GB=$(free -g | awk '/^Mem:/{print $2}')

# Calculate optimal concurrency
# Rule: Use 50% of cores for scraping (leave room for system + browser overhead)
# Each browser instance needs ~2GB RAM, so limit by RAM too
MAX_BY_CORES=$(( $AVAILABLE_CORES / 2 ))
MAX_BY_RAM=$(( $AVAILABLE_RAM_GB / 3 ))  # Each task uses ~3GB (browser + data)

# Use the smaller value
if [ $MAX_BY_CORES -lt $MAX_BY_RAM ]; then
    RECOMMENDED_CONCURRENCY=$MAX_BY_CORES
else
    RECOMMENDED_CONCURRENCY=$MAX_BY_RAM
fi

# Allow override from command line
CONCURRENCY=${1:-$RECOMMENDED_CONCURRENCY}

echo "System Resources:"
echo "  CPU Cores: $AVAILABLE_CORES"
echo "  RAM: $AVAILABLE_RAM_GB GB"
echo ""
echo "Optimal Configuration:"
echo "  Recommended Concurrency: $RECOMMENDED_CONCURRENCY"
echo "  Using Concurrency: $CONCURRENCY"
echo ""

# Performance calculation
TOTAL_TASKS=4452
TIME_PER_TASK=10
ESTIMATED_MINUTES=$(( ($TOTAL_TASKS * $TIME_PER_TASK) / $CONCURRENCY ))
ESTIMATED_HOURS=$(( $ESTIMATED_MINUTES / 60 ))
ESTIMATED_DAYS=$(( $ESTIMATED_HOURS / 24 ))

echo "📊 Performance Estimate for 4452 tasks:"
echo "  Time per task: ~$TIME_PER_TASK minutes"
echo "  Parallel tasks: $CONCURRENCY"
echo "  Total time: ~$ESTIMATED_HOURS hours ($ESTIMATED_DAYS days)"
echo ""

# Confirm
read -p "Start with $CONCURRENCY parallel workers? (y/n): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# Create logs directory
mkdir -p logs

# Check dependencies
echo "Checking dependencies..."

if ! pgrep -x redis-server > /dev/null; then
    echo "❌ Redis is not running!"
    echo "   Start it with: sudo systemctl start redis"
    echo "   Or: redis-server &"
    exit 1
fi

if ! mongosh "mongodb://admin:Aaziko%21%40%23123@202.47.115.6:27017/?authSource=admin" --quiet --eval "db.adminCommand('ping')" > /dev/null 2>&1; then
    echo "❌ MongoDB is not accessible!"
    exit 1
fi

echo "✅ Redis: Running"
echo "✅ MongoDB: Connected"
echo ""

# Stop existing workers
echo "Stopping existing workers..."
pkill -9 -f "celery.*trademap" 2>/dev/null
pkill -9 -f "uvicorn" 2>/dev/null
sleep 3

# Start FastAPI server
echo "Starting FastAPI server..."
uvicorn core.main:app --host 0.0.0.0 --port 1080 \
    --workers 4 \
    > logs/fastapi.log 2>&1 &
sleep 3

# Start Celery worker with high concurrency
echo "Starting Celery worker with $CONCURRENCY parallel tasks..."
celery -A celery_app.tasks worker \
    --loglevel=info \
    -Q trademap \
    --concurrency=$CONCURRENCY \
    --max-tasks-per-child=50 \
    --prefetch-multiplier=2 \
    --time-limit=1200 \
    --soft-time-limit=1000 \
    > logs/celery_trademap.log 2>&1 &

sleep 5

# Verify everything is running
echo ""
echo "=========================================="
echo "  Status Check"
echo "=========================================="

FASTAPI_RUNNING=$(pgrep -f uvicorn | wc -l)
CELERY_RUNNING=$(pgrep -f "celery.*trademap" | wc -l)

if [ $FASTAPI_RUNNING -gt 0 ]; then
    echo "✅ FastAPI: Running ($FASTAPI_RUNNING processes)"
else
    echo "❌ FastAPI: Not running"
fi

if [ $CELERY_RUNNING -gt 0 ]; then
    echo "✅ Celery: Running ($CELERY_RUNNING processes)"
    echo "   Concurrency: $CONCURRENCY parallel tasks"
else
    echo "❌ Celery: Not running"
    exit 1
fi

echo ""
echo "📊 Expected Performance:"
echo "   Total Tasks: $TOTAL_TASKS"
echo "   Parallel Workers: $CONCURRENCY"
echo "   Estimated Time: $ESTIMATED_HOURS hours (~$ESTIMATED_DAYS days)"
echo "   Speed Improvement: $(( 742 / $ESTIMATED_HOURS ))x faster than single worker"
echo ""

echo "🌐 Web Form:"
echo "   http://localhost:1080"
echo "   Or: ./open_form.sh"
echo ""

echo "📊 Monitor Progress:"
echo "   ./monitor_scraping.sh"
echo "   tail -f logs/trademap_scraper.log"
echo "   tail -f logs/celery_trademap.log"
echo ""

echo "=========================================="
echo "  🚀 System Ready!"
echo "=========================================="
