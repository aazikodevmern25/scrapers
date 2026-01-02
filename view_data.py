#!/usr/bin/env python3
"""
Simple script to view TradeMap scraped data from MongoDB
"""

from pymongo import MongoClient
from datetime import datetime
import json
import os

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/?authSource=admin')
MONGO_DB = os.getenv('MONGO_DB', 'jaimish_data')

def main():
    try:
        # Connect to MongoDB
        client = MongoClient(MONGO_URI)
        db = client[MONGO_DB]
        collection = db['trademap']
        
        print("=" * 70)
        print("TradeMap Scraped Data Viewer".center(70))
        print("=" * 70)
        print()
        
        # Count documents
        count = collection.count_documents({})
        print(f"📊 Total Documents: {count}")
        print()
        
        if count == 0:
            print("⚠️  No data found in database yet.")
            print("Submit a scraping task via the web form!")
            return
        
        print("-" * 70)
        print("📋 Summary of All Scraped Data:")
        print("-" * 70)
        
        # Get all documents
        docs = collection.find({}).sort('DateCreated', -1)
        
        for i, doc in enumerate(docs, 1):
            print(f"\n{i}. HS Code: {doc.get('HsCode', 'N/A')}")
            print(f"   Product: {doc.get('ProductName', 'N/A')}")
            print(f"   Route: {doc.get('Data', {}).get('Country1', 'N/A')} → {doc.get('Data', {}).get('Country2', 'N/A')}")
            print(f"   Mode: {doc.get('Mode', 'N/A')}")
            print(f"   Date: {doc.get('DateCreated', 'N/A')}")
            
            # Show sample data
            data = doc.get('Data', {})
            yearly = data.get('Yearly', {})
            if yearly:
                products = yearly.get('products', [])
                if products and len(products) > 0:
                    first_product = products[0]
                    trades = first_product.get('trades', [])
                    if trades and len(trades) > 0:
                        first_trade = trades[0]
                        trade_data = first_trade.get('data', {})
                        if trade_data:
                            # Show latest year
                            years = sorted(trade_data.keys(), reverse=True)
                            if years:
                                latest_year = years[0]
                                latest_value = trade_data[latest_year]
                                print(f"   Latest Data ({latest_year}): ${latest_value:,}")
        
        print()
        print("-" * 70)
        print()
        
        # Show unique HS codes
        unique_codes = collection.distinct('HsCode')
        print(f"📦 Unique HS Codes: {', '.join(unique_codes)}")
        print()
        
        # Show unique countries
        unique_countries = collection.distinct('Data.Country1')
        print(f"🌍 Reporter Countries: {', '.join(unique_countries)}")
        print()
        
        # Export option
        print("=" * 70)
        print("💾 Export Options:")
        print("=" * 70)
        print("1. Export all to JSON: mongoexport --db=jaimish_data --collection=trademap --out=export.json")
        print("2. View specific HS: mongosh jaimish_data --eval \"db.trademap.find({HsCode: 'YOUR_CODE'}).pretty()\"")
        print("3. Run this script again: python3 view_data.py")
        print()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nMake sure MongoDB is running and the database exists.")

if __name__ == "__main__":
    main()
