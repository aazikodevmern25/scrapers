#!/usr/bin/env python3
"""
Celery Status Checker - Syncs database task status with Celery task status
Handles FAILURE status properly and prevents retrying failed tasks
"""

import os
import sys
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from celery import Celery
    from celery.result import AsyncResult
    CELERY_AVAILABLE = True
except ImportError:
    print("⚠️  Celery not installed. Install with: pip install celery")
    CELERY_AVAILABLE = False

# Celery configuration - adjust these based on your setup
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

# Initialize Celery app
if CELERY_AVAILABLE:
    celery_app = Celery('scraper', 
                       broker=CELERY_BROKER_URL,
                       backend=CELERY_RESULT_BACKEND)
else:
    celery_app = None

def check_celery_task_status(task_id: str) -> str:
    """
    Check individual Celery task status
    
    Returns:
        'SUCCESS' - Task completed successfully
        'FAILURE' - Task failed (should not retry)
        'PENDING' - Task is pending/running
        'RETRY' - Task should be retried
        'REVOKED' - Task was revoked
        'ERROR' - Unknown error checking status
    """
    if not CELERY_AVAILABLE or not celery_app:
        # Fallback to HTTP-based checking if Celery not available
        return check_task_status_http(task_id)
    
    try:
        result = AsyncResult(task_id, app=celery_app)
        celery_status = result.status
        
        # Map Celery status to our system status
        status_mapping = {
            'SUCCESS': 'SUCCESS',
            'FAILURE': 'FAILURE',  # Important: Don't retry failed tasks
            'PENDING': 'PENDING',   # Task queued but not started
            'STARTED': 'RUNNING',   # Task actively running - wait for completion
            'RETRY': 'RETRY',       # Task being retried
            'REVOKED': 'FAILED',    # Treat revoked as failed
            'REJECTED': 'FAILED',   # Treat rejected as failed
            'PAUSED': 'PAUSED',     # Task is paused - support for pause/resume functionality
        }
        
        mapped_status = status_mapping.get(celery_status, 'PENDING')
        
        # Log status details for debugging
        if celery_status == 'FAILURE':
            try:
                error_info = str(result.result) if result.result else "Unknown error"
                print(f"🔍 Task {task_id} failed in Celery: {error_info}")
            except:
                pass
        elif celery_status == 'STARTED':
            print(f"🏃 Task {task_id} is actively running in Celery - waiting for completion...")
        elif celery_status == 'RETRY':
            print(f"🔄 Task {task_id} is being retried in Celery...")
        elif celery_status == 'PAUSED':
            print(f"⏸️  Task {task_id} is paused in Celery - waiting for resume...")
        
        return mapped_status
        
    except Exception as e:
        print(f"❌ Error checking Celery status for task {task_id}: {e}")
        return 'ERROR'


def get_celery_task_details(task_id: str) -> Dict[str, Any]:
    """Return detailed information (status/result/traceback) for a Celery task."""
    if not task_id:
        return {}
    if not CELERY_AVAILABLE or not celery_app:
        return {}
    try:
        result = AsyncResult(task_id, app=celery_app)
        return {
            'task_id': task_id,
            'status': result.status,
            'result': str(result.result) if result.result is not None else None,
            'traceback': result.traceback,
            'date_done': result.date_done.isoformat() if result.date_done else None
        }
    except Exception as e:
        return {'task_id': task_id, 'error': str(e)}

def check_task_status_http(task_id: str) -> str:
    """
    Fallback HTTP-based status checking (original method)
    Used when Celery is not available
    """
    try:
        import requests
        TASK_STATUS_URL = "http://192.168.29.10:1080/api/v1/task-status"
        response = requests.get(f"{TASK_STATUS_URL}/{task_id}", timeout=10)
        response.raise_for_status()
        return response.json().get("status", "UNKNOWN")
    except:
        return "ERROR"

def batch_celery_status_check(task_ids: List[str], max_workers: int = 10) -> Dict[str, str]:
    """
    Check multiple Celery task statuses concurrently
    
    Args:
        task_ids: List of task IDs to check
        max_workers: Maximum concurrent workers
        
    Returns:
        Dictionary mapping task_id -> status
    """
    if not task_ids:
        return {}
    
    results = {}
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {
            executor.submit(check_celery_task_status, task_id): task_id 
            for task_id in task_ids
        }
        
        for future in as_completed(future_to_task):
            task_id = future_to_task[future]
            try:
                status = future.result()
                results[task_id] = status
            except Exception as e:
                print(f"❌ Error checking status for task {task_id}: {e}")
                results[task_id] = "ERROR"
    
    return results

