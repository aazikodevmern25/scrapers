#!/usr/bin/env python3
"""
Enhanced Task Selector - Improved logic to skip failed and retry tasks in Celery queue
This module provides enhanced task selection logic that avoids problematic tasks.
"""

import sqlite3
import time
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from tools.celery_status_checker import check_celery_task_status

class EnhancedTaskSelector:
    """
    Enhanced task selector that intelligently skips problematic tasks
    """
    
    def __init__(self, db_path: str, max_retries: int = 3):
        self.db_path = db_path
        self.max_retries = max_retries
        self.failed_task_cache = set()  # Cache of known failed task IDs
        self.retry_task_cache = set()   # Cache of known retry task IDs
        self.last_cache_update = 0
        self.cache_ttl = 300  # 5 minutes cache TTL
    
    def update_problematic_task_cache(self):
        """Update cache of problematic tasks from Celery"""
        current_time = time.time()
        if current_time - self.last_cache_update < self.cache_ttl:
            return  # Cache still valid
        
        print("🔍 Updating problematic task cache...")
        
        # Get all active tasks from database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT task_id, status, retry_count, created_at
            FROM tasks 
            WHERE task_id != '' 
            AND status IN ('PENDING', 'RUNNING', 'RETRY', 'PAUSED')
            AND task_id IS NOT NULL
        """)
        
        active_tasks = cursor.fetchall()
        conn.close()
        
        failed_count = 0
        retry_count = 0
        
        # Check each task status in Celery
        for task_id, db_status, retry_count_db, created_at in active_tasks:
            if not task_id:
                continue
                
            try:
                celery_status = check_celery_task_status(task_id)
                
                # Identify failed tasks
                if celery_status in ['FAILED', 'FAILURE', 'ERROR', 'REVOKED']:
                    self.failed_task_cache.add(task_id)
                    failed_count += 1
                    print(f"❌ Cached failed task: {task_id}")
                
                # Identify retry tasks
                elif celery_status == 'RETRY':
                    self.retry_task_cache.add(task_id)
                    retry_count += 1
                    print(f"🔄 Cached retry task: {task_id}")
                
                # Identify stuck tasks (pending for too long)
                elif celery_status == 'PENDING' and created_at:
                    try:
                        created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        if datetime.now() - created_time > timedelta(hours=1):  # Stuck for > 1 hour
                            self.failed_task_cache.add(task_id)
                            failed_count += 1
                            print(f"⏰ Cached stuck task: {task_id} (pending for > 1 hour)")
                    except:
                        pass  # Skip if date parsing fails
                        
            except Exception as e:
                print(f"⚠️ Error checking task {task_id}: {e}")
        
        self.last_cache_update = current_time
        print(f"✅ Cache updated: {failed_count} failed, {retry_count} retry tasks")
    
    def get_smart_pending_tasks_batch(self, limit: int = 50, offset: int = 0) -> List[Tuple]:
        """
        Get pending tasks with intelligent filtering to avoid problematic tasks
        """
        self.update_problematic_task_cache()
        
        conn = sqlite3.connect(self.db_path)
        
        # Enhanced query that excludes problematic tasks
        query = """
            SELECT id, endpoint, payload_json, task_id, status, retry_count, created_at
            FROM tasks 
            WHERE (
                -- New tasks without task_id
                (task_id = '' OR task_id IS NULL)
                OR 
                -- Existing tasks that are not problematic
                (
                    task_id != '' 
                    AND task_id IS NOT NULL
                    AND status NOT IN ('SUCCESS', 'FAILED', 'RUNNING', 'PAUSED')
                    AND (retry_count IS NULL OR retry_count < ?)
                )
            )
            AND status != 'FAILED'
            ORDER BY 
                CASE 
                    WHEN task_id = '' OR task_id IS NULL THEN 0  -- Prioritize new tasks
                    ELSE 1 
                END,
                created_at ASC  -- Oldest first
            LIMIT ? OFFSET ?
        """
        
        cursor = conn.execute(query, (self.max_retries, limit, offset))
        tasks = cursor.fetchall()
        conn.close()
        
        # Filter out cached problematic tasks
        filtered_tasks = []
        skipped_failed = 0
        skipped_retry = 0
        
        for task in tasks:
            task_id = task[3]  # task_id is at index 3
            
            # Skip if task is in failed cache
            if task_id and task_id in self.failed_task_cache:
                skipped_failed += 1
                continue
            
            # Skip if task is in retry cache
            if task_id and task_id in self.retry_task_cache:
                skipped_retry += 1
                continue
            
            filtered_tasks.append(task)
        
        if skipped_failed > 0 or skipped_retry > 0:
            print(f"🚫 Skipped {skipped_failed} failed and {skipped_retry} retry tasks")
        
        return filtered_tasks
    
    def mark_task_as_problematic(self, task_id: str, reason: str = "failed"):
        """Mark a task as problematic to avoid it in future selections"""
        if reason == "failed":
            self.failed_task_cache.add(task_id)
            print(f"❌ Marked task as failed: {task_id}")
        elif reason == "retry":
            self.retry_task_cache.add(task_id)
            print(f"🔄 Marked task as retry: {task_id}")
    
    def clean_problematic_caches(self):
        """Clean up problematic task caches"""
        self.failed_task_cache.clear()
        self.retry_task_cache.clear()
        self.last_cache_update = 0
        print("🧹 Cleaned problematic task caches")
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get statistics about cached problematic tasks"""
        return {
            'failed_tasks': len(self.failed_task_cache),
            'retry_tasks': len(self.retry_task_cache),
            'cache_age_seconds': int(time.time() - self.last_cache_update)
        }


