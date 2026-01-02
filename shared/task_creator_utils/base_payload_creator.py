#!/usr/bin/env python3
"""
Base Payload Creator - MongoDB Version
High-Performance Payload Creator with all features from SQLite version
"""

import json
import time
import os
import sys
import itertools
from datetime import datetime
from typing import Dict, List, Any, Callable, Generator

# Add parent directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
data_extractor_dir = os.path.dirname(os.path.dirname(script_dir))
if data_extractor_dir not in sys.path:
    sys.path.insert(0, data_extractor_dir)

from shared.task_creator_utils.mongodb_base import MongoDBScraperBase, get_database


class BasePayloadCreator:
    """Base class for all MongoDB-based payload creators with high-performance features"""
    
    def __init__(self, scraper_id: str, scraper_name: str, 
                 unique_fields: List[str], endpoint: str):
        """
        Initialize payload creator
        
        Args:
            scraper_id: Scraper identifier (e.g., 'indiantradeportal')
            scraper_name: Display name (e.g., 'IndianTradePortal')
            unique_fields: Fields that uniquely identify a task
            endpoint: API endpoint for the scraper
        """
        self.scraper_id = scraper_id
        self.scraper_name = scraper_name
        self.unique_fields = unique_fields
        self.endpoint = endpoint
        self.batch_size = int(os.environ.get('BATCH_SIZE', '100'))
        
        # Get database instance
        self.db = MongoDBScraperBase("scraper_tasks", scraper_name)
        self._ensure_schema()
    
    def _ensure_schema(self):
        """Ensure database schema and indexes are correct"""
        self.db.ensure_schema(self.unique_fields)
        print(f"✅ {self.scraper_name} MongoDB database initialized")
    
    def get_database_stats(self) -> Dict:
        """Get database statistics"""
        stats = self.db.get_database_stats()
        
        # Get breakdown by first unique field
        try:
            db = get_database()
            collection = db["scraper_tasks"]
            
            pipeline = [
                {"$match": {"scraper": self.scraper_name}},
                {"$group": {
                    "_id": f"$payload.{self.unique_fields[0]}",
                    "count": {"$sum": 1},
                    "pending": {"$sum": {"$cond": [
                        {"$or": [
                            {"$eq": ["$task_id", ""]},
                            {"$ne": ["$status", "SUCCESS"]}
                        ]}, 1, 0
                    ]}}
                }},
                {"$limit": 10}
            ]
            
            field_stats = list(collection.aggregate(pipeline))
            stats['by_field'] = {item['_id']: {'total': item['count'], 'pending': item['pending']} 
                                for item in field_stats if item['_id']}
        except:
            stats['by_field'] = {}
        
        return stats
    
    def check_existing_combination(self, **kwargs) -> bool:
        """Check if a combination already exists"""
        result = self.db.check_payload_exists(kwargs)
        return result.get('exists', False)

    def insert_payload(self, payload: Dict) -> bool:
        """Insert a single payload"""
        result = self.db.insert_task(self.endpoint, payload)
        return result is not None
    
    def batch_insert_payloads(self, payloads: List[Dict]) -> int:
        """Insert multiple payloads efficiently"""
        tasks_data = [(self.endpoint, payload) for payload in payloads]
        return self.db.insert_tasks_batch(tasks_data)
    
    def cleanup_duplicates(self) -> int:
        """Remove duplicate entries"""
        return self.db.cleanup_duplicates()
    
    def print_header(self, title: str):
        """Print formatted header"""
        print(f"\n{'='*80}")
        print(f"  {title}")
        print(f"{'='*80}")
    
    def print_stats(self, stats: Dict, title: str = None):
        """Print formatted statistics"""
        title = title or f"{self.scraper_name} Database Summary"
        print(f"\n📊 {title}:")
        print(f"   Total: {stats.get('total_tasks', 0):,} tasks")
        print(f"   ✅ Completed: {stats.get('completed_tasks', 0):,}")
        print(f"   ⏳ Pending: {stats.get('pending_tasks', 0):,}")
        print(f"   ❌ Failed: {stats.get('failed_tasks', 0):,}")
        
        if stats.get('by_field'):
            print(f"\n📋 By {self.unique_fields[0]}:")
            for field, counts in list(stats['by_field'].items())[:5]:
                print(f"   {field}: {counts['total']:,} total ({counts['pending']:,} pending)")
    
    def show_stats(self):
        """Display current database statistics"""
        stats = self.get_database_stats()
        self.print_stats(stats, f"Current {self.scraper_name} Status")
    
    def create_payloads_from_params(self, **params):
        """
        Create payloads from parameter combinations - Ultra-fast mode
        
        Args:
            **params: Dictionary of field_name -> list of values
        """
        start_time = time.time()
        
        self.print_header(f"🚀 {self.scraper_name} Payload Creation (ULTRA FAST MODE)")
        
        # Calculate total combinations
        total_combinations = 1
        for field in self.unique_fields:
            field_values = params.get(field, [])
            if isinstance(field_values, str):
                field_values = [field_values]
            total_combinations *= len(field_values)
            print(f"{field.replace('_', ' ').title()}: {len(field_values)} selected")
        
        print(f"Total combinations: {total_combinations:,}")
        
        # Prepare batch insert data
        payloads_batch = []
        processed_count = 0
        inserted_count = 0
        
        print(f"\n📊 Processing {total_combinations:,} combinations...")
        
        # Generate all combinations
        field_values_list = []
        for field in self.unique_fields:
            values = params.get(field, [])
            if isinstance(values, str):
                values = [values]
            field_values_list.append(values)
        
        for combo in itertools.product(*field_values_list):
            payload = dict(zip(self.unique_fields, combo))
            payloads_batch.append(payload)
            processed_count += 1
            
            # Batch insert every BATCH_SIZE records
            if len(payloads_batch) >= self.batch_size:
                try:
                    inserted = self.batch_insert_payloads(payloads_batch)
                    inserted_count += inserted
                    
                    elapsed = time.time() - start_time
                    rate = processed_count / elapsed if elapsed > 0 else 0
                    eta = (total_combinations - processed_count) / rate if rate > 0 else 0
                    progress = (processed_count / total_combinations) * 100
                    
                    if inserted > 0:
                        print(f"📊 Progress: {processed_count:,}/{total_combinations:,} ({progress:.1f}%) | "
                              f"Inserted: {inserted} | Rate: {rate:.0f}/s | ETA: {eta:.0f}s")
                    
                    payloads_batch = []
                except Exception as e:
                    print(f"❌ Error inserting batch: {e}")
                    raise
        
        # Insert remaining payloads
        if payloads_batch:
            try:
                inserted = self.batch_insert_payloads(payloads_batch)
                inserted_count += inserted
                if inserted > 0:
                    print(f"📊 Inserted final batch of {inserted} payloads")
            except Exception as e:
                print(f"❌ Error inserting final batch: {e}")
        
        # Performance summary
        processing_time = time.time() - start_time
        
        self.print_header(f"🎉 {self.scraper_name} Payload Creation Complete")
        
        final_stats = self.get_database_stats()
        self.print_stats(final_stats, f"Final {self.scraper_name} Results")
        
        print(f"\n⚡ Performance Summary:")
        print(f"   ⏱️  Total Processing Time: {processing_time:.1f} seconds")
        print(f"   🚀 Combinations Processed: {processed_count:,}")
        print(f"   ✅ New Payloads Inserted: {inserted_count:,}")
        if processing_time > 0:
            print(f"   💻 Processing Rate: {processed_count/processing_time:.0f} combinations/second")
        print(f"   📊 Final Database Size: {final_stats.get('total_tasks', 0):,} tasks")
    
    @staticmethod
    def get_single_input(prompt: str) -> str:
        """Get single value input with validation"""
        return input(f"{prompt}: ").strip()
    
    @staticmethod
    def get_list_input(prompt: str) -> List[str]:
        """Get comma-separated list input"""
        value = input(f"{prompt} (comma-separated): ").strip()
        return [item.strip() for item in value.split(',') if item.strip()]
    
    def run_interactive(self, field_prompts: Dict[str, str] = None):
        """Run interactive payload creation"""
        self.print_header(f"🚀 {self.scraper_name} Payload Creator (MongoDB)")
        
        # Show current stats
        self.show_stats()
        
        print("\n🔧 Choose an option:")
        print("1. Interactive payload creation")
        print("2. Show database statistics")
        print("3. Cleanup duplicates")
        print("4. Exit")
        
        choice = input("\nEnter choice (1-4): ").strip()
        
        if choice == '1':
            try:
                params = {}
                field_prompts = field_prompts or {}
                
                print("\n📝 Please provide the following information:")
                for field in self.unique_fields:
                    prompt = field_prompts.get(field, field.replace('_', ' ').title())
                    params[field] = self.get_list_input(prompt)
                
                # Confirm before proceeding
                print("\n📋 Configuration Summary:")
                total_combinations = 1
                for field, values in params.items():
                    print(f"   {field.replace('_', ' ').title()}: {len(values)} items")
                    total_combinations *= len(values)
                
                print(f"\n🎯 Total combinations to create: {total_combinations:,}")
                
                confirm = input("\n▶️  Proceed with payload creation? (y/n): ").strip().lower()
                if confirm == 'y':
                    self.create_payloads_from_params(**params)
                    
            except KeyboardInterrupt:
                print("\n❌ Operation cancelled by user")
            except Exception as e:
                print(f"❌ Error: {e}")
                import traceback
                traceback.print_exc()
                
        elif choice == '2':
            self.show_stats()
        
        elif choice == '3':
            print("\n🧹 Cleaning up duplicates...")
            removed = self.cleanup_duplicates()
            print(f"✅ Removed {removed} duplicate entries")
            self.show_stats()
        
        elif choice == '4':
            print("👋 Goodbye!")
        
        else:
            print("❌ Invalid choice")
    
    def create_payloads_programmatic(self, payloads: List[Dict]):
        """
        Create payloads programmatically (for API calls)
        
        Args:
            payloads: List of payload dictionaries
        """
        start_time = time.time()
        
        print(f"📊 Creating {len(payloads)} payloads for {self.scraper_name}...")
        
        inserted_count = 0
        for i in range(0, len(payloads), self.batch_size):
            batch = payloads[i:i + self.batch_size]
            inserted = self.batch_insert_payloads(batch)
            inserted_count += inserted
        
        processing_time = time.time() - start_time
        
        print(f"✅ Created {inserted_count} payloads in {processing_time:.1f}s")
        return inserted_count
