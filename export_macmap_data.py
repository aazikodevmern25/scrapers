#!/usr/bin/env python3
"""
Export MacMap Tariff Data from Dhruval Database

This script exports data to CSV, JSON, or Excel formats.
"""

import os
import sys
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime
import json
import pandas as pd

# Load environment variables
load_dotenv()

# MongoDB connection
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/?authSource=admin')
MONGO_DB = os.getenv('MONGO_DB', 'Dhruval')

print("╔══════════════════════════════════════════════════════════════════════════════╗")
print("║                    MacMap Data Export (Dhruval Database)                    ║")
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
        print("⚠️  No data to export yet.")
        print("Scraping is in progress. Data will be available soon.")
        exit(0)
    
    # Get export format
    print("Select export format:")
    print("  1. CSV (Recommended)")
    print("  2. JSON")
    print("  3. Excel (XLSX)")
    print("  4. All formats")
    print()
    
    choice = input("Enter choice (1-4) [default: 1]: ").strip() or "1"
    print()
    
    # Ask for filters
    print("Export filters (press Enter to skip):")
    year_filter = input("  Year (e.g., 2025): ").strip()
    country1_filter = input("  Importing Country (e.g., United States): ").strip()
    country2_filter = input("  Exporting Country (e.g., China): ").strip()
    hsc_filter = input("  HS Code (e.g., 380861): ").strip()
    print()
    
    # Build query
    query = {}
    if year_filter:
        try:
            query['TargetYear'] = int(year_filter)
        except:
            print(f"⚠️  Invalid year: {year_filter}")
    
    if country1_filter:
        query['ImportingCountry'] = {"$regex": country1_filter, "$options": "i"}
    
    if country2_filter:
        query['ExportingCountry'] = {"$regex": country2_filter, "$options": "i"}
    
    if hsc_filter:
        query['HsCode'] = hsc_filter
    
    # Count filtered results
    filtered_count = collection.count_documents(query)
    
    if filtered_count == 0:
        print("❌ No documents match your filters.")
        exit(0)
    
    print(f"✓ Found {filtered_count:,} documents matching filters")
    print()
    print("Exporting data...")
    
    # Fetch data
    cursor = collection.find(query)
    
    # Convert to list of dicts
    data_list = []
    for doc in cursor:
        # Remove MongoDB _id for cleaner export
        doc_dict = {
            'ImportingCountry': doc.get('ImportingCountry'),
            'ExportingCountry': doc.get('ExportingCountry'),
            'TargetYear': doc.get('TargetYear'),
            'HsCode': doc.get('HsCode'),
            'ProductName': doc.get('ProductName'),
            'ScraperName': doc.get('ScraperName'),
            'Source': doc.get('Source'),
            'Data': json.dumps(doc.get('Data', [])),  # Convert list to JSON string
            'DateCreated': str(doc.get('DateCreated', '')),
            'DateUpdated': str(doc.get('DateUpdated', ''))
        }
        data_list.append(doc_dict)
    
    # Create exports directory
    os.makedirs("exports", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Export based on choice
    exported_files = []
    
    if choice in ["1", "4"]:
        # CSV export
        df = pd.DataFrame(data_list)
        csv_file = f"exports/macmap_tariff_{timestamp}.csv"
        df.to_csv(csv_file, index=False)
        exported_files.append(csv_file)
        print(f"✓ Exported to CSV: {csv_file}")
    
    if choice in ["2", "4"]:
        # JSON export
        json_file = f"exports/macmap_tariff_{timestamp}.json"
        with open(json_file, 'w') as f:
            json.dump(data_list, f, indent=2, default=str)
        exported_files.append(json_file)
        print(f"✓ Exported to JSON: {json_file}")
    
    if choice in ["3", "4"]:
        # Excel export
        df = pd.DataFrame(data_list)
        xlsx_file = f"exports/macmap_tariff_{timestamp}.xlsx"
        df.to_excel(xlsx_file, index=False, engine='openpyxl')
        exported_files.append(xlsx_file)
        print(f"✓ Exported to Excel: {xlsx_file}")
    
    print()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("✅ Export Complete!")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    print(f"📁 Exported {filtered_count:,} documents")
    print()
    print("Files created:")
    for f in exported_files:
        file_size = os.path.getsize(f) / 1024 / 1024  # MB
        print(f"  • {f} ({file_size:.2f} MB)")
    print()
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    print()

finally:
    if 'client' in locals():
        client.close()
