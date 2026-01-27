import pandas as pd
from tools import decrypt
from utils import FetchCountries, client, db
import copy
from tools.decrypt import decrypt_exim_data, encrypt_exim_data
from concurrent.futures import ThreadPoolExecutor
import requests as pdf_req
from curl_cffi import requests
import json
from scrapy import Selector
import os
import datetime
import scraper_helper
import itertools
from utils import obj_storage, client, db
import base64
import logging
import traceback
from pathlib import Path

log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"eximpedia_scraper_{datetime.datetime.now().strftime('%Y%m%d')}.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('eximpedia_scraper')

# Get the directory of this file for relative paths
_current_dir = Path(__file__).parent

# Using db from utils - connects to Dhruval database on 202.47.115.6:27017
exCollection = db['eximpedia']

headers = {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Encoding': 'gzip, deflate, br, zstd',
    'Accept-Language': 'en-US,en;q=0.9,de;q=0.8',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'Content-Type': 'application/json',
    'Host': 'web.eximpedia.app',
    'Origin': 'https://web.eximpedia.app',
    'Pragma': 'no-cache',
    'Referer': 'https://web.eximpedia.app/consumers/login',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Chromium";v="131", "Google Chrome";v="131", "Not.A/Brand";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"'
}

logger.info("Loading configuration files")
try:
    os.makedirs("pdf_files", exist_ok=True)
    cwd = os.getcwd()
    expPayload = json.load(open(_current_dir / 'payloads/ex_payload.json', 'r', encoding='utf-8'))
    # FetchCountries adds 'payloads/' prefix, so we need to work around it
    # Save current dir and change to scraper dir temporarily
    original_cwd = os.getcwd()
    os.chdir(_current_dir)
    impCn = FetchCountries("imp_ex_countries.json")
    expCn = FetchCountries("exp_ex_countries.json")
    os.chdir(original_cwd)
    logger.info(f"Successfully loaded configuration files - Import countries: {len(impCn)}, Export countries: {len(expCn)}")
except Exception as e:
    logger.error(f"Failed to load configuration files: {e}")
    raise


def decode_jwt_part(b64_segment):
    try:
        padded = b64_segment + '=' * (-len(b64_segment) % 4)
        decoded_bytes = base64.urlsafe_b64decode(padded)
        return json.loads(decoded_bytes)
    except Exception as e:
        logger.error(f"JWT decoding failed: {e}")
        raise


def GetExpTime(jwt_token):
    try:
        header_b64, payload_b64, signature_b64 = jwt_token.split('.')
        payload = decode_jwt_part(payload_b64)
        exp = payload['exp']
        logger.debug(f"JWT expiration time extracted: {exp}")
        return str(exp)
    except Exception as e:
        logger.error(f"JWT expiration time extraction failed: {e}")
        raise


def ParseDates(startDate, endDate):
    try:
        logger.debug(f"Parsing dates: {startDate} to {endDate}")
        startDate = datetime.datetime.strptime(startDate, '%m/%d/%Y')
        endDate = datetime.datetime.strptime(endDate, '%m/%d/%Y')
        startDate = startDate.strftime('%Y-%m-%d')
        endDate = endDate.strftime('%Y-%m-%d')
        
        logger.info(f"Dates parsed successfully: {startDate} to {endDate}")
        return startDate, endDate
    except Exception as e:
        logger.error(f"Date parsing failed for {startDate} to {endDate}: {e}")
        raise


# Global session cache to reuse authenticated sessions
_cached_session = None
_cached_auth_data = None
_cache_time = None
_cached_email = None

