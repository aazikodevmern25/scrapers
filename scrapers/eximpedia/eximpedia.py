import pandas as pd
import decrypt
from utils import FetchCountries, client, db
import copy
from decrypt import decrypt_exim_data
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


def AuthenticateSession():
    try:
        logger.info("Starting authentication process")
        sess = requests.Session(impersonate="chrome131")
        payload = {"email_id": "chhabinrai2017@gmail.com", "password": "Test@1234"}
        
        req = sess.put("https://web.eximpedia.app/backend/auths/login", json=payload, headers=headers)
        logger.info(f"Login request: {req.url} - Status: {req.status_code}")
        
        if req.status_code != 200:
            logger.error(f"Login request failed with status {req.status_code}")
            return None, None
            
        js = req.json()['data']
        if js['msg'] != "Access Granted":
            logger.error(f"Authentication failed: {js['msg']}")
            return None, None
            
        adxToken = js['adxToken']
        customerId = js['customer_id']
        userId = js['user_id']
        expTime = int(GetExpTime(adxToken)) * 1000
        
        headers['Adxtoken'] = adxToken
        headers['Ddxtokenexpiretime'] = str(expTime)
        
        logger.info(f"Authentication successful - Customer ID: {customerId}, User ID: {userId}")
        logger.debug(f"Token expiration time: {expTime}")
        
        return sess, {
            'adxToken': adxToken,
            'customerId': customerId,
            'userId': userId,
            'expTime': expTime
        }
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None, None


def GetTaxonomyData(sess, country, mode):
    try:
        logger.info(f"Retrieving taxonomy data for {country.upper()} - {mode.upper()}")
        
        req = sess.get(
            f'https://web.eximpedia.app/backend/taxonomies?countryName={country.upper()}&tradeType={mode.upper()}',
            headers=headers
        )
        logger.info(f"Taxonomy request: {req.url} - Status: {req.status_code}")
        
        # Eximpedia returns encrypted data even with 401 status - check for cryptexim field
        response_json = req.json()
        logger.debug(f"Raw response keys: {response_json.keys()}")
        
        if 'cryptexim' not in response_json:
            logger.error(f"Response does not contain 'cryptexim' key. Keys: {response_json.keys()}")
            logger.error(f"Full response: {json.dumps(response_json, indent=2)[:1000]}")
            return None
            
        txn = decrypt_exim_data(response_json['cryptexim'])
        
        if txn is None:
            logger.error("Decryption returned None")
            logger.error(f"Encrypted data sample: {response_json['cryptexim'][:100]}...")
            return None
        
        taxonomy_info = {
            'hs_code_digit_classification': txn['data'][0]['hs_code_digit_classification'],
            'date_field': txn['data'][0]['fields']['explore_aggregation']['sortTerm'],
            'all_fields': txn['data'][0]['fields']['all'],
            'group_expressions': txn['data'][0]['fields']['explore_aggregation']['groupExpressions'],
            'purchasable': txn['data'][0]['fields']['purchasable'],
            'sort_term': txn['data'][0]['fields']['records_aggregation']['sortTerm']
        }
        
        logger.info("Taxonomy data retrieved successfully:")
        logger.info(f"  - HS Code Classification: {taxonomy_info['hs_code_digit_classification']} digits")
        logger.info(f"  - Date Field: {taxonomy_info['date_field']}")
        logger.info(f"  - Sort Term: {taxonomy_info['sort_term']}")
        logger.info(f"  - All Fields Count: {len(taxonomy_info['all_fields'])}")
        logger.info(f"  - Group Expressions Count: {len(taxonomy_info['group_expressions'])}")
        logger.info(f"  - Purchasable Fields Count: {len(taxonomy_info['purchasable'])}")
        
        return taxonomy_info
    except Exception as e:
        logger.error(f"Taxonomy data retrieval failed for {country} - {mode}: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None


def BuildRequestPayload(auth_data, taxonomy_info, sd, ed, hsc, country, mode, page_start=0, page_length=1000):
    try:
        logger.info(f"Building request payload for {country.upper()} - {mode.upper()}")
        logger.debug(f"Date range: {sd} to {ed}")
        logger.debug(f"HS Code: {hsc}")
        
        if mode == 'import':
            cid = impCn[country]['code_iso_3']
        elif mode == 'export':
            cid = expCn[country]['code_iso_3']
        else:
            logger.error(f"Invalid mode: {mode}")
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
        if taxonomy_info['hs_code_digit_classification'] == 6:
            rp['matchExpressions'][1]['fieldValueArr'] = [
                {"fieldValueLeft": int(hsc), "fieldValueRight": int(hsc)}
            ]
            logger.debug(f"HS Code set for 6-digit classification: {hsc}")
        else:
            rp['matchExpressions'][1]['fieldValueArr'] = [
                {"fieldValueLeft": int(f'{hsc}00'), "fieldValueRight": int(f'{hsc}99')}
            ]
            logger.debug(f"HS Code set for 8-digit classification: {hsc}00-{hsc}99")
        
        logger.info("Request payload built successfully")
        return rp
    except Exception as e:
        logger.error(f"Payload building failed: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None


def ExecuteAPIRequest(sess, payload):
    try:
        logger.info(f"Executing API request (start: {payload.get('start', 0)}, length: {payload.get('length', 1000)})")
        
        req = sess.post(
            'https://web.eximpedia.app/backend/trade/shipments/explore/records',
            headers=headers,
            json=payload
        )
        logger.info(f"API request: {req.url} - Status: {req.status_code}")
        
        if req.status_code != 200:
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


def SaveToDatabase(response_data, hsc, country, mode):
    try:
        logger.info(f"Saving data to database for {country} - {mode}")
        
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
            "data": response_data.get('data', []),
            "record_count": len(response_data.get('data', [])),
            "country": country,
            "date_created": datetime.datetime.now(),
            "date_updated": datetime.datetime.now()
        }
        
        result = exCollection.insert_one(data)
        logger.info(f"Data saved successfully to MongoDB with ID: {result.inserted_id}")
        logger.info(f"Record count: {len(response_data.get('data', []))}")
        
        return result.inserted_id
    except Exception as e:
        logger.error(f"Database save failed: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None



def ScrapeEximpedia(sd, ed, hsc, country, mode):
    try:
        logger.info(f"=== Starting Eximpedia scraping ===")
        logger.info(f"Parameters: HS Code: {hsc}, Country: {country}, Mode: {mode}")
        logger.info(f"Date range: {sd} to {ed}")
        
        sess, auth_data = AuthenticateSession()
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
        
        while True:
            payload = BuildRequestPayload(auth_data, taxonomy_info, sd, ed, hsc, country, mode, page_start, page_size)
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
            logger.info(f"Fetched {len(all_records)} of {total_available} total records")
            
            # Break if we got all records or less than page size (last page)
            if len(current_records) < page_size or len(all_records) >= total_available:
                break
                
            page_start += page_size
        
        # Save all collected records
        final_response = {'data': all_records}
        saved_id = SaveToDatabase(final_response, hsc, country, mode)
        if not saved_id:
            logger.error("Database save failed")
            return "Database Save Failed"
            
        logger.info(f"=== Eximpedia scraping completed successfully ===")
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
            saved_id = SaveToDatabase(final_response, hscode, country, mode)
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

