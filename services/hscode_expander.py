#!/usr/bin/env python3
"""
HS Code Expander Service
Expands 6-digit HS codes to all their 8-digit variants for specific countries
"""
import json
import logging
from pathlib import Path
from typing import List, Dict, Set
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class HSCodeExpander:
    """Service to expand 6-digit HS codes to 8-digit codes for specific countries"""
    
    def __init__(self):
        self.mongo_uri = os.getenv('MONGO_URI')
        self.mongo_db = os.getenv('MONGO_DB', 'jaimish_data')
        self.client = None
        self.db = None
        self._country_caches = {}  # Cache for country-specific HS codes
        self._global_hscodes = None  # Global HS codes from payloads/hscodes.json
        
    def _get_db(self):
        """Get MongoDB database connection"""
        if self.client is None:
            self.client = MongoClient(self.mongo_uri)
            self.db = self.client[self.mongo_db]
        return self.db
    
    def _load_global_hscodes(self) -> Dict[str, str]:
        """Load global HS codes from payloads/hscodes.json"""
        if self._global_hscodes is None:
            try:
                hscodes_file = Path(__file__).parent.parent / "payloads" / "hscodes.json"
                with open(hscodes_file, 'r', encoding='utf-8') as f:
                    hscodes_list = json.load(f)
                self._global_hscodes = {item['Code']: item['Name'] for item in hscodes_list}
                logger.info(f"Loaded {len(self._global_hscodes)} global HS codes")
            except Exception as e:
                logger.error(f"Error loading global HS codes: {e}")
                self._global_hscodes = {}
        return self._global_hscodes
    
    def _fetch_and_cache_hscodes(self, country_code: str, country_name: str = None) -> Set[str]:
        """
        Fetch HS codes from MacMap API and cache them in MongoDB
        
        Args:
            country_code: MacMap country code
            country_name: Country name (optional, for logging)
            
        Returns:
            Set of HS code strings
        """
        logger.info(f"🔄 Fetching HS codes from MacMap API for country {country_code}...")
        
        try:
            import requests
            
            # Use headers directly without relying on utils.py
            headers = {
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Accept-Encoding': 'gzip, deflate, br',
                'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Content-Type': 'application/json; charset=utf-8',
                'DNT': '1',
                'Host': 'www.macmap.org',
                'Pragma': 'no-cache',
                'Referer': 'https://www.macmap.org/',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'X-Requested-With': 'XMLHttpRequest',
            }
            
            # Use the NTM products endpoint for regulatory HS codes
            # reporterCode = the country whose regulations we're checking (country1 in the scraper)
            # For both import and export regulations, we use the reporter country's HS codes
            products_url = f'https://www.macmap.org/api/ntm-products?reporterCode={country_code}&level=8'
            logger.info(f"📡 Fetching HS codes from: {products_url}")
            print(f"📡 Fetching HS codes from: {products_url}")
            
            products_req = requests.get(products_url, headers=headers, timeout=60)
            
            if products_req.status_code != 200:
                logger.error(f"Failed to fetch NTM products for {country_code}. Status: {products_req.status_code}")
                print(f"❌ Failed to fetch NTM products for {country_code}. Status: {products_req.status_code}")
                print(f"❌ Response: {products_req.text[:500]}")
                return set()
            
            try:
                products = products_req.json()
                print(f"✅ Successfully fetched {len(products)} products from API")
            except Exception as e:
                logger.error(f"Failed to parse NTM products JSON for {country_code}: {e}")
                print(f"❌ Failed to parse JSON for {country_code}: {e}")
                print(f"❌ Response text: {products_req.text[:500]}")
                return set()
            
            hscodes_dict = {}  # Store as dict with code: name
            
            for product in products:
                code = product.get('Code')
                name = product.get('Name', '')
                # Accept all HS codes regardless of length (8, 10, or more digits)
                if code:
                    hscodes_dict[code] = name
            
            logger.info(f"✅ Fetched {len(hscodes_dict)} HS codes for country {country_code}")
            print(f"✅ Fetched {len(hscodes_dict)} HS codes for country {country_code}")
            
            # Cache in MongoDB with descriptions
            if hscodes_dict:
                db = self._get_db()
                collection = db['macmap_hscodes_cache']
                
                # Convert to list of objects for better storage
                hscodes_list = [{'code': code, 'name': name} for code, name in sorted(hscodes_dict.items())]
                
                import datetime
                doc = {
                    'reporter_code': country_code,
                    'country_name': country_name or f"Country {country_code}",
                    'hscodes': hscodes_list,
                    'cached_at': datetime.datetime.utcnow(),
                    'total_codes': len(hscodes_list),
                    'source': 'macmap_api'
                }
                
                collection.update_one(
                    {'reporter_code': country_code},
                    {'$set': doc},
                    upsert=True
                )
                
                logger.info(f"💾 Cached {len(hscodes_list)} HS codes for country {country_code}")
                print(f"💾 Cached {len(hscodes_list)} HS codes for country {country_code}")
            
            return set(hscodes_dict.keys())
            
        except Exception as e:
            logger.error(f"Error fetching HS codes for {country_code}: {e}", exc_info=True)
            print(f"❌ Error fetching HS codes for {country_code}: {e}")
            return set()
    
    def _load_country_hscodes(self, country_code: str, auto_fetch: bool = True) -> Set[str]:
        """
        Load country-specific HS codes from MongoDB cache
        
        Args:
            country_code: MacMap country code
            auto_fetch: If True, automatically fetch from API if not cached
            
        Returns:
            Set of HS code strings
        """
        if country_code not in self._country_caches:
            try:
                db = self._get_db()
                collection = db['macmap_hscodes_cache']
                
                # Find cached HS codes for this country
                doc = collection.find_one({'reporter_code': country_code})
                
                if doc and 'hscodes' in doc:
                    hscodes = doc['hscodes']
                    if isinstance(hscodes, list):
                        # Handle both old format (list of strings) and new format (list of objects)
                        if hscodes and isinstance(hscodes[0], dict):
                            # New format: [{code, name}, ...]
                            self._country_caches[country_code] = set(item['code'] for item in hscodes)
                        else:
                            # Old format: ['code1', 'code2', ...]
                            self._country_caches[country_code] = set(hscodes)
                        logger.info(f"✅ Loaded {len(self._country_caches[country_code])} cached HS codes for country {country_code}")
                    else:
                        self._country_caches[country_code] = set()
                else:
                    # Cache not found
                    logger.warning(f"⚠️  No cached HS codes found for country {country_code}")
                    print(f"⚠️  No cached HS codes found for country {country_code}")
                    
                    # Try auto-fetch if enabled
                    if auto_fetch:
                        print(f"🔄 Auto-fetch is enabled. Attempting to fetch from MacMap API...")
                        # Get country name for better logging
                        country_name = None
                        try:
                            countries_file = Path(__file__).parent.parent / "scrapers" / "macmap" / "macmap_countries" / "countries.json"
                            with open(countries_file, 'r', encoding='utf-8') as f:
                                countries = __import__('json').load(f)
                            for item in countries:
                                if item['Code'] == country_code:
                                    country_name = item['Name']
                                    break
                        except:
                            pass
                        
                        logger.info(f"🔄 Attempting to auto-fetch HS codes from MacMap API...")
                        
                        # Fetch and cache from API
                        fetched_codes = self._fetch_and_cache_hscodes(country_code, country_name)
                        
                        if fetched_codes:
                            self._country_caches[country_code] = fetched_codes
                            logger.info(f"✅ Successfully auto-fetched and cached {len(fetched_codes)} HS codes from API")
                        else:
                            # API failed - try using global HS codes as fallback
                            logger.warning(f"⚠️  API fetch failed. Using global HS codes as fallback...")
                            global_hscodes = self._load_global_hscodes()
                            
                            if global_hscodes:
                                # Cache all 8-digit codes from global file
                                eight_digit_codes = {code: name for code, name in global_hscodes.items() if len(code) == 8}
                                
                                if eight_digit_codes:
                                    # Store in MongoDB for future use
                                    db = self._get_db()
                                    collection = db['macmap_hscodes_cache']
                                    
                                    hscodes_list = [{'code': code, 'name': name} for code, name in sorted(eight_digit_codes.items())]
                                    
                                    doc = {
                                        'reporter_code': country_code,
                                        'country_name': country_name or f"Country {country_code}",
                                        'hscodes': hscodes_list,
                                        'cached_at': __import__('datetime').datetime.utcnow(),
                                        'total_codes': len(hscodes_list),
                                        'source': 'global_fallback'  # Mark as fallback
                                    }
                                    
                                    collection.update_one(
                                        {'reporter_code': country_code},
                                        {'$set': doc},
                                        upsert=True
                                    )
                                    
                                    self._country_caches[country_code] = set(eight_digit_codes.keys())
                                    logger.info(f"✅ Cached {len(eight_digit_codes)} HS codes from global file as fallback")
                                else:
                                    logger.warning(f"❌ No 8-digit codes found in global file")
                                    self._country_caches[country_code] = set()
                            else:
                                logger.warning(f"❌ Could not load global HS codes. To manually cache, run: python tools/fetch_macmap_hscodes.py --country \"{country_name or country_code}\"")
                                self._country_caches[country_code] = set()
                    else:
                        logger.warning(f"Auto-fetch is disabled. To manually cache, run: python tools/fetch_macmap_hscodes.py --country-code {country_code}")
                        self._country_caches[country_code] = set()
            except Exception as e:
                logger.error(f"Error loading country HS codes for {country_code}: {e}")
                self._country_caches[country_code] = set()
        
        return self._country_caches[country_code]
    
    def expand_6digit_to_8digit(self, six_digit_code: str, country_code: str) -> List[Dict[str, str]]:
        """
        Expand a 6-digit HS code to all its variants (8, 10, or more digits) for a specific country
        
        Args:
            six_digit_code: 6-digit HS code (e.g., "010121")
            country_code: Country code (e.g., "699" for India)
            
        Returns:
            List of dicts with 'code' and 'name' keys
        """
        # Validate input
        if len(six_digit_code) != 6 or not six_digit_code.isdigit():
            logger.error(f"Invalid 6-digit HS code: {six_digit_code}")
            return []
        
        # Load country-specific HS codes
        country_hscodes = self._load_country_hscodes(country_code)
        
        # Find all codes starting with the 6-digit code (regardless of length)
        matching_codes = [
            code for code in country_hscodes 
            if code.startswith(six_digit_code)
        ]
        
        # Get names from cache if available (new format)
        cached_names = {}
        try:
            db = self._get_db()
            collection = db['macmap_hscodes_cache']
            doc = collection.find_one({'reporter_code': country_code})
            
            if doc and 'hscodes' in doc:
                hscodes = doc['hscodes']
                if hscodes and isinstance(hscodes[0], dict):
                    # New format with names
                    cached_names = {item['code']: item['name'] for item in hscodes}
        except:
            pass
        
        # Load global HS codes as fallback
        global_hscodes = self._load_global_hscodes()
        
        # Build result with names (prefer cached names, fallback to global)
        result = []
        for code in sorted(matching_codes):
            name = cached_names.get(code) or global_hscodes.get(code, f"HS Code {code}")
            result.append({
                'code': code,
                'name': name
            })
        
        logger.info(f"Expanded {six_digit_code} to {len(result)} 8-digit codes for country {country_code}")
        return result
    
    def expand_multiple_6digit_codes(self, six_digit_codes: List[str], country_code: str) -> List[Dict[str, str]]:
        """
        Expand multiple 6-digit HS codes to their 8-digit variants
        
        Args:
            six_digit_codes: List of 6-digit HS codes
            country_code: Country code
            
        Returns:
            List of dicts with 'code' and 'name' keys (deduplicated)
        """
        all_codes = []
        seen_codes = set()
        
        for six_digit in six_digit_codes:
            expanded = self.expand_6digit_to_8digit(six_digit, country_code)
            for item in expanded:
                if item['code'] not in seen_codes:
                    all_codes.append(item)
                    seen_codes.add(item['code'])
        
        return all_codes
    
    def check_cache_status(self, country_code: str) -> Dict[str, any]:
        """
        Check if HS codes are cached for a country
        
        Args:
            country_code: MacMap country code
            
        Returns:
            Dict with 'exists', 'total_codes', 'source', 'cached_at' keys
        """
        try:
            db = self._get_db()
            collection = db['macmap_hscodes_cache']
            
            doc = collection.find_one({'reporter_code': country_code})
            
            if doc:
                return {
                    'exists': True,
                    'total_codes': doc.get('total_codes', 0),
                    'source': doc.get('source', 'unknown'),
                    'cached_at': doc.get('cached_at')
                }
            else:
                return {
                    'exists': False,
                    'total_codes': 0,
                    'source': None,
                    'cached_at': None
                }
        except Exception as e:
            logger.error(f"Error checking cache status: {e}")
            return {
                'exists': False,
                'total_codes': 0,
                'source': None,
                'cached_at': None
            }
    
    def fetch_and_cache_country(self, country_code: str, country_name: str = None) -> int:
        """
        Fetch and cache HS codes for a country (public method for pre-caching)
        
        Args:
            country_code: MacMap country code
            country_name: Country name (optional)
            
        Returns:
            Number of HS codes cached, or 0 if failed
        """
        try:
            # Use the internal fetch method
            fetched_codes = self._fetch_and_cache_hscodes(country_code, country_name)
            return len(fetched_codes) if fetched_codes else 0
        except Exception as e:
            logger.error(f"Error in fetch_and_cache_country: {e}")
            return 0
    
    def get_country_code_from_name(self, country_name: str) -> str:
        """
        Get country code from country name using MacMap countries mapping
        
        Args:
            country_name: Country name (e.g., "India", "United States of America")
            
        Returns:
            Country code (e.g., "699")
        """
        try:
            # Load MacMap countries
            countries_file = Path(__file__).parent.parent / "scrapers" / "macmap" / "macmap_countries" / "countries.json"
            with open(countries_file, 'r', encoding='utf-8') as f:
                countries = json.load(f)
            
            country_map = {item['Name']: item['Code'] for item in countries}
            
            if country_name in country_map:
                return country_map[country_name]
            else:
                logger.error(f"Country not found: {country_name}")
                return None
        except Exception as e:
            logger.error(f"Error getting country code: {e}")
            return None


# Global instance
hscode_expander = HSCodeExpander()


if __name__ == "__main__":
    # Test the expander
    logging.basicConfig(level=logging.INFO)
    
    # Test with India
    country_code = hscode_expander.get_country_code_from_name("India")
    print(f"\nIndia country code: {country_code}")
    
    # Test expansion
    test_codes = ["010121", "847971"]
    for code in test_codes:
        print(f"\n=== Expanding {code} for India ===")
        expanded = hscode_expander.expand_6digit_to_8digit(code, country_code)
        print(f"Found {len(expanded)} 8-digit codes:")
        for item in expanded[:10]:  # Show first 10
            print(f"  {item['code']}: {item['name'][:60]}...")
