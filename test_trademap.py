#!/usr/bin/env python3
"""
Quick test script for TradeMap scraper
This will directly call the scraper function without Celery
"""

import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scrapers.trademap.trademap import ScrapeTrademap
import logging

# Configure logging to show in console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def main():
    print("=" * 60)
    print("TradeMap Scraper - Direct Test")
    print("=" * 60)
    print()
    
    # Example scraping task
    # You can modify these values
    hscode = '29211'
    country1 = 'United States of America'
    country2 = 'Canada'
    
    print(f"HS Code: {hscode}")
    print(f"Reporter Country: {country1}")
    print(f"Partner Country: {country2}")
    print()
    print("Starting scraper...")
    print("-" * 60)
    
    try:
        ScrapeTrademap(hscode, country1, country2)
        print()
        print("=" * 60)
        print("✅ Scraping completed successfully!")
        print("=" * 60)
        print()
        print("Check MongoDB 'trademap' collection for results:")
        print("  mongo jaimish_data --eval 'db.trademap.find().pretty()'")
        print()
    except Exception as e:
        print()
        print("=" * 60)
        print("❌ Error occurred during scraping!")
        print("=" * 60)
        print(f"Error: {str(e)}")
        print()
        logger.exception("Detailed error:")

if __name__ == "__main__":
    main()
