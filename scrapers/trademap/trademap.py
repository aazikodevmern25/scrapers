import copy
import logging
import traceback
from twocaptcha import TwoCaptcha
from rapidfuzz import fuzz
from scrapy import Selector
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from urllib.parse import quote, urlencode
import sys
import os
import pandas as pd
# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from utils import *
import scraper_helper
import json
import datetime
from curl_cffi import requests
from dataparser import parse_trademap_table_flexible
from utils import client
import os
from pathlib import Path

# Configure logging
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir,'trademap_scraper.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load proxies
try:
    proxies_df = pd.read_csv('config/proxies.txt', names=['proxy'])
    PROXIES = proxies_df['proxy'].to_list()
    logger.info(f"Loaded {len(PROXIES)} proxies from config/proxies.txt")
except Exception as e:
    logger.warning(f"Failed to load proxies: {e}. Running without proxy.")
    PROXIES = []

def get_random_proxy():
    """Get a random proxy from the list"""
    if not PROXIES:
        return None
    proxy_string = random.choice(PROXIES)
    parts = proxy_string.split(':')
    if len(parts) == 4:
        host, port, username, password = parts
        proxy_url = f"http://{username}:{password}@{host}:{port}"
        logger.info(f"Using proxy: {host}:{port}")
        return proxy_url
    return None

# Get the directory of this file for relative paths
_current_dir = Path(__file__).parent

# Load payloads
try:
    payload1 = json.load(open(_current_dir / 'payloads/payload1.json','r',encoding='utf-8'))
    payload2 = json.load(open(_current_dir / 'payloads/payload2.json','r',encoding='utf-8'))
    payloadQ1 = json.load(open(_current_dir / 'payloads/quarterly_payload.json','r',encoding='utf-8'))
    payloadQ2 = json.load(open(_current_dir / 'payloads/quarterly_payload2.json','r',encoding='utf-8'))
    payloadM1 = json.load(open(_current_dir / 'payloads/monthly_payload1.json','r',encoding='utf-8'))
    payloadM2 = json.load(open(_current_dir / 'payloads/monthly_payload2.json','r',encoding='utf-8'))
    logger.info("Successfully loaded all payload files")
except Exception as e:
    logger.error(f"Failed to load payload files: {e}")
    raise
# Using db from utils (no need to recreate)
trademap_collection = db['trademap']

json_headers = """
Accept: */*
Accept-Encoding: gzip, deflate, br, zstd
Accept-Language: en-US,en;q=0.9
Connection: keep-aliven
Content-Type: application/json; charset=utf-8
Host: www.trademap.org
Referer: https://www.trademap.org/Index.aspx
Sec-Fetch-Dest: empty
Sec-Fetch-Mode: cors
Sec-Fetch-Site: same-origin
User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36
sec-ch-ua: "Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"
sec-ch-ua-mobile: ?0RadComboBox_Partner_text
sec-ch-ua-platform: "Linux"
"""
json_headers = scraper_helper.get_dict(json_headers)

post_headers = """
Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7
Accept-Encoding: gzip, deflate, br, zstd
Accept-Language: en-US,en;q=0.9
Cache-Control: max-age=0
Connection: keep-alive
Content-Length: 3071
Content-Type: application/x-www-form-urlencoded
Host: www.trademap.org
Origin: https://www.trademap.org
Referer: https://www.trademap.org/Index.aspx
Sec-Fetch-Dest: document
Sec-Fetch-Mode: navigate
Sec-Fetch-Site: same-origin
Sec-Fetch-User: ?1
Upgrade-Insecure-Requests: 1
User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36
sec-ch-ua: "Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"
sec-ch-ua-mobile: ?0
sec-ch-ua-platform: "Linux"
"""
post_headers = scraper_helper.get_dict(post_headers)
headers = None

def solver():
    try:
        logger.info("Starting CAPTCHA solving process")
        config = {
            'apiKey': 'baf9821867a0c0414a15c5b6ac77599c',
            'defaultTimeout': 300,
            'recaptchaTimeout': 400,
            'pollingInterval': 10,
        }
        solver = TwoCaptcha(**config)
        result = solver.normal(file='./captcha.jpeg')
        logger.info("CAPTCHA solved successfully")
        return result['code']
    except Exception as e:
        logger.error(f"CAPTCHA solving failed: {e}")
        raise

def CaptchaSolver(driver):
    try:
        logger.info("Detecting and solving CAPTCHA")
        img_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"
        }
        img_url = Selector(text=driver.page_source).xpath('//div[@class="div_captchaImg"]/img/@src').get()
        if img_url:
            img_url = f'https://www.trademap.org/{img_url}'
            req = requests.get(img_url, headers=img_headers)
            logger.info(f"CAPTCHA image downloaded: {req.url} - Status: {req.status_code}")
            
            with open('captcha.jpeg','wb') as f:
                f.write(req.content)
            
            code = solver()
            driver.find_element(By.CSS_SELECTOR, 'input[id="ctl00_PageContent_CaptchaAnswer"]').send_keys(code)
            time.sleep(1)
            driver.find_element(By.CSS_SELECTOR, 'input[value="Validate"]').click()
            time.sleep(3)
            logger.info("CAPTCHA validation completed")
    except Exception as e:
        logger.error(f"CAPTCHA handling failed: {e}")
        raise

def ParseCountry(country, hsValue):
    try:
        logger.info(f"Parsing country: {country}")
        country_url = f'https://www.trademap.org/Index.aspx?nvpm=1|||||||||||||||||&=&rcbID=ctl00_PageContent_RadComboBox_Country&rcbServerID=RadComboBox_Country&text={quote(country)}&comboText={quote(country)}&comboValue=&skin=WebBlue&clientDataString=C&timeStamp={int(datetime.datetime.now().timestamp())}'
        
        req = requests.get(country_url, headers=json_headers)
        logger.info(f"Country search request: {req.url} - Status: {req.status_code}")
        
        if req.status_code != 200:
            logger.error(f"Country search failed with status {req.status_code}")
            return None, None
            
        c1, c2 = None, None
        for i in req.json()['Items']:
            if fuzz.ratio(country.lower(), i['Text'].lower()) > 85:
                c1 = i['Text']
                c2 = i['Value']
                logger.info(f"Country match found: {c1} ({c2})")
                break
        
        if not c1:
            logger.warning(f"No matching country found for: {country}")
            
        return c1, c2
    except Exception as e:
        logger.error(f"Country parsing failed for {country}: {e}")
        return None, None