def create_enhanced_task_selector(db_path: str, max_retries: int = 3) -> EnhancedTaskSelector:
    """Factory function to create an enhanced task selector"""
    return EnhancedTaskSelector(db_path, max_retries)


# Utility functions for backward compatibility
def get_smart_pending_tasks_batch(db_path: str, limit: int = 50, offset: int = 0, max_retries: int = 3) -> List[Tuple]:
    """
    Standalone function to get smart pending tasks batch
    """
    selector = EnhancedTaskSelector(db_path, max_retries)
    return selector.get_smart_pending_tasks_batch(limit, offset)


def update_task_status_with_smart_detection(db_path: str, task_db_id: int, task_id: str = None, 
                                          status: str = None, retry_count: int = None):
    """
    Enhanced task status update with smart detection of problematic tasks
    """
    conn = sqlite3.connect(db_path)
    
    # Build update query dynamically
    updates = []
    params = []
    
    if task_id is not None:
        updates.append("task_id = ?")
        params.append(task_id)
    
    if status is not None:
        updates.append("status = ?")
        params.append(status)
        
        # If marking as failed, also update failure timestamp
        if status == 'FAILED':
            updates.append("failed_at = ?")
            params.append(datetime.now().isoformat())
    
    if retry_count is not None:
        updates.append("retry_count = ?")
        params.append(retry_count)
    
    # Always update the updated_at timestamp
    updates.append("updated_at = ?")
    params.append(datetime.now().isoformat())
    
    # Add the WHERE clause parameter
    params.append(task_db_id)
    
    query = f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?"
    
    try:
        conn.execute(query, params)
        conn.commit()
        
        # Log significant status changes
        if status in ['FAILED', 'SUCCESS']:
            print(f"📊 Task {task_db_id} marked as {status}")
            
    except Exception as e:
        print(f"❌ Error updating task {task_db_id}: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    # Test the enhanced task selector
    import sys
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
        selector = EnhancedTaskSelector(db_path)
        
        print("🧪 Testing Enhanced Task Selector")
        print(f"Database: {db_path}")
        
        # Get cache stats
        stats = selector.get_cache_stats()
        print(f"Cache Stats: {stats}")
        
        # Get smart batch
        tasks = selector.get_smart_pending_tasks_batch(limit=10)
        print(f"Retrieved {len(tasks)} smart tasks")
        
        for i, task in enumerate(tasks[:3]):  # Show first 3
            print(f"  Task {i+1}: ID={task[0]}, Status={task[4]}, TaskID={task[3]}")
    else:
        print("Usage: python enhanced_task_selector.py <db_path>")
