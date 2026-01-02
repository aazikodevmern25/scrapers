#!/bin/bash

# Check Workers Status Script
# Shows current state of all Celery workers

echo "🔍 Checking Celery Workers Status..."
echo ""

# Check for running celery processes
CELERY_COUNT=$(ps aux | grep -i "celery.*worker" | grep -v grep | wc -l)
FLOWER_COUNT=$(ps aux | grep -i "celery.*flower" | grep -v grep | wc -l)

echo "📊 Process Status:"
echo "  Celery Workers: $CELERY_COUNT"
echo "  Flower Monitor: $FLOWER_COUNT"
echo ""

if [ $CELERY_COUNT -gt 0 ]; then
    echo "🟢 Running Celery Workers:"
    ps aux | grep -i "celery.*worker" | grep -v grep | awk '{print "  PID:", $2, "| Queue:", $(NF-5)}'
    echo ""
fi

if [ $FLOWER_COUNT -gt 0 ]; then
    echo "🌸 Flower is running on port 5555"
    echo ""
fi

# Check Redis
echo "📦 Redis Status:"
if redis-cli ping > /dev/null 2>&1; then
    echo "  ✅ Redis is running"
    KEYS=$(redis-cli DBSIZE | grep -o '[0-9]*')
    echo "  📝 Keys in database: $KEYS"
else
    echo "  ❌ Redis is not running"
fi
echo ""

# Check for PID files
PID_FILES=$(find . -name "*.pid" -type f 2>/dev/null | wc -l)
if [ $PID_FILES -gt 0 ]; then
    echo "⚠️  Found $PID_FILES PID file(s):"
    find . -name "*.pid" -type f 2>/dev/null
    echo ""
fi

# Summary
echo "📋 Summary:"
if [ $CELERY_COUNT -eq 0 ]; then
    echo "  ✅ No workers running - Ready to start fresh"
else
    echo "  🟢 $CELERY_COUNT worker(s) active"
fi