def InitializeDriver():
    try:
        logger.info("Initializing Selenium driver (headless mode for server)")
        
        chrome_options = Options()
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
        # Don't use user-data-dir to avoid creating temp folders
        
        driver = webdriver.Chrome(options=chrome_options)
        logger.info("Driver initialized successfully (headless mode)")
        driver.get('https://www.trademap.org/Index.aspx')
        time.sleep(2)
        
        resp = Selector(text=driver.page_source)
        if resp.xpath('//a[@onclick="Login();"]').get():
            logger.info("Login required, proceeding with authentication")
            driver.find_element(By.CSS_SELECTOR, 'a[onclick="Login();"]').click()
            time.sleep(2)
            
            resp = Selector(text=driver.page_source)
            if resp.xpath('//button[@value="login"]'):
                logger.info("Filling login credentials")
                driver.find_element(By.CSS_SELECTOR, 'input[aria-label="Username"]').send_keys('aazikodevteamleader@gmail.com')
                driver.find_element(By.CSS_SELECTOR, 'input[aria-label="Password"]').send_keys('Aaziko@123')
                time.sleep(1)
                driver.find_element(By.CSS_SELECTOR, 'label[class="switch switch-remember"]').click()
                driver.find_element(By.CSS_SELECTOR, 'button[value="login"]').click()
                time.sleep(3)
                logger.info("Login submitted")
            elif Selector(text=driver.page_source).xpath('//div[@class="div_captchaImg"]').get():
                CaptchaSolver(driver)
                
            resp = Selector(text=driver.page_source)
            if Selector(text=driver.page_source).xpath('//div[@class="div_captchaImg"]').get():
                CaptchaSolver(driver)
        
        logger.info("Driver initialization completed successfully")
        return driver
    except Exception as e:
        logger.error(f"Driver initialization failed: {e}")
        raise

def DetectCaptcha(driver):

    try:
        if Selector(text=driver.page_source).xpath('//div[@class="div_captchaImg"]').get():
            logger.info("CAPTCHA detected, solving...")
            CaptchaSolver(driver)
            driver.get('https://www.trademap.org/Index.aspx')
        else:
            logger.info("No CAPTCHA detected")
    except Exception as e:
        logger.error(f"CAPTCHA detection failed: {e}")
        raise

def GetCookies(driver):
    global headers, json_headers, post_headers
    try:
        logger.info("Extracting cookies from browser")
        
        # Method 1: Try from driver cookies directly (more reliable)
        try:
            cookies = driver.get_cookies()
            cookie_strings = []
            for cookie in cookies:
                cookie_strings.append(f"{cookie['name']}={cookie['value']}")
            
            if cookie_strings:
                cookie_header = '; '.join(cookie_strings)
                json_headers['Cookie'] = cookie_header
                post_headers['Cookie'] = cookie_header
                logger.info(f"Cookies extracted successfully: {cookie_header[:100]}...")
                return
        except Exception as e:
            logger.warning(f"Direct cookie extraction failed, trying logs: {e}")
        
        # Method 2: Fallback to performance logs
        logger.info("Trying cookie extraction from performance logs")
        logs = driver.get_log("performance")
        
        for entry in logs:
            log = json.loads(entry["message"])["message"]["params"]
            
            if 'associatedCookies' not in log:
                continue
            if 'Cookie' not in log.get('headers', {}):
                continue
            
            cookie_header = log['headers']['Cookie']
            referer = log['headers'].get('Referer',None)
            
            # Check for required cookies and referer
            has_session_id = 'ASP.NET_SessionId' in cookie_header
            has_access_token = 'TradeMap.access_token' in cookie_header
            is_correct_referer = referer == "https://www.trademap.org/Index.aspx"
            
            if has_session_id and has_access_token and is_correct_referer:
                print(log.keys())
                headers = log['headers']
                json_headers['Cookie'] = headers['Cookie']
                post_headers['Cookie'] = headers['Cookie']
                logger.info("Cookies extracted successfully from logs")
                return
        
        logger.warning("Required cookies not found in logs")
    except Exception as e:
        logger.error(f"Cookie extraction failed: {e}")
        raise

def get_trademap_url_params(time_series, view_type, value_type):
    """
    Map time_series, view_type, value_type to TradeMap URL parameters
    Returns: (frequency, indicator_code, view_code) tuple
    """
    freq_map = {"yearly": "1", "quarterly": "3", "monthly": "5", "trade_indicators": "1"}
    indicator_map = {"values": "1", "quantities": "2", "growth_value": "3", "growth_quantity": "4", "share_value": "5", "unit_values": "6", "growth_unit_values": "7", "index_values": "8", "index_unit_values": "9"}
    view_map = {"by_country": "2", "by_product": "4", "by_service": "6"}
    return freq_map.get(time_series, "1"), indicator_map.get(value_type, "1"), view_map.get(view_type, "2")

def ScrapeDataByTypeSelenium(driver, mode, country1_code, country2_code, hs_code, time_series="yearly", view_type="by_country", value_type="values"):
    """Universal scraping function for all combinations of time_series, view_type, and value_type"""
    try:
        logger.info(f"ScrapeDataByTypeSelenium: mode={mode}, ts={time_series}, view={view_type}, value={value_type}")
        frequency, indicator, view = get_trademap_url_params(time_series, view_type, value_type)
        trade_type = "1" if mode == "I" else "2"
        url = f"https://www.trademap.org/Bilateral_TS.aspx?nvpm=1%7c{country2_code}%7c%7c{country1_code}%7c%7c{hs_code}%7c%7c%7c4%7c{frequency}%7c{trade_type}%7c2%7c{indicator}%7c1%7c{view}%7c1%7c1%7c1"
        logger.info(f"Navigating to: {url}")
        driver.get(url)
        time.sleep(3)
        try:
            WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.ID, "ctl00_PageContent_MyGridView1")))
        except:
            logger.warning(f"Table not found after navigation")
        select_20_per_page(driver)
        try:
            WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.ID, "ctl00_PageContent_MyGridView1")))
        except:
            pass
        resp = Selector(text=driver.page_source)
        table_ = resp.xpath('//table[@id="ctl00_PageContent_MyGridView1"]').get()
        if not table_:
            table_ = resp.xpath('//table[contains(@id, "GridView")]').get()
        if table_:
            data = parse_trademap_table_flexible(table_)
            logger.info(f"Successfully scraped: {time_series}/{view_type}/{value_type} for mode {mode}")
            return data
        else:
            logger.warning(f"No table found for: {time_series}/{view_type}/{value_type}")
            return {"format": "no_data", "trade_descriptions": [], "years": [], "products": []}
    except Exception as e:
        logger.error(f"ScrapeDataByTypeSelenium failed: {e}")
        return {"format": "error", "error": str(e), "trade_descriptions": [], "years": [], "products": []}

