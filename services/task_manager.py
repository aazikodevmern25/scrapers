#!/usr/bin/env python3
"""
Task Manager - Web-based replacement for PM2 task creators
Provides start/pause controls and task creation limits
"""

import subprocess
import json
import time
import threading
import os
from pathlib import Path
from datetime import datetime
import psutil
import logging

# Import Celery app for task control
try:
    from celery_app.tasks import app as celery_app
except ImportError:
    celery_app = None
    print("Warning: Could not import Celery app - task revocation will not be available")

# Set up logger
logger = logging.getLogger(__name__)

class TaskManager:
    def __init__(self):
        # Get the absolute path to data-extractor directory
        self.service_dir = Path(__file__).parent.absolute()
        self.data_extractor_dir = self.service_dir.parent
        
        # Scraper to Celery queue mapping
        self.SCRAPER_QUEUE_MAPPING = {
            'comparemarket': 'macmap_compare',
            'competitors': 'macmap_competitors',
            'eximpedia': 'eximpedia',
            'fulltariff': 'tariff_full',
            'indiantradeportal': 'indian_trade_portal',
            'macmapproduct': 'macmap_products',
            'macmapregulatory': 'macmap_regulatory',
            'macmaptariff': 'macmap_tariff',
            'trademap': 'trademap',
            'traderemedies': 'macmap_trade_remedies',
            'portscraper': 'port_scraper',
            'indiamart_products': 'indiamart',
            'indiamart_categories': 'indiamart'
        }
        
        self.task_creators = {
            'comparemarket': {
                'name': 'CompareMarket',
                'script': './scrapers/macmap/comparemarket/comparemarketTaskCreator.py',
                'status': 'stopped',
                'process': None,
                'task_limit': 50,
                'current_tasks': 0,
                'total_created': 0,
                'worker_concurrency': 6,
                'worker_name': 'comparemarket_worker',
                'worker_process': None,
                'worker_status': 'stopped',
                'queue_name': 'macmap_compare'
            },
            'competitors': {
                'name': 'Competitors',
                'script': './scrapers/macmap/competitors/competitorsTaskCreator.py',
                'status': 'stopped',
                'process': None,
                'task_limit': 50,
                'current_tasks': 0,
                'total_created': 0,
                'worker_concurrency': 6,
                'worker_name': 'competitors_worker',
                'worker_process': None,
                'worker_status': 'stopped',
                'queue_name': 'macmap_competitors'
            },
            'eximpedia': {
                'name': 'EximPedia',
                'script': './scrapers/eximpedia/eximPediaTaskCreator.py',
                'status': 'stopped',
                'process': None,
                'task_limit': 50,
                'current_tasks': 0,
                'total_created': 0,
                'worker_concurrency': 2,
                'worker_name': 'eximpedia_worker',
                'worker_process': None,
                'worker_status': 'stopped',
                'queue_name': 'eximpedia'
            },
            'fulltariff': {
                'name': 'FullTariff',
                'script': './scrapers/macmap/fulltariff/fulltariffTaskCreator.py',
                'status': 'stopped',
                'process': None,
                'task_limit': 50,
                'current_tasks': 0,
                'total_created': 0,
                'worker_concurrency': 2,
                'worker_name': 'fulltariff_worker',
                'worker_process': None,
                'worker_status': 'stopped',
                'queue_name': 'tariff_full'
            },
            'indiantradeportal': {
                'name': 'IndianTradePortal',
                'script': './scrapers/indiantradeportal/indiantradeportalTaskCreator.py',
                'status': 'stopped',
                'process': None,
                'task_limit': 50,
                'current_tasks': 0,
                'total_created': 0,
                'worker_concurrency': 4,
                'worker_name': 'indiantradeportal_worker',
                'worker_process': None,
                'worker_status': 'stopped',
                'queue_name': 'indian_trade_portal'
            },
            'macmapproduct': {
                'name': 'MacMapProduct',
                'script': './scrapers/macmap/product/macmapproductTaskCreator.py',
                'status': 'stopped',
                'process': None,
                'task_limit': 50,
                'current_tasks': 0,
                'total_created': 0,
                'worker_concurrency': 6,
                'worker_name': 'macmapproduct_worker',
                'worker_process': None,
                'worker_status': 'stopped',
                'queue_name': 'macmap_products'
            },
            'macmapregulatory': {
                'name': 'MacMapRegulatory',
                'script': './scrapers/macmap/regulatory/macmapregulatoryTaskCreator.py',
                'status': 'stopped',
                'process': None,
                'task_limit': 50,
                'current_tasks': 0,
                'total_created': 0,
                'worker_concurrency': 6,
                'worker_name': 'macmapregulatory_worker',
                'worker_process': None,
                'worker_status': 'stopped',
                'queue_name': 'macmap_regulatory'
            },
            'macmaptariff': {
                'name': 'MacMapTariff',
                'script': './scrapers/macmap/tariff/macmapTariffTaskCreator.py',
                'status': 'stopped',
                'process': None,
                'task_limit': 50,
                'current_tasks': 0,
                'total_created': 0,
                'worker_concurrency': 6,
                'worker_name': 'macmaptariff_worker',
                'worker_process': None,
                'worker_status': 'stopped',
                'queue_name': 'macmap_tariff'
            },
            'trademap': {
                'name': 'TradeMap',
                'script': './scrapers/trademap/tradeMapTaskCreator.py',
                'status': 'stopped',
                'process': None,
                'task_limit': 50,
                'current_tasks': 0,
                'total_created': 0,
                'worker_concurrency': 4,
                'worker_name': 'trademap_worker',
                'worker_process': None,
                'worker_status': 'stopped',
                'queue_name': 'trademap'
            },
            'traderemedies': {
                'name': 'TradeRemedies',
                'script': './scrapers/macmap/traderemedies/tradeRemediesTaskCreator.py',
                'status': 'stopped',
                'process': None,
                'task_limit': 50,
                'current_tasks': 0,
                'total_created': 0,
                'worker_concurrency': 6,
                'worker_name': 'traderemedies_worker',
                'worker_process': None,
                'worker_status': 'stopped',
                'queue_name': 'macmap_trade_remedies'
            },
            'portscraper': {
                'name': 'PortScraper',
                'script': './scrapers/port_scraper/portScraperTaskCreator.py',
                'status': 'stopped',
                'process': None,
                'task_limit': 50,
                'current_tasks': 0,
                'total_created': 0,
                'worker_concurrency': 1,
                'worker_name': 'portscraper_worker',
                'worker_process': None,
                'worker_status': 'stopped',
                'queue_name': 'port_scraper'
            },
            'indiamart_products': {
                'name': 'IndiaMartProducts',
                'script': './scrapers/indiamart/indiamart_scraper.py',
                'status': 'stopped',
                'process': None,
                'task_limit': 100,
                'current_tasks': 0,
                'total_created': 0,
                'worker_concurrency': 1,
                'worker_name': 'indiamart_products_worker',
                'worker_process': None,
                'worker_status': 'stopped',
                'queue_name': 'indiamart'
            },
            'indiamart_categories': {
                'name': 'IndiaMartCategories',
                'script': './scrapers/indiamart/indiamart_category_crawler.py',
                'status': 'stopped',
                'process': None,
                'task_limit': 50,
                'current_tasks': 0,
                'total_created': 0,
                'worker_concurrency': 1,
                'worker_name': 'indiamart_categories_worker',
                'worker_process': None,
                'worker_status': 'stopped',
                'queue_name': 'indiamart'
            }
        }
        
        self.monitor_thread = None
        self.monitoring = False
        
    def start_monitoring(self):
        """Start the monitoring thread"""
        if not self.monitoring:
            self.monitoring = True
            self.monitor_thread = threading.Thread(target=self._monitor_tasks, daemon=True)
            self.monitor_thread.start()
    
    def stop_monitoring(self):
        """Stop the monitoring thread"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join()
    
    def _monitor_tasks(self):
        """Monitor task creators and update statistics"""
        while self.monitoring:
            for creator_id, creator in self.task_creators.items():
                # Always update task counts from database
                self._update_task_counts(creator_id)
                
                # Check task creator process status
                if creator['process']:
                    if creator['process'].poll() is not None:
                        # Process has terminated
                        creator['status'] = 'stopped'
                        creator['process'] = None
                        # Clean up any orphaned tracking since we had a managed process
                        if hasattr(creator, 'orphaned_pid'):
                            del creator['orphaned_pid']
                        if hasattr(creator, '_orphaned_logged'):
                            del creator['_orphaned_logged']
                        print(f"🔄 {creator['name']} task creator process terminated")
                    else:
                        # Process is still running - mark as running and clear orphaned status
                        creator['status'] = 'running'
                        # Clear orphaned tracking since we have a managed process
                        if hasattr(creator, 'orphaned_pid'):
                            del creator['orphaned_pid']
                        if hasattr(creator, '_orphaned_logged'):
                            del creator['_orphaned_logged']
                else:
                    # No process tracked, check if one is running by script name
                    script_name = os.path.basename(creator['script'])
                    try:
                        # Check if process is running by script name
                        import psutil
                        found_process = None
                        for proc in psutil.process_iter(['pid', 'cmdline']):
                            try:
                                cmdline = proc.info['cmdline']
                                if cmdline and len(cmdline) > 1 and script_name in cmdline[-1]:
                                    found_process = proc
                                    break
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                continue
                        
                        if found_process:
                            # Found orphaned process, attach to it for management
                            creator['status'] = 'running'
                            creator['orphaned_pid'] = found_process.pid
                            # Only print once when first discovered
                            if not hasattr(creator, '_orphaned_logged'):
                                print(f"🔍 Found orphaned {creator['name']} task creator process (PID: {found_process.pid})")
                                creator['_orphaned_logged'] = True
                        else:
                            creator['status'] = 'stopped'
                            if hasattr(creator, 'orphaned_pid'):
                                del creator['orphaned_pid']
                            if hasattr(creator, '_orphaned_logged'):
                                del creator['_orphaned_logged']
                                
                    except Exception as e:
                        print(f"⚠️ Error checking for orphaned task creator processes: {e}")
                
                # Check worker process status
                if creator['worker_process']:
                    if creator['worker_process'].poll() is not None:
                        # Worker process has terminated
                        creator['worker_status'] = 'stopped'
                        creator['worker_process'] = None
                        print(f"🔄 {creator['name']} worker process terminated")
                    else:
                        # Worker is still running
                        creator['worker_status'] = 'running'
                else:
                    # No worker process tracked
                    if creator['worker_status'] == 'running':
                        # Was running but process is None, mark as stopped
                        creator['worker_status'] = 'stopped'
            
            time.sleep(5)  # Update every 5 seconds
    
    def _update_task_counts(self, creator_id):
        """Update task counts from MongoDB"""
        creator = self.task_creators[creator_id]
        
        try:
            from shared.task_creator_utils.mongodb_base import get_database
            
            db = get_database()
            collection = db["scraper_tasks"]
            scraper_name = creator['name']
            
            # Aggregate stats for this scraper
            pipeline = [
                {"$match": {"scraper": scraper_name}},
                {"$group": {
                    "_id": None,
                    "total": {"$sum": 1},
                    "completed": {"$sum": {"$cond": [{"$eq": ["$status", "SUCCESS"]}, 1, 0]}},
                    "failed": {"$sum": {"$cond": [{"$eq": ["$status", "FAILED"]}, 1, 0]}},
                    "pending": {"$sum": {"$cond": [
                        {"$or": [
                            {"$eq": ["$task_id", ""]},
                            {"$and": [
                                {"$ne": ["$status", "SUCCESS"]},
                                {"$ne": ["$status", "FAILED"]},
                                {"$ne": ["$status", "PAUSED"]}
                            ]}
                        ]}, 1, 0
                    ]}}
                }}
            ]
            
            result = list(collection.aggregate(pipeline))
            if result:
                creator['total_tasks'] = result[0].get('total', 0)
                creator['total_created'] = result[0].get('total', 0)
                creator['completed_tasks'] = result[0].get('completed', 0)
                creator['failed_tasks'] = result[0].get('failed', 0)
                creator['pending_tasks'] = result[0].get('pending', 0)
                creator['current_tasks'] = result[0].get('pending', 0)
            else:
                self._reset_task_counts(creator)
                
        except Exception as e:
            print(f"❌ Error updating task counts from MongoDB for {creator_id}: {e}")
            self._reset_task_counts(creator)
    
    def _reset_task_counts(self, creator):
        """Reset all task counts to 0"""
        creator['total_tasks'] = 0
        creator['pending_tasks'] = 0
        creator['completed_tasks'] = 0
        creator['failed_tasks'] = 0
        creator['total_created'] = 0
        creator['current_tasks'] = 0
    
    def start_task_creator(self, creator_id):
        """Start a task creator - it will automatically process any pending tasks first"""
        if creator_id not in self.task_creators:
            return False, "Task creator not found"
        
        creator = self.task_creators[creator_id]
        
        # Check if already running
        if creator['status'] == 'running' and creator['process'] and creator['process'].poll() is None:
            return False, f"{creator['name']} is already running"
        
        # Note: Task creators automatically check for pending tasks first before creating new ones
        print(f"🔄 Starting {creator['name']} - will process pending tasks first, then create new ones")
        
        try:
            # Ensure log directory exists
            log_dir = self.data_extractor_dir / 'logs'
            log_dir.mkdir(parents=True, exist_ok=True)
            
            # Set environment variables for task limits
            env = os.environ.copy()
            env['MAX_CONCURRENT_TASKS'] = str(creator['task_limit'])
            # Use environment Redis URL if set, otherwise fallback to localhost for local dev
            env['CELERY_BROKER_URL'] = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
            env['CELERY_RESULT_BACKEND'] = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
            # Enable continuous mode so task creators stay alive
            env['CONTINUOUS_MODE'] = 'true'
            env['CHECK_INTERVAL'] = '60'  # Check for new tasks every 60 seconds
            # Don't set ORCHESTRATOR_MANAGED to allow task creators to run normally
            # env['ORCHESTRATOR_MANAGED'] = 'true'
            
            # Create log files
            out_log = log_dir / f"{creator_id}_task_creator.log"
            err_log = log_dir / f"{creator_id}_task_creator_error.log"
            
            # Start the process with proper logging and explicit working directory
            working_dir = str(self.data_extractor_dir)
            
            # Use virtual environment Python if available, otherwise system Python
            venv_python = os.path.join(working_dir, 'venv', 'bin', 'python3')
            if os.path.exists(venv_python):
                python_executable = venv_python
            else:
                # Use sys.executable to get the current Python interpreter path
                # This works in Docker containers and any environment
                import sys
                python_executable = sys.executable
            
            with open(out_log, 'a') as stdout_file, open(err_log, 'a') as stderr_file:
                process = subprocess.Popen(
                    [python_executable, creator['script']],
                    cwd=working_dir,
                    env=env,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    preexec_fn=os.setsid  # Create new process group
                )
                
            print(f"🔧 Started process in directory: {working_dir}")
            
            creator['process'] = process
            creator['status'] = 'running'
            
            # Start monitoring if not already started
            if not self.monitoring:
                self.start_monitoring()
            
            print(f"✅ Started {creator['name']} task creator (PID: {process.pid})")
            
            # Start dedicated worker for this scraper
            worker_success, worker_message = self._start_dedicated_worker(creator_id)
            if worker_success:
                print(f"✅ {worker_message}")
                return True, f"Started {creator['name']} task creator and dedicated worker"
            else:
                print(f"⚠️ Task creator started but worker failed: {worker_message}")
                # Task creator is still running, just worker failed
                # This allows the system to work with manually started workers
                return True, f"Started {creator['name']} task creator (Note: Automatic worker startup failed - {worker_message}. You may need to start workers manually or fix dependencies)"
            
        except Exception as e:
            print(f"❌ Failed to start {creator['name']}: {str(e)}")
            return False, f"Failed to start task creator: {str(e)}"
    
    def stop_task_creator(self, creator_id):
        """Stop a task creator and pause all its tasks"""
        # Ensure logger is accessible in this method scope
        import logging
        method_logger = logging.getLogger(__name__)
        
        if creator_id not in self.task_creators:
            return False, "Task creator not found"
        
        creator = self.task_creators[creator_id]
        
        # Check if both task creator AND worker are stopped
        task_creator_stopped = creator['status'] == 'stopped'
        worker_stopped = creator['worker_status'] == 'stopped'
        
        if task_creator_stopped and worker_stopped:
            return False, f"{creator['name']} is already stopped"
        
        # First, revoke all active Celery tasks for this scraper
        if celery_app:
            try:
                # Get active tasks from Celery
                active_tasks = celery_app.control.inspect().active()
                revoked_count = 0
                
                if active_tasks:
                    for worker, tasks in active_tasks.items():
                        for task in tasks:
                            task_name = task.get('name', '')
                            # Check if this task belongs to the scraper being paused
                            if self._is_scraper_task(task_name, creator_id):
                                task_id = task.get('id')
                                if task_id:
                                    celery_app.control.revoke(task_id, terminate=True)
                                    revoked_count += 1
                                    print(f"🚫 Revoked Celery task: {task_name} (ID: {task_id})")
                
                if revoked_count > 0:
                    print(f"⏹️  Revoked {revoked_count} active Celery tasks for {creator['name']}")
                    
            except Exception as e:
                print(f"⚠️  Error revoking Celery tasks: {e}")
        
        # Second, pause all tasks in MongoDB
        try:
            from shared.task_creator_utils.mongodb_base import get_database
            from datetime import datetime
            
            db = get_database()
            collection = db["scraper_tasks"]
            scraper_name = creator['name']
            
            # Update all PENDING and RUNNING tasks to PAUSED
            result = collection.update_many(
                {"scraper": scraper_name, "status": {"$in": ["PENDING", "RUNNING"]}},
                {"$set": {"status": "PAUSED", "updated_at": datetime.utcnow()}}
            )
            
            paused_count = result.modified_count
            print(f"⏸️  Paused {paused_count} tasks for {creator['name']}")
            
        except Exception as e:
            print(f"❌ Error pausing tasks for {creator_id}: {e}")
        
        try:
            stopped = False
            
            # Determine timeout based on script type
            timeout = 10  # Default timeout
            script_name = os.path.basename(creator['script'])
            
            # Longer timeout for IndiaMART scraper due to large CSV loading
            if 'indiamart_scraper' in script_name.lower():
                timeout = 300  # 5 minutes for IndiaMART scraper initialization
                method_logger.info(f"Using extended timeout ({timeout}s) for IndiaMART scraper")
            
            # Try to stop managed process first
            if creator['process'] and creator['process'].poll() is None:
                import signal
                os.killpg(os.getpgid(creator['process'].pid), signal.SIGTERM)
                
                try:
                    creator['process'].wait(timeout=timeout)
                    stopped = True
                except subprocess.TimeoutExpired:
                    method_logger.warning(f"Process {creator['name']} did not terminate within {timeout}s, force killing")
                    os.killpg(os.getpgid(creator['process'].pid), signal.SIGKILL)
                    creator['process'].wait()
                    stopped = True
            
            # Handle orphaned processes or find running process by script name
            else:
                import signal
                import psutil
                script_name = os.path.basename(creator['script'])
                found_process = None
                
                # First check if we have a tracked orphaned PID
                if hasattr(creator, 'orphaned_pid'):
                    try:
                        found_process = psutil.Process(creator['orphaned_pid'])
                    except psutil.NoSuchProcess:
                        # Orphaned PID no longer exists
                        if hasattr(creator, 'orphaned_pid'):
                            del creator['orphaned_pid']
                        if hasattr(creator, '_orphaned_logged'):
                            del creator['_orphaned_logged']
                
                # If no tracked orphaned process, search for running process by script name
                if not found_process:
                    try:
                        for proc in psutil.process_iter(['pid', 'cmdline']):
                            try:
                                cmdline = proc.info['cmdline']
                                if cmdline and len(cmdline) > 1 and script_name in cmdline[-1]:
                                    found_process = proc
                                    break
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                continue
                    except Exception as e:
                        print(f"⚠️ Error searching for process: {e}")
                
                # Try to terminate the found process
                if found_process:
                    try:
                        print(f"🛑 Terminating {creator['name']} process (PID: {found_process.pid})")
                        found_process.terminate()
                        
                        # Wait for termination
                        try:
                            found_process.wait(timeout=10)
                            stopped = True
                            print(f"✅ Successfully terminated {creator['name']} process")
                        except psutil.TimeoutExpired:
                            # Force kill if needed
                            print(f"⚡ Force killing {creator['name']} process")
                            found_process.kill()
                            found_process.wait()
                            stopped = True
                            
                    except psutil.NoSuchProcess:
                        # Process already terminated
                        stopped = True
                        print(f"🔄 {creator['name']} process already terminated")
                    except Exception as e:
                        print(f"❌ Error terminating {creator['name']} process: {e}")
                
                # Clean up orphaned process tracking
                if hasattr(creator, 'orphaned_pid'):
                    del creator['orphaned_pid']
                if hasattr(creator, '_orphaned_logged'):
                    del creator['_orphaned_logged']
            
            # Stop dedicated worker for this scraper
            worker_success, worker_message = self._stop_dedicated_worker(creator_id)
            if worker_success:
                print(f"✅ {worker_message}")
            else:
                print(f"⚠️ Worker stop failed: {worker_message}")
            
            # Clean up state
            creator['status'] = 'stopped'
            creator['process'] = None
            
            if stopped:
                print(f"🛑 Stopped {creator['name']} task creator")
                return True, f"Stopped {creator['name']} task creator and dedicated worker"
            else:
                return False, f"{creator['name']} was not running"
            
        except Exception as e:
            print(f"❌ Failed to stop {creator['name']}: {str(e)}")
            creator['status'] = 'stopped'
            creator['process'] = None
            # Clean up orphaned process tracking on error
            if hasattr(creator, 'orphaned_pid'):
                del creator['orphaned_pid']
            if hasattr(creator, '_orphaned_logged'):
                del creator['_orphaned_logged']
            return False, f"Failed to stop task creator: {str(e)}"
    
    def _is_scraper_task(self, task_name, creator_id):
        """Check if a Celery task belongs to a specific scraper"""
        task_mappings = {
            'macmaptariff': ['scrape_macmap_tariff'],
            'traderemedies': ['scrape_macmap_trade_remedies'],
            'regulatory': ['scrape_macmap_regulatory_requirements'],
            'comparemarket': ['scrape_macmap_compare_market'],
            'competitors': ['scrape_macmap_competitors'],
            'macmapproduct': ['scrape_macmap_products'],
            'fulltariff': ['scrape_tariff_full'],
            'indiantradeportal': ['scrape_indian_trade_portal'],
            'trademap': ['trademap_scraper_task'],
            'eximpedia': ['eximpedia_scraper_task', 'eximpedia_batch_scraper_task'],
            'portscraper': ['port_scraper_start_fresh_task', 'port_scraper_resume_task', 
                           'port_scraper_update_existing_task', 'port_scraper_get_statistics_task'],
            'indiamart': ['indiamart_product_scraper_task', 'indiamart_category_crawler_task']
        }
        
        scraper_tasks = task_mappings.get(creator_id, [])
        return any(task in task_name for task in scraper_tasks)
    
    def set_task_limit(self, creator_id, limit):
        """Set task creation limit for a creator"""
        if creator_id not in self.task_creators:
            return False, "Task creator not found"
        
        try:
            limit = int(limit)
            if limit < 1 or limit > 1000:
                return False, "Task limit must be between 1 and 1000"
            
            self.task_creators[creator_id]['task_limit'] = limit
            return True, f"Set task limit to {limit} for {self.task_creators[creator_id]['name']}"
            
        except ValueError:
            return False, "Invalid task limit value"
    
    def get_status(self):
        """Get status of all task creators"""
        # First, detect running IndiaMART workers that may have been started externally
        self._detect_external_indiamart_workers()
        
        status = {}
        for creator_id, creator in self.task_creators.items():
            self._update_task_counts(creator_id)
            
            status[creator_id] = {
                'name': creator['name'],
                'status': creator['status'],
                'total_tasks': creator.get('total_tasks', 0),
                'pending_tasks': creator.get('pending_tasks', 0),
                'completed_tasks': creator.get('completed_tasks', 0),
                'failed_tasks': creator.get('failed_tasks', 0),
                'current_tasks': creator['current_tasks'],
                'total_created': creator['total_created'],
                'cpu_usage': 0,
                'memory_usage': 0,
                'worker_status': creator['worker_status'],
                'worker_concurrency': creator['worker_concurrency'],
                'worker_pid': creator['worker_process'].pid if creator['worker_process'] and creator['worker_process'].poll() is None else None,
                'worker_queue': creator['queue_name'],
                'worker_cpu_usage': 0,
                'worker_memory_usage': 0
            }
            
            # Get process stats if running
            if creator['status'] == 'running':
                try:
                    if creator['process']:
                        # Managed process
                        proc = psutil.Process(creator['process'].pid)
                        status[creator_id]['cpu_usage'] = proc.cpu_percent()
                        status[creator_id]['memory_usage'] = proc.memory_info().rss / 1024 / 1024  # MB
                    elif hasattr(creator, 'orphaned_pid'):
                        # Orphaned process
                        proc = psutil.Process(creator['orphaned_pid'])
                        status[creator_id]['cpu_usage'] = proc.cpu_percent()
                        status[creator_id]['memory_usage'] = proc.memory_info().rss / 1024 / 1024  # MB
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    # Process no longer exists or access denied
                    status[creator_id]['cpu_usage'] = 0
                    status[creator_id]['memory_usage'] = 0
            
            # Get worker process stats if running
            if creator['worker_status'] == 'running' and creator['worker_process'] and creator['worker_process'].poll() is None:
                try:
                    worker_proc = psutil.Process(creator['worker_process'].pid)
                    status[creator_id]['worker_cpu_usage'] = worker_proc.cpu_percent()
                    status[creator_id]['worker_memory_usage'] = worker_proc.memory_info().rss / 1024 / 1024  # MB
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    # Worker process no longer exists or access denied
                    status[creator_id]['worker_cpu_usage'] = 0
                    status[creator_id]['worker_memory_usage'] = 0
        
        return status
    
    def _detect_external_indiamart_workers(self):
        """Detect IndiaMART workers that were started externally (not by task_manager)"""
        try:
            import subprocess
            
            # Check for categories worker
            result_categories = subprocess.run(
                ['pgrep', '-f', 'celery.*indiamart_categories_worker'],
                capture_output=True,
                text=True
            )
            categories_worker_running = bool(result_categories.stdout.strip())
            
            # Check for products worker
            result_products = subprocess.run(
                ['pgrep', '-f', 'celery.*indiamart_products_worker'],
                capture_output=True,
                text=True
            )
            products_worker_running = bool(result_products.stdout.strip())
            
            # Update status for categories scraper
            if 'indiamart_categories' in self.task_creators:
                if categories_worker_running:
                    self.task_creators['indiamart_categories']['worker_status'] = 'running'
                else:
                    if not self.task_creators['indiamart_categories']['worker_process']:
                        self.task_creators['indiamart_categories']['worker_status'] = 'stopped'
            
            # Update status for products scraper
            if 'indiamart_products' in self.task_creators:
                if products_worker_running:
                    self.task_creators['indiamart_products']['worker_status'] = 'running'
                else:
                    if not self.task_creators['indiamart_products']['worker_process']:
                        self.task_creators['indiamart_products']['worker_status'] = 'stopped'
                        
        except Exception as e:
            logger.debug(f"Error detecting external IndiaMART workers: {e}")
    
    def get_system_stats(self):
        """Get overall system statistics"""
        total_running = sum(1 for c in self.task_creators.values() if c['status'] == 'running')
        total_tasks = sum(c['current_tasks'] for c in self.task_creators.values())
        total_created = sum(c['total_created'] for c in self.task_creators.values())
        
        return {
            'total_creators': len(self.task_creators),
            'running_creators': total_running,
            'total_pending_tasks': total_tasks,
            'total_created_tasks': total_created,
            'system_cpu': psutil.cpu_percent(),
            'system_memory': psutil.virtual_memory().percent
        }
    
    def _get_worker_command(self, creator_id):
        """Build celery worker command for a specific scraper"""
        if creator_id not in self.task_creators:
            return None
        
        creator = self.task_creators[creator_id]
        queue_name = creator['queue_name']
        concurrency = creator['worker_concurrency']
        worker_name = creator['worker_name']
        
        # Use venv's celery if available, otherwise use system celery
        venv_celery = "./venv/bin/celery"
        if os.path.exists(venv_celery):
            celery_executable = venv_celery
        else:
            # In Docker or system-wide installation, use 'celery' from PATH
            celery_executable = "celery"
        
        cmd = [
            celery_executable, "-A", "celery_app.tasks", "worker",
            "--loglevel", "info",
            "--concurrency", str(concurrency),
            "-Q", queue_name,
            "--hostname", f"{worker_name}@%h",
            "--max-tasks-per-child", "50",
            "--prefetch-multiplier", "1"
        ]
        
        return cmd
    
    def _start_dedicated_worker(self, creator_id):
        """Start a dedicated Celery worker for a specific scraper"""
        if creator_id not in self.task_creators:
            return False, f"Scraper {creator_id} not found"
        
        creator = self.task_creators[creator_id]
        
        # Check if worker is already running
        if creator['worker_process'] and creator['worker_process'].poll() is None:
            return False, f"Worker for {creator['name']} is already running"
        
        try:
            cmd = self._get_worker_command(creator_id)
            if not cmd:
                return False, f"Failed to build worker command for {creator_id}"
            
            # Ensure log directory exists
            log_dir = self.data_extractor_dir / 'logs'
            log_dir.mkdir(parents=True, exist_ok=True)
            
            # Create worker log files
            worker_out_log = log_dir / f"{creator_id}_worker.log"
            worker_err_log = log_dir / f"{creator_id}_worker_error.log"
            
            # Start the worker process with logging
            with open(worker_out_log, 'a') as stdout_file, open(worker_err_log, 'a') as stderr_file:
                process = subprocess.Popen(
                    cmd,
                    cwd=str(self.data_extractor_dir),
                    stdout=stdout_file,
                    stderr=stderr_file,
                    start_new_session=True
                )
            
            # Give the process a moment to start
            time.sleep(0.5)
            
            # Check if the process is still running
            if process.poll() is not None:
                # Process died immediately
                error_msg = f"Worker process died immediately after start"
                print(f"❌ {error_msg} for {creator['name']}")
                # Try to read error log
                try:
                    with open(worker_err_log, 'r') as f:
                        error_output = f.read()
                        if error_output:
                            print(f"Error output: {error_output[-500:]}")  # Last 500 chars
                except:
                    pass
                return False, error_msg
            
            creator['worker_process'] = process
            creator['worker_status'] = 'running'
            
            print(f"✅ Started dedicated worker for {creator['name']} (PID: {process.pid})")
            print(f"   Worker logs: {worker_out_log}")
            return True, f"Started dedicated worker for {creator['name']} (PID: {process.pid})"
            
        except Exception as e:
            print(f"❌ Failed to start worker for {creator['name']}: {str(e)}")
            import traceback
            traceback.print_exc()
            return False, f"Failed to start worker: {str(e)}"
    
    def _stop_dedicated_worker(self, creator_id):
        """Stop the dedicated Celery worker for a specific scraper"""
        if creator_id not in self.task_creators:
            return False, f"Scraper {creator_id} not found"
        
        creator = self.task_creators[creator_id]
        worker_name = creator['worker_name']
        
        # Always try to kill worker processes by name, even if we don't have a process reference
        # This handles orphaned workers that the task manager lost track of
        try:
            # First, try to kill any workers matching this name
            result = subprocess.run(['pkill', '-TERM', '-f', worker_name], capture_output=True)
            
            # Wait a moment for graceful shutdown
            time.sleep(2)
            
            # Force kill any remaining processes
            subprocess.run(['pkill', '-KILL', '-f', worker_name], capture_output=True, check=False)
            
            print(f"✅ Killed all worker processes for {creator['name']}")
        except Exception as e:
            print(f"⚠️ Error killing worker processes: {e}")
        
        # If we have a process reference, also try to stop it properly
        if creator['worker_process'] and creator['worker_process'].poll() is None:
            try:
                process = creator['worker_process']
                pid = process.pid
                
                # Additional cleanup for process reference
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except:
                    pass
            except Exception as e:
                print(f"⚠️ Error stopping process reference: {e}")
        
        # Always clean up state
        creator['worker_process'] = None
        creator['worker_status'] = 'stopped'
        
        print(f"🛑 Stopped dedicated worker for {creator['name']}")
        return True, f"Stopped dedicated worker for {creator['name']}"
    
    def set_worker_concurrency(self, creator_id, concurrency):
        """Set worker concurrency for a specific scraper"""
        if creator_id not in self.task_creators:
            return False, f"Scraper {creator_id} not found"
        
        try:
            concurrency = int(concurrency)
            if concurrency < 1 or concurrency > 20:
                return False, "Concurrency must be between 1 and 20"
            
            creator = self.task_creators[creator_id]
            old_concurrency = creator['worker_concurrency']
            creator['worker_concurrency'] = concurrency
            
            # If worker is running, restart it with new concurrency
            if creator['worker_status'] == 'running':
                print(f"🔄 Restarting worker for {creator['name']} with new concurrency: {concurrency}")
                self._stop_dedicated_worker(creator_id)
                time.sleep(2)  # Wait for graceful shutdown
                self._start_dedicated_worker(creator_id)
                return True, f"Updated concurrency from {old_concurrency} to {concurrency} and restarted worker"
            else:
                return True, f"Updated concurrency from {old_concurrency} to {concurrency} (will apply on next start)"
                
        except ValueError:
            return False, "Invalid concurrency value"

# Global task manager instance
task_manager = TaskManager()
