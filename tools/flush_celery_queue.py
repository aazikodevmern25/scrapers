#!/usr/bin/env python3
"""
Flush Celery Queue - Clear all pending tasks from Redis
"""

import os
import redis
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Redis configuration
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_DB = 0

# Get from environment or use defaults
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')

def parse_redis_url(url):
    """Parse Redis URL to get host, port, db"""
    # redis://localhost:6379/0
    parts = url.replace('redis://', '').split('/')
    host_port = parts[0].split(':')
    host = host_port[0]
    port = int(host_port[1]) if len(host_port) > 1 else 6379
    db = int(parts[1]) if len(parts) > 1 else 0
    return host, port, db

def flush_celery_queues():
    """Flush all Celery queues and terminate active tasks"""
    try:
        # Parse Redis URL
        host, port, db = parse_redis_url(CELERY_BROKER_URL)
        
        print(f"🔗 Connecting to Redis: {host}:{port}/{db}")
        
        # Connect to Redis
        r = redis.Redis(host=host, port=port, db=db, decode_responses=True)
        
        # Test connection
        r.ping()
        print("✅ Connected to Redis successfully!")
        
        # Get all keys
        all_keys = r.keys('*')
        print(f"\n📊 Found {len(all_keys)} total keys in Redis")
        
        # Find Celery-related keys
        celery_keys = []
        queue_keys = []
        result_keys = []
        
        for key in all_keys:
            if 'celery' in key.lower():
                celery_keys.append(key)
                if 'celery-task-meta' in key:
                    result_keys.append(key)
                else:
                    queue_keys.append(key)
        
        print(f"\n🔍 Found Celery keys:")
        print(f"   • Queue keys: {len(queue_keys)}")
        print(f"   • Result keys: {len(result_keys)}")
        
        # Show queue names
        if queue_keys:
            print(f"\n📋 Queue keys:")
            for key in queue_keys[:10]:  # Show first 10
                queue_length = r.llen(key) if r.type(key) == 'list' else 'N/A'
                print(f"   • {key}: {queue_length} items")
            if len(queue_keys) > 10:
                print(f"   ... and {len(queue_keys) - 10} more")
        
        # Ask for confirmation
        print("\n⚠️  This will:")
        print("   • TERMINATE all active/running tasks")
        print("   • DELETE all pending tasks from queue")
        print("   • Clear all task results")
        print("\n   This action cannot be undone!")
        response = input("\n❓ Are you sure you want to continue? (yes/no): ")
        
        if response.lower() != 'yes':
            print("❌ Aborted. No changes made.")
            return
        
        # Step 1: Revoke all active tasks using Celery
        print("\n🛑 Terminating active tasks...")
        try:
            from celery import Celery
            celery_app = Celery('scraper', 
                              broker=CELERY_BROKER_URL,
                              backend=CELERY_BROKER_URL.replace('redis://', 'redis://'))
            
            # Get active tasks
            inspect = celery_app.control.inspect()
            active = inspect.active()
            
            if active:
                active_count = sum(len(tasks) for tasks in active.values())
                print(f"   Found {active_count} active tasks")
                
                # Revoke all active tasks
                for worker, tasks in active.items():
                    for task in tasks:
                        task_id = task.get('id')
                        if task_id:
                            celery_app.control.revoke(task_id, terminate=True, signal='SIGKILL')
                            print(f"   ✓ Terminated task: {task_id[:8]}...")
                
                print(f"✅ Terminated {active_count} active tasks")
            else:
                print("   No active tasks found")
        except Exception as e:
            print(f"   ⚠️  Could not terminate active tasks: {e}")
        
        # Step 2: Delete queue keys
        deleted_count = 0
        if queue_keys:
            print(f"\n🗑️  Deleting {len(queue_keys)} queue keys...")
            for key in queue_keys:
                r.delete(key)
                deleted_count += 1
            print(f"✅ Deleted {deleted_count} queue keys")
        
        # Step 3: Delete result keys
        if result_keys:
            print(f"\n🗑️  Deleting {len(result_keys)} result keys...")
            result_deleted = 0
            for key in result_keys:
                r.delete(key)
                result_deleted += 1
            print(f"✅ Deleted {result_deleted} result keys")
        
        print(f"\n🎉 Successfully flushed all tasks!")
        print(f"   • Active tasks terminated")
        print(f"   • Queue keys deleted: {deleted_count}")
        print(f"   • Result keys deleted: {len(result_keys)}")
        
    except redis.ConnectionError as e:
        print(f"❌ Redis connection error: {e}")
        print("   Make sure Redis is running on the correct port")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def show_queue_stats():
    """Show statistics about Celery queues"""
    try:
        # Parse Redis URL
        host, port, db = parse_redis_url(CELERY_BROKER_URL)
        
        print(f"🔗 Connecting to Redis: {host}:{port}/{db}")
        
        # Connect to Redis
        r = redis.Redis(host=host, port=port, db=db, decode_responses=True)
        
        # Test connection
        r.ping()
        print("✅ Connected to Redis successfully!")
        
        # Get all keys
        all_keys = r.keys('*')
        
        # Find queue keys
        queue_keys = [k for k in all_keys if 'celery' in k.lower() and 'celery-task-meta' not in k]
        result_keys = [k for k in all_keys if 'celery-task-meta' in k]
        
        print(f"\n📊 Celery Queue Statistics:")
        print(f"=" * 60)
        
        if queue_keys:
            total_tasks = 0
            for key in queue_keys:
                if r.type(key) == 'list':
                    length = r.llen(key)
                    total_tasks += length
                    print(f"   Queue: {key}")
                    print(f"   Tasks: {length}")
                    print(f"   {'-' * 58}")
            print(f"\n   Total pending tasks: {total_tasks}")
        else:
            print("   No queues found (all empty)")
        
        if result_keys:
            print(f"\n   Stored results: {len(result_keys)}")
        else:
            print(f"\n   No task results stored")
        
        print(f"=" * 60)
        
    except redis.ConnectionError as e:
        print(f"❌ Redis connection error: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    import sys
    
    print("=" * 60)
    print("  🔥 Celery Queue Flusher")
    print("=" * 60)
    
    if len(sys.argv) > 1 and sys.argv[1] == '--stats':
        show_queue_stats()
    else:
        print("\nOptions:")
        print("  1. Flush all Celery queues (DELETE all pending tasks)")
        print("  2. Show queue statistics")
        print("  3. Exit")
        
        choice = input("\nEnter your choice (1-3): ")
        
        if choice == '1':
            flush_celery_queues()
        elif choice == '2':
            show_queue_stats()
        elif choice == '3':
            print("👋 Exiting...")
        else:
            print("❌ Invalid choice")

