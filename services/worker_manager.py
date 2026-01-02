#!/usr/bin/env python3
"""
Celery Worker Manager - Dedicated Worker Assignment System
Allows assigning specific Celery workers to particular scrapers using queue-based routing
"""

import os
import sys
import json
import subprocess
import signal
import time
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path

# Configure logging
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"worker_manager_{datetime.now().strftime('%Y%m%d')}.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('worker_manager')

# Worker configuration file
WORKER_CONFIG_FILE = "worker_assignments.json"

# Default scraper-to-queue mappings
DEFAULT_SCRAPER_QUEUES = {
    'macmaptariff': 'macmap_tariff',
    'traderemedies': 'macmap_trade_remedies', 
    'regulatory': 'macmap_regulatory',
    'comparemarket': 'macmap_compare',
    'competitors': 'macmap_competitors',
    'macmapproduct': 'macmap_products',
    'fulltariff': 'tariff_full',
    'indiantradeportal': 'indian_trade_portal',
    'trademap': 'trademap',
    'eximpedia': 'eximpedia',
    'portscraper': 'port_scraper',
    'indiamart': 'indiamart',
    'batch_operations': 'batch_operations',
    'default': 'default'
}

# Active worker processes
active_workers = {}

class WorkerManager:
    """Manages dedicated Celery workers for specific scrapers"""
    
    def __init__(self):
        self.config_file = WORKER_CONFIG_FILE
        self.load_config()
    
    def load_config(self):
        """Load worker configuration from file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    self.config = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load config: {e}, using defaults")
                self.config = self._get_default_config()
        else:
            self.config = self._get_default_config()
            self.save_config()
    
    def save_config(self):
        """Save worker configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
    
    def _get_default_config(self):
        """Get default worker configuration"""
        return {
            "workers": {
                "macmap_worker": {
                    "queues": ["macmap_tariff", "macmap_trade_remedies", "macmap_regulatory"],
                    "concurrency": 4,
                    "loglevel": "info",
                    "enabled": True,
                    "description": "MacMap scraper tasks"
                },
                "comparison_worker": {
                    "queues": ["macmap_compare", "macmap_competitors", "macmap_products"],
                    "concurrency": 3,
                    "loglevel": "info", 
                    "enabled": True,
                    "description": "MacMap comparison and product tasks"
                },
                "tariff_worker": {
                    "queues": ["tariff_full"],
                    "concurrency": 2,
                    "loglevel": "info",
                    "enabled": True,
                    "description": "Full tariff scraping (resource intensive)"
                },
                "trade_worker": {
                    "queues": ["indian_trade_portal", "trademap"],
                    "concurrency": 3,
                    "loglevel": "info",
                    "enabled": True,
                    "description": "Trade portal and TradeMap tasks"
                },
                "eximpedia_worker": {
                    "queues": ["eximpedia"],
                    "concurrency": 2,
                    "loglevel": "info",
                    "enabled": True,
                    "description": "Eximpedia scraping tasks"
                },
                "port_worker": {
                    "queues": ["port_scraper"],
                    "concurrency": 1,
                    "loglevel": "info",
                    "enabled": True,
                    "description": "Port scraper (browser-based)"
                },
                "indiamart_worker": {
                    "queues": ["indiamart"],
                    "concurrency": 3,
                    "loglevel": "info",
                    "enabled": True,
                    "description": "Indiamart scraping tasks"
                },
                "batch_worker": {
                    "queues": ["batch_operations"],
                    "concurrency": 2,
                    "loglevel": "info",
                    "enabled": True,
                    "description": "Batch and comprehensive operations"
                },
                "default_worker": {
                    "queues": ["default"],
                    "concurrency": 4,
                    "loglevel": "info",
                    "enabled": True,
                    "description": "Default queue for miscellaneous tasks"
                }
            },
            "global_settings": {
                "worker_max_tasks_per_child": 50,
                "worker_prefetch_multiplier": 1,
                "task_acks_late": True
            }
        }
    
    def start_worker(self, worker_name: str) -> Tuple[bool, str]:
        """Start a specific worker"""
        if worker_name not in self.config["workers"]:
            return False, f"Worker {worker_name} not found in configuration"
        
        worker_config = self.config["workers"][worker_name]
        
        if not worker_config.get("enabled", True):
            return False, f"Worker {worker_name} is disabled"
        
        if worker_name in active_workers:
            return False, f"Worker {worker_name} is already running"
        
        try:
            # Build celery command
            queues = ",".join(worker_config["queues"])
            cmd = [
                "celery", "-A", "tasks", "worker",
                "--loglevel", worker_config["loglevel"],
                "--concurrency", str(worker_config["concurrency"]),
                "-Q", queues,
                "--hostname", f"{worker_name}@%h",
                "--max-tasks-per-child", str(self.config["global_settings"]["worker_max_tasks_per_child"]),
                "--prefetch-multiplier", str(self.config["global_settings"]["worker_prefetch_multiplier"])
            ]
            
            if self.config["global_settings"]["task_acks_late"]:
                cmd.append("--task-acks-late")
            
            # Start the worker process
            process = subprocess.Popen(
                cmd,
                cwd=os.getcwd(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True
            )
            
            active_workers[worker_name] = {
                "process": process,
                "pid": process.pid,
                "queues": worker_config["queues"],
                "started_at": datetime.now().isoformat(),
                "config": worker_config
            }
            
            logger.info(f"Started worker {worker_name} (PID: {process.pid}) for queues: {queues}")
            return True, f"Worker {worker_name} started successfully (PID: {process.pid})"
            
        except Exception as e:
            logger.error(f"Failed to start worker {worker_name}: {e}")
            return False, f"Failed to start worker: {str(e)}"
    
    def stop_worker(self, worker_name: str) -> Tuple[bool, str]:
        """Stop a specific worker"""
        if worker_name not in active_workers:
            return False, f"Worker {worker_name} is not running"
        
        try:
            worker_info = active_workers[worker_name]
            process = worker_info["process"]
            
            # Send SIGTERM for graceful shutdown
            process.terminate()
            
            # Wait for graceful shutdown
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                # Force kill if graceful shutdown fails
                process.kill()
                process.wait()
            
            del active_workers[worker_name]
            logger.info(f"Stopped worker {worker_name}")
            return True, f"Worker {worker_name} stopped successfully"
            
        except Exception as e:
            logger.error(f"Failed to stop worker {worker_name}: {e}")
            return False, f"Failed to stop worker: {str(e)}"
    
    def start_all_workers(self) -> Dict[str, Tuple[bool, str]]:
        """Start all enabled workers"""
        results = {}
        for worker_name, worker_config in self.config["workers"].items():
            if worker_config.get("enabled", True):
                results[worker_name] = self.start_worker(worker_name)
            else:
                results[worker_name] = (False, "Worker is disabled")
        return results
    
    def stop_all_workers(self) -> Dict[str, Tuple[bool, str]]:
        """Stop all active workers"""
        results = {}
        for worker_name in list(active_workers.keys()):
            results[worker_name] = self.stop_worker(worker_name)
        return results
    
    def get_worker_status(self) -> Dict:
        """Get status of all workers"""
        status = {
            "active_workers": {},
            "configured_workers": {},
            "scraper_queue_mapping": DEFAULT_SCRAPER_QUEUES
        }
        
        # Active workers
        for worker_name, worker_info in active_workers.items():
            process = worker_info["process"]
            status["active_workers"][worker_name] = {
                "pid": worker_info["pid"],
                "queues": worker_info["queues"],
                "started_at": worker_info["started_at"],
                "is_alive": process.poll() is None,
                "description": worker_info["config"].get("description", "")
            }
        
        # Configured workers
        for worker_name, worker_config in self.config["workers"].items():
            status["configured_workers"][worker_name] = {
                "queues": worker_config["queues"],
                "concurrency": worker_config["concurrency"],
                "enabled": worker_config.get("enabled", True),
                "description": worker_config.get("description", ""),
                "is_running": worker_name in active_workers
            }
        
        return status
    
    def assign_scraper_to_worker(self, scraper_id: str, worker_name: str) -> Tuple[bool, str]:
        """Assign a scraper to a specific worker by updating queue routing"""
        if scraper_id not in DEFAULT_SCRAPER_QUEUES:
            return False, f"Unknown scraper: {scraper_id}"
        
        if worker_name not in self.config["workers"]:
            return False, f"Unknown worker: {worker_name}"
        
        queue_name = DEFAULT_SCRAPER_QUEUES[scraper_id]
        worker_config = self.config["workers"][worker_name]
        
        # Add queue to worker if not already present
        if queue_name not in worker_config["queues"]:
            worker_config["queues"].append(queue_name)
            self.save_config()
            
            # If worker is running, it needs to be restarted to pick up new queue
            if worker_name in active_workers:
                self.stop_worker(worker_name)
                time.sleep(2)
                self.start_worker(worker_name)
                return True, f"Scraper {scraper_id} assigned to {worker_name} (worker restarted)"
            else:
                return True, f"Scraper {scraper_id} assigned to {worker_name} (start worker to activate)"
        else:
            return True, f"Scraper {scraper_id} already assigned to {worker_name}"

def main():
    """CLI interface for worker management"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Celery Worker Manager")
    parser.add_argument("action", choices=["start", "stop", "restart", "status", "assign"], 
                       help="Action to perform")
    parser.add_argument("--worker", help="Specific worker name")
    parser.add_argument("--scraper", help="Scraper ID for assignment")
    parser.add_argument("--all", action="store_true", help="Apply to all workers")
    
    args = parser.parse_args()
    
    manager = WorkerManager()
    
    if args.action == "start":
        if args.all:
            results = manager.start_all_workers()
            for worker, (success, msg) in results.items():
                print(f"{'✅' if success else '❌'} {worker}: {msg}")
        elif args.worker:
            success, msg = manager.start_worker(args.worker)
            print(f"{'✅' if success else '❌'} {msg}")
        else:
            print("❌ Specify --worker or --all")
    
    elif args.action == "stop":
        if args.all:
            results = manager.stop_all_workers()
            for worker, (success, msg) in results.items():
                print(f"{'✅' if success else '❌'} {worker}: {msg}")
        elif args.worker:
            success, msg = manager.stop_worker(args.worker)
            print(f"{'✅' if success else '❌'} {msg}")
        else:
            print("❌ Specify --worker or --all")
    
    elif args.action == "restart":
        if args.worker:
            print(f"🔄 Restarting {args.worker}...")
            manager.stop_worker(args.worker)
            time.sleep(2)
            success, msg = manager.start_worker(args.worker)
            print(f"{'✅' if success else '❌'} {msg}")
        else:
            print("❌ Specify --worker for restart")
    
    elif args.action == "status":
        status = manager.get_worker_status()
        print("\n📊 Worker Status:")
        print("=" * 60)
        
        print("\n🟢 Active Workers:")
        for worker, info in status["active_workers"].items():
            alive_status = "🟢 Running" if info["is_alive"] else "🔴 Dead"
            print(f"  {worker} (PID: {info['pid']}) - {alive_status}")
            print(f"    Queues: {', '.join(info['queues'])}")
            print(f"    Started: {info['started_at']}")
            print(f"    Description: {info['description']}")
        
        print("\n⚙️  Configured Workers:")
        for worker, info in status["configured_workers"].items():
            enabled_status = "✅ Enabled" if info["enabled"] else "❌ Disabled"
            running_status = "🟢 Running" if info["is_running"] else "⚪ Stopped"
            print(f"  {worker} - {enabled_status} | {running_status}")
            print(f"    Queues: {', '.join(info['queues'])}")
            print(f"    Concurrency: {info['concurrency']}")
            print(f"    Description: {info['description']}")
        
        print("\n🔗 Scraper-Queue Mapping:")
        for scraper, queue in status["scraper_queue_mapping"].items():
            print(f"  {scraper} → {queue}")
    
    elif args.action == "assign":
        if args.scraper and args.worker:
            success, msg = manager.assign_scraper_to_worker(args.scraper, args.worker)
            print(f"{'✅' if success else '❌'} {msg}")
        else:
            print("❌ Specify both --scraper and --worker for assignment")

if __name__ == "__main__":
    main()