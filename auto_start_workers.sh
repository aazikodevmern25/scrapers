#!/bin/bash

# Auto-start TradeMap workers if not running
# This script checks if workers are running and starts them if needed

WORKERS_RUNNING=$(ps aux | grep "celery.*trademap" | grep -v grep | wc -l)

if [ "$WORKERS_RUNNING" -eq 0 ]; then
    echo "TradeMap workers not running. Starting workers..."
    cd /home/aaziko/scrapers
    celery -A celery_app.tasks worker --loglevel=info -Q trademap --concurrency=20 --logfile=logs/celery_trademap.log --detach
    sleep 3
    
    # Verify workers started
    WORKERS_RUNNING=$(ps aux | grep "celery.*trademap" | grep -v grep | wc -l)
    if [ "$WORKERS_RUNNING" -gt 0 ]; then
        echo "✅ TradeMap workers started successfully ($WORKERS_RUNNING workers)"
    else
        echo "❌ Failed to start TradeMap workers"
        exit 1
    fi
else
    echo "✅ TradeMap workers already running ($WORKERS_RUNNING workers)"
fi
