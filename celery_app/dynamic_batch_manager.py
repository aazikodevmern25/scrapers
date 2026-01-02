import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
from collections import deque
import sqlite3
from pathlib import Path
import json

@dataclass
class TaskInfo:
    """Information about a task"""
    db_id: int
    task_id: Optional[str] = None
    payload: Optional[str] = None
    status: str = 'PENDING'
    created_at: Optional[float] = None
    completed_at: Optional[float] = None
    retry_count: int = 0

@dataclass
class BatchConfig:
    """Configuration for dynamic batching"""
    initial_batch_size: int = 50
    max_active_tasks: int = 25
    replacement_threshold: int = 2  # Create new tasks when this many complete
    status_check_interval: float = 5.0  # seconds
    max_workers: int = 5
    status_check_workers: int = 10

class DynamicBatchManager:
    """
    Dynamic batch manager that maintains a rolling window of active tasks.
    When tasks complete/fail, immediately creates new ones to maintain optimal throughput.
    """
    
    def __init__(self, 
                 config: BatchConfig,
                 task_creator_func: Callable,
                 status_checker_func: Callable,
                 get_pending_tasks_func: Callable,
                 update_status_func: Callable,
                 name: str = "DynamicBatch"):
        
        self.config = config
        self.task_creator_func = task_creator_func
        self.status_checker_func = status_checker_func
        self.get_pending_tasks_func = get_pending_tasks_func
        self.update_status_func = update_status_func
        self.name = name
        
        # Task tracking
        self.active_tasks: Dict[str, TaskInfo] = {}
        self.pending_queue: deque = deque()
        self.completed_tasks: List[TaskInfo] = []
        self.failed_tasks: List[TaskInfo] = []
        
        # Thread control
        self.running = False
        self.lock = threading.RLock()
        self.monitor_thread = None
        
        # Statistics
        self.stats = {
            'total_created': 0,
            'total_completed': 0,
            'total_failed': 0,
            'batches_processed': 0,
            'start_time': None
        }

    def load_pending_tasks(self) -> int:
        """Load pending tasks from database into the queue"""
        with self.lock:
            pending_tasks = self.get_pending_tasks_func()
            # pending_tasks is now a list of tuples: (id, endpoint, payload_json, task_id, status, retry_count)
            for task_tuple in pending_tasks:
                task_info = TaskInfo(
                    db_id=task_tuple[0],  # id
                    payload=task_tuple,   # pass the full tuple to create_single_task
                    status='QUEUED'
                )
                self.pending_queue.append(task_info)
            
            loaded_count = len(pending_tasks)
            print(f"📋 {self.name}: Loaded {loaded_count} pending tasks into queue")
            return loaded_count

    def create_tasks_batch(self, count: int) -> List[TaskInfo]:
        """Create a batch of tasks up to the specified count"""
        if count <= 0:
            return []
        
        tasks_to_create = []
        with self.lock:
            # Get tasks from pending queue
            for _ in range(min(count, len(self.pending_queue))):
                if self.pending_queue:
                    tasks_to_create.append(self.pending_queue.popleft())
        
        if not tasks_to_create:
            return []
        
        print(f"🚀 {self.name}: Creating batch of {len(tasks_to_create)} tasks...")
        
        # Create tasks concurrently
        created_tasks = []
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            future_to_task = {
                executor.submit(self.task_creator_func, task.payload): task 
                for task in tasks_to_create
            }
            
            for future in as_completed(future_to_task):
                task_info = future_to_task[future]
                try:
                    result = future.result()
                    
                    # Existing task creators return {'success': True/False, 'task_id': ..., 'db_id': ...}
                    if result and result.get('success'):
                        task_info.task_id = result.get('task_id')
                        task_info.status = 'ACTIVE'
                        task_info.created_at = time.time()
                        created_tasks.append(task_info)
                        self.stats['total_created'] += 1
                        
                    else:  # failed
                        task_info.status = 'FAILED'
                        task_info.retry_count += 1
                        self.failed_tasks.append(task_info)
                        self.stats['total_failed'] += 1
                        error_msg = result.get('error', 'Unknown error') if result else 'No result'
                        print(f"❌ {self.name}: Task creation failed: {error_msg}")
                        
                except Exception as e:
                    print(f"❌ {self.name}: Task creation error: {e}")
                    task_info.status = 'FAILED'
                    task_info.retry_count += 1
                    self.failed_tasks.append(task_info)
                    self.stats['total_failed'] += 1
        
        # Add successfully created tasks to active tracking
        with self.lock:
            for task in created_tasks:
                if task.task_id:
                    self.active_tasks[task.task_id] = task
        
        print(f"✅ {self.name}: Created {len(created_tasks)} active tasks")
        return created_tasks

    def check_active_tasks_status(self) -> int:
        """Check status of all active tasks and move completed ones"""
        if not self.active_tasks:
            return 0
        
        with self.lock:
            task_ids = list(self.active_tasks.keys())
        
        if not task_ids:
            return 0
        
        # Batch status check
        try:
            status_results = self.status_checker_func(task_ids)
        except Exception as e:
            print(f"❌ {self.name}: Status check error: {e}")
            return 0
        
        completed_count = 0
        with self.lock:
            for task_id, api_status in status_results.items():
                if task_id not in self.active_tasks:
                    continue
                    
                task_info = self.active_tasks[task_id]
                
                if api_status == 'SUCCESS':
                    task_info.status = 'SUCCESS'
                    task_info.completed_at = time.time()
                    self.update_status_func(task_info.db_id, status='SUCCESS')
                    self.completed_tasks.append(task_info)
                    del self.active_tasks[task_id]
                    completed_count += 1
                    self.stats['total_completed'] += 1
                    
                elif api_status in ['FAILED', 'FAILURE', 'ERROR']:
                    task_info.status = 'FAILED'
                    task_info.completed_at = time.time()
                    self.update_status_func(task_info.db_id, status='FAILED')
                    self.failed_tasks.append(task_info)
                    del self.active_tasks[task_id]
                    completed_count += 1
                    self.stats['total_failed'] += 1
                    if api_status == 'ERROR':
                        print(f"⚠️  {self.name}: Task {task_id} reported ERROR status – marking as FAILED")
                    
                elif api_status == 'RUNNING':
                    # Task is actively running - keep in active pool and continue monitoring
                    task_info.status = 'RUNNING'
                    self.update_status_func(task_info.db_id, status='RUNNING')
                    # Don't remove from active_tasks, don't increment completed_count
                    
                elif api_status in ['PENDING', 'RETRY']:
                    # Task is still pending or retrying - keep monitoring
                    task_info.status = api_status
                    # Don't remove from active_tasks, don't increment completed_count
                else:
                    # Unknown status responses should not block progress – treat as failure
                    print(f"⚠️  {self.name}: Task {task_id} returned unknown status '{api_status}', marking as FAILED")
                    task_info.status = 'FAILED'
                    task_info.completed_at = time.time()
                    self.update_status_func(task_info.db_id, status='FAILED')
                    self.failed_tasks.append(task_info)
                    del self.active_tasks[task_id]
                    completed_count += 1
                    self.stats['total_failed'] += 1
        
        return completed_count

    def get_current_stats(self) -> Dict[str, Any]:
        """Get current statistics"""
        with self.lock:
            current_time = time.time()
            runtime = current_time - self.stats['start_time'] if self.stats['start_time'] else 0
            
            return {
                'active_tasks': len(self.active_tasks),
                'pending_queue': len(self.pending_queue),
                'completed': len(self.completed_tasks),
                'failed': len(self.failed_tasks),
                'total_created': self.stats['total_created'],
                'total_completed': self.stats['total_completed'],
                'total_failed': self.stats['total_failed'],
                'runtime_seconds': runtime,
                'throughput': self.stats['total_completed'] / runtime if runtime > 0 else 0
            }

    def print_status(self):
        """Print current status"""
        stats = self.get_current_stats()
        print(f"\r🔄 {self.name}: Active: {stats['active_tasks']} | "
              f"Queue: {stats['pending_queue']} | "
              f"✅ {stats['completed']} | "
              f"❌ {stats['failed']} | "
              f"Rate: {stats['throughput']:.1f}/min", end="", flush=True)

    def monitor_and_refill(self):
        """Monitor active tasks and refill as needed"""
        last_status_print = 0
        
        while self.running:
            try:
                # Check status of active tasks
                completed_count = self.check_active_tasks_status()
                
                # Determine if we need to create new tasks
                with self.lock:
                    active_count = len(self.active_tasks)
                    pending_count = len(self.pending_queue)
                    can_create = self.config.max_active_tasks - active_count
                
                # Create new tasks if:
                # 1. We have completed >= replacement_threshold tasks, OR
                # 2. Active tasks < initial_batch_size and we have pending tasks
                should_create_count = 0
                
                if completed_count >= self.config.replacement_threshold:
                    # Replace completed tasks
                    should_create_count = min(completed_count, can_create, pending_count)
                elif active_count < self.config.initial_batch_size and pending_count > 0:
                    # Fill up to initial batch size
                    should_create_count = min(
                        self.config.initial_batch_size - active_count,
                        can_create,
                        pending_count
                    )
                
                if should_create_count > 0:
                    print(f"\n🔄 {self.name}: Creating {should_create_count} new tasks "
                          f"(completed: {completed_count}, active: {active_count})")
                    self.create_tasks_batch(should_create_count)
                
                # Print status periodically
                current_time = time.time()
                if current_time - last_status_print >= 2.0:  # Every 2 seconds
                    self.print_status()
                    last_status_print = current_time
                
                # Check if we're done
                with self.lock:
                    if len(self.active_tasks) == 0 and len(self.pending_queue) == 0:
                        print(f"\n✅ {self.name}: All tasks completed!")
                        self.running = False
                        break
                
                time.sleep(self.config.status_check_interval)
                
            except Exception as e:
                print(f"\n❌ {self.name}: Monitor error: {e}")
                time.sleep(self.config.status_check_interval)

    def start_processing(self) -> Dict[str, Any]:
        """Start the dynamic batch processing"""
        if self.running:
            raise RuntimeError("Dynamic batch manager is already running")
        
        print(f"🚀 Starting {self.name} Dynamic Batch Manager")
        print(f"📊 Config: Initial batch: {self.config.initial_batch_size}, "
              f"Max active: {self.config.max_active_tasks}, "
              f"Replacement threshold: {self.config.replacement_threshold}")
        
        self.stats['start_time'] = time.time()
        self.running = True
        
        # Load pending tasks
        pending_count = self.load_pending_tasks()
        if pending_count == 0:
            print(f"🎉 {self.name}: No pending tasks to process!")
            return self.get_current_stats()
        
        # Create initial batch
        initial_count = min(self.config.initial_batch_size, pending_count, self.config.max_active_tasks)
        print(f"🔥 {self.name}: Creating initial batch of {initial_count} tasks...")
        self.create_tasks_batch(initial_count)
        
        # Start monitoring thread
        self.monitor_thread = threading.Thread(target=self.monitor_and_refill, daemon=True)
        self.monitor_thread.start()
        
        # Wait for completion
        try:
            while self.running and self.monitor_thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            print(f"\n⏹️ {self.name}: Stopping due to keyboard interrupt...")
            self.running = False
        
        # Wait for monitor thread to finish
        if self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=10)
        
        # Final statistics
        final_stats = self.get_current_stats()
        print(f"\n🎉 {self.name} Processing Complete!")
        print(f"📊 Final Stats: Created: {final_stats['total_created']}, "
              f"Completed: {final_stats['completed']}, "
              f"Failed: {final_stats['failed']}")
        print(f"⚡ Throughput: {final_stats['throughput']:.1f} tasks/minute")
        
        return final_stats

    def stop(self):
        """Stop the dynamic batch manager"""
        self.running = False


