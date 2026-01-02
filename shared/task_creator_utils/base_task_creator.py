#!/usr/bin/env python3
"""
Base Task Creator - MongoDB Version
High-Performance Task Creator with all features from SQLite version
"""

import json
import time
import os
import sys
import signal
import multiprocessing
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any, Callable, Optional

# Add parent directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
data_extractor_dir = os.path.dirname(os.path.dirname(script_dir))
if data_extractor_dir not in sys.path:
    sys.path.insert(0, data_extractor_dir)


class BaseTaskCreator:
    """Base class for all MongoDB-based task creators with high-performance features"""
    
    def __init__(self, scraper_id: str, scraper_name: str, queue_name: str,
                 celery_task_func: Callable, payload_extractor: Callable):
        """
        Initialize task creator
        
        Args:
            scraper_id: Scraper identifier (e.g., 'indiantradeportal')
            scraper_name: Display name (e.g., 'IndianTradePortal')
            queue_name: Celery queue name
            celery_task_func: The Celery task function to call
            payload_extractor: Function to extract kwargs from payload dict
        """
        self.scraper_id = scraper_id
        self.scraper_name = scraper_name
        self.queue_name = queue_name
        self.celery_task_func = celery_task_func
        self.payload_extractor = payload_extractor
        
        # High-Performance Configuration from environment
        self.max_workers = int(os.environ.get('MAX_WORKERS', '16'))
        self.status_check_workers = int(os.environ.get('STATUS_CHECK_WORKERS', '8'))
        self.batch_size = int(os.environ.get('BATCH_SIZE', '10'))
        self.concurrent_batches = int(os.environ.get('CONCURRENT_BATCHES', '3'))
        self.max_retries = int(os.environ.get('MAX_RETRIES', '3'))
        self.rate_limit_delay = float(os.environ.get('RATE_LIMIT_DELAY', '0.1'))
        self.max_concurrent_tasks = int(os.environ.get('MAX_CONCURRENT_TASKS', '50'))
        
        # Get database instance
        from shared.task_creator_utils.task_db import get_scraper_db
        self.db = get_scraper_db(scraper_id)
        
        # Running flag for graceful shutdown
        self.running = True
    
    def print_header(self, title: str):
        """Print formatted header"""
        print(f"\n{'='*80}")
        print(f"  {title}")
        print(f"{'='*80}")
    
    def print_performance_config(self):
        """Print current performance configuration"""
        print(f"\n🚀 {self.scraper_name} High-Performance Configuration:")
        print(f"   💻 CPU Cores Available: {multiprocessing.cpu_count()}")
        print(f"   🔧 Task Creation Workers: {self.max_workers}")
        print(f"   🔍 Status Check Workers: {self.status_check_workers}")
        print(f"   📦 Batch Size: {self.batch_size}")
        print(f"   ⚡ Concurrent Batches: {self.concurrent_batches}")
        print(f"   🎯 Max Concurrent Tasks: {self.max_concurrent_tasks}")
        print(f"   🔄 Max Retries: {self.max_retries}")

    def check_task_status(self, task_id: str) -> str:
        """Check individual task status using Celery"""
        try:
            from celery_app.tasks import app
            from celery.result import AsyncResult
            
            result = AsyncResult(task_id, app=app)
            status = result.status
            # Map Celery status to our status
            if status in ['SUCCESS', 'FAILURE', 'PENDING', 'RETRY', 'REVOKED']:
                return status
            return status
        except Exception:
            return "ERROR"
    
    def batch_status_check(self, task_ids: List[str]) -> Dict[str, str]:
        """Check multiple task statuses concurrently"""
        results = {}
        
        with ThreadPoolExecutor(max_workers=self.status_check_workers) as executor:
            future_to_task = {executor.submit(self.check_task_status, task_id): task_id 
                             for task_id in task_ids}
            
            for future in as_completed(future_to_task):
                task_id = future_to_task[future]
                try:
                    status = future.result()
                    results[task_id] = status
                except:
                    results[task_id] = "ERROR"
        
        return results
    
    def check_all_existing_task_statuses(self) -> Dict:
        """Check status of all existing tasks and update database"""
        from shared.task_creator_utils.mongodb_base import get_database
        
        db = get_database()
        collection = db["scraper_tasks"]
        
        # Get all tasks with task_id that are not completed
        existing_tasks = list(collection.find({
            "scraper": self.scraper_name,
            "task_id": {"$ne": ""},
            "status": {"$nin": ["SUCCESS", "FAILED"]}
        }))
        
        if not existing_tasks:
            return {'total_checked': 0, 'success': 0, 'failed': 0, 'pending': 0, 'updated': 0}
        
        print(f"📊 Checking {len(existing_tasks)} existing {self.scraper_name} tasks...")
        
        # Extract task IDs for batch checking
        task_ids = [task['task_id'] for task in existing_tasks]
        task_map = {task['task_id']: (str(task['_id']), task.get('status', '')) for task in existing_tasks}
        
        # Check all statuses concurrently
        status_results = self.batch_status_check(task_ids)
        
        # Update database with changes
        updated_count = 0
        success_count = 0
        failed_count = 0
        pending_count = 0
        
        for task_id, api_status in status_results.items():
            db_id, current_status = task_map[task_id]
            
            if api_status != current_status and api_status not in ['ERROR', 'UNKNOWN']:
                self.db.update_task_status(db_id, status=api_status)
                updated_count += 1
            
            if api_status == 'SUCCESS':
                success_count += 1
            elif api_status in ['FAILURE', 'FAILED', 'ERROR']:
                failed_count += 1
            else:
                pending_count += 1
        
        print(f"✅ Status check complete: {success_count} success, {failed_count} failed, {pending_count} pending")
        
        return {
            'total_checked': len(existing_tasks),
            'success': success_count,
            'failed': failed_count,
            'pending': pending_count,
            'updated': updated_count
        }
    
    def send_scrape_request(self, payload: Dict) -> Optional[str]:
        """Send scrape request to Celery"""
        try:
            kwargs = self.payload_extractor(payload)
            result = self.celery_task_func.apply_async(
                kwargs=kwargs,
                queue=self.queue_name
            )
            return result.id
        except Exception as e:
            print(f"❌ Task dispatch error: {e}")
            return None
    
    def create_single_task(self, task_data: tuple) -> Dict:
        """Create a single task - for concurrent processing"""
        task_db_id, endpoint, payload_json, existing_task_id, status, retry_count = task_data
        retry_count = retry_count or 0
        
        payload = json.loads(payload_json) if isinstance(payload_json, str) else payload_json
        
        # Check existing task status if available
        if existing_task_id:
            current_status = self.check_task_status(existing_task_id)
            if current_status != status and current_status not in ['ERROR', 'UNKNOWN']:
                self.db.update_task_status(task_db_id, status=current_status)
            
            if current_status == 'SUCCESS':
                return {'status': 'skipped', 'task_id': existing_task_id, 'db_id': task_db_id}
        
        # Create new task
        task_id = self.send_scrape_request(payload)
        
        if task_id:
            self.db.update_task_status(task_db_id, task_id=task_id, status='PENDING', retry_count=retry_count + 1)
            return {'status': 'created', 'task_id': task_id, 'db_id': task_db_id}
        else:
            if retry_count < self.max_retries - 1:
                self.db.update_task_status(task_db_id, retry_count=retry_count + 1)
                return {'status': 'retry', 'db_id': task_db_id}
            else:
                self.db.update_task_status(task_db_id, status='FAILED')
                return {'status': 'failed', 'db_id': task_db_id}
    
    def wait_for_batch_completion(self, batch_tasks: List[Dict], batch_num: int, timeout: int = 300) -> bool:
        """Wait for batch completion - wait indefinitely until ALL tasks complete"""
        if not batch_tasks:
            return True
        
        print(f"⏳ Waiting for {self.scraper_name} batch #{batch_num} ({len(batch_tasks)} tasks)...")
        
        start_time = time.time()
        
        task_status = {task['task_id']: {
            'db_id': task['db_id'],
            'final_status': 'PENDING'
        } for task in batch_tasks}
        
        while self.running:
            pending_task_ids = [tid for tid, info in task_status.items() 
                               if info['final_status'] == 'PENDING']
            
            if not pending_task_ids:
                break
            
            status_results = self.batch_status_check(pending_task_ids)
            
            for task_id, api_status in status_results.items():
                if api_status == 'SUCCESS':
                    task_status[task_id]['final_status'] = 'SUCCESS'
                    self.db.update_task_status(task_status[task_id]['db_id'], status='SUCCESS')
                elif api_status in ['FAILURE', 'FAILED', 'ERROR']:
                    task_status[task_id]['final_status'] = 'FAILED'
                    self.db.update_task_status(task_status[task_id]['db_id'], status='FAILED')
            
            success = sum(1 for info in task_status.values() if info['final_status'] == 'SUCCESS')
            failed = sum(1 for info in task_status.values() if info['final_status'] == 'FAILED')
            pending = len(pending_task_ids)
            
            print(f"\r🔄 Batch #{batch_num}: ✅ {success} | ⏳ {pending} | ❌ {failed}", end="", flush=True)
            
            # Show elapsed time every minute
            elapsed_time = time.time() - start_time
            if int(elapsed_time) % 60 == 0 and elapsed_time > 0:
                print(f"\n⏱️  Batch #{batch_num} running for {elapsed_time//60:.0f} minutes...")
            
            if not pending_task_ids:
                print(f"\n✅ {self.scraper_name} Batch #{batch_num} completed: {success} success, {failed} failed")
                return True
            
            time.sleep(10)
        
        return True

    def process_batch_concurrent(self, batch_data: tuple) -> Dict:
        """Process a single batch using concurrent task creation"""
        batch_num, batch = batch_data
        
        print(f"🔄 {self.scraper_name} Batch #{batch_num} - Processing {len(batch)} tasks with {self.max_workers} workers")
        
        batch_tasks = []
        created_count = 0
        failed_count = 0
        skipped_count = 0
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_task = {executor.submit(self.create_single_task, task_data): task_data 
                             for task_data in batch}
            
            for future in as_completed(future_to_task):
                try:
                    result = future.result()
                    
                    if result['status'] == 'created':
                        batch_tasks.append({
                            'task_id': result['task_id'],
                            'db_id': result['db_id']
                        })
                        created_count += 1
                    elif result['status'] == 'failed':
                        failed_count += 1
                    elif result['status'] == 'skipped':
                        skipped_count += 1
                        
                except Exception as e:
                    print(f"❌ Task creation error: {e}")
                    failed_count += 1
                
                time.sleep(self.rate_limit_delay)
        
        if skipped_count > 0:
            print(f"⏭️  {self.scraper_name} Batch #{batch_num}: Skipped {skipped_count} (already completed)")
        if failed_count > 0:
            print(f"❌ {self.scraper_name} Batch #{batch_num}: {failed_count} creation failures")
        
        if created_count > 0:
            print(f"✅ {self.scraper_name} Batch #{batch_num}: Created {created_count} tasks - waiting for completion...")
            completion_success = self.wait_for_batch_completion(batch_tasks, batch_num)
            
            return {
                'batch_num': batch_num,
                'created': created_count,
                'completed': completion_success,
                'tasks': batch_tasks
            }
        
        return {
            'batch_num': batch_num,
            'created': created_count,
            'completed': True,
            'tasks': []
        }
    
    def process_tasks(self):
        """Main function to process tasks with high-performance concurrent processing"""
        self.print_header(f"🚀 {self.scraper_name} High-Performance Task Creator (MongoDB)")
        self.print_performance_config()
        
        # Get initial stats
        stats = self.db.get_database_stats()
        self.db.print_stats()
        
        if stats['pending_tasks'] == 0:
            print(f"\n🎉 All {self.scraper_name} tasks are already completed!")
            return
        
        # Check existing task statuses using concurrent processing
        print(f"\n🔍 Checking existing {self.scraper_name} task statuses...")
        start_time = time.time()
        status_check_result = self.check_all_existing_task_statuses()
        check_duration = time.time() - start_time
        print(f"⚡ Status check completed in {check_duration:.1f} seconds")
        
        # Get updated stats
        updated_stats = self.db.get_database_stats()
        self.db.print_stats("Updated Summary")
        
        if updated_stats['pending_tasks'] == 0:
            print(f"\n🎉 All {self.scraper_name} tasks completed successfully!")
            return
        
        self.print_header(f"📋 {self.scraper_name} Processing: {updated_stats['pending_tasks']:,} Pending Tasks")
        
        # Calculate number of batches needed
        total_batches = (updated_stats['pending_tasks'] + self.batch_size - 1) // self.batch_size
        print(f"🔥 Processing {total_batches} batches concurrently ({self.batch_size} tasks per batch)")
        
        start_time = time.time()
        total_created = 0
        
        # Process batches with concurrent batch processing
        batch_offset = 0
        batch_number = 1
        
        while self.running and batch_offset < updated_stats['pending_tasks']:
            # Prepare multiple batches for concurrent processing
            concurrent_batches = []
            
            for i in range(self.concurrent_batches):
                if batch_offset >= updated_stats['pending_tasks']:
                    break
                
                batch = self.db.get_pending_tasks_batch(self.batch_size, batch_offset)
                if batch:
                    concurrent_batches.append((batch_number + i, batch))
                    batch_offset += len(batch)
            
            if not concurrent_batches:
                break
            
            print(f"\n🔥 Processing {len(concurrent_batches)} {self.scraper_name} batches concurrently...")
            
            # Process batches concurrently
            with ThreadPoolExecutor(max_workers=len(concurrent_batches)) as executor:
                future_to_batch = {executor.submit(self.process_batch_concurrent, batch_data): batch_data 
                                   for batch_data in concurrent_batches}
                
                for future in as_completed(future_to_batch):
                    try:
                        result = future.result()
                        total_created += result['created']
                        
                        if result['completed']:
                            print(f"🎉 {self.scraper_name} Batch #{result['batch_num']} completed successfully")
                        else:
                            print(f"⚠️  {self.scraper_name} Batch #{result['batch_num']} had issues")
                            
                    except Exception as e:
                        print(f"❌ {self.scraper_name} batch processing error: {e}")
            
            batch_number += len(concurrent_batches)
            time.sleep(1)  # Brief pause between concurrent batch groups
        
        # Final summary
        processing_duration = time.time() - start_time
        final_stats = self.db.get_database_stats()
        
        self.print_header(f"🎉 {self.scraper_name} High-Performance Processing Complete")
        self.db.print_stats("Final Results")
        
        print(f"\n⚡ {self.scraper_name} Performance Summary:")
        print(f"   ⏱️  Total Processing Time: {processing_duration:.1f} seconds")
        print(f"   🚀 Tasks Created: {total_created:,}")
        if processing_duration > 0:
            print(f"   💻 Processing Rate: {total_created/processing_duration:.1f} tasks/second")
        if final_stats['total_tasks'] > 0:
            print(f"   🎯 Final Success Rate: {(final_stats['completed_tasks']/final_stats['total_tasks']*100):.1f}%")
    
    def run(self):
        """Run the task creator with signal handling and continuous mode support"""
        def signal_handler(signum, frame):
            self.running = False
            print("\n🛑 Shutdown signal received, will exit after current cycle...")
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        continuous_mode = os.environ.get('CONTINUOUS_MODE', 'false').lower() == 'true'
        check_interval = int(os.environ.get('CHECK_INTERVAL', '60'))
        
        if continuous_mode:
            print("=" * 60)
            print(f"🔄 CONTINUOUS MODE ENABLED")
            print(f"   Scraper: {self.scraper_name}")
            print(f"   Check interval: {check_interval} seconds")
            print(f"   Press Ctrl+C or click STOP to exit")
            print("=" * 60)
            
            cycle_count = 0
            while self.running:
                try:
                    cycle_count += 1
                    print(f"\n{'='*60}")
                    print(f"⏰ Cycle #{cycle_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    print(f"{'='*60}")
                    
                    stats = self.db.get_database_stats()
                    print(f"📊 Current status: {stats['pending_tasks']:,} pending, {stats['completed_tasks']:,} completed")
                    
                    if stats['pending_tasks'] > 0:
                        self.process_tasks()
                    else:
                        print("📭 No pending tasks found")
                    
                    if not self.running:
                        break
                    
                    print(f"\n✅ Cycle #{cycle_count} complete")
                    print(f"   Waiting {check_interval} seconds before next check...")
                    
                    for _ in range(check_interval):
                        if not self.running:
                            break
                        time.sleep(1)
                        
                except KeyboardInterrupt:
                    print("\n🛑 Stopped by user")
                    break
                except Exception as e:
                    print(f"\n❌ Error in cycle #{cycle_count}: {e}")
                    if not self.running:
                        break
                    print(f"   Will retry in {check_interval} seconds...")
                    for _ in range(check_interval):
                        if not self.running:
                            break
                        time.sleep(1)
            
            print("\n👋 Task creator stopped gracefully")
        else:
            # Single-run mode
            try:
                stats = self.db.get_database_stats()
                print(f"📊 Current status: {stats['pending_tasks']:,} pending, {stats['completed_tasks']:,} completed")
                print(f"🖥️  Server specs: {multiprocessing.cpu_count()} CPU cores detected")
                
                if stats['pending_tasks'] > 0:
                    print(f"\n🏃 SINGLE-RUN MODE")
                    self.process_tasks()
                else:
                    print(f"🎉 All {self.scraper_name} tasks completed successfully!")
            except Exception as e:
                print(f"❌ {self.scraper_name} Error: {e}")
                import traceback
                traceback.print_exc()
