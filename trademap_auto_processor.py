#!/usr/bin/env python3
"""
TradeMap Auto Processor - Continuous Task Monitor
Automatically processes all trademap tasks without manual intervention
"""
import sys
import os
import time
import signal
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import db
from celery_app.tasks import trademap_scraper_task

# Configuration
CHECK_INTERVAL = 10  # Check for new tasks every 10 seconds
BATCH_SIZE = 50      # Process up to 50 tasks per batch
RATE_LIMIT = 0.1     # Delay between task submissions (seconds)

running = True

def signal_handler(sig, frame):
    """Handle graceful shutdown"""
    global running
    print("\n🛑 Shutdown signal received, finishing current batch...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def push_pending_tasks():
    """Find and push all pending trademap tasks to Celery queue"""
    try:
        # Find pending tasks that haven't been assigned to workers yet
        tasks = list(db['scraper_tasks'].find({
            'scraper': 'TradeMap',
            'status': 'pending',
            'task_id': ''
        }).limit(BATCH_SIZE))
        
        if not tasks:
            return 0
        
        print(f"⏰ {datetime.now().strftime('%H:%M:%S')} - Found {len(tasks)} pending tasks, pushing to queue...")
        
        pushed = 0
        for task in tasks:
            if not running:
                break
                
            try:
                payload = task['payload']
                
                # Push task to Celery queue
                result = trademap_scraper_task.apply_async(
                    kwargs={
                        'hscode': payload.get('hscode'),
                        'country1': payload.get('country1'),
                        'country2': payload.get('country2'),
                        'time_series_list': payload.get('time_series_list'),
                        'view_type_list': payload.get('view_type_list'),
                        'value_type_list': payload.get('value_type_list'),
                        'all_hs_codes': payload.get('all_hs_codes', False),
                        'all_exporting': payload.get('all_exporting', False),
                        'all_importing': payload.get('all_importing', False)
                    },
                    queue='trademap'
                )
                
                # Update task status in MongoDB
                db['scraper_tasks'].update_one(
                    {'_id': task['_id']},
                    {'$set': {'task_id': result.id, 'status': 'PENDING'}}
                )
                
                pushed += 1
                time.sleep(RATE_LIMIT)
                
            except Exception as e:
                print(f"  ✗ Error pushing task: {e}")
        
        if pushed > 0:
            print(f"  ✅ Pushed {pushed} tasks to workers")
        
        return pushed
        
    except Exception as e:
        print(f"❌ Error in push_pending_tasks: {e}")
        return 0

def print_status():
    """Print current task status"""
    try:
        success = db['scraper_tasks'].count_documents({'scraper': 'TradeMap', 'status': 'SUCCESS'})
        pending_processing = db['scraper_tasks'].count_documents({'scraper': 'TradeMap', 'status': 'PENDING'})
        pending_waiting = db['scraper_tasks'].count_documents({'scraper': 'TradeMap', 'status': 'pending'})
        failed = db['scraper_tasks'].count_documents({'scraper': 'TradeMap', 'status': 'FAILED'})
        total = success + pending_processing + pending_waiting + failed
        
        print(f"\n📊 TradeMap Status: ✅ {success}/{total} completed | ⏳ {pending_processing} processing | 📋 {pending_waiting} waiting | ❌ {failed} failed")
        
    except Exception as e:
        print(f"Error getting status: {e}")

def main():
    """Main loop - continuously monitor and process tasks"""
    print("=" * 80)
    print("🚀 TradeMap Auto Processor - Continuous Task Monitor")
    print("=" * 80)
    print(f"⚙️  Configuration:")
    print(f"   - Check interval: {CHECK_INTERVAL}s")
    print(f"   - Batch size: {BATCH_SIZE} tasks")
    print(f"   - Rate limit: {RATE_LIMIT}s between tasks")
    print("=" * 80)
    
    # Initial status
    print_status()
    
    cycle = 0
    last_status_print = time.time()
    
    print("\n🔄 Starting continuous monitoring... (Press Ctrl+C to stop)")
    
    while running:
        try:
            cycle += 1
            
            # Push any pending tasks to queue
            pushed = push_pending_tasks()
            
            # Print status every 60 seconds or if tasks were pushed
            if pushed > 0 or (time.time() - last_status_print) > 60:
                print_status()
                last_status_print = time.time()
            
            # Wait before next check
            if running:
                for _ in range(CHECK_INTERVAL):
                    if not running:
                        break
                    time.sleep(1)
                    
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\n❌ Error in main loop: {e}")
            if running:
                print(f"   Retrying in {CHECK_INTERVAL} seconds...")
                time.sleep(CHECK_INTERVAL)
    
    print("\n👋 TradeMap Auto Processor stopped")
    print_status()

if __name__ == "__main__":
    main()
