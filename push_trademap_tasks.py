#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import db
from celery_app.tasks import trademap_scraper_task
import time

print("Starting continuous trademap task pusher...")

while True:
    # Get pending tasks
    tasks = list(db["scraper_tasks"].find({
        "scraper": "TradeMap",
        "status": "pending",
        "task_id": ""
    }).limit(50))
    
    if not tasks:
        print(f"No pending tasks. Waiting 30s...")
        time.sleep(30)
        continue
    
    print(f"Found {len(tasks)} pending tasks. Pushing to queue...")
    
    for task in tasks:
        try:
            payload = task["payload"]
            result = trademap_scraper_task.apply_async(
                kwargs={
                    "hscode": payload.get("hscode"),
                    "country1": payload.get("country1"),
                    "country2": payload.get("country2"),
                    "time_series_list": payload.get("time_series_list"),
                    "view_type_list": payload.get("view_type_list"),
                    "value_type_list": payload.get("value_type_list"),
                    "all_hs_codes": payload.get("all_hs_codes", False),
                    "all_exporting": payload.get("all_exporting", False),
                    "all_importing": payload.get("all_importing", False)
                },
                queue="trademap"
            )
            
            # Update task with celery task_id
            db["scraper_tasks"].update_one(
                {"_id": task["_id"]},
                {"$set": {"task_id": result.id, "status": "PENDING"}}
            )
            print(f"  Pushed: {payload.get('country2')} - {result.id[:20]}")
            time.sleep(0.1)  # Small delay to avoid overwhelming
            
        except Exception as e:
            print(f"  Error pushing task: {e}")
    
    print(f"Batch complete. Waiting 10s before next batch...")
    time.sleep(10)
