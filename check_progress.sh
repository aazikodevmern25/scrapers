#!/bin/bash

# Quick Progress Checker for TradeMap Scraper

echo "=========================================="
echo "  TradeMap Scraper - Progress Check"
echo "=========================================="
echo ""

# Check workers
WORKER_COUNT=$(pgrep -af "celery.*trademap" | wc -l)
if [ $WORKER_COUNT -gt 0 ]; then
    echo "✅ Celery Workers: $WORKER_COUNT processes running"
else
    echo "❌ Celery Workers: NOT RUNNING!"
    echo "   Start with: ./start_optimized.sh"
    exit 1
fi

# Check tasks in queue
QUEUE_SIZE=$(redis-cli llen trademap 2>/dev/null)
echo "📋 Tasks in Queue: $QUEUE_SIZE"

# Check active tasks
echo ""
echo "🔄 Active Tasks:"
celery -A celery_app.tasks inspect active -Q trademap 2>/dev/null | grep -A 2 "trademap_scraper_task" | head -20

# Check MongoDB count
echo ""
echo "📊 MongoDB Status:"
CURRENT_COUNT=$(mongosh "mongodb://admin:Aaziko%21%40%23123@202.47.115.6:27017/Dhruval?authSource=admin" --quiet --eval "db.trademap.countDocuments()" 2>/dev/null)
echo "   Current Documents: $CURRENT_COUNT"

# Calculate progress
TOTAL_TASKS=4452
EXPECTED_DOCS=$((TOTAL_TASKS * 2))
if [ ! -z "$CURRENT_COUNT" ]; then
    PROGRESS=$(echo "scale=2; ($CURRENT_COUNT / $EXPECTED_DOCS) * 100" | bc)
    echo "   Expected Total: $EXPECTED_DOCS"
    echo "   Progress: ${PROGRESS}%"
fi

# Check recent activity
echo ""
echo "🕐 Recent Activity (last 5 minutes):"
FIVE_MIN_AGO=$(date -u -d '5 minutes ago' '+%Y-%m-%dT%H:%M:%S')
RECENT_COUNT=$(mongosh "mongodb://admin:Aaziko%21%40%23123@202.47.115.6:27017/Dhruval?authSource=admin" --quiet --eval "db.trademap.countDocuments({DateCreated: {\$gte: new Date('$FIVE_MIN_AGO')}})" 2>/dev/null)
echo "   New documents: $RECENT_COUNT"

if [ "$RECENT_COUNT" -gt 0 ]; then
    echo "   ✅ Scraping is ACTIVE!"
else
    echo "   ⚠️  No new documents in last 5 minutes"
    echo "   Check logs: tail -f logs/trademap_scraper.log"
fi

# Show latest document
echo ""
echo "📄 Latest Document:"
mongosh "mongodb://admin:Aaziko%21%40%23123@202.47.115.6:27017/Dhruval?authSource=admin" --quiet --eval "db.trademap.find().sort({DateCreated: -1}).limit(1).forEach(doc => print('   HS Code: ' + doc.HsCode + ' | Mode: ' + doc.Mode + ' | ' + doc.Data.Country1 + ' → ' + doc.Data.Country2 + ' | Created: ' + doc.DateCreated))" 2>/dev/null

echo ""
echo "=========================================="
echo "  Commands:"
echo "=========================================="
echo "  Watch live:    watch -n 10 ./check_progress.sh"
echo "  View logs:     tail -f logs/trademap_scraper.log"
echo "  Full monitor:  ./monitor_scraping.sh"
echo "=========================================="
