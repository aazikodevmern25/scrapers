#!/usr/bin/env python3
"""
MongoDB Base Class for High-Performance Scrapers
Drop-in replacement for SQLite with same interface
"""

import json
import threading
import time
import os
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

# MongoDB connection settings from environment
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://202.47.115.6:27017/')
MONGO_DB = os.environ.get('MONGO_DB', 'Dhruval')

# Global connection pool
_mongo_client = None
_client_lock = threading.Lock()


def get_mongo_client():
    """Get or create MongoDB client (connection pooling)"""
    global _mongo_client
    if _mongo_client is None:
        with _client_lock:
            if _mongo_client is None:
                _mongo_client = MongoClient(MONGO_URI, maxPoolSize=50)
    return _mongo_client


def get_database():
    """Get MongoDB database instance"""
    client = get_mongo_client()
    return client[MONGO_DB]


class MongoDBScraperBase:
    """Base class for MongoDB-powered scrapers - same interface as SQLiteScraperBase"""
    
    def __init__(self, collection_name: str, scraper_name: str):
        """
        Initialize MongoDB scraper base
        
        Args:
            collection_name: MongoDB collection name (replaces db_name)
            scraper_name: Name of the scraper for filtering
        """
        self.collection_name = collection_name
        self.scraper_name = scraper_name
        self.db = get_database()
        self.collection = self.db[collection_name]
        self._ensure_indexes()
    
    def _ensure_indexes(self):
        """Create indexes for performance"""
        try:
            # Index for task_id and status queries
            self.collection.create_index([("task_id", ASCENDING), ("status", ASCENDING)])
            # Index for scraper and status queries
            self.collection.create_index([("scraper", ASCENDING), ("status", ASCENDING)])
            # Index for pending tasks query
            self.collection.create_index([
                ("scraper", ASCENDING), 
                ("status", ASCENDING), 
                ("retry_count", ASCENDING)
            ])
        except Exception as e:
            # Indexes might already exist
            pass
    
    def ensure_schema(self, unique_fields: List[str] = None):
        """Ensure database schema is correct and clean up duplicates (like SQLite version)"""
        print(f"🔧 Ensuring schema for {self.scraper_name}...")
        
        # Create unique index if fields provided
        if unique_fields:
            self.add_unique_index(unique_fields)
        
        # Clean up any existing duplicates
        removed = self.cleanup_duplicates()
        if removed > 0:
            print(f"🧹 Removed {removed} {self.scraper_name} duplicate entries")

    def add_unique_index(self, fields: List[str]):
        """Add unique index for specific payload combinations per scraper"""
        index_name = f"idx_unique_{self.scraper_name.lower().replace(' ', '_')}"
        try:
            # Create unique compound index with partial filter to only apply to this scraper
            # This prevents conflicts with other scrapers' indexes
            index_fields = [("scraper", ASCENDING)] + [(f"payload.{field}", ASCENDING) for field in fields]
            
            # Use partialFilterExpression to only apply index to documents from this scraper
            self.collection.create_index(
                index_fields, 
                unique=True, 
                name=index_name,
                partialFilterExpression={"scraper": self.scraper_name}
            )
            print(f"✅ Unique index created for {self.scraper_name}: {[f[0] for f in index_fields]}")
        except Exception as e:
            # Index might already exist - check if it's the right one
            existing_indexes = self.collection.index_information()
            if index_name in existing_indexes:
                print(f"✅ Unique index already exists for {self.scraper_name}")
            else:
                print(f"⚠️  Could not create unique index for {self.scraper_name}: {e}")
    
    def insert_task(self, endpoint: str, payload: Dict) -> Optional[str]:
        """Insert a single task, returns document ID or None if duplicate"""
        try:
            doc = {
                "scraper": self.scraper_name,
                "endpoint": endpoint,
                "payload": payload,
                "payload_json": json.dumps(payload),  # For compatibility
                "task_id": "",
                "status": "pending",
                "retry_count": 0,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            result = self.collection.insert_one(doc)
            return str(result.inserted_id)
        except DuplicateKeyError:
            return None
    
    def insert_tasks_batch(self, tasks_data: List[Tuple[str, Dict]]) -> int:
        """Insert multiple tasks efficiently, skipping duplicates"""
        if not tasks_data:
            return 0
        
        docs = []
        now = datetime.utcnow()
        for endpoint, payload in tasks_data:
            doc = {
                "scraper": self.scraper_name,
                "endpoint": endpoint,
                "payload": payload,
                "payload_json": json.dumps(payload),
                "task_id": "",
                "status": "pending",
                "retry_count": 0,
                "created_at": now,
                "updated_at": now
            }
            docs.append(doc)
        
        try:
            # ordered=False allows continuing after duplicate errors
            result = self.collection.insert_many(docs, ordered=False)
            return len(result.inserted_ids)
        except Exception as e:
            # BulkWriteError contains info about successful inserts
            if hasattr(e, 'details'):
                # Get count of successfully inserted documents
                if 'nInserted' in e.details:
                    inserted = e.details['nInserted']
                    # Count duplicates for logging
                    write_errors = e.details.get('writeErrors', [])
                    dup_count = sum(1 for err in write_errors if err.get('code') == 11000)
                    if dup_count > 0:
                        print(f"   ℹ️  Skipped {dup_count} duplicates")
                    return inserted
            return 0
    
    def get_database_stats(self) -> Dict[str, int]:
        """Get current database statistics"""
        pipeline = [
            {"$match": {"scraper": self.scraper_name}},
            {"$group": {
                "_id": None,
                "total_tasks": {"$sum": 1},
                "completed_tasks": {
                    "$sum": {"$cond": [{"$eq": ["$status", "SUCCESS"]}, 1, 0]}
                },
                "failed_tasks": {
                    "$sum": {"$cond": [{"$eq": ["$status", "FAILED"]}, 1, 0]}
                },
                "pending_tasks": {
                    "$sum": {"$cond": [
                        {"$or": [
                            {"$eq": ["$task_id", ""]},
                            {"$and": [
                                {"$ne": ["$status", "SUCCESS"]},
                                {"$ne": ["$status", "FAILED"]}
                            ]}
                        ]}, 1, 0
                    ]}
                }
            }}
        ]
        
        result = list(self.collection.aggregate(pipeline))
        if result:
            return {
                "total_tasks": result[0].get("total_tasks", 0),
                "completed_tasks": result[0].get("completed_tasks", 0),
                "failed_tasks": result[0].get("failed_tasks", 0),
                "pending_tasks": result[0].get("pending_tasks", 0)
            }
        return {"total_tasks": 0, "completed_tasks": 0, "failed_tasks": 0, "pending_tasks": 0}
    
    def get_pending_tasks_batch(self, limit: int = 100, offset: int = 0) -> List[Tuple]:
        """Get next batch of pending tasks - returns tuples for compatibility"""
        query = {
            "scraper": self.scraper_name,
            "$and": [
                # Task not yet submitted or not completed
                {"$or": [
                    {"task_id": ""},
                    {"task_id": {"$exists": False}},
                    {"status": {"$nin": ["SUCCESS", "FAILED"]}}
                ]},
                # Retry count check
                {"$or": [
                    {"retry_count": {"$exists": False}},
                    {"retry_count": None},
                    {"retry_count": {"$lt": 3}}
                ]}
            ]
        }
        
        cursor = self.collection.find(query).skip(offset).limit(limit)
        
        tasks = []
        for doc in cursor:
            # Return tuple format matching SQLite: (id, endpoint, payload_json, task_id, status, retry_count)
            tasks.append((
                str(doc["_id"]),
                doc.get("endpoint", ""),
                doc.get("payload_json", json.dumps(doc.get("payload", {}))),
                doc.get("task_id", ""),
                doc.get("status", ""),
                doc.get("retry_count", 0)
            ))
        
        return tasks
    
    def update_task_status(self, task_db_id: str, task_id: str = None, 
                          status: str = None, retry_count: int = None):
        """Update task status"""
        from bson import ObjectId
        
        update_doc = {"$set": {"updated_at": datetime.utcnow()}}
        
        if task_id is not None:
            update_doc["$set"]["task_id"] = task_id
        if status is not None:
            update_doc["$set"]["status"] = status
        if retry_count is not None:
            update_doc["$set"]["retry_count"] = retry_count
        
        # Handle both ObjectId and string IDs
        try:
            doc_id = ObjectId(task_db_id) if len(str(task_db_id)) == 24 else task_db_id
        except:
            doc_id = task_db_id
        
        self.collection.update_one({"_id": doc_id}, update_doc)
    
    def check_payload_exists(self, payload_fields: Dict) -> Dict:
        """Check if a specific payload combination exists"""
        query = {"scraper": self.scraper_name}
        for key, value in payload_fields.items():
            query[f"payload.{key}"] = value
        
        doc = self.collection.find_one(query)
        if doc:
            return {
                "exists": True,
                "db_id": str(doc["_id"]),
                "task_id": doc.get("task_id", ""),
                "status": doc.get("status", "")
            }
        return {"exists": False}
    
    def cleanup_duplicates(self) -> int:
        """Remove duplicate entries based on payload content"""
        # Find duplicates by payload_json
        pipeline = [
            {"$match": {"scraper": self.scraper_name}},
            {"$group": {
                "_id": "$payload_json",
                "count": {"$sum": 1},
                "ids": {"$push": "$_id"},
                "first_id": {"$first": "$_id"}
            }},
            {"$match": {"count": {"$gt": 1}}}
        ]
        
        duplicates = list(self.collection.aggregate(pipeline))
        removed_count = 0
        
        for dup in duplicates:
            # Keep the first, remove the rest
            ids_to_remove = [id for id in dup["ids"] if id != dup["first_id"]]
            if ids_to_remove:
                result = self.collection.delete_many({"_id": {"$in": ids_to_remove}})
                removed_count += result.deleted_count
        
        return removed_count
    
    def export_to_json(self, output_file: str) -> int:
        """Export tasks to JSON format for compatibility"""
        cursor = self.collection.find(
            {"scraper": self.scraper_name}
        ).sort("_id", ASCENDING)
        
        tasks = []
        for doc in cursor:
            tasks.append({
                "scrapper": self.scraper_name,
                "endpoint": doc.get("endpoint", ""),
                "payload": doc.get("payload", {}),
                "task_id": doc.get("task_id", "")
            })
        
        with open(output_file, 'w') as f:
            json.dump(tasks, f, indent=4)
        
        return len(tasks)
    
    def print_stats(self, title: str = "Database Summary") -> Dict:
        """Print formatted statistics"""
        stats = self.get_database_stats()
        print(f"\n📊 {title} - {self.scraper_name}:")
        print(f"   Total: {stats['total_tasks']:,} tasks")
        print(f"   ✅ Completed: {stats['completed_tasks']:,}")
        print(f"   ⏳ Pending: {stats['pending_tasks']:,}")
        print(f"   ❌ Failed: {stats.get('failed_tasks', 0):,}")
        
        if stats['total_tasks'] > 0:
            completion_rate = (stats['completed_tasks'] / stats['total_tasks']) * 100
            print(f"   📈 Completion Rate: {completion_rate:.1f}%")
        
        return stats


# Convenience function to get all scraper stats
def get_all_scrapers_stats() -> Dict[str, Dict]:
    """Get stats for all scrapers in the tasks collection"""
    db = get_database()
    
    # Get unique scrapers
    scrapers = db["scraper_tasks"].distinct("scraper")
    
    all_stats = {}
    for scraper in scrapers:
        base = MongoDBScraperBase("scraper_tasks", scraper)
        all_stats[scraper] = base.get_database_stats()
    
    return all_stats