def MapDataEnhanced(scraped_data, hscode, hsv, hst, c1, c2, time_series, view_type, value_type):
    """Enhanced MapData that saves data with scraping parameters metadata"""
    try:
        logger.info(f"Mapping enhanced data: {hscode} ({c1} -> {c2}), ts={time_series}, view={view_type}, value={value_type}")
        main_data = {"Country1": c1, "Country2": c2, "ScrapingParams": {"time_series": time_series, "view_type": view_type, "value_type": value_type}, "Data": scraped_data}
        data = {"ScraperName": "trademap_scraper", "HsCode": hscode, "HsCodeSearched": hsv, "ProductName": hst, "Source": "TradeMap", "TimeSeries": time_series, "ViewType": view_type, "ValueType": value_type, "Month": datetime.datetime.now().strftime("%b"), "Year": datetime.datetime.now().strftime("%Y"), "Data": main_data, "DateCreated": datetime.datetime.now(), "DateUpdated": datetime.datetime.now()}
        filter_query = {"HsCode": hscode, "Data.Country1": c1, "Data.Country2": c2, "TimeSeries": time_series, "ViewType": view_type, "ValueType": value_type}
        existing = trademap_collection.find_one(filter_query)
        if existing:
            trademap_collection.update_one(filter_query, {"$set": {"Data": main_data, "ProductName": hst, "DateUpdated": datetime.datetime.now()}})
            logger.info(f"Updated existing record: {hscode} ({c1}->{c2}), {time_series}/{view_type}/{value_type}")
        else:
            result = trademap_collection.insert_one(data)
            logger.info(f"Saved new record with ID: {result.inserted_id}")
    except Exception as e:
        logger.error(f"MapDataEnhanced failed: {e}")
        raise


def MapData(yqm, hscode, hsv, hst, c1, c2, mode):
    try:
        logger.info(f"Mapping data for {mode}: {hscode} ({c1} -> {c2})")
        main_data = {
            'Country1': c1,
            'Country2': c2,
            mode: yqm
        }
        
        data = {
            "ScraperName": "trademap_scraper",
            "HsCode": hscode,
            'HsCodeSearched': hsv,
            "ProductName": hst,
            "Source": "TradeMap",
            "Mode": mode,
            "Month": datetime.datetime.now().strftime("%b"),
            "Year": datetime.datetime.now().strftime("%Y"),
            "Data": main_data,
            "DateCreated": datetime.datetime.now(),
            "DateUpdated": datetime.datetime.now()
        }
        
        # Prevent duplicates: unique combination of HsCode + Country1 + Country2 + Mode
        # Import and Export are different, so same HS code with different modes is allowed
        filter_query = {
            "HsCode": hscode,
            "Data.Country1": c1,
            "Data.Country2": c2,
            "Mode": mode
        }
        
        # Check if record already exists
        existing = trademap_collection.find_one(filter_query)
        if existing:
            # Update existing record instead of creating duplicate
            result = trademap_collection.update_one(
                filter_query,
                {"$set": {
                    "Data": main_data,
                    "ProductName": hst,
                    "DateUpdated": datetime.datetime.now()
                }}
            )
            logger.info(f"Updated existing record in MongoDB (HsCode: {hscode}, {c1}->{c2}, Mode: {mode})")
        else:
            # Insert new record
            result = trademap_collection.insert_one(data)
            logger.info(f"Data saved to MongoDB with ID: {result.inserted_id}")
        
    except Exception as e:
        logger.error(f"Data mapping/saving failed: {e}")
        raise

