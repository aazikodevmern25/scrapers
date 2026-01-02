#!/bin/bash

# Kill All Celery Workers Script
# This script stops all Celery workers and cleans up

echo "🔴 Killing all Celery workers..."

# Kill all celery worker processes
pkill -9 -f "celery.*worker"

# Kill flower if running
pkill -9 -f "celery.*flower"

# Wait a moment
sleep 1

# Check if any celery processes are still running
REMAINING=$(ps aux | grep -i celery | grep -v grep | wc -l)

if [ $REMAINING -eq 0 ]; then
    echo "✅ All Celery workers killed successfully"
else
    echo "⚠️  Warning: $REMAINING Celery processes still running"
    ps aux | grep -i celery | grep -v grep
fi

# Optional: Clear Redis (uncomment if you want to clear all task data)
# echo "🧹 Clearing Redis..."
# redis-cli FLUSHALL

# Clean up PID files
echo "🧹 Cleaning up PID files..."
find . -name "*.pid" -type f -delete 2>/dev/null

echo ""
echo "✨ Cleanup complete!"
echo ""
echo "To start workers again, use:"
echo "  python main.py  (starts API server)"
echo "  Or use the dashboard to start individual workers"
