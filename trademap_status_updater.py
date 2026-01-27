#!/usr/bin/env python3
"""
TradeMap Status Updater - Continuously checks Celery task status and updates MongoDB
This ensures tasks are marked as SUCCESS/FAILED in the database
"""
import sys
import os
import time
import signal
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import db
from celery.result import AsyncResult
from celery_app.tasks import app

running = True

def signal_handler(sig, frame):
    global running
    print("\n🛑 Shutdown signal received...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def check_and_update_statuses():
    """Check PENDING tasks in MongoDB and update their status from Celery"""
    try:
        # Get all PENDING tasks
        pending_tasks = list(db['scraper_tasks'].find({
            'scraper': 'TradeMap',
            'status': 'PENDING',
            'task_id': {'$ne': ''}
        }))
        
        if not pending_tasks:
            return 0
        
        updated = 0
        for task in pending_tasks:
            try:
                task_id = task.get('task_id')
                if not task_id:
                    continue
                
                # Check Celery status
                result = AsyncResult(task_id, app=app)
                celery_status = result.status
                
                # Update if status changed
                if celery_status == 'SUCCESS':
                    db['scraper_tasks'].update_one(
                        {'_id': task['_id']},
                        {'$set': {'status': 'SUCCESS', 'updated_at': datetime.utcnow()}}
                    )
                    updated += 1
                    print(f"✅ Task completed: {task.get('payload', {}).get('country2', 'N/A')}")
                    
                elif celery_status in ['FAILURE', 'REVOKED']:
                    db['scraper_tasks'].update_one(
                        {'_id': task['_id']},
                        {'$set': {'status': 'FAILED', 'updated_at': datetime.utcnow()}}
                    )
                    updated += 1
                    print(f"❌ Task failed: {task.get('payload', {}).get('country2', 'N/A')}")
                    
            except Exception as e:
                pass  # Skip errors for individual tasks
        
        return updated
        
    except Exception as e:
        print(f"Error checking statuses: {e}")
        return 0

def main():
    print("=" * 80)
    print("🔄 TradeMap Status Updater")
    print("=" * 80)
    print("Monitors PENDING tasks and updates their status from Celery")
    print("Checks every 15 seconds")
    print("=" * 80)
    
    cycle = 0
    
    while running:
        try:
            cycle += 1
            
            # Check and update statuses
            updated = check_and_update_statuses()
            
            if updated > 0:
                # Show current stats
                success = db['scraper_tasks'].count_documents({'scraper': 'TradeMap', 'status': 'SUCCESS'})
                pending = db['scraper_tasks'].count_documents({'scraper': 'TradeMap', 'status': 'PENDING'})
                total_records = db['trademap'].count_documents({})
                
                print(f"📊 Status: {success} completed | {pending} pending | {total_records} records")
            
            # Wait before next check
            if running:
                for _ in range(15):  # 15 second intervals
                    if not running:
                        break
                    time.sleep(1)
                    
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ Error in main loop: {e}")
            if running:
                time.sleep(15)
    
    print("\n👋 Status updater stopped")

if __name__ == "__main__":
    main()
