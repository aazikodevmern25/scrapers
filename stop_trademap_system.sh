#!/bin/bash
##############################################################################
# Stop TradeMap System
##############################################################################

cd "$(dirname "$0")"

echo "=========================================="
echo "🛑 Stopping TradeMap System"
echo "=========================================="

# Stop auto processor
if [ -f .trademap_auto_processor.pid ]; then
    PID=$(cat .trademap_auto_processor.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "Stopping Auto Processor (PID: $PID)..."
        kill $PID
        sleep 2
        # Force kill if still running
        if ps -p $PID > /dev/null 2>&1; then
            kill -9 $PID
        fi
    fi
    rm .trademap_auto_processor.pid
fi

# Stop status updater
if [ -f .trademap_status_updater.pid ]; then
    PID=$(cat .trademap_status_updater.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "Stopping Status Updater (PID: $PID)..."
        kill $PID
        sleep 2
        if ps -p $PID > /dev/null 2>&1; then
            kill -9 $PID
        fi
    fi
    rm .trademap_status_updater.pid
fi

# Stop all trademap workers
echo "Stopping TradeMap workers..."
pkill -9 -f 'celery.*trademap' 2>/dev/null || true
pkill -9 -f 'trademap_auto_processor' 2>/dev/null || true
pkill -9 -f 'tradeMapTaskCreator' 2>/dev/null || true

# Clean up PID files
rm -f .trademap_worker*.pid

sleep 2

echo ""
echo "✅ TradeMap System stopped"
echo ""
