"""
WebSocket Data Providers
Provides real-time data for different channels
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class DashboardProvider:
    """Provides dashboard statistics data"""
    
    @staticmethod
    async def get_data() -> Dict[str, Any]:
        """Get current dashboard statistics"""
        try:
            from services.task_manager import task_manager
            
            # Get task manager status - returns dict with creator_id as keys
            scrapers = task_manager.get_status()
            
            logger.info(f"Dashboard provider: Found {len(scrapers)} scrapers")
            
            # Calculate statistics
            total_tasks = sum(scraper_stats.get('total_tasks', 0) 
                            for scraper_stats in scrapers.values())
            completed_tasks = sum(scraper_stats.get('completed_tasks', 0) 
                                for scraper_stats in scrapers.values())
            failed_tasks = sum(scraper_stats.get('failed_tasks', 0) 
                             for scraper_stats in scrapers.values())
            pending_tasks = sum(scraper_stats.get('pending_tasks', 0) 
                              for scraper_stats in scrapers.values())
            
            # Transform scrapers data to match frontend expectations
            transformed_scrapers = {}
            for scraper_id, scraper_data in scrapers.items():
                # Status is based ONLY on worker status
                # Queued tasks don't mean the scraper is "running"
                worker_status = scraper_data.get('worker_status', 'stopped')
                
                # Use worker status directly
                effective_status = 'running' if worker_status == 'running' else 'stopped'
                
                base_scraper = {
                    "id": scraper_id,
                    "name": scraper_data.get('name', scraper_id.replace('_', ' ').title()),
                    "displayName": scraper_data.get('display_name', scraper_id.replace('_', ' ').title()),
                    "status": effective_status,
                    "queue": scraper_data.get('worker_queue', scraper_id),
                    "tasksQueued": scraper_data.get('pending_tasks', 0),
                    "tasksRunning": scraper_data.get('current_tasks', 0),
                    "tasksCompleted": scraper_data.get('completed_tasks', 0),
                    "tasksFailed": scraper_data.get('failed_tasks', 0),
                    "taskLimit": scraper_data.get('total_tasks', 0),
                    "workerConcurrency": scraper_data.get('worker_concurrency', 1),
                    "workerStatus": worker_status,
                    "workerPid": scraper_data.get('worker_pid'),
                }
                
                # Add IndiaMART-specific statistics
                if scraper_id in ['indiamart', 'indiamart_categories', 'indiamart_products']:
                    try:
                        from scrapers.indiamart.indiamart_mongodb import IndiamartMongoDB
                        # Use read-only mode (no background thread) to avoid thread exhaustion
                        db = IndiamartMongoDB(enable_background_flush=False)
                        stats = db.get_statistics()
                        
                        # For categories scraper - show categories and product URLs
                        if scraper_id == 'indiamart_categories':
                            base_scraper["totalCategories"] = stats.get('total_categories', 0)
                            base_scraper["totalProductUrls"] = stats.get('total_urls', 0)
                        
                        # For products scraper - show scraped products and sellers
                        elif scraper_id == 'indiamart_products':
                            base_scraper["scrapedProducts"] = stats.get('scraped_products', 0)
                            base_scraper["scrapedSellers"] = stats.get('scraped_sellers', 0)
                            base_scraper["pendingUrls"] = stats.get('pending_urls', 0)
                            base_scraper["completedUrls"] = stats.get('completed_urls', 0)
                        
                        # For main indiamart scraper - show all stats
                        else:
                            base_scraper["totalCategories"] = stats.get('total_categories', 0)
                            base_scraper["totalProductUrls"] = stats.get('total_urls', 0)
                            base_scraper["scrapedProducts"] = stats.get('scraped_products', 0)
                            base_scraper["scrapedSellers"] = stats.get('scraped_sellers', 0)
                        
                        # Get crawler settings from MongoDB
                        settings = db.get_crawler_settings()
                        if settings:
                            base_scraper["workerConcurrency"] = settings.get('max_workers', 150)
                            base_scraper["maxConcurrentRequests"] = settings.get('max_concurrent_requests', 300)
                            base_scraper["batchSize"] = settings.get('batch_size', 1000)
                        
                        # Close connection immediately after use
                        db.close()
                        
                        logger.info(f"IndiaMART stats for {scraper_id}: {stats}")
                    except Exception as e:
                        logger.warning(f"Failed to get IndiaMART statistics for {scraper_id}: {e}")
                        base_scraper["totalCategories"] = 0
                        base_scraper["totalProductUrls"] = 0
                
                transformed_scrapers[scraper_id] = base_scraper
            
            result = {
                "type": "dashboard_stats",
                "stats": {
                    "totalScrapers": len(scrapers),
                    "activeScrapers": sum(1 for s in scrapers.values() 
                                        if s.get('status') == 'running'),
                    "totalTasks": total_tasks,
                    "completedTasks": completed_tasks,
                    "failedTasks": failed_tasks,
                    "pendingTasks": pending_tasks,
                    "successRate": (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0,
                    "activeWorkers": sum(1 for s in scrapers.values() 
                                       if s.get('worker_status') == 'running'),
                    "queuedJobs": pending_tasks
                },
                "scrapers": transformed_scrapers,
                "timestamp": datetime.now().isoformat()
            }
            
            return result
        except Exception as e:
            logger.error(f"Error getting dashboard data: {e}", exc_info=True)
            return {
                "type": "error",
                "message": f"Failed to get dashboard data: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }


class TaskManagerProvider:
    """Provides task manager data"""
    
    @staticmethod
    async def get_data() -> Dict[str, Any]:
        """Get current task manager status"""
        try:
            from services.task_manager import task_manager
            
            status = task_manager.get_status()
            
            return {
                "type": "task_manager_status",
                "status": status,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting task manager data: {e}")
            return {
                "type": "error",
                "message": f"Failed to get task manager data: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }


class LogsProvider:
    """Provides real-time log streaming"""
    
    def __init__(self):
        self.log_positions: Dict[str, int] = {}
    
    async def get_data(self, log_type: Optional[str] = None, lines: int = 50) -> Dict[str, Any]:
        """Get recent log entries"""
        try:
            log_dir = Path("logs")
            today = datetime.now().strftime('%Y%m%d')
            
            logs = []
            
            # Determine which log files to read
            if log_type:
                log_files = [f"{log_type}_{today}.log"]
            else:
                # Read all log files
                log_files = [
                    f"indiamart_category_crawler_{today}.log",
                    f"port_scraper_{today}.log",
                    f"scraper_{today}.log",
                    "celery.log",
                    "worker.log"
                ]
            
            for log_filename in log_files:
                log_file_path = log_dir / log_filename
                
                if log_file_path.exists():
                    try:
                        with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            # Get last position for this file
                            last_pos = self.log_positions.get(str(log_file_path), 0)
                            
                            # Seek to last position
                            f.seek(last_pos)
                            
                            # Read new lines
                            new_lines = f.readlines()
                            
                            if new_lines:
                                for line in new_lines[-lines:]:
                                    logs.append({
                                        "timestamp": datetime.now().isoformat(),
                                        "source": log_filename,
                                        "message": line.strip(),
                                        "level": self._extract_log_level(line)
                                    })
                                
                                # Update position
                                self.log_positions[str(log_file_path)] = f.tell()
                    
                    except Exception as e:
                        logger.warning(f"Error reading log file {log_filename}: {e}")
            
            return {
                "type": "logs",
                "logs": logs[-lines:],  # Return last N lines
                "total": len(logs),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting logs: {e}")
            return {
                "type": "error",
                "message": f"Failed to get logs: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    @staticmethod
    def _extract_log_level(line: str) -> str:
        """Extract log level from log line"""
        line_upper = line.upper()
        if "ERROR" in line_upper:
            return "error"
        elif "WARNING" in line_upper or "WARN" in line_upper:
            return "warning"
        elif "INFO" in line_upper:
            return "info"
        elif "DEBUG" in line_upper:
            return "debug"
        else:
            return "info"


class WorkersProvider:
    """Provides worker status data"""
    
    @staticmethod
    async def get_data() -> Dict[str, Any]:
        """Get current worker status"""
        try:
            from celery_app.tasks import app as celery_app
            
            # Get active workers
            inspect = celery_app.control.inspect()
            
            active_workers = inspect.active() or {}
            stats = inspect.stats() or {}
            registered = inspect.registered() or {}
            
            workers_data = {}
            
            for worker_name in stats.keys():
                worker_stats = stats.get(worker_name, {})
                worker_active = active_workers.get(worker_name, [])
                
                # Get active tasks count
                active_count = len(worker_active)
                
                # Get total tasks processed
                total_tasks = 0
                try:
                    if 'total' in worker_stats and isinstance(worker_stats['total'], dict):
                        for task_name, count in worker_stats['total'].items():
                            if isinstance(count, (int, float)):
                                total_tasks += count
                except Exception:
                    total_tasks = 0
                
                # Get concurrency
                concurrency = 4
                try:
                    if 'pool' in worker_stats and 'max-concurrency' in worker_stats['pool']:
                        concurrency = worker_stats['pool']['max-concurrency']
                except Exception:
                    pass
                
                # Get load average
                load_avg = '0.00'
                try:
                    if 'rusage' in worker_stats and 'utime' in worker_stats['rusage']:
                        load_avg = f"{worker_stats['rusage']['utime']:.2f}"
                except Exception:
                    pass
                
                # Parse queues
                queues_list = ['default']
                try:
                    if 'pool' in worker_stats and 'queues' in worker_stats['pool']:
                        queues_list = worker_stats['pool']['queues']
                except Exception:
                    pass
                
                workers_data[worker_name] = {
                    "name": worker_name,
                    "status": "online",
                    "activeTasks": active_count,
                    "totalTasks": total_tasks,
                    "loadAverage": load_avg,
                    "queues": queues_list,
                    "concurrency": concurrency,
                    "clock": str(worker_stats.get('clock', 'N/A'))
                }
            
            return {
                "type": "workers_status",
                "data": workers_data,
                "totalWorkers": len(workers_data),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting workers data: {e}")
            return {
                "type": "error",
                "message": f"Failed to get workers data: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }


class DataSourcesProvider:
    """Provides data sources status"""
    
    @staticmethod
    async def get_data() -> Dict[str, Any]:
        """Get data sources status"""
        try:
            from services.task_manager import task_manager
            
            status = task_manager.get_status()
            scrapers = status.get('scrapers', {})
            
            data_sources = []
            
            for scraper_id, scraper_data in scrapers.items():
                scraper_obj = {
                    "id": scraper_id,
                    "name": scraper_data.get('name', scraper_id.replace('_', ' ').title()),
                    "status": scraper_data.get('status', 'unknown'),
                    "queue": scraper_data.get('worker_queue', scraper_id),
                    "tasksQueued": scraper_data.get('pending_tasks', 0),
                    "tasksRunning": scraper_data.get('current_tasks', 0),
                    "tasksCompleted": scraper_data.get('completed_tasks', 0),
                    "tasksFailed": scraper_data.get('failed_tasks', 0),
                    "taskLimit": scraper_data.get('total_tasks', 0),
                    "workerConcurrency": scraper_data.get('worker_concurrency', 1),
                    "workerStatus": scraper_data.get('worker_status', 'stopped'),
                    "workerPid": scraper_data.get('worker_pid'),
                    "lastUpdate": scraper_data.get('last_update', datetime.now().isoformat())
                }
                data_sources.append(scraper_obj)
                logger.debug(f"Scraper {scraper_id}: {scraper_obj}")
            
            return {
                "type": "data_sources_status",
                "dataSources": data_sources,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting data sources: {e}")
            return {
                "type": "error",
                "message": f"Failed to get data sources: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }


class IndiamartProvider:
    """Provides IndiaMART scraper data with MongoDB statistics"""
    
    def __init__(self):
        self.last_log_position = 0
    
    async def get_data(self) -> Dict[str, Any]:
        """Get IndiaMART scraper status and data"""
        try:
            from scrapers.indiamart.indiamart_mongodb import IndiamartMongoDB
            
            # Get statistics from MongoDB
            db = IndiamartMongoDB()
            stats = db.get_statistics()
            
            # Extract key metrics
            total_categories = stats.get('total_categories', 0)
            total_product_urls = stats.get('total_urls', 0)
            pending_urls = stats.get('pending_urls', 0)
            completed_urls = stats.get('completed_urls', 0)
            failed_urls = stats.get('failed_urls', 0)
            scraped_products = stats.get('scraped_products', 0)
            scraped_sellers = stats.get('scraped_sellers', 0)
            
            # Get recent logs
            log_dir = Path("logs")
            today = datetime.now().strftime('%Y%m%d')
            log_file = log_dir / f"indiamart_category_crawler_{today}.log"
            
            logs = []
            if log_file.exists():
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    f.seek(self.last_log_position)
                    new_lines = f.readlines()
                    if new_lines:
                        logs = [line.strip() for line in new_lines[-10:]]
                        self.last_log_position = f.tell()
            
            # Get active crawler status
            from celery_app.tasks import app as celery_app
            inspect = celery_app.control.inspect()
            active_tasks = inspect.active() or {}
            
            indiamart_tasks = []
            for worker, tasks in active_tasks.items():
                for task in tasks:
                    if task.get("name") in ["tasks.indiamart_category_crawler_task", "tasks.indiamart_product_scraper_task"]:
                        indiamart_tasks.append({
                            "task_id": task.get("id"),
                            "worker": worker,
                            "task_name": task.get("name"),
                            "started": task.get("time_start")
                        })
            
            return {
                "type": "indiamart_update",
                "statistics": {
                    "total_categories": total_categories,
                    "total_product_urls": total_product_urls,
                    "pending_urls": pending_urls,
                    "completed_urls": completed_urls,
                    "failed_urls": failed_urls,
                    "scraped_products": scraped_products,
                    "scraped_sellers": scraped_sellers,
                    "cache_hit_rate": stats.get('cache_hit_rate', 0)
                },
                "logs": logs,
                "activeCrawlers": indiamart_tasks,
                "crawlerStatus": "running" if indiamart_tasks else "stopped",
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting IndiaMART data: {e}")
            return {
                "type": "error",
                "message": f"Failed to get IndiaMART data: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }


class SystemHealthProvider:
    """Provides real-time system health metrics"""
    
    @staticmethod
    async def get_data() -> Dict[str, Any]:
        """Get current system health metrics"""
        try:
            import psutil
            
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=0.1)
            cpu_count = psutil.cpu_count()
            
            # Memory metrics
            memory = psutil.virtual_memory()
            
            # Disk metrics
            disk = psutil.disk_usage('/')
            
            # Check Redis connection
            redis_healthy = False
            try:
                from celery_app.tasks import app as celery_app
                celery_app.backend.client.ping()
                redis_healthy = True
            except Exception as e:
                logger.debug(f"Redis health check failed: {e}")
            
            # Check Celery workers
            celery_healthy = False
            try:
                from celery_app.tasks import app as celery_app
                inspect = celery_app.control.inspect()
                stats = inspect.stats()
                celery_healthy = stats is not None and len(stats) > 0
            except Exception as e:
                logger.debug(f"Celery health check failed: {e}")
            
            # Check database (SQLite)
            database_healthy = False
            try:
                import sqlite3
                from pathlib import Path
                # Check if at least one database exists and is accessible
                db_path = Path("shared/task_creator_utils/scrapped_data/macmap_tariff_tasks.db")
                if db_path.exists():
                    conn = sqlite3.connect(db_path)
                    conn.execute("SELECT 1")
                    conn.close()
                    database_healthy = True
                else:
                    # If no database exists yet, consider it healthy (not an error)
                    database_healthy = True
            except Exception as e:
                logger.debug(f"Database health check failed: {e}")
            
            return {
                "type": "system_health",
                "health": {
                    "cpu": {
                        "percent": round(cpu_percent, 2),
                        "cores": cpu_count
                    },
                    "memory": {
                        "percent": round(memory.percent, 2),
                        "total": memory.total,
                        "used": memory.used,
                        "available": memory.available
                    },
                    "disk": {
                        "percent": round((disk.used / disk.total) * 100, 2),
                        "total": disk.total,
                        "used": disk.used,
                        "free": disk.free
                    },
                    "services": {
                        "redis": "healthy" if redis_healthy else "unhealthy",
                        "celery": "healthy" if celery_healthy else "unhealthy",
                        "database": "healthy" if database_healthy else "unhealthy"
                    }
                },
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting system health: {e}")
            return {
                "type": "error",
                "message": f"Failed to get system health: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }


# Global provider instances
dashboard_provider = DashboardProvider()
task_manager_provider = TaskManagerProvider()
logs_provider = LogsProvider()
workers_provider = WorkersProvider()
data_sources_provider = DataSourcesProvider()
indiamart_provider = IndiamartProvider()
system_health_provider = SystemHealthProvider()