# Example integration function for existing task creators
def create_dynamic_batch_processor(db_path: str, 
                                   task_creator_func: Callable,
                                   status_checker_func: Callable,
                                   update_status_func: Callable,
                                   name: str = "DynamicBatch",
                                   config: Optional[BatchConfig] = None,
                                   use_celery_status: bool = True) -> DynamicBatchManager:
    """
    Create a dynamic batch processor for existing task creators
    
    Args:
        db_path: Path to SQLite database
        task_creator_func: Function to create single task (payload_json) -> result
        status_checker_func: Function to check task status (task_ids_list) -> status_dict  
        update_status_func: Function to update task status (db_id, status)
        name: Name for logging
        config: Batch configuration
        use_celery_status: Whether to use Celery status checking (default: True)
    """
    
    if config is None:
        config = BatchConfig()
    
    def get_pending_tasks():
        """Get pending tasks from database - excluding FAILED tasks to prevent retries"""
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("""
            SELECT id, endpoint, payload_json, task_id, status, retry_count 
            FROM tasks 
            WHERE (task_id = '' OR task_id IS NULL OR status NOT IN ('SUCCESS', 'FAILED')) 
            AND (retry_count IS NULL OR retry_count < 3)
            AND status NOT IN ('FAILED')
            ORDER BY id
        """)
        tasks = cursor.fetchall()  # Return as tuples, same as existing get_pending_tasks_batch
        conn.close()
        return tasks
    
    # Use Celery status checking if enabled
    actual_status_checker = status_checker_func
    if use_celery_status:
        try:
            from celery_status_checker import batch_celery_status_check
            actual_status_checker = batch_celery_status_check
            print(f"✅ {name}: Using Celery status checking")
        except ImportError:
            print(f"⚠️  {name}: Celery status checker not available, using HTTP fallback")
    
    return DynamicBatchManager(
        config=config,
        task_creator_func=task_creator_func,
        status_checker_func=actual_status_checker,
        get_pending_tasks_func=get_pending_tasks,
        update_status_func=update_status_func,
        name=name
    ) 