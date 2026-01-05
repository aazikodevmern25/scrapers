#!/usr/bin/env python3
"""
Remove duplicate TradeMap records from MongoDB
Keeps the most recent record for each unique combination of:
HsCode + Country1 + Country2 + Mode
"""

from pymongo import MongoClient
import os
from dotenv import load_dotenv
from collections import defaultdict

# Load environment variables
load_dotenv()

# MongoDB connection
MONGO_URI = os.getenv('MONGO_URI')
MONGO_DB = os.getenv('MONGO_DB', 'Dhruval')

print("=" * 70)
print("Removing Duplicate TradeMap Records")
print("=" * 70)
print()

try:
    # Connect to MongoDB
    print(f"🔌 Connecting to MongoDB...")
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    collection = db['trademap']
    
    print(f"✅ Connected to database: {MONGO_DB}")
    print(f"✅ Collection: trademap")
    print()
    
    # Count total records
    total_count = collection.count_documents({})
    print(f"📊 Total records: {total_count}")
    print()
    
    # Find duplicates
    print("🔍 Searching for duplicates...")
    print("   Unique key: HsCode + Data.Country1 + Data.Country2 + Mode")
    print()
    
    # Group records by unique combination
    duplicates_map = defaultdict(list)
    
    all_records = collection.find({}, {
        "_id": 1,
        "HsCode": 1,
        "Data.Country1": 1,
        "Data.Country2": 1,
        "Mode": 1,
        "DateCreated": 1,
        "DateUpdated": 1
    })
    
    for record in all_records:
        # Create unique key
        try:
            hscode = record.get('HsCode', '')
            country1 = record.get('Data', {}).get('Country1', '')
            country2 = record.get('Data', {}).get('Country2', '')
            mode = record.get('Mode', '')
            
            unique_key = f"{hscode}|{country1}|{country2}|{mode}"
            
            duplicates_map[unique_key].append({
                '_id': record['_id'],
                'date_updated': record.get('DateUpdated', record.get('DateCreated')),
                'hscode': hscode,
                'country1': country1,
                'country2': country2,
                'mode': mode
            })
        except Exception as e:
            print(f"⚠️  Skipping malformed record: {record.get('_id')} - {e}")
            continue
    
    # Find duplicates
    duplicate_groups = {k: v for k, v in duplicates_map.items() if len(v) > 1}
    
    if not duplicate_groups:
        print("✅ No duplicates found!")
        print()
        exit(0)
    
    print(f"📊 Found {len(duplicate_groups)} duplicate groups")
    print(f"📊 Total duplicate records: {sum(len(v) - 1 for v in duplicate_groups.values())}")
    print()
    
    # Show sample duplicates
    print("📋 Sample duplicates (first 5):")
    for i, (key, records) in enumerate(list(duplicate_groups.items())[:5]):
        print(f"\n   {i+1}. {key}")
        print(f"      Count: {len(records)} duplicates")
        for rec in records[:3]:
            print(f"        - ID: {rec['_id']}, Updated: {rec['date_updated']}")
    print()
    
    # Ask for confirmation
    response = input(f"⚠️  Delete {sum(len(v) - 1 for v in duplicate_groups.values())} duplicate records? (yes/no): ")
    
    if response.lower() != 'yes':
        print("❌ Operation cancelled.")
        exit(0)
    
    print()
    print("🗑️  Removing duplicates (keeping most recent)...")
    deleted_count = 0
    
    for key, records in duplicate_groups.items():
        # Sort by DateUpdated (most recent first)
        sorted_records = sorted(records, key=lambda x: x['date_updated'], reverse=True)
        
        # Keep the first (most recent), delete the rest
        to_delete = [rec['_id'] for rec in sorted_records[1:]]
        
        if to_delete:
            result = collection.delete_many({'_id': {'$in': to_delete}})
            deleted_count += result.deleted_count
            
            if deleted_count % 100 == 0:
                print(f"   Deleted {deleted_count} records...")
    
    print()
    print(f"✅ Cleanup complete!")
    print(f"   Total deleted: {deleted_count}")
    print(f"   Remaining: {collection.count_documents({})}")
    print()
    
    print("=" * 70)
    print("Next step: Run create_trademap_index.py to create unique index")
    print("=" * 70)
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
