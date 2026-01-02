#!/usr/bin/env python3
"""
Fetch and Cache MacMap HS Codes for a Country

This script fetches all 8-digit HS codes from MacMap API for a specific country
and caches them in MongoDB for fast lookup during scraping.

Usage:
    python tools/fetch_macmap_hscodes.py --country India
    python tools/fetch_macmap_hscodes.py --country-code 699
    python tools/fetch_macmap_hscodes.py --all  # Fetch for all countries
"""

import sys
import os
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv

# Add parent directory to path
script_dir = Path(__file__).parent
data_extractor_dir = script_dir.parent
if str(data_extractor_dir) not in sys.path:
    sys.path.insert(0, str(data_extractor_dir))

from utils import SendGetRequests

# Load environment
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# MongoDB connection
MONGO_URI = os.getenv('MONGO_URI')
MONGO_DB = os.getenv('MONGO_DB', 'jaimish_data')

# MacMap headers
headers = """Accept: application/json, text/javascript, */*; q=0.01
Accept-Encoding: gzip, deflate, br, zstd
Accept-Language: en-GB,en-US;q=0.9,en;q=0.8
Cache-Control: no-cache
Connection: keep-alive
Content-Type: application/json; charset=utf-8
DNT: 1
Host: www.macmap.org
Pragma: no-cache
Referer: https://www.macmap.org/
Sec-Fetch-Dest: empty
Sec-Fetch-Mode: cors
Sec-Fetch-Site: same-origin
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36
X-Requested-With: XMLHttpRequest
sec-ch-ua: "Google Chrome";v="131", "Not-A.Brand";v="8", "Chromium";v="131"
sec-ch-ua-mobile: ?0
sec-ch-ua-platform: "Windows"
"""

def parse_headers(headers_str):
    """Parse headers string into dict"""
    headers_dict = {}
    for line in headers_str.strip().split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            headers_dict[key.strip()] = value.strip()
    return headers_dict

def load_countries():
    """Load MacMap countries mapping"""
    countries_file = data_extractor_dir / "scrapers" / "macmap" / "macmap_countries" / "countries.json"
    with open(countries_file, 'r', encoding='utf-8') as f:
        countries_list = json.load(f)
    return {item['Name']: item['Code'] for item in countries_list}

def get_country_code(country_name, countries_map):
    """Get country code from name"""
    if country_name in countries_map:
        return countries_map[country_name]
    else:
        logger.error(f"Country not found: {country_name}")
        return None

def fetch_hscodes_for_country(country_code, country_name):
    """
    Fetch all 8-digit HS codes for a country from MacMap API
    
    Args:
        country_code: MacMap country code (e.g., "699" for India)
        country_name: Country name for logging
        
    Returns:
        List of dicts with 'code' and 'name' keys
    """
    logger.info(f"Fetching HS codes for {country_name} (code: {country_code})")
    
    headers_dict = parse_headers(headers)
    all_hscodes = {}  # Store as dict with code: name
    
    try:
        # Use the NTM products endpoint for regulatory HS codes
        # reporterCode = destination/importing country (the country whose regulations we're checking)
        products_url = f'https://www.macmap.org/api/ntm-products?reporterCode={country_code}&level=8'
        logger.info(f"Fetching HS codes from: {products_url}")
        
        products_req = SendGetRequests(products_url, headers_dict)
        
        if products_req.status_code == 200:
            products = products_req.json()
            logger.info(f"Found {len(products)} products")
            
            # Debug: Check first few products
            if products:
                logger.info(f"Sample products (first 3):")
                for i, product in enumerate(products[:3], 1):
                    code = product.get('Code', 'N/A')
                    name = product.get('Name', 'N/A')
                    logger.info(f"  {i}. Code: '{code}' (len={len(code) if code else 0}) - {name[:50]}")
            
            for product in products:
                code = product.get('Code')
                name = product.get('Name', '')
                # Accept all HS codes regardless of length (8, 10, or more digits)
                if code:
                    all_hscodes[code] = name
            
            logger.info(f"Collected {len(all_hscodes)} unique HS codes with descriptions")
        else:
            logger.error(f"Failed to fetch products. Status: {products_req.status_code}")
        
        # Convert to list of objects
        return [{'code': code, 'name': name} for code, name in sorted(all_hscodes.items())]
        
    except Exception as e:
        logger.error(f"Error fetching HS codes: {e}", exc_info=True)
        return []

def cache_hscodes_in_mongodb(country_code, country_name, hscodes):
    """
    Cache HS codes in MongoDB
    
    Args:
        country_code: MacMap country code
        country_name: Country name
        hscodes: List of dicts with 'code' and 'name' keys
    """
    try:
        client = MongoClient(MONGO_URI)
        db = client[MONGO_DB]
        collection = db['macmap_hscodes_cache']
        
        # Check if cache already exists
        existing = collection.find_one({'reporter_code': country_code})
        
        doc = {
            'reporter_code': country_code,
            'country_name': country_name,
            'hscodes': hscodes,  # Now list of {code, name} objects
            'cached_at': datetime.utcnow(),
            'total_codes': len(hscodes),
            'source': 'macmap_api'  # Mark as fetched from API
        }
        
        if existing:
            logger.info(f"Updating existing cache for {country_name}")
            collection.update_one(
                {'reporter_code': country_code},
                {'$set': doc}
            )
        else:
            logger.info(f"Creating new cache for {country_name}")
            collection.insert_one(doc)
        
        logger.info(f"✅ Cached {len(hscodes)} HS codes with descriptions for {country_name} (code: {country_code})")
        
    except Exception as e:
        logger.error(f"Error caching HS codes: {e}", exc_info=True)

def main():
    parser = argparse.ArgumentParser(description='Fetch and cache MacMap HS codes')
    parser.add_argument('--country', help='Country name (e.g., "India")')
    parser.add_argument('--country-code', help='MacMap country code (e.g., "699")')
    parser.add_argument('--all', action='store_true', help='Fetch for all countries')
    parser.add_argument('--list-countries', action='store_true', help='List all available countries')
    
    args = parser.parse_args()
    
    # Load countries
    countries_map = load_countries()
    
    if args.list_countries:
        print("\n=== Available Countries ===")
        for name, code in sorted(countries_map.items()):
            print(f"{name}: {code}")
        return
    
    if args.all:
        logger.info("Fetching HS codes for all countries...")
        for country_name, country_code in countries_map.items():
            logger.info(f"\n{'='*60}")
            logger.info(f"Processing: {country_name}")
            logger.info(f"{'='*60}")
            
            hscodes = fetch_hscodes_for_country(country_code, country_name)
            if hscodes:
                cache_hscodes_in_mongodb(country_code, country_name, hscodes)
            else:
                logger.warning(f"No HS codes found for {country_name}")
        
        logger.info("\n✅ Completed fetching HS codes for all countries")
        
    elif args.country:
        country_code = get_country_code(args.country, countries_map)
        if country_code:
            hscodes = fetch_hscodes_for_country(country_code, args.country)
            if hscodes:
                cache_hscodes_in_mongodb(country_code, args.country, hscodes)
            else:
                logger.error(f"Failed to fetch HS codes for {args.country}")
        
    elif args.country_code:
        # Find country name from code
        country_name = None
        for name, code in countries_map.items():
            if code == args.country_code:
                country_name = name
                break
        
        if country_name:
            hscodes = fetch_hscodes_for_country(args.country_code, country_name)
            if hscodes:
                cache_hscodes_in_mongodb(args.country_code, country_name, hscodes)
        else:
            logger.error(f"Country code not found: {args.country_code}")
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
