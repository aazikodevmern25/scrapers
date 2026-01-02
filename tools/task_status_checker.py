#!/usr/bin/env python3
"""
Task Status Checker - Utility to check if tasks should be paused
"""

import sqlite3
import os
from typing import Optional

def check_task_should_pause(task_id: str) -> bool:
    """
    Check if a task should be paused by looking up its status in the database
    
    Args:
        task_id: The Celery task ID
        
    Returns:
        True if the task should be paused, False otherwise
    """
    if not task_id:
        return False
    
    # Check all possible database paths
    db_paths = [
        'task_creator/competitors_tasks.db',
        'task_creator/macmapTariff_tasks.db',
        'task_creator/macmapproduct_tasks.db',
        'task_creator/comparemarket_tasks.db',
        'task_creator/fulltariff_tasks.db',
        'task_creator/tradeMap_tasks.db',
        'task_creator/eximPedia_tasks.db'
    ]
    
    for db_path in db_paths:
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.execute(
                    "SELECT status FROM tasks WHERE task_id = ? LIMIT 1",
                    (task_id,)
                )
                result = cursor.fetchone()
                conn.close()
                
                if result and result[0] == 'PAUSED':
                    return True
            except Exception:
                continue
    
    return False

def get_task_status(task_id: str) -> Optional[str]:
    """
    Get the current status of a task from the database
    
    Args:
        task_id: The Celery task ID
        
    Returns:
        The task status or None if not found
    """
    if not task_id:
        return None
    
    # Check all possible database paths
    db_paths = [
        'task_creator/competitors_tasks.db',
        'task_creator/macmapTariff_tasks.db',
        'task_creator/macmapproduct_tasks.db',
        'task_creator/comparemarket_tasks.db',
        'task_creator/fulltariff_tasks.db',
        'task_creator/tradeMap_tasks.db',
        'task_creator/eximPedia_tasks.db'
    ]
    
    for db_path in db_paths:
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.execute(
                    "SELECT status FROM tasks WHERE task_id = ? LIMIT 1",
                    (task_id,)
                )
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    return result[0]
            except Exception:
                continue
    
    return None

class TaskPausedException(Exception):
    """Exception raised when a task is paused"""
    pass