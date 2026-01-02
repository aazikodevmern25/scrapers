#!/bin/bash

# TradeMap Scraper - HIGH PERFORMANCE MODE
# For servers with high RAM and CPU cores

echo "=========================================="
echo "  TradeMap Scraper - Fast Mode"
echo "=========================================="
echo ""

# Configuration
CONCURRENCY=${1:-20}  # Default 20 parallel tasks (can be changed)
LOG_DIR="logs"

# Create logs directory if not exists
mkdir -p $LOG_DIR

echo "Configuration:"
echo "  Concurrency: $CONCURRENCY parallel tasks"
echo "  Log file: $LOG_DIR/celery_trademap.log"
echo ""

# Check if Redis is running
if ! pgrep -x redis-server > /dev/null; then
    echo "❌ Redis is not running!"
    echo "   Start it with: sudo systemctl start redis"
    exit 1
fi

# Check if MongoDB is accessible
if ! mongosh "mongodb://admin:Aaziko%21%40%23123@202.47.115.6:27017/?authSource=admin" --quiet --eval "db.adminCommand('ping')" > /dev/null 2>&1; then
    echo "❌ MongoDB is not accessible!"
    echo "   Check connection to 202.47.115.6:27017"
    exit 1
fi

echo "✅ Redis: Running"
echo "✅ MongoDB: Connected"
echo ""

# Stop existing workers
echo "Stopping existing Celery workers..."
pkill -9 -f "celery.*trademap" 2>/dev/null
sleep 2

# Start Celery worker with high concurrency
echo "Starting Celery worker with $CONCURRENCY concurrent tasks..."
celery -A celery_app.tasks worker \
    --loglevel=info \
    -Q trademap \
    --concurrency=$CONCURRENCY \
    --max-tasks-per-child=50 \
    --prefetch-multiplier=2 \
    > $LOG_DIR/celery_trademap.log 2>&1 &

CELERY_PID=$!
sleep 3

# Check if worker started
if pgrep -f "celery.*trademap" > /dev/null; then
    echo "✅ Celery worker started successfully!"
    echo "   PID: $CELERY_PID"
    echo "   Concurrency: $CONCURRENCY parallel tasks"
    echo ""
    echo "📊 Performance Estimate:"
    echo "   - 4452 tasks at 10 min each"
    echo "   - Single worker: ~742 hours (31 days)"
    echo "   - With $CONCURRENCY workers: ~$(( 742 / $CONCURRENCY )) hours ($(( 742 / $CONCURRENCY / 24 )) days)"
    echo ""
    echo "Monitor progress:"
    echo "   tail -f $LOG_DIR/celery_trademap.log"
    echo "   ./monitor_scraping.sh"
else
    echo "❌ Failed to start Celery worker!"
    echo "   Check logs: tail $LOG_DIR/celery_trademap.log"
    exit 1
fi

echo ""
echo "=========================================="
echo "  Worker is running in background!"
echo "=========================================="
