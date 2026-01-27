#!/usr/bin/env python3
"""
Permanent MacMap Worker - Runs continuously and processes pending tasks
"""
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from utils import db
from celery_app.tasks import scrape_macmap_tariff

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('macmap_worker')

collection = db['scraper_tasks']

def process_macmap_task(task_data):
    """Process a single MacMap task"""
    try:
        payload = task_data.get('payload', {})
        task_id = task_data.get('_id')
        
        # Update to processing
        collection.update_one(
            {'_id': task_id},
            {'$set': {'status': 'processing'}}
        )
        
        # Execute scraper
        result = scrape_macmap_tariff(
            country1=payload.get('country1'),
            country2=payload.get('country2'),
            year=payload.get('year'),
            hsc=payload.get('hsc')
        )
        
        # Check result
        if result and isinstance(result, dict) and result.get('status') == 'success':
            collection.update_one(
                {'_id': task_id},
                {'$set': {'status': 'completed'}}
            )
            logger.info(f"✅ Task {task_id} completed")
            return True
        else:
            error_msg = str(result) if result else 'No result returned'
            collection.update_one(
                {'_id': task_id},
                {'$set': {'status': 'failed', 'error': error_msg}}
            )
            logger.error(f"❌ Task {task_id} failed: {error_msg}")
            return False
    except Exception as e:
        logger.error(f"Task error: {e}")
        collection.update_one(
            {'_id': task_data.get('_id')},
            {'$set': {'status': 'failed', 'error': str(e)}}
        )
        return False

def run_worker():
    """Main worker loop - runs forever"""
    logger.info("🚀 MacMap Worker Started - Running continuously with 2-minute timeout")
    
    while True:
        try:
            # Reset any stuck processing tasks (older than 2 minutes)
            import datetime
            two_min_ago = datetime.datetime.now() - datetime.timedelta(minutes=2)
            stuck = collection.update_many(
                {
                    'scraper': 'MacMapTariff',
                    'status': 'processing',
                    'updated_at': {'$lt': two_min_ago}
                },
                {'$set': {'status': 'pending'}}
            )
            if stuck.modified_count > 0:
                logger.warning(f"⚠️ Reset {stuck.modified_count} stuck tasks (>2 min) to pending")
            
            # Fetch pending tasks
            pending = list(collection.find(
                {'scraper': 'MacMapTariff', 'status': 'pending'}
            ).limit(100))
            
            if not pending:
                logger.info("No pending tasks, waiting 10 seconds...")
                time.sleep(10)
                continue
            
            pending_count = collection.count_documents({'scraper': 'MacMapTariff', 'status': 'pending'})
            logger.info(f"📦 Processing batch of {len(pending)} tasks ({pending_count} total pending)")
            
            # Process with 12 parallel workers
            with ThreadPoolExecutor(max_workers=12) as executor:
                futures = [executor.submit(process_macmap_task, task) for task in pending]
                for future in futures:
                    try:
                        future.result()
                    except Exception as e:
                        logger.error(f"Worker error: {e}")
            
            time.sleep(1)  # Small delay between batches
            
        except Exception as e:
            logger.error(f"Main loop error: {e}")
            time.sleep(10)  # Wait before retrying

if __name__ == "__main__":
    run_worker()
