#!/bin/bash

echo "════════════════════════════════════════════════════════════"
echo "  Starting MacMap Tariff Workers"
echo "════════════════════════════════════════════════════════════"
echo ""

# Check if MacMap API is working first
echo "Checking MacMap API status..."
HTTP_CODE=$(curl -s -w "%{http_code}" -o /dev/null --max-time 10 "https://www.macmap.org/api/getyears?datatype=Tariff&reporters=156")

if [ "$HTTP_CODE" != "200" ]; then
    echo "❌ ERROR: MacMap API is NOT working (HTTP: $HTTP_CODE)"
    echo ""
    echo "API must be working before starting workers!"
    echo "Run ./check_macmap_api.sh to check status"
    echo ""
    exit 1
fi

echo "✅ MacMap API is working! (HTTP: 200)"
echo ""

# Stop any existing workers
echo "Stopping any existing workers..."
pkill -f "celery.*macmap_tariff" 2>/dev/null
sleep 2

# Start workers
cd /home/aaziko/scrapers
echo "Starting 4 workers with 3 concurrency each..."

for i in {1..4}; do 
    nohup celery -A celery_app.tasks worker --loglevel=info \
      -Q macmap_tariff --concurrency=3 \
      --hostname=macmap_tariff_worker_${i}@%h \
      --max-tasks-per-child=50 \
      > logs/celery_macmap_tariff_worker${i}.log 2>&1 & 
    echo "  Started worker ${i}"
    sleep 1
done

echo ""
echo "✅ 4 workers started successfully!"
echo ""
echo "Next steps:"
echo "  1. Go to form: https://c7ee853f5480.ngrok-free.app/static/macmap_tariff_form.html"
echo "  2. Submit SMALL batch (500-1000 tasks)"
echo "  3. Monitor with: tail -f logs/celery_macmap_tariff_worker1.log"
echo "  4. Check data: python3 -c \"from pymongo import MongoClient; import os; from dotenv import load_dotenv; load_dotenv(); client = MongoClient(os.getenv('MONGO_URI')); db = client[os.getenv('MONGO_DB')]; print(f'{db.macmap_tariff.count_documents({})} documents')\""
echo ""
echo "════════════════════════════════════════════════════════════"