def AuthenticateSession(force_new=False, email=None, password=None):
    global _cached_session, _cached_auth_data, _cache_time, _cached_email
    import time
    import random
    
    # Use default credentials if not provided
    if not email:
        email = "Priyam@eximpedia.app"
    if not password:
        password = "Priyam@177"
    
    # Reuse cached session if valid (within 10 minutes) AND using same credentials
    if not force_new and _cached_session and _cached_auth_data and _cache_time and _cached_email:
        if time.time() - _cache_time < 600 and _cached_email == email:  # 10 minutes, same email
            logger.info("Reusing cached authentication session")
            return _cached_session, _cached_auth_data
    
    max_retries = 3
    base_delay = 5  # seconds
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Authentication attempt {attempt}/{max_retries}")
            
            # Add random delay before each attempt (except first)
            if attempt > 1:
                delay = base_delay * attempt + random.uniform(1, 3)
                logger.info(f"Waiting {delay:.1f}s before retry...")
                time.sleep(delay)
            
            sess = requests.Session(impersonate="chrome131")
            payload = {"email_id": email, "password": password}
            
            logger.info("Attempting login to web.eximpedia.app")
            req = sess.put(
                "https://web.eximpedia.app/backend/auths/login", 
                json=payload, 
                headers=headers, 
                timeout=90,  # Increased timeout
                allow_redirects=True
            )
            logger.info(f"Login request: {req.url} - Status: {req.status_code}")
            
            if req.status_code != 200:
                logger.error(f"Login request failed with status {req.status_code}")
                if attempt < max_retries:
                    continue
                return None, None
                
            js = req.json()['data']
            if js['msg'] != "Access Granted":
                logger.error(f"Authentication failed: {js['msg']}")
                if attempt < max_retries:
                    continue
                return None, None
                
            adxToken = js['adxToken']
            customerId = js['customer_id']
            userId = js['user_id']
            expTime = int(GetExpTime(adxToken)) * 1000
            
            headers['Adxtoken'] = adxToken
            headers['Ddxtokenexpiretime'] = str(expTime)
            
            logger.info(f"✅ Authentication successful - Customer ID: {customerId}, User ID: {userId}")
            
            auth_data = {
                'adxToken': adxToken,
                'customerId': customerId,
                'userId': userId,
                'expTime': expTime
            }
            
            # Cache the session
            _cached_session = sess
            _cached_auth_data = auth_data
            _cache_time = time.time()
            _cached_email = email
            
            return sess, auth_data
            
        except Exception as e:
            logger.error(f"Authentication attempt {attempt} failed: {e}")
            if attempt < max_retries:
                logger.info(f"Will retry in {base_delay * (attempt + 1)}s...")
                continue
            logger.error(f"All {max_retries} authentication attempts failed")
            return None, None
    
    return None, None


def GetTaxonomyData(sess, country, mode, retry_count=0):
    import time
    max_retries = 3
    
    try:
        logger.info(f"Retrieving taxonomy data for {country.upper()} - {mode.upper()} (attempt {retry_count + 1}/{max_retries})")
        
        req = sess.get(
            f'https://web.eximpedia.app/backend/taxonomies?countryName={country.upper()}&tradeType={mode.upper()}',
            headers=headers,
            timeout=60
        )
        logger.info(f"Taxonomy request: {req.url} - Status: {req.status_code}")
        
        # If 401 Unauthorized, re-authenticate and retry
        if req.status_code == 401:
            logger.warning(f"Taxonomy request returned 401 - session expired, re-authenticating...")
            if retry_count < max_retries - 1:
                # Force new authentication
                new_sess, new_auth = AuthenticateSession(force_new=True)
                if new_sess and new_auth:
                    time.sleep(2)  # Small delay before retry
                    return GetTaxonomyData(new_sess, country, mode, retry_count + 1)
            logger.error("Max retries exceeded for taxonomy request")
            return None
        
        # Eximpedia returns encrypted data even with 401 status - check for cryptexim field
        response_json = req.json()
        logger.debug(f"Raw response keys: {response_json.keys()}")
        
        if 'cryptexim' not in response_json:
            logger.error(f"Response does not contain 'cryptexim' key. Keys: {response_json.keys()}")
            if retry_count < max_retries - 1:
                time.sleep(3)
                return GetTaxonomyData(sess, country, mode, retry_count + 1)
            return None
            
        txn = decrypt_exim_data(response_json['cryptexim'])
        
        if txn is None:
            logger.error("Decryption returned None")
            if retry_count < max_retries - 1:
                time.sleep(3)
                return GetTaxonomyData(sess, country, mode, retry_count + 1)
            return None
        
        # Check if data exists
        if not txn.get('data') or len(txn['data']) == 0:
            logger.error("Taxonomy response has no data")
            if retry_count < max_retries - 1:
                time.sleep(3)
                return GetTaxonomyData(sess, country, mode, retry_count + 1)
            return None
        
        taxonomy_info = {
            'hs_code_digit_classification': txn['data'][0]['hs_code_digit_classification'],
            'date_field': txn['data'][0]['fields']['explore_aggregation']['sortTerm'],
            'all_fields': txn['data'][0]['fields']['all'],
            'group_expressions': txn['data'][0]['fields']['explore_aggregation']['groupExpressions'],
            'purchasable': txn['data'][0]['fields']['purchasable'],
            'sort_term': txn['data'][0]['fields']['records_aggregation']['sortTerm']
        }
        
        logger.info("✅ Taxonomy data retrieved successfully")
        return taxonomy_info
        
    except Exception as e:
        logger.error(f"Taxonomy data retrieval failed for {country} - {mode}: {e}")
        if retry_count < max_retries - 1:
            logger.info(f"Retrying taxonomy request in 3 seconds...")
            time.sleep(3)
            return GetTaxonomyData(sess, country, mode, retry_count + 1)
        return None