def ScrapeYearlyData(vs, vg, code_list, mode):
    try:
        logger.info(f"Starting yearly data scraping for mode: {mode}")
        hsText, hsValue, cText1, cValue1, cText2, cValue2 = code_list
        
        yearly_payload = copy.deepcopy(payload1)
        yearly_payload['__VIEWSTATE'] = vs
        yearly_payload['__VIEWSTATEGENERATOR'] = vg
        yearly_payload['ctl00$PageContent$RadComboBox_Product_Input'] = hsText
        yearly_payload['ctl00$PageContent$RadComboBox_Product_value'] = hsValue
        yearly_payload['ctl00$PageContent$RadComboBox_Product_text'] = hsText
        yearly_payload['ctl00$PageContent$RadComboBox_Country_Input'] = cText1
        yearly_payload['ctl00$PageContent$RadComboBox_Country_value'] = cValue1
        yearly_payload['ctl00$PageContent$RadComboBox_Country_text'] = cText1
        yearly_payload['ctl00$PageContent$RadComboBox_Partner_Input'] = cText2
        yearly_payload['ctl00$PageContent$RadComboBox_Partner_value'] = cValue2
        yearly_payload['ctl00$PageContent$RadComboBox_Partner_text'] = cText2
        yearly_payload['ctl00$PageContent$RadioButton_TradeType'] = mode
        yearly_payload = urlencode(yearly_payload)
        
        req = requests.post('https://www.trademap.org/Index.aspx',
            headers=post_headers, data=yearly_payload, allow_redirects=True)
        logger.info(f"First yearly request: {req.url} - Status: {req.status_code}")
        
        if req.status_code != 200:
            logger.error(f"First yearly request failed with status {req.status_code}")
            return {}
        
        resp = Selector(text=req.text)
        viewgenerator = resp.xpath('//input[@name="__VIEWSTATEGENERATOR"]/@value').get()
        viewstate = resp.xpath('//input[@name="__VIEWSTATE"]/@value').get()
        forgeryToken = resp.xpath('//input[@id="ctl00_forgeryToken"]/@value').get()
        oldNumTimePeriod = resp.xpath('//input[@name="ctl00$PageContent$GridViewPanelControl$HiddenField_OldNumTimePeriod"]/@value').get()
        gridViewColumns = resp.xpath('//input[@name="ctl00$PageContent$GridViewPanelControl$HiddenField_OldGridViewColumns"]/@value').get()
        lastTimePeriod = resp.xpath('//input[@name="ctl00$PageContent$GridViewPanelControl$HiddenField_CurrentLastTimePeriod"]/@value').get()
        referencePeriod = resp.xpath('//input[@name="ctl00$PageContent$GridViewPanelControl$HiddenField_Current_TS_ReferencePeriod"]/@value').get()
        
        yearly_payload2 = copy.deepcopy(payload2)
        yearly_payload2['__VIEWSTATE'] = viewstate
        yearly_payload2['__VIEWSTATEGENERATOR'] = viewgenerator
        yearly_payload2['ctl00$forgeryToken'] = forgeryToken
        yearly_payload2['ctl00$NavigationControl$DropDownList_Product'] = hsValue
        yearly_payload2['ctl00$NavigationControl$DropDownList_Country'] = cValue1
        yearly_payload2['ctl00$NavigationControl$DropDownList_Partner'] = cValue2
        yearly_payload2['ctl00$NavigationControl$HiddenField_Current_ProductCode'] = hsValue
        yearly_payload2['ctl00$NavigationControl$HiddenField_Current_CountryCode'] = cValue1
        yearly_payload2['ctl00$NavigationControl$HiddenField_Current_PartnerCode'] = cValue2
        yearly_payload2['ctl00$PageContent$GridViewPanelControl$HiddenField_OldNumTimePeriod'] = oldNumTimePeriod 
        yearly_payload2['ctl00$PageContent$GridViewPanelControl$HiddenField_OldGridViewColumns'] = gridViewColumns 
        yearly_payload2['ctl00$PageContent$GridViewPanelControl$HiddenField_CurrentLastTimePeriod'] = lastTimePeriod
        yearly_payload2['ctl00$PageContent$GridViewPanelControl$HiddenField_Current_TS_LastTimePeriod'] = lastTimePeriod  
        yearly_payload2['ctl00$PageContent$GridViewPanelControl$HiddenField_Current_TS_ReferencePeriod'] = referencePeriod  
        yearly_payload2['ctl00$NavigationControl$DropDownList_TradeType'] = mode
        
        yearly_payload2 = urlencode(yearly_payload2)
        next_url = resp.xpath('//form[@name="aspnetForm"]/@action').get()
        
        if next_url:
            next_url = f'https://www.trademap.org/{next_url}'
            req = requests.post(next_url, headers=post_headers, data=yearly_payload2)
            logger.info(f"Second yearly request: {req.url} - Status: {req.status_code}")
            
            if req.status_code == 200:
                resp = Selector(text=req.text)
                table_ = resp.xpath('//table[@id="ctl00_PageContent_MyGridView1"]').get()
                data = parse_trademap_table_flexible(table_)
                logger.info(f"Yearly data scraped successfully for mode: {mode}")
                return data
            else:
                logger.error(f"Second yearly request failed with status {req.status_code}")
                return {}
        else:
            logger.error("No next URL found for yearly data")
            return {}
            
    except Exception as e:
        logger.error(f"Yearly data scraping failed for mode {mode}: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {}





def select_20_per_page(driver):
    """Select 20 per page from the dropdown to get more years of data"""
    try:
        # Find the per-page dropdown
        dropdown_selectors = [
            '//select[contains(@id, "DropDownList_PageSize")]',
            '//select[contains(@id, "PageSize")]',
            '//select[option[text()="20 per page"]]',
            '//select[option[contains(text(), "per page")]]',
        ]
        
        for selector in dropdown_selectors:
            try:
                dropdown = driver.find_element(By.XPATH, selector)
                if dropdown:
                    from selenium.webdriver.support.ui import Select
                    select = Select(dropdown)
                    # Try to select 20 per page
                    try:
                        select.select_by_visible_text("20 per page")
                        logger.info("Selected 20 per page from dropdown")
                        time.sleep(2)
                        return True
                    except:
                        # Try by value
                        try:
                            select.select_by_value("20")
                            logger.info("Selected 20 per page by value")
                            time.sleep(2)
                            return True
                        except:
                            pass
            except:
                continue
        
        logger.warning("Could not find per-page dropdown")
        return False
    except Exception as e:
        logger.warning(f"Error selecting 20 per page: {e}")
        return False

def ScrapeYearlyDataSelenium(driver, mode, country1_code, country2_code, hs_code):
    """Scrape yearly data using Selenium to maintain session"""
    try:
        logger.info(f"Starting Selenium yearly data scraping for mode: {mode}")
        
        trade_type = "1" if mode == "I" else "2"
        yearly_url = f"https://www.trademap.org/Bilateral_TS.aspx?nvpm=1%7c{country2_code}%7c%7c{country1_code}%7c%7c{hs_code}%7c%7c%7c4%7c1%7c1%7c{trade_type}%7c2%7c1%7c1%7c1%7c1%7c1"
        
        logger.info(f"Navigating to yearly page: {yearly_url}")
        driver.get(yearly_url)
        time.sleep(3)
        
        # Wait for table
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.ID, "ctl00_PageContent_MyGridView1"))
            )
        except:
            logger.warning(f"Yearly table not found after navigation")
        
        # Select 20 per page to get more years of data
        select_20_per_page(driver)
        
        # Wait for table to reload with more data
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.ID, "ctl00_PageContent_MyGridView1"))
            )
        except:
            pass
        
        resp = Selector(text=driver.page_source)
        table_ = resp.xpath('//table[@id="ctl00_PageContent_MyGridView1"]').get()
        if not table_:
            table_ = resp.xpath('//table[contains(@id, "GridView")]').get()
        
        if table_:
            data = parse_trademap_table_flexible(table_)
            logger.info(f"Selenium yearly data scraped successfully for mode: {mode}")
            return data
        else:
            logger.warning(f"Selenium yearly: No table found for mode: {mode}")
            return {"format": "no_data", "trade_descriptions": [], "years": [], "products": []}
            
    except Exception as e:
        logger.error(f"Selenium yearly data scraping failed for mode {mode}: {e}")
        return {"format": "no_data", "trade_descriptions": [], "years": [], "products": []}