def update_task_status_with_celery_sync(db_update_func, task_mappings: Dict[str, tuple], 
                                       max_workers: int = 10) -> Dict[str, int]:
    """
    Update database task statuses by syncing with Celery
    
    Args:
        db_update_func: Function to update database (db_id, status)
        task_mappings: Dict mapping task_id -> (db_id, current_status)
        max_workers: Maximum concurrent workers
        
    Returns:
        Dictionary with counts of updated statuses
    """
    if not task_mappings:
        return {'total_checked': 0, 'success': 0, 'failed': 0, 'pending': 0, 'updated': 0}
    
    task_ids = list(task_mappings.keys())
    print(f"🔍 Syncing {len(task_ids)} tasks with Celery status...")
    
    # Get Celery statuses
    celery_statuses = batch_celery_status_check(task_ids, max_workers)
    
    # Update database based on Celery status
    updated_count = 0
    success_count = 0
    failed_count = 0
    pending_count = 0
    
    for task_id, celery_status in celery_statuses.items():
        if task_id not in task_mappings:
            continue
            
        db_id, current_status = task_mappings[task_id]
        
        # Map Celery status to database status
        if celery_status == 'SUCCESS':
            new_status = 'SUCCESS'
            success_count += 1
        elif celery_status == 'FAILURE':
            new_status = 'FAILED'  # Important: Mark as FAILED to prevent retries
            failed_count += 1
            print(f"⚠️  Task {task_id} marked as FAILED (Celery FAILURE) - will not retry")
        elif celery_status == 'RUNNING':
            new_status = 'RUNNING'  # Task actively running - keep monitoring
            pending_count += 1
            print(f"🏃 Task {task_id} is RUNNING - continuing to monitor...")
        elif celery_status in ['ERROR', 'REVOKED']:
            new_status = 'FAILED'  # Also mark errors as failed
            failed_count += 1
        else:
            new_status = 'PENDING'
            pending_count += 1
        
        # Update database if status changed
        if new_status != current_status and celery_status not in ['ERROR']:
            try:
                db_update_func(db_id, status=new_status)
                updated_count += 1
            except Exception as e:
                print(f"❌ Error updating task {task_id} status: {e}")
    
    print(f"✅ Celery sync complete: {success_count} success, {failed_count} failed, {pending_count} pending")
    print(f"📊 Database updates: {updated_count} tasks updated")
    
    return {
        'total_checked': len(task_ids),
        'success': success_count,
        'failed': failed_count,
        'pending': pending_count,
        'updated': updated_count
    }

def get_celery_connection_status() -> bool:
    """Check if Celery connection is working"""
    if not CELERY_AVAILABLE or not celery_app:
        return False
    
    try:
        # Try to get inspector to test connection
        inspect = celery_app.control.inspect()
        stats = inspect.stats()
        return stats is not None
    except:
        return False

def print_celery_status():
    """Print Celery connection status"""
    if not CELERY_AVAILABLE:
        print("❌ Celery Status: Not installed")
        return False
    
    if get_celery_connection_status():
        print("✅ Celery Status: Connected and ready")
        print(f"   📡 Broker: {CELERY_BROKER_URL}")
        print(f"   💾 Backend: {CELERY_RESULT_BACKEND}")
        return True
    else:
        print("⚠️  Celery Status: Connection failed")
        print(f"   📡 Broker: {CELERY_BROKER_URL}")
        print(f"   💾 Backend: {CELERY_RESULT_BACKEND}")
        print("   🔄 Falling back to HTTP status checking")
        return False

# Example usage functions for integration with existing task creators
def create_celery_aware_status_checker(update_status_func):
    """
    Create a Celery-aware status checking function compatible with existing task creators
    
    Args:
        update_status_func: Database update function (db_id, status)
        
    Returns:
        Function compatible with batch_status_check signature
    """
    def celery_batch_status_check(task_ids: List[str]) -> Dict[str, str]:
        """Celery-aware batch status checker"""
        return batch_celery_status_check(task_ids)
    
    return celery_batch_status_check

def create_celery_aware_single_checker():
    """
    Create a Celery-aware single task status checker
    
    Returns:
        Function compatible with check_task_status signature  
    """
    def celery_check_task_status(task_id: str) -> str:
        """Celery-aware single task status checker"""
        return check_celery_task_status(task_id)
    
    return celery_check_task_status

if __name__ == "__main__":
    # Test Celery connection
    print("🔍 Testing Celery Status Checker")
    print("=" * 50)
    
    print_celery_status()
    
    # Test with a sample task ID if provided
    if len(sys.argv) > 1:
        test_task_id = sys.argv[1]
        print(f"\n🧪 Testing with task ID: {test_task_id}")
        status = check_celery_task_status(test_task_id)
        print(f"📊 Task status: {status}")