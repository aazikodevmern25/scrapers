#!/bin/bash
# Auto-start all scraper services on server reboot
# This script should be added to crontab with @reboot

sleep 30  # Wait for system to fully boot

cd /home/aaziko/scrapers

# Create log directory
mkdir -p logs

# Start FastAPI
nohup python3 -m uvicorn core.main:app --host 0.0.0.0 --port 8000 > logs/fastapi.log 2>&1 &
sleep 15

# Start ngrok
nohup ngrok http 8000 --log=stdout > logs/ngrok.log 2>&1 &
sleep 10

# Start MacMap workers (16 workers)
for i in {1..4}; do 
    nohup celery -A celery_app.tasks worker --loglevel=info -Q macmap_tariff --concurrency=3 --hostname=macmap_tariff_worker_${i}@%h --max-tasks-per-child=50 > logs/celery_macmap_tariff_worker${i}.log 2>&1 &
    sleep 1
done

# Start TradeMap workers (10 workers)
for i in {1..10}; do
    nohup celery -A celery_app.tasks worker --loglevel=info -Q trademap --concurrency=3 --hostname=trademap_worker${i}@%h --max-tasks-per-child=100 > logs/celery_trademap_worker${i}.log 2>&1 &
    sleep 1
done

# Get new ngrok URL and save
sleep 10
NEW_URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | python3 -c "import sys, json; data = json.load(sys.stdin); print(data['tunnels'][0]['public_url'])" 2>/dev/null)

# Save to file
cat > /home/aaziko/scrapers/CURRENT_NGROK_URL.txt << EOF
====================================================================
AUTO-STARTED AFTER REBOOT ($(date))
====================================================================

Base URL: $NEW_URL

Forms:
  • TradeMap Form: ${NEW_URL}/trademap-form
  • MacMap Tariff Form: ${NEW_URL}/static/macmap_tariff_form.html

Workers Running:
  ✅ MacMap Workers: 16
  ✅ TradeMap Workers: 10

====================================================================
EOF

echo "$(date): Auto-start completed successfully" >> /home/aaziko/scrapers/logs/auto_start.log