def check_and_reauth(driver):
    """Check if we're on a login page and re-authenticate if needed"""
    try:
        page_source = driver.page_source.lower()
        if 'login' in page_source or 'sign in' in page_source or len(driver.page_source) < 1000:
            logger.warning("Login page detected, re-authenticating...")
            driver.get('https://www.trademap.org/Index.aspx')
            time.sleep(2)
            DetectCaptcha(driver)
            GetCookies(driver)
            return True
        return False
    except Exception as e:
        logger.warning(f"Error checking auth status: {e}")
        return False

def ScrapeQuarterlyDataSelenium(driver, mode, country1_code, country2_code, hs_code):
    """Scrape quarterly data by clicking on quarterly link/button on the page"""
    try:
        logger.info(f"Starting Selenium quarterly data scraping for mode: {mode}")
        
        # Look for quarterly time series link or button on the current page
        quarterly_found = False
        
        # Try clicking on "Quarterly time series" link
        quarterly_selectors = [
            '//a[contains(text(), "Quarterly")]',
            '//input[contains(@value, "Quarterly")]',
            '//button[contains(text(), "Quarterly")]',
            '//select/option[contains(text(), "Quarterly")]',
            '//*[contains(@id, "Quarterly")]',
            '//*[contains(@id, "TimeSeries_Q")]',
        ]
        
        for selector in quarterly_selectors:
            try:
                element = driver.find_element(By.XPATH, selector)
                if element:
                    logger.info(f"Found quarterly element with selector: {selector}")
                    driver.execute_script("arguments[0].click();", element)
                    time.sleep(3)
                    quarterly_found = True
                    break
            except:
                continue
        
        if not quarterly_found:
            # If no quarterly control found, try URL navigation as fallback
            trade_type = "1" if mode == "I" else "2"
            quarterly_url = f"https://www.trademap.org/Bilateral_MQ_TS.aspx?nvpm=1%7c{country2_code}%7c%7c{country1_code}%7c%7c{hs_code}%7c%7c%7c4%7c1%7c1%7c{trade_type}%7c2%7c2%7c1%7c1%7c1%7c1"
            logger.info(f"No quarterly control found, trying URL: {quarterly_url}")
            driver.get(quarterly_url)
            time.sleep(3)
            
            if check_and_reauth(driver):
                driver.get(quarterly_url)
                time.sleep(3)
        
        # Select 20 per page to get more data
        select_20_per_page(driver)
        time.sleep(2)
        
        # Parse the table
        resp = Selector(text=driver.page_source)
        table_ = resp.xpath('//table[@id="ctl00_PageContent_MyGridView1"]').get()
        if not table_:
            table_ = resp.xpath('//table[contains(@id, "GridView")]').get()
        
        if table_:
            data = parse_trademap_table_flexible(table_)
            logger.info(f"Selenium quarterly data scraped successfully for mode: {mode}")
            return data
        else:
            logger.warning(f"Selenium quarterly: No table found for mode: {mode}")
            return {"format": "no_data", "trade_descriptions": [], "years": [], "products": []}
            
    except Exception as e:
        logger.error(f"Selenium quarterly data scraping failed for mode {mode}: {e}")
        return {"format": "no_data", "trade_descriptions": [], "years": [], "products": []}


def ScrapeMonthlyDataSelenium(driver, mode, country1_code, country2_code, hs_code):
    """Scrape monthly data by clicking on monthly link/button on the page"""
    try:
        logger.info(f"Starting Selenium monthly data scraping for mode: {mode}")
        
        # Look for monthly time series link or button on the current page
        monthly_found = False
        
        # Try clicking on "Monthly time series" link
        monthly_selectors = [
            '//a[contains(text(), "Monthly")]',
            '//input[contains(@value, "Monthly")]',
            '//button[contains(text(), "Monthly")]',
            '//select/option[contains(text(), "Monthly")]',
            '//*[contains(@id, "Monthly")]',
            '//*[contains(@id, "TimeSeries_M")]',
        ]
        
        for selector in monthly_selectors:
            try:
                element = driver.find_element(By.XPATH, selector)
                if element:
                    logger.info(f"Found monthly element with selector: {selector}")
                    driver.execute_script("arguments[0].click();", element)
                    time.sleep(3)
                    monthly_found = True
                    break
            except:
                continue
        
        if not monthly_found:
            # If no monthly control found, try URL navigation as fallback
            trade_type = "1" if mode == "I" else "2"
            monthly_url = f"https://www.trademap.org/Bilateral_MQ_TS.aspx?nvpm=1%7c{country2_code}%7c%7c{country1_code}%7c%7c{hs_code}%7c%7c%7c4%7c1%7c1%7c{trade_type}%7c2%7c3%7c1%7c1%7c1%7c1"
            logger.info(f"No monthly control found, trying URL: {monthly_url}")
            driver.get(monthly_url)
            time.sleep(3)
            
            if check_and_reauth(driver):
                driver.get(monthly_url)
                time.sleep(3)
        
        # Select 20 per page to get more data
        select_20_per_page(driver)
        time.sleep(2)
        
        # Parse the table
        resp = Selector(text=driver.page_source)
        table_ = resp.xpath('//table[@id="ctl00_PageContent_MyGridView1"]').get()
        if not table_:
            table_ = resp.xpath('//table[contains(@id, "GridView")]').get()
        
        if table_:
            data = parse_trademap_table_flexible(table_)
            logger.info(f"Selenium monthly data scraped successfully for mode: {mode}")
            return data
        else:
            logger.warning(f"Selenium monthly: No table found for mode: {mode}")
            return {"format": "no_data", "trade_descriptions": [], "years": [], "products": []}
            
    except Exception as e:
        logger.error(f"Selenium monthly data scraping failed for mode {mode}: {e}")
        return {"format": "no_data", "trade_descriptions": [], "years": [], "products": []}


