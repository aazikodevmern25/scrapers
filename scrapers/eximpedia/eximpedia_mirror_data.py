#!/usr/bin/env python3
"""
Eximpedia Mirror Data Scraper
Uses existing Eximpedia infrastructure to scrape mirror trade data across multiple countries.
Fetches ALL records with pagination (no 1000 limit) like regular Eximpedia download.
"""
import os
import json
import datetime
import logging
import traceback
import time
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd

# Setup logging
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"eximpedia_mirror_data_{datetime.datetime.now().strftime('%Y%m%d')}.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('eximpedia_mirror_data')

# Import database connection
import sys
script_dir = os.path.dirname(os.path.abspath(__file__))
data_extractor_dir = os.path.dirname(os.path.dirname(script_dir))
if data_extractor_dir not in sys.path:
    sys.path.insert(0, data_extractor_dir)

from utils import client, db

# Import existing Eximpedia scraper functions
from scrapers.eximpedia.eximpedia import (
    AuthenticateSession,
    GetTaxonomyData,
    BuildRequestPayload,
    ExecuteAPIRequest,
    impCn,
    expCn
)

# Ensure Excel sheets directory exists
EXCEL_SHEETS_DIR = Path(__file__).parent.parent.parent / 'eximpedia_sheets'
EXCEL_SHEETS_DIR.mkdir(exist_ok=True)

SEARCH_TYPE_MAPPING = {
    'HS_CODE': 'HS CODE',
    'EXPORTER': 'EXPORTER',
    'IMPORTER': 'IMPORTER',
    'PRODUCT': 'PRODUCT'
}


def save_mirror_data_to_db(records: List[Dict], search_type: str, search_value: str,
                           countries: List[str], start_date: str, end_date: str, match_type: str):
    """
    Save mirror data records to MongoDB
    """
    try:
        mirror_data_collection = db['eximpedia_mirror_data']
        
        # Create document
        document = {
            'search_type': search_type,
            'search_value': search_value,
            'countries': countries,
            'start_date': start_date,
            'end_date': end_date,
            'match_type': match_type,
            'records': records,
            'record_count': len(records),
            'created_at': datetime.datetime.now(),
            'updated_at': datetime.datetime.now()
        }
        
        result = mirror_data_collection.insert_one(document)
        logger.info(f"Saved {len(records)} records to MongoDB with ID: {result.inserted_id}")
        return result.inserted_id
    except Exception as e:
        logger.error(f"Error saving to MongoDB: {e}")
        return None


def parse_date(date_str):
    """Parse date from MM/DD/YYYY format"""
    try:
        return datetime.datetime.strptime(date_str, '%m/%d/%Y').strftime('%Y-%m-%d')
    except:
        return date_str


