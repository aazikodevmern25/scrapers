#!/usr/bin/env python3
"""
Trigger Eximpedia Tasks - Manually process pending MongoDB tasks and queue to Celery
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pymongo import MongoClient
from dotenv import load_dotenv
from celery_app.tasks import eximpedia_scraper_task

load_dotenv()

# Connect to MongoDB
client = MongoClient(os.getenv('MONGO_URI'))
db = client[os.getenv('MONGO_DB', 'Dhruval')]
tasks_collection = db['scraper_tasks']

print("=" * 70)
print("EXIMPEDIA TASK PROCESSOR")
print("=" * 70)

# Get pending tasks
pending_tasks = list(tasks_collection.find({
    'scraper': 'eximpedia',
    'status': 'pending'
}).limit(100))

print(f"\n📊 Found {len(pending_tasks)} pending tasks")

if not pending_tasks:
    print("✅ No pending tasks to process")
    sys.exit(0)

# Process each task
queued_count = 0
for task in pending_tasks:
    payload = task.get('payload', {})
    
    # Extract payload data
    start_date = payload.get('start_date')
    end_date = payload.get('end_date')
    hscode = payload.get('hscode')
    country = payload.get('country')
    mode = payload.get('mode')
    
    print(f"\n📤 Queueing task:")
    print(f"   HS Code: {hscode}")
    print(f"   Country: {country}")
    print(f"   Mode: {mode}")
    print(f"   Dates: {start_date} to {end_date}")
    
    # Queue to Celery
    celery_task = eximpedia_scraper_task.delay(
        start_date=start_date,
        end_date=end_date,
        hscode=hscode,
        country=country,
        mode=mode
    )
    
    # Update MongoDB task with Celery task ID
    tasks_collection.update_one(
        {'_id': task['_id']},
        {
            '$set': {
                'task_id': celery_task.id,
                'status': 'processing'
            }
        }
    )
    
    queued_count += 1
    print(f"   ✅ Queued (Celery ID: {celery_task.id})")

print(f"\n" + "=" * 70)
print(f"✅ Successfully queued {queued_count} tasks to Celery workers")
print("=" * 70)
print("\n💡 Monitor progress:")
print(f"   tail -f logs/eximpedia_scraper_$(date +%Y%m%d).log")
print(f"   tail -f logs/eximpedia_worker1.log")
