#!/bin/bash

# Stop any existing workers
pkill -9 -f "celery.*worker.*eximpedia" 2>/dev/null

# Clear Python cache
cd /home/aaziko/scrapers
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete 2>/dev/null

# Start worker with autoreload to pick up code changes
export PYTHONDONTWRITEBYTECODE=1
celery -A celery_app.tasks worker \
    --loglevel=info \
    -Q eximpedia \
    --logfile=logs/celery_eximpedia.log \
    -n eximpedia_worker@%h \
    --concurrency=4 \
    --autoreload \
    --max-tasks-per-child=1
