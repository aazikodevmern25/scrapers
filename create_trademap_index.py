#!/usr/bin/env python3
"""
Create unique index for TradeMap collection to prevent duplicates
Unique combination: HsCode + Country1 + Country2 + Mode
"""

from pymongo import MongoClient, ASCENDING
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MongoDB connection
MONGO_URI = os.getenv('MONGO_URI')
MONGO_DB = os.getenv('MONGO_DB', 'Dhruval')

print("=" * 70)
print("Creating Unique Index for TradeMap Collection")
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
    
    # Check existing indexes
    print("📋 Current indexes:")
    existing_indexes = collection.list_indexes()
    for idx in existing_indexes:
        print(f"   - {idx['name']}")
    print()
    
    # Create unique compound index
    print("🔧 Creating unique index...")
    print("   Index fields: HsCode + Data.Country1 + Data.Country2 + Mode")
    print()
    
    index_name = collection.create_index(
        [
            ("HsCode", ASCENDING),
            ("Data.Country1", ASCENDING),
            ("Data.Country2", ASCENDING),
            ("Mode", ASCENDING)
        ],
        unique=True,
        name="unique_hscode_country_mode"
    )
    
    print(f"✅ Index created successfully: {index_name}")
    print()
    
    # Verify index
    print("📋 Updated indexes:")
    existing_indexes = collection.list_indexes()
    for idx in existing_indexes:
        print(f"   - {idx['name']}")
        if idx['name'] == 'unique_hscode_country_mode':
            print(f"     Fields: {idx['key']}")
            print(f"     Unique: {idx.get('unique', False)}")
    print()
    
    print("=" * 70)
    print("✅ SUCCESS!")
    print()
    print("This index will:")
    print("  ✅ Prevent duplicate records with same HsCode+Country1+Country2+Mode")
    print("  ✅ Allow same HS code with different modes (Import vs Export)")
    print("  ✅ Improve query performance")
    print("=" * 70)
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