def ScrapeQuarterlyData(vs, vg, code_list, mode):
    try:
        logger.info(f"Starting quarterly data scraping for mode: {mode}")
        hsText, hsValue, cText1, cValue1, cText2, cValue2 = code_list
        
        q_payload = copy.deepcopy(payloadQ1)
        q_payload['__VIEWSTATE'] = vs
        q_payload['__VIEWSTATEGENERATOR'] = vg
        q_payload['ctl00$PageContent$RadComboBox_Product_Input'] = hsText
        q_payload['ctl00$PageContent$RadComboBox_Product_value'] = hsValue
        q_payload['ctl00$PageContent$RadComboBox_Product_text'] = hsText
        q_payload['ctl00$PageContent$RadComboBox_Country_Input'] = cText1
        q_payload['ctl00$PageContent$RadComboBox_Country_value'] = cValue1
        q_payload['ctl00$PageContent$RadComboBox_Country_text'] = cText1
        q_payload['ctl00$PageContent$RadComboBox_Partner_Input'] = cText2
        q_payload['ctl00$PageContent$RadComboBox_Partner_value'] = cValue2
        q_payload['ctl00$PageContent$RadComboBox_Partner_text'] = cText2
        q_payload['ctl00$PageContent$RadioButton_TradeType'] = mode
        q_payload = urlencode(q_payload)
        
        req = requests.post('https://www.trademap.org/Index.aspx',
            headers=post_headers, data=q_payload, allow_redirects=True)
        logger.info(f"First quarterly request: {req.url} - Status: {req.status_code}")
        
        if req.status_code != 200:
            logger.error(f"First quarterly request failed with status {req.status_code}")
            return {}
        
        resp = Selector(text=req.text)
        viewgenerator = resp.xpath('//input[@name="__VIEWSTATEGENERATOR"]/@value').get()
        viewstate = resp.xpath('//input[@name="__VIEWSTATE"]/@value').get()
        forgeryToken = resp.xpath('//input[@id="ctl00_forgeryToken"]/@value').get()
        oldNumTimePeriod = resp.xpath('//input[@name="ctl00$PageContent$GridViewPanelControl$HiddenField_OldNumTimePeriod"]/@value').get()
        gridViewColumns = resp.xpath('//input[@name="ctl00$PageContent$GridViewPanelControl$HiddenField_OldGridViewColumns"]/@value').get()
        lastTimePeriod = resp.xpath('//input[@name="ctl00$PageContent$GridViewPanelControl$HiddenField_CurrentLastTimePeriod"]/@value').get()
        referencePeriod = resp.xpath('//input[@name="ctl00$PageContent$GridViewPanelControl$HiddenField_Current_TS_ReferencePeriod"]/@value').get()
        
        q_payload2 = copy.deepcopy(payloadQ2)
        q_payload2['__VIEWSTATE'] = viewstate
        q_payload2['__VIEWSTATEGENERATOR'] = viewgenerator
        q_payload2['ctl00$forgeryToken'] = forgeryToken
        q_payload2['ctl00$NavigationControl$DropDownList_Product'] = hsValue
        q_payload2['ctl00$NavigationControl$DropDownList_Country'] = cValue1
        q_payload2['ctl00$NavigationControl$DropDownList_Partner'] = cValue2
        q_payload2['ctl00$NavigationControl$HiddenField_Current_ProductCode'] = hsValue
        q_payload2['ctl00$NavigationControl$HiddenField_Current_CountryCode'] = cValue1
        q_payload2['ctl00$NavigationControl$HiddenField_Current_PartnerCode'] = cValue2
        q_payload2['ctl00$PageContent$GridViewPanelControl$HiddenField_OldNumTimePeriod'] = oldNumTimePeriod 
        q_payload2['ctl00$PageContent$GridViewPanelControl$HiddenField_OldGridViewColumns'] = gridViewColumns 
        q_payload2['ctl00$PageContent$GridViewPanelControl$HiddenField_CurrentLastTimePeriod'] = lastTimePeriod
        q_payload2['ctl00$PageContent$GridViewPanelControl$HiddenField_Current_TS_LastTimePeriod'] = lastTimePeriod  
        q_payload2['ctl00$PageContent$GridViewPanelControl$HiddenField_Current_TS_ReferencePeriod'] = referencePeriod  
        q_payload2['ctl00$NavigationControl$DropDownList_TradeType'] = mode
        q_payload2 = urlencode(q_payload2)
        
        next_url = resp.xpath('//form[@name="aspnetForm"]/@action').get()
        if next_url:
            next_url = f'https://www.trademap.org/{next_url}'
            req = requests.post(next_url, headers=post_headers, data=q_payload2)
            logger.info(f"Second quarterly request: {req.url} - Status: {req.status_code}")
            
            if req.status_code == 200:
                resp = Selector(text=req.text)
                # Try primary table selector
                table_ = resp.xpath('//table[@id="ctl00_PageContent_MyGridView1"]').get()
                
                # If primary fails, try alternative selectors
                if not table_:
                    table_ = resp.xpath('//table[contains(@id, "GridView")]').get()
                if not table_:
                    table_ = resp.xpath('//table[@class="tbldata"]').get()
                if not table_:
                    # Log available tables for debugging
                    all_tables = resp.xpath('//table/@id').getall()
                    logger.warning(f"Quarterly: Primary table not found. Available tables: {all_tables[:5]}")
                    # Check for "no data" messages
                    no_data_msg = resp.xpath('//span[contains(text(), "No data")]/text()').get()
                    page_title = resp.xpath('//title/text()').get()
                    body_text = resp.xpath('//body//text()').getall()[:10]
                    logger.warning(f"Quarterly page title: {page_title}")
                    if no_data_msg:
                        logger.warning(f"Quarterly: No data message found: {no_data_msg}")
                
                data = parse_trademap_table_flexible(table_)
                logger.info(f"Quarterly data scraped successfully for mode: {mode}")
                return data
            else:
                logger.error(f"Second quarterly request failed with status {req.status_code}")
                return {}
        else:
            logger.error("No next URL found for quarterly data")
            return {}
            
    except Exception as e:
        logger.error(f"Quarterly data scraping failed for mode {mode}: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {}

def ScrapeMonthlyData(vs, vg, code_list, mode):
    try:
        logger.info(f"Starting monthly data scraping for mode: {mode}")
        hsText, hsValue, cText1, cValue1, cText2, cValue2 = code_list
        
        m_payload = copy.deepcopy(payloadM1)
        m_payload['__VIEWSTATE'] = vs
        m_payload['__VIEWSTATEGENERATOR'] = vg
        m_payload['ctl00$PageContent$RadComboBox_Product_Input'] = hsText
        m_payload['ctl00$PageContent$RadComboBox_Product_value'] = hsValue
        m_payload['ctl00$PageContent$RadComboBox_Product_text'] = hsText
        m_payload['ctl00$PageContent$RadComboBox_Country_Input'] = cText1
        m_payload['ctl00$PageContent$RadComboBox_Country_value'] = cValue1
        m_payload['ctl00$PageContent$RadComboBox_Country_text'] = cText1
        m_payload['ctl00$PageContent$RadComboBox_Partner_Input'] = cText2
        m_payload['ctl00$PageContent$RadComboBox_Partner_value'] = cValue2
        m_payload['ctl00$PageContent$RadComboBox_Partner_text'] = cText2
        m_payload['ctl00$PageContent$RadioButton_TradeType'] = mode
        m_payload = urlencode(m_payload)
        
        req = requests.post('https://www.trademap.org/Index.aspx',
            headers=post_headers, data=m_payload, allow_redirects=True)
        logger.info(f"First monthly request: {req.url} - Status: {req.status_code}")
        
        if req.status_code != 200:
            logger.error(f"First monthly request failed with status {req.status_code}")
            return {}
        
        resp = Selector(text=req.text)
        viewgenerator = resp.xpath('//input[@name="__VIEWSTATEGENERATOR"]/@value').get()
        viewstate = resp.xpath('//input[@name="__VIEWSTATE"]/@value').get()
        forgeryToken = resp.xpath('//input[@id="ctl00_forgeryToken"]/@value').get()
        oldNumTimePeriod = resp.xpath('//input[@name="ctl00$PageContent$GridViewPanelControl$HiddenField_OldNumTimePeriod"]/@value').get()
        gridViewColumns = resp.xpath('//input[@name="ctl00$PageContent$GridViewPanelControl$HiddenField_OldGridViewColumns"]/@value').get()
        lastTimePeriod = resp.xpath('//input[@name="ctl00$PageContent$GridViewPanelControl$HiddenField_CurrentLastTimePeriod"]/@value').get()
        referencePeriod = resp.xpath('//input[@name="ctl00$PageContent$GridViewPanelControl$HiddenField_Current_TS_ReferencePeriod"]/@value').get()
        
        m_payload2 = copy.deepcopy(payloadM2)
        m_payload2['__VIEWSTATE'] = viewstate
        m_payload2['__VIEWSTATEGENERATOR'] = viewgenerator
        m_payload2['ctl00$forgeryToken'] = forgeryToken
        m_payload2['ctl00$NavigationControl$DropDownList_Product'] = hsValue
        m_payload2['ctl00$NavigationControl$DropDownList_Country'] = cValue1
        m_payload2['ctl00$NavigationControl$DropDownList_Partner'] = cValue2
        m_payload2['ctl00$NavigationControl$HiddenField_Current_ProductCode'] = hsValue
        m_payload2['ctl00$NavigationControl$HiddenField_Current_CountryCode'] = cValue1
        m_payload2['ctl00$NavigationControl$HiddenField_Current_PartnerCode'] = cValue2
        m_payload2['ctl00$PageContent$GridViewPanelControl$HiddenField_OldNumTimePeriod'] = oldNumTimePeriod 
        m_payload2['ctl00$PageContent$GridViewPanelControl$HiddenField_OldGridViewColumns'] = gridViewColumns 
        m_payload2['ctl00$PageContent$GridViewPanelControl$HiddenField_CurrentLastTimePeriod'] = lastTimePeriod
        m_payload2['ctl00$PageContent$GridViewPanelControl$HiddenField_Current_TS_LastTimePeriod'] = lastTimePeriod  
        m_payload2['ctl00$PageContent$GridViewPanelControl$HiddenField_Current_TS_ReferencePeriod'] = referencePeriod  
        m_payload2['ctl00$NavigationControl$DropDownList_TradeType'] = mode
        m_payload2 = urlencode(m_payload2)
        
        next_url = resp.xpath('//form[@name="aspnetForm"]/@action').get()
        if next_url:
            next_url = f'https://www.trademap.org/{next_url}'
            req = requests.post(next_url, headers=post_headers, data=m_payload2)
            logger.info(f"Second monthly request: {req.url} - Status: {req.status_code}")
            
            if req.status_code == 200:
                resp = Selector(text=req.text)
                # Try primary table selector
                table_ = resp.xpath('//table[@id="ctl00_PageContent_MyGridView1"]').get()
                
                # If primary fails, try alternative selectors
                if not table_:
                    table_ = resp.xpath('//table[contains(@id, "GridView")]').get()
                if not table_:
                    table_ = resp.xpath('//table[@class="tbldata"]').get()
                if not table_:
                    # Log available tables for debugging
                    all_tables = resp.xpath('//table/@id').getall()
                    logger.warning(f"Monthly: Primary table not found. Available tables: {all_tables[:5]}")
                    # Check for "no data" messages
                    no_data_msg = resp.xpath('//span[contains(text(), "No data")]/text()').get()
                    page_title = resp.xpath('//title/text()').get()
                    logger.warning(f"Monthly page title: {page_title}")
                    if no_data_msg:
                        logger.warning(f"Monthly: No data message found: {no_data_msg}")
                
                data = parse_trademap_table_flexible(table_)
                logger.info(f"Monthly data scraped successfully for mode: {mode}")
                return data
            else:
                logger.error(f"Second monthly request failed with status {req.status_code}")
                return {}
        else:
            logger.error("No next URL found for monthly data")
            return {}
            
    except Exception as e:
        logger.error(f"Monthly data scraping failed for mode {mode}: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {}
def SaveAllDataToMongoDB(all_data, hscode, hsv, hst, c1, c2, time_series_list, view_type_list, value_type_list):
    """Save all scraped data in ONE MongoDB document with nested structure"""
    try:
        logger.info(f"Saving comprehensive data: {hscode} ({c1} -> {c2})")
        main_data = {"Country1": c1, "Country2": c2, "ScrapingParams": {"time_series": time_series_list, "view_types": view_type_list, "value_types": value_type_list}}
        main_data.update(all_data)
        data = {"ScraperName": "trademap_scraper", "HsCode": hscode, "HsCodeSearched": hsv, "ProductName": hst, "Source": "TradeMap", "Month": datetime.datetime.now().strftime("%b"), "Year": datetime.datetime.now().strftime("%Y"), "Data": main_data, "DateCreated": datetime.datetime.now(), "DateUpdated": datetime.datetime.now()}
        filter_query = {"HsCode": hscode, "Data.Country1": c1, "Data.Country2": c2}
        existing = trademap_collection.find_one(filter_query)
        if existing:
            trademap_collection.update_one(filter_query, {"$set": {"Data": main_data, "ProductName": hst, "DateUpdated": datetime.datetime.now()}})
            logger.info(f"Updated existing record: {hscode} ({c1}->{c2})")
        else:
            result = trademap_collection.insert_one(data)
            logger.info(f"Saved new comprehensive record with ID: {result.inserted_id}")
    except Exception as e:
        logger.error(f"SaveAllDataToMongoDB failed: {e}")
        raise



def ScrapeTrademap(hscode, country1, country2, time_series_list=None, view_type_list=None, value_type_list=None, all_hs_codes=False, all_exporting=False, all_importing=False):
    """Enhanced ScrapeTrademap that scrapes ALL combinations and saves in ONE record"""
    # Default to single values if not lists
    if time_series_list is None or isinstance(time_series_list, str):
        time_series_list = [time_series_list or 'yearly']
    if view_type_list is None or isinstance(view_type_list, str):
        view_type_list = [view_type_list or 'by_country']
    if value_type_list is None or isinstance(value_type_list, str):
        value_type_list = [value_type_list or 'values']
    
    driver = None
    try:
        logger.info(f"Starting TradeMap scrape: {hscode}, {country1} -> {country2}")
        logger.info(f"Will scrape {len(time_series_list)} time series × {len(view_type_list)} views × {len(value_type_list)} values = {len(time_series_list)*len(view_type_list)*len(value_type_list)} combinations")
        
        driver = InitializeDriver()
        driver.get('https://www.trademap.org/Index.aspx')
        time.sleep(3)
        DetectCaptcha(driver)
        GetCookies(driver)
        
        resp = Selector(text=driver.page_source)
        viewgenerator = resp.xpath('//input[@name="__VIEWSTATEGENERATOR"]/@value').get()
        viewstate = resp.xpath('//input[@name="__VIEWSTATE"]/@value').get()
        
        req = requests.get(f'https://www.trademap.org/Index.aspx?nvpm=1|||||||||||||||||&rcbID=ctl00_PageContent_RadComboBox_Product&rcbServerID=RadComboBox_Product&text={hscode}&comboText={hscode}&comboValue=&skin=WebBlue&clientDataString=P&timeStamp={int(datetime.datetime.now().timestamp())}', headers=json_headers)
        
        if req.status_code != 200:
            logger.error(f"Product search failed with status {req.status_code}")
            raise ValueError(f"Product search failed with status {req.status_code}")
        
        product_data = req.json()
        if not product_data.get('Items'):
            logger.error(f"No products found for HS code: {hscode}")
            raise ValueError(f"No products found for HS code: {hscode}")
        
        hsText = product_data['Items'][0]['Text']
        hsValue = product_data['Items'][0]['Value']
        
        # Only use "World" if country is explicitly 'all', NOT based on all_exporting/all_importing flags
        # The flags are for task expansion - individual tasks should use specific country names
        if country1.lower() == 'all':
            cText1, cValue1 = "World", "000"
        else:
            cText1, cValue1 = ParseCountry(country1, hsValue)
        
        if country2.lower() == 'all':
            cText2, cValue2 = "World", "000"
        else:
            cText2, cValue2 = ParseCountry(country2, hsValue)
        
        if not all([cText1, cValue1, cText2, cValue2]):
            raise ValueError(f"Failed to resolve countries: {country1} -> {country2}")
        
        logger.info(f"Countries resolved: {cText1} ({cValue1}) -> {cText2} ({cValue2})")
        
        all_data = {}
        
        for ts in time_series_list:
            ts_key = ts.replace('_', ' ').title()
            all_data[ts_key] = {}
            
            for vt in view_type_list:
                vt_key = vt.replace('_', ' ').title()
                all_data[ts_key][vt_key] = {}
                
                for val_t in value_type_list:
                    val_key = val_t.replace('_', ' ').title()
                    
                    logger.info(f"Scraping: {ts}/{vt}/{val_t}")
                    
                    import_data = ScrapeDataByTypeSelenium(driver, 'I', cValue1, cValue2, hsValue, ts, vt, val_t)
                    export_data = ScrapeDataByTypeSelenium(driver, 'E', cValue1, cValue2, hsValue, ts, vt, val_t)
                    
                    all_data[ts_key][vt_key][val_key] = {
                        'Import': import_data,
                        'Export': export_data
                    }
        
        logger.info("Saving all scraped data to database")
        SaveAllDataToMongoDB(all_data, hscode, hsValue, hsText, country1, country2, time_series_list, view_type_list, value_type_list)
        
        logger.info(f"TradeMap scraping completed successfully for HS Code: {hscode}")
        
    except Exception as e:
        logger.error(f"TradeMap scraping failed: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise
#     hscode = '29211'
#     country1 = 'united states of america'
#     country2 = 'canada'
    
#     logger.info("Starting TradeMap scraper...")
#     ScrapeTrademap(hscode, country1, country2)    finally:
        if driver:
            try:
                driver.quit()
                logger.info("Driver closed successfully")
            except Exception as e:
                logger.error(f"Failed to close driver: {e}")
