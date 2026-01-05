#!/bin/bash

# MacMap Tariff Worker Optimization Script
# Optimizes workers for 80-core system with 125GB RAM

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║            MacMap Tariff Worker Optimization                                ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""

# System info
echo "📊 System Resources:"
echo "  CPU Cores: $(nproc)"
echo "  Total RAM: $(free -h | grep Mem | awk '{print $2}')"
echo "  Available RAM: $(free -h | grep Mem | awk '{print $7}')"
echo ""

# Current workers
CURRENT_WORKERS=$(ps aux | grep "macmap_tariff" | grep -v grep | wc -l)
echo "📌 Current MacMap workers: $CURRENT_WORKERS"
echo ""

# Kill existing workers
echo "🛑 Stopping existing MacMap tariff workers..."
pkill -f "celery.*macmap_tariff"
sleep 3

# Verify stopped
REMAINING=$(ps aux | grep "macmap_tariff" | grep -v grep | wc -l)
if [ $REMAINING -gt 0 ]; then
    echo "⚠️  Force killing remaining workers..."
    pkill -9 -f "celery.*macmap_tariff"
    sleep 2
fi

echo "✓ All workers stopped"
echo ""

# Recommended settings for 80-core, 125GB RAM system:
# - 4 workers (not too many to avoid database connection issues)
# - Concurrency 3 per worker = 12 parallel tasks total
# - This balances performance with stability

WORKERS=4
CONCURRENCY=3

echo "🚀 Starting optimized MacMap tariff workers..."
echo "  Workers: $WORKERS"
echo "  Concurrency per worker: $CONCURRENCY"
echo "  Total parallel tasks: $((WORKERS * CONCURRENCY))"
echo ""

cd /home/aaziko/scrapers

# Start workers
for i in $(seq 1 $WORKERS); do
    echo "  Starting worker $i..."
    nohup celery -A celery_app.tasks worker \
        --loglevel=info \
        -Q macmap_tariff \
        --concurrency=$CONCURRENCY \
        --hostname=macmap_tariff_worker_${i}@%h \
        --max-tasks-per-child=50 \
        > logs/celery_macmap_tariff_worker${i}.log 2>&1 &
    
    sleep 1
done

echo ""
echo "⏳ Waiting for workers to start..."
sleep 5

# Verify workers started
STARTED=$(ps aux | grep "macmap_tariff" | grep -v grep | wc -l)

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Optimization Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📊 Status:"
echo "  Workers started: $STARTED / $WORKERS"
echo "  Parallel capacity: $((WORKERS * CONCURRENCY)) tasks"
echo ""
echo "📋 Logs:"
for i in $(seq 1 $WORKERS); do
    echo "  Worker $i: logs/celery_macmap_tariff_worker${i}.log"
done
echo ""
echo "🔍 Monitor workers:"
echo "  ps aux | grep macmap_tariff | grep -v grep"
echo ""
echo "📈 Watch logs:"
echo "  tail -f logs/celery_macmap_tariff_worker1.log"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