def BuildRequestPayload(auth_data, taxonomy_info, sd, ed, hsc, country, mode, page_start=0, page_length=1000):
    try:
        logger.info(f"Building request payload for {country.upper()} - {mode.upper()}")
        logger.debug(f"Date range: {sd} to {ed}")
        logger.debug(f"HS Code: {hsc}")
        
        # Get country code - try static files first, then use fallback mapping
        cid = None
        if mode == 'import':
            if country in impCn:
                cid = impCn[country]['code_iso_3']
            else:
                logger.warning(f"Country '{country}' not in static import file, using fallback ISO code")
        elif mode == 'export':
            if country in expCn:
                cid = expCn[country]['code_iso_3']
            else:
                logger.warning(f"Country '{country}' not in static export file, using fallback ISO code")
        else:
            logger.error(f"Invalid mode: {mode}")
            return None
        
        # Fallback: Comprehensive ISO 3166-1 alpha-3 codes for all Eximpedia countries
        if not cid:
            fallback_codes = {
                # Asia
                'India': 'IND', 'Indonesia': 'IDN', 'Bangladesh': 'BGD', 'Pakistan': 'PAK',
                'Philippines': 'PHL', 'Vietnam': 'VNM', 'Vietnam_2022': 'VNM_NEW',
                'Turkey': 'TUR', 'Srilanka': 'LKA', 'Kazakhstan': 'KAZ', 'Uzbekistan': 'UZB',
                'Malaysia': 'MYS', 'Singapore': 'SGP', 'Thailand': 'THA',
                'Myanmar': 'MMR', 'Cambodia': 'KHM', 'Laos': 'LAO', 'Brunei': 'BRN',
                'China': 'CHN', 'Japan': 'JPN', 'South Korea': 'KOR', 'Taiwan': 'TWN',
                'Hong Kong': 'HKG', 'Nepal': 'NPL', 'Bhutan': 'BTN', 'Maldives': 'MDV',
                'Afghanistan': 'AFG', 'Iran': 'IRN', 'Iraq': 'IRQ', 'Israel': 'ISR',
                'Saudi Arabia': 'SAU', 'UAE': 'ARE', 'United Arab Emirates': 'ARE',
                # South America
                'Argentina': 'ARG', 'Bl_brazil': 'BRA', 'Brazil': 'BRA', 'Chile': 'CHL',
                'Colombia': 'COL', 'Equador': 'ECU', 'Ecuador': 'ECU', 'Paraguay': 'PRY',
                'Peru': 'PER', 'Uruguay': 'URY', 'Venezuela': 'VEN', 'Bolivia': 'BOL',
                # Central America
                'Costarica': 'CRI', 'Costa Rica': 'CRI', 'Panama': 'PAN', 'Nicaragua': 'NIC',
                # North America
                'Mexico': 'MEX', 'Usa': 'USA', 'USA': 'USA', 'United States': 'USA',
                'Canada': 'CAN',
                # Africa
                'Ghana': 'GHA', 'Nigeria': 'NGA', 'Ethiopia': 'ETH', 'Tanzania': 'TZA',
                'Uganda': 'UGA', 'Cameroon': 'CMR', 'Ivory_coast': 'CIV', 'Botswana': 'BWA',
                'Namibia': 'NAM', 'Lesotho': 'LSO', 'Rwanda': 'RWA', 'Zimbabwe': 'ZWE',
                'Kenya': 'KEN', 'Burundi': 'BDI', 'Liberia': 'LBR', 'South_sudan': 'SSD',
                'Angola': 'AGO', 'South Africa': 'ZAF', 'Egypt': 'EGY', 'Morocco': 'MAR',
                'Algeria': 'DZA', 'Tunisia': 'TUN',
                # Europe
                'Russia': 'RSA', 'Ukraine': 'UKR', 'Moldova': 'MDA',
                'Germany': 'DEU', 'France': 'FRA', 'United Kingdom': 'GBR', 'UK': 'GBR',
                'Italy': 'ITA', 'Spain': 'ESP', 'Poland': 'POL', 'Netherlands': 'NLD',
                'Belgium': 'BEL', 'Greece': 'GRC', 'Portugal': 'PRT', 'Sweden': 'SWE',
                'Austria': 'AUT', 'Switzerland': 'CHE', 'Denmark': 'DNK', 'Finland': 'FIN',
                'Norway': 'NOR', 'Ireland': 'IRL', 'Czech Republic': 'CZE', 'Romania': 'ROU',
                'Hungary': 'HUN', 'Bulgaria': 'BGR', 'Slovakia': 'SVK', 'Croatia': 'HRV',
                # Oceania
                'Australia': 'AUS', 'New Zealand': 'NZL'
            }
            # Try case-insensitive lookup
            cid = fallback_codes.get(country)
            if not cid:
                # Try case-insensitive match
                country_lower = country.lower()
                for k, v in fallback_codes.items():
                    if k.lower() == country_lower:
                        cid = v
                        break
            
            if cid:
                logger.info(f"Using fallback ISO code for {country}: {cid}")
            else:
                logger.error(f"Country '{country}' not supported and no fallback code available")
                return None
            
        logger.debug(f"Country code resolved: {cid}")
        
        rp = copy.deepcopy(expPayload)
        
        rp['allFields'] = taxonomy_info['all_fields']
        rp['groupExpressions'] = taxonomy_info['group_expressions']
        rp['purchasable'] = taxonomy_info['purchasable']
        
        rp['sortTerms'] = [{
            "sortField": taxonomy_info['sort_term'],
            "column": taxonomy_info['sort_term'],
            "defaultDataType": "",
            "sortType": "desc"
        }]
        
        rp['matchExpressions'][0]['fieldTerm'] = taxonomy_info['date_field']
        rp['matchExpressions'][0]['fieldValueLeft'] = sd
        rp['matchExpressions'][0]['fieldValueRight'] = ed
        rp['matchExpressions'][0]["dividedDateRange"] = [
            {"leftFieldvalueHot": sd, "rightFieldValueHot": ed}
        ]
        
        rp['start'] = page_start
        rp['length'] = page_length
        
        rp['accountId'] = auth_data['customerId']
        rp['userId'] = auth_data['userId']
        rp['tradeType'] = mode.upper()
        rp['countryCode'] = cid.upper()
        rp['country'] = country.upper()
        rp['AdxToken'] = auth_data['adxToken']
        rp['AdxTokenExpireTime'] = auth_data['expTime']
        
        rp['matchExpressions'][1]['fieldValue'] = [hsc]
        hs_classification = taxonomy_info['hs_code_digit_classification']
        hsc_len = len(str(hsc))
        
        logger.info(f"🔍 DEBUG: HS classification={hs_classification}, Input HS code={hsc}, Length={hsc_len}")
        
        # Try 6-digit exact match regardless of classification to match website behavior
        rp['matchExpressions'][1]['fieldValueArr'] = [
            {"fieldValueLeft": int(hsc), "fieldValueRight": int(hsc)}
        ]
        logger.info(f"HS Code set for 6-digit exact match: {hsc}")
        
        # Keep original logic for reference
        if False and hs_classification == 6:
            # 6-digit classification - exact match
            rp['matchExpressions'][1]['fieldValueArr'] = [
                {"fieldValueLeft": int(hsc), "fieldValueRight": int(hsc)}
            ]
            logger.info(f"HS Code set for 6-digit classification: {hsc}")
        elif False and hs_classification == 8:
            # 8-digit classification - add 2 digits padding
            rp['matchExpressions'][1]['fieldValueArr'] = [
                {"fieldValueLeft": int(f'{hsc}00'), "fieldValueRight": int(f'{hsc}99')}
            ]
            logger.info(f"HS Code set for 8-digit classification: {hsc}00-{hsc}99")
        elif hs_classification == 10:
            # 10-digit classification - add 4 digits padding
            rp['matchExpressions'][1]['fieldValueArr'] = [
                {"fieldValueLeft": int(f'{hsc}0000'), "fieldValueRight": int(f'{hsc}9999')}
            ]
            logger.info(f"HS Code set for 10-digit classification: {hsc}0000-{hsc}9999")
        else:
            # Default - calculate padding based on classification
            padding_needed = hs_classification - hsc_len
            if padding_needed > 0:
                left_pad = '0' * padding_needed
                right_pad = '9' * padding_needed
                rp['matchExpressions'][1]['fieldValueArr'] = [
                    {"fieldValueLeft": int(f'{hsc}{left_pad}'), "fieldValueRight": int(f'{hsc}{right_pad}')}
                ]
                logger.info(f"HS Code set for {hs_classification}-digit classification: {hsc}{left_pad}-{hsc}{right_pad}")
            else:
                rp['matchExpressions'][1]['fieldValueArr'] = [
                    {"fieldValueLeft": int(hsc), "fieldValueRight": int(hsc)}
                ]
                logger.info(f"HS Code set for {hs_classification}-digit classification: {hsc} (exact match)")
        
        # Log the actual HS code range being sent
        hs_range = rp['matchExpressions'][1]['fieldValueArr'][0]
        logger.info(f"🔍 DEBUG: Sending HS code range to API: {hs_range['fieldValueLeft']} - {hs_range['fieldValueRight']}")
        
        logger.info(f"Request payload built successfully")
        logger.info(f"📋 Payload details: Country={country.upper()}, CountryCode={cid.upper()}, TradeType={mode.upper()}, HSCode={hsc}")
        logger.info(f"📋 Date range: {sd} to {ed}, HS classification: {taxonomy_info['hs_code_digit_classification']}-digit")
        return rp
    except Exception as e:
        logger.error(f"Payload building failed: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None


def ExecuteAPIRequest(sess, payload):
    try:
        logger.info(f"Executing API request (start: {payload.get('start', 0)}, length: {payload.get('length', 1000)})")
        logger.info(f"🔍 FULL PAYLOAD: {json.dumps(payload, indent=2)}")
        
        # Add delay to avoid rate limiting
        import time
        time.sleep(2)
        
        # Send plain JSON payload - server expects unencrypted requests
        req = sess.post(
            'https://web.eximpedia.app/backend/trade/shipments/explore/records',
            headers=headers,
            json=payload,
            timeout=60  # Increase timeout to 60 seconds
        )
        logger.info(f"API request: {req.url} - Status: {req.status_code}")
        
        if req.status_code == 429:
            logger.warning(f"Rate limited (429) - waiting 10 seconds before retry")
            import time
            time.sleep(10)
            return None
        elif req.status_code != 200:
            logger.error(f"API request failed with status {req.status_code}")
            try:
                error_response = decrypt_exim_data(req.json()['cryptexim'])
                logger.error(f"Decrypted error response: {error_response}")
            except Exception as decrypt_error:
                logger.error(f"Could not decrypt error response: {decrypt_error}")
                logger.error(f"Raw response: {req.text[:500]}...")
            return None
            
        response = decrypt_exim_data(req.json()['cryptexim'])
        
        record_count = len(response.get('data', []))
        total_records = response.get('recordsTotal', record_count)
        logger.info(f"API request successful - Retrieved {record_count} records (Total available: {total_records})")
        return response
    except Exception as e:
        logger.error(f"API request execution failed: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None


def SaveToDatabase(response_data, hsc, country, mode, start_date=None, end_date=None):
    try:
        logger.info(f"Saving data to database for {country} - {mode}")
        
        new_records = response_data.get('data', [])
        new_record_count = len(new_records)
        
        # Always create a new document per scrape to avoid MongoDB 16MB document size limit
        # Do NOT aggregate - each date range gets its own document
        data = {
            "scraper_name": "eximpedia_scraper",
            "hscode": hsc,
            "product_name": "",
            "importing_country": "Unknown",
            "exporting_country": country,
            "source": "Eximpedia",
            "target_year": None,
            "mode": mode.lower(),
            "month": datetime.datetime.now().strftime("%b"),
            "year": datetime.datetime.now().strftime("%Y"),
            "data": new_records,
            "record_count": new_record_count,
            "country": country,
            "start_date": start_date,
            "end_date": end_date,
            "date_created": datetime.datetime.now(),
            "date_updated": datetime.datetime.now()
        }
        
        result = exCollection.insert_one(data)
        logger.info(f"NEW document created with ID: {result.inserted_id}")
        logger.info(f"Record count: {new_record_count}, Date range: {start_date} to {end_date}")
        return result.inserted_id
    except Exception as e:
        logger.error(f"Database save failed: {e}")
        return None


def ScrapeEximpedia(sd, ed, hsc, country, mode, email=None, password=None):
    try:
        logger.info(f"=== Starting Eximpedia scraping ===")
        logger.info(f"Parameters: HS Code: {hsc}, Country: {country}, Mode: {mode}")
        logger.info(f"Date range: {sd} to {ed}")
        if email:
            logger.info(f"Using custom credentials: {email}")
        
        # Authenticate and get session (with custom credentials if provided)
        sess, auth_data = AuthenticateSession(email=email, password=password)
        if not sess or not auth_data:
            logger.error("Authentication failed, aborting scraping")
            return "Authentication Failed"
            
        taxonomy_info = GetTaxonomyData(sess, country, mode)
        if not taxonomy_info:
            logger.error("Taxonomy data retrieval failed, aborting scraping")
            return "Taxonomy Failed"
        
        # Fetch all records with pagination
        all_records = []
        page_start = 0
        page_size = 1000
        max_retries = 3
        
        while True:
            payload = BuildRequestPayload(auth_data, taxonomy_info, sd, ed, hsc, country, mode, page_start, page_size)
            if not payload:
                logger.error("Payload building failed")
                # Save partial data if we have any
                if all_records:
                    logger.warning(f"Saving {len(all_records)} partial records due to payload build failure")
                    break
                return "Payload Build Failed"
            
            # Retry API request on failure with exponential backoff
            response_data = None
            for retry in range(max_retries):
                response_data = ExecuteAPIRequest(sess, payload)
                if response_data:
                    break
                # Exponential backoff: 5s, 10s, 20s
                wait_time = 5 * (2 ** retry)
                logger.warning(f"API request failed, retry {retry + 1}/{max_retries} - waiting {wait_time}s")
                import time
                time.sleep(wait_time)
            
            if not response_data:
                logger.error(f"API request failed after {max_retries} retries")
                # Save partial data if we have any
                if all_records:
                    logger.warning(f"Saving {len(all_records)} partial records due to API failure")
                    break
                return "API Request Failed"
            
            current_records = response_data.get('data', [])
            if not current_records:
                logger.info("No more records returned, ending pagination")
                break
            
            all_records.extend(current_records)
            
            total_available = response_data.get('recordsTotal', len(current_records))
            logger.info(f"Fetched {len(all_records)} of {total_available} total records")
            
            # Break if we got all records or less than page size (last page)
            if len(current_records) < page_size or len(all_records) >= total_available:
                logger.info(f"Pagination complete: fetched all available records")
                break
                
            page_start += page_size
        
        # Save all collected records (even if partial)
        if not all_records:
            logger.warning("No records fetched - API returned empty data")
            return "No Records Available"
        
        final_response = {'data': all_records}
        saved_id = SaveToDatabase(final_response, hsc, country, mode, start_date=sd, end_date=ed)
        if not saved_id:
            logger.error("Database save failed")
            return "Database Save Failed"
            
        logger.info(f"=== Eximpedia scraping completed ===")
        logger.info(f"Total records scraped: {len(all_records)}")
        logger.info(f"MongoDB ID: {saved_id}")
        
        return "Success"
        
    except Exception as e:
        logger.error(f"Unexpected error in ScrapeEximpedia: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return f"Unexpected Error: {str(e)}"


# def SearchHsCode(auth_data, taxonomy_info, sd, ed, sd1, ed1, hsc, country, mode):
#     payload2 = {
#       "countryCode": country.upper(),
#       "dateField": "IMP_DATE",
#       "endDate": ed,
#       "searchField": "HS_CODE",
#       "searchTerm": hsc,
#       "startDate": sd,
#       "tradeType": mode.upper(),
#       "hs_code_digit_classification": 8,
#       "dividedDateRange": [
#           {"leftFieldvalueHot": sd, "rightFieldValueHot": ed1},
#           {"leftFieldvalue": sd1, "rightFieldValue": sd1}
#         ],
#       "fieldValueRight":f'{hsc}99',
#       "fieldValueLeft": f'{hsc}00',
#       "dateExpression": 2,
#       "AdxToken": auth_data['adxToken'],
#       "AdxTokenExpireTime": auth_data['expTime']
#     }
#     print(json.dumps(payload2,indent=2))


def ScrapeEximpediaBatch(lst_of_dict):
    try:
        
        logger.info(f"=== Starting Batch Eximpedia scraping ===")
        sess, auth_data = AuthenticateSession()
        if not sess or not auth_data:
            logger.error("Authentication failed, aborting scraping")
            return "Authentication Failed"
        
        
        for lod in lst_of_dict:
            start_date, end_date, hscode, country, mode = lod['start_date'], lod['end_date'], lod['hscode'], lod['country'], lod['mode']
            taxonomy_info = GetTaxonomyData(sess, country, mode)
            
            sd, ed = ParseDates(start_date, end_date)
            if not taxonomy_info:
                logger.error("Taxonomy data retrieval failed, aborting scraping")
                return "Taxonomy Failed"
            
            # Fetch with pagination
            all_records = []
            page_start = 0
            page_size = 1000
            
            while True:
                payload = BuildRequestPayload(auth_data, taxonomy_info, sd, ed, hscode, country, mode, page_start, page_size)
                if not payload:
                    logger.error("Payload building failed, aborting scraping")
                    return "Payload Build Failed"
                    
                response_data = ExecuteAPIRequest(sess, payload)
                if not response_data:
                    logger.error("API request failed, aborting scraping")
                    return "API Request Failed"
                
                current_records = response_data.get('data', [])
                all_records.extend(current_records)
                
                total_available = response_data.get('recordsTotal', len(current_records))
                
                if len(current_records) < page_size or len(all_records) >= total_available:
                    break
                    
                page_start += page_size
            
            final_response = {'data': all_records}
            saved_id = SaveToDatabase(final_response, hscode, country, mode, start_date=sd, end_date=ed)
            if not saved_id:
                logger.error("Database save failed")
                return "Database Save Failed"
                
            logger.info(f"=== Eximpedia scraping completed successfully ===")
            logger.info(f"MongoDB ID: {saved_id}")
        
        return "Success"
        
    except Exception as e:
        logger.error(f"Unexpected error in ScrapeEximpedia: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return f"Unexpected Error: {str(e)}"

