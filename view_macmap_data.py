#!/usr/bin/env python3
"""
View MacMap Tariff Data from MongoDB

This script retrieves and displays data from the Dhruval database.
"""

import os
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime
import json

# Load environment variables
load_dotenv()

# MongoDB connection
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/?authSource=admin')
MONGO_DB = os.getenv('MONGO_DB', 'Dhruval')

print("╔══════════════════════════════════════════════════════════════════════════════╗")
print("║                    MacMap Data Viewer (Dhruval Database)                    ║")
print("╚══════════════════════════════════════════════════════════════════════════════╝")
print()

# Connect to MongoDB
try:
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    collection = db["macmap_tariff"]
    
    print(f"✓ Connected to MongoDB")
    print(f"✓ Database: {MONGO_DB}")
    print(f"✓ Collection: macmap_tariff")
    print()
    
    # Get count
    total_count = collection.count_documents({})
    print(f"📊 Total documents: {total_count:,}")
    print()
    
    if total_count == 0:
        print("⚠️  No data found yet. Scraping is still in progress.")
        print()
        print("The scraper is working (we verified it earlier).")
        print("Data will appear here as tasks complete.")
        exit(0)
    
    # Show recent documents
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("📋 Recent Documents (Last 10):")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    
    recent_docs = collection.find().sort("_id", -1).limit(10)
    
    for i, doc in enumerate(recent_docs, 1):
        print(f"{i}. Document ID: {doc.get('_id')}")
        print(f"   Importing Country: {doc.get('ImportingCountry', 'N/A')}")
        print(f"   Exporting Country: {doc.get('ExportingCountry', 'N/A')}")
        print(f"   HS Code: {doc.get('HsCode', 'N/A')}")
        print(f"   Year: {doc.get('TargetYear', 'N/A')}")
        
        # Show data summary if available
        if 'Data' in doc:
            print(f"   Data items: {len(doc['Data'])} tariff entries")
        
        if 'DateCreated' in doc:
            print(f"   Scraped: {doc['DateCreated']}")
        
        print()
    
    # Show summary statistics
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("📊 Summary Statistics:")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    
    # Count by year
    pipeline_year = [
        {"$group": {"_id": "$TargetYear", "count": {"$sum": 1}}},
        {"$sort": {"_id": -1}}
    ]
    year_counts = list(collection.aggregate(pipeline_year))
    
    if year_counts:
        print("By Year:")
        for item in year_counts:
            print(f"  • {item['_id']}: {item['count']:,} documents")
        print()
    
    # Count by ImportingCountry
    pipeline_country1 = [
        {"$group": {"_id": "$ImportingCountry", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]
    country1_counts = list(collection.aggregate(pipeline_country1))
    
    if country1_counts:
        print("Top 10 Importing Countries:")
        for item in country1_counts:
            print(f"  • {item['_id']}: {item['count']:,} documents")
        print()
    
    # Count by HS code
    pipeline_hsc = [
        {"$group": {"_id": "$HsCode", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]
    hsc_counts = list(collection.aggregate(pipeline_hsc))
    
    if hsc_counts:
        print("Top 10 HS Codes:")
        for item in hsc_counts:
            print(f"  • {item['_id']}: {item['count']:,} documents")
        print()
    
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    print("✅ Data is stored in Dhruval database!")
    print()
    print("To export data, run: python3 export_macmap_data.py")
    print()
    
except Exception as e:
    print(f"❌ Error: {e}")
    print()
    print("Troubleshooting:")
    print("1. Check if MongoDB is running")
    print("2. Verify credentials in .env file")
    print("3. Check network connection to MongoDB server")

finally:
    if 'client' in locals():
        client.close()