def scrape_mirror_data(search_type: str, search_value: str, start_date: str, end_date: str,
                      countries: List[str], match_type: str = 'EXACT',
                      email: str = None, password: str = None,
                      download_excel: bool = True, max_records: int = 100000):
    """
    Scrape mirror trade data for multiple countries.
    Fetches ALL records with pagination (no 1000 limit) like regular Eximpedia download.
    
    Args:
        search_type: Type of search (HS_CODE, EXPORTER, IMPORTER, PRODUCT)
        search_value: Search value (e.g., HS code)
        start_date: Start date in MM/DD/YYYY format
        end_date: End date in MM/DD/YYYY format
        countries: List of country names
        match_type: Match type (EXACT, CONTAINS, STARTS_WITH)
        email: Eximpedia email (optional, uses default if not provided)
        password: Eximpedia password (optional, uses default if not provided)
        download_excel: Whether to download Excel report
        max_records: Maximum records per country (default 100000 = fetch ALL)
    
    Returns:
        Dictionary containing scraping results
    """
    result = {
        "status": "failed",
        "message": "",
        "records_scraped": 0,
        "document_id": None,
        "excel_path": None,
        "countries_processed": [],
        "countries_failed": []
    }
    
    try:
        logger.info("=" * 60)
        logger.info("Starting Mirror Data scraping")
        logger.info(f"Search Type: {search_type}")
        logger.info(f"Search Value: {search_value}")
        logger.info(f"Date Range: {start_date} to {end_date}")
        logger.info(f"Countries: {len(countries)} - {countries[:5]}{'...' if len(countries) > 5 else ''}")
        logger.info(f"Match Type: {match_type}")
        logger.info("=" * 60)
        
        # Parse dates
        sd = parse_date(start_date)
        ed = parse_date(end_date)
        
        # Authenticate using existing Eximpedia function
        sess, auth_data = AuthenticateSession(email=email, password=password)
        if not sess or not auth_data:
            result["message"] = "Authentication failed"
            return result
        
        logger.info(f"Authentication successful")
        
        # Mirror Data searches all trade types and fetches ALL records (no 1000 limit)
        all_records = []
        
        # Mirror Data API: Always iterate through each country individually
        # The Priyam account only has access to specific countries (like India)
        # Removing country filter causes 401 "You don't have access to data of this Country"
        
        # Countries that the account has verified access to
        accessible_countries = ['India']  # Add more as verified
        
        if len(countries) > 1:
            # Filter to only accessible countries when "All Countries" selected
            countries_to_process = [c for c in countries if c in accessible_countries]
            if not countries_to_process:
                countries_to_process = accessible_countries  # Fallback to accessible countries
            logger.info(f"Searching {len(countries_to_process)} accessible countries: {countries_to_process}")
        else:
            countries_to_process = countries
            logger.info(f"Searching single country: {countries[0]}")
        
        # Process countries (will be just 1 iteration if "All Countries")
        for country in countries_to_process:
            try:
                logger.info(f"\nProcessing country: {country}")
                
                # Check if country is available
                if country not in impCn and country not in expCn:
                    logger.warning(f"Country '{country}' not found in available countries, skipping")
                    result["countries_failed"].append(country)
                    continue
                
                # Mirror Data - use 1 API search per trade type
                # Each API call = 1 search credit from daily limit
                country_records = []
                
                # Try both import and export to get all data (2 searches but complete data)
                modes_to_try = ['import', 'export']
                
                for mode in modes_to_try:
                    logger.info(f"  Fetching {mode.upper()} data for {country}")
                    
                    # Get taxonomy data for this mode
                    taxonomy_info = GetTaxonomyData(sess, country, mode)
                    if not taxonomy_info:
                        logger.info(f"  No {mode} data available for {country}, skipping")
                        continue
                    
                    # Fetch ALL records with pagination
                    mode_records = []
                    page_start = 0
                    page_size = 1000
                    total_records = None
                    
                    while True:
                        # Build request payload for current page
                        payload = BuildRequestPayload(
                            auth_data, taxonomy_info, sd, ed, 
                            search_value, country, mode, 
                            page_start=page_start, page_length=page_size
                        )
                    
                        if not payload:
                            logger.warning(f"Failed to build payload for {country} {mode}")
                            break
                        
                        # Execute API request
                        response = ExecuteAPIRequest(sess, payload)
                        
                        if not response or 'data' not in response:
                            break
                        
                        records = response.get('data', [])
                        total_records = response.get('recordsTotal', len(records))
                        
                        if not records:
                            break
                        
                        # Add metadata to each record
                        for record in records:
                            record['_source_country'] = country
                            record['_trade_type'] = mode.upper()
                            record['_search_type'] = search_type
                            record['_search_value'] = search_value
                        
                        mode_records.extend(records)
                        logger.info(f"  {country} {mode.upper()}: Page {page_start//page_size + 1} - {len(records)} records (total: {len(mode_records)}/{total_records})")
                    
                        # Check if we've retrieved all records
                        page_start += page_size
                        if len(mode_records) >= total_records:
                            break
                        
                        # Add small delay to avoid rate limiting
                        time.sleep(0.5)
                    
                    if mode_records:
                        logger.info(f"  {country} {mode.upper()}: Retrieved {len(mode_records)} records")
                        country_records.extend(mode_records)
                
                logger.info(f"{country}: Total retrieved {len(country_records)} records across all trade types")
                
                # Add all country records to results
                if country_records:
                    all_records.extend(country_records)
                    result["countries_processed"].append({
                        "country": country,
                        "records": len(country_records)
                    })
                else:
                    logger.info(f"{country}: No records found")
                    result["countries_processed"].append({
                        "country": country,
                        "records": 0
                    })
                
                # Add delay between countries to avoid rate limiting
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error processing {country}: {e}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                result["countries_failed"].append(country)
                continue
        
        # Log total records collected
        logger.info(f"Total records collected: {len(all_records)}")
        
        # Check if we got any records
        if not all_records:
            result["status"] = "success"
            result["message"] = f"No records found"
            return result
        
        # Save to database
        doc_id = save_mirror_data_to_db(
            all_records, search_type, search_value, countries,
            start_date, end_date, match_type
        )
        
        result["records_scraped"] = len(all_records)
        result["document_id"] = str(doc_id) if doc_id else None
        
        # Download Excel report if requested
        if download_excel and all_records:
            try:
                timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                countries_str = '_'.join([c[:3] for c in countries[:3]]) if len(countries) <= 3 else f"{countries[0][:3]}_and_{len(countries)-1}_more"
                filename = f"mirror_data_{search_type}_{search_value}_{countries_str}_{timestamp}.xlsx"
                filepath = EXCEL_SHEETS_DIR / filename
                
                df = pd.DataFrame(all_records)
                df.to_excel(filepath, index=False)
                result["excel_path"] = str(filepath)
                logger.info(f"Excel report saved to: {filepath}")
            except Exception as e:
                logger.error(f"Error saving Excel: {e}")
        
        result["status"] = "success"
        countries_success = len([c for c in result['countries_processed'] if c['records'] > 0])
        result["message"] = f"Successfully scraped {len(all_records)} records from {countries_success} countries"
        
        logger.info("=" * 60)
        logger.info(f"Mirror Data scraping completed: {len(all_records)} total records")
        logger.info("=" * 60)
        
        return result
        
    except Exception as e:
        logger.error(f"Unexpected error in scrape_mirror_data: {e}")
        traceback.print_exc()
        result["message"] = str(e)
        return result


# Alias for backward compatibility
ScrapeMirrorData = scrape_mirror_data

if __name__ == "__main__":
    result = scrape_mirror_data(
        search_type="HS_CODE",
        search_value="450310",
        start_date="01/01/2025",
        end_date="12/31/2025",
        countries=["India"],
        match_type="EXACT",
        download_excel=True
    )
    print(json.dumps(result, indent=2, default=str))
