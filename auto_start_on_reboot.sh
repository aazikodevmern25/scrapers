#!/bin/bash
# Auto-start all scraper services on server reboot
# This script should be added to crontab with @reboot
# Uses port 8001 (avoiding 8000 used by Cloudflare)

sleep 30  # Wait for system to fully boot

cd /home/aaziko/scrapers

# Create log directory
mkdir -p logs

echo "$(date): Starting auto-start sequence..." >> /home/aaziko/scrapers/logs/auto_start.log

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Start Redis if not running
if ! pgrep -x "redis-server" > /dev/null; then
    redis-server --daemonize yes
    sleep 2
fi

# Start FastAPI on port 8001 (avoiding 8000)
nohup python3 -m uvicorn core.main:app --host 0.0.0.0 --port 8001 > logs/fastapi.log 2>&1 &
sleep 15

# Start ngrok on port 8001
nohup ~/ngrok http 8001 --log=stdout > logs/ngrok.log 2>&1 &
sleep 10

# Start Eximpedia Workers (5 workers total: 1 task creator + 4 scrapers)
nohup celery -A celery_app.tasks worker --loglevel=info -Q eximpedia_task_creator --concurrency=1 --hostname=eximpedia_task_creator@%h --logfile=logs/eximpedia_task_creator.log --pidfile=.eximpedia_task_creator.pid --detach > /dev/null 2>&1 &
sleep 1

for i in {1..4}; do
    nohup celery -A celery_app.tasks worker --loglevel=info -Q eximpedia --concurrency=2 --hostname=eximpedia_worker${i}@%h --logfile=logs/eximpedia_worker${i}.log --pidfile=.eximpedia_worker${i}.pid --detach > /dev/null 2>&1 &
    sleep 1
done

# Start TradeMap workers (10 workers)
for i in {1..10}; do
    nohup celery -A celery_app.tasks worker --loglevel=info -Q trademap --concurrency=3 --hostname=trademap_worker${i}@%h --max-tasks-per-child=100 --logfile=logs/celery_trademap_worker${i}.log --pidfile=.trademap_worker${i}.pid --detach > /dev/null 2>&1 &
    sleep 0.5
done

# Start MacMap workers (4 workers)
for i in {1..4}; do 
    nohup celery -A celery_app.tasks worker --loglevel=info -Q macmap_tariff --concurrency=3 --hostname=macmap_tariff_worker_${i}@%h --max-tasks-per-child=50 --logfile=logs/celery_macmap_tariff_worker${i}.log --pidfile=.macmap_worker${i}.pid --detach > /dev/null 2>&1 &
    sleep 0.5
done

# Get new ngrok URL and save
sleep 10
NEW_URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | python3 -c "import sys, json; data = json.load(sys.stdin); print(data['tunnels'][0]['public_url'])" 2>/dev/null)

# Retry if URL not available
if [ -z "$NEW_URL" ]; then
    sleep 10
    NEW_URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | python3 -c "import sys, json; data = json.load(sys.stdin); print(data['tunnels'][0]['public_url'])" 2>/dev/null)
fi

# Count workers
EXIMPEDIA_WORKERS=$(ps aux | grep 'celery.*eximpedia' | grep -v grep | wc -l)
TRADEMAP_WORKERS=$(ps aux | grep 'celery.*trademap' | grep -v grep | wc -l)
MACMAP_WORKERS=$(ps aux | grep 'celery.*macmap_tariff' | grep -v grep | wc -l)

# Save to file
cat > /home/aaziko/scrapers/CURRENT_NGROK_URL.txt << EOF
====================================================================
AUTO-STARTED AFTER REBOOT ($(date))
====================================================================

Base URL: $NEW_URL
Port: 8001 (FastAPI)

EXIMPEDIA:
  • Form: ${NEW_URL}/eximpedia-form
  • Mirror Data: ${NEW_URL}/eximpedia-mirror-data-form

TRADEMAP:
  • Form: ${NEW_URL}/trademap-form

MACMAP:
  • Tariff Form: ${NEW_URL}/static/macmap_tariff_form.html
  • Trade Agreements: ${NEW_URL}/static/macmap_trade_agreements_form.html

API:
  • Docs: ${NEW_URL}/docs
  • Health: ${NEW_URL}/api/v1/health

Workers Running:
  ✅ Eximpedia Workers: $EXIMPEDIA_WORKERS
  ✅ TradeMap Workers: $TRADEMAP_WORKERS
  ✅ MacMap Workers: $MACMAP_WORKERS

====================================================================
EOF

# Save individual URLs
echo "$NEW_URL" > /home/aaziko/scrapers/EXIMPEDIA_NGROK_URL.txt
echo "$NEW_URL" > /home/aaziko/scrapers/TRADEMAP_NGROK_URL.txt
echo "$NEW_URL" > /home/aaziko/scrapers/MACMAP_NGROK_URL.txt

echo "$(date): Auto-start completed successfully. URL: $NEW_URL" >> /home/aaziko/scrapers/logs/auto_start.log
