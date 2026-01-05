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
            time.sleep(5)
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
        
        # Initialize driver with Chrome options for server environment
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        # Don't use user-data-dir to avoid creating temp folders
        
        driver = webdriver.Chrome(options=chrome_options)
        logger.info("Driver initialized successfully (headless mode)")
        driver.get('https://www.trademap.org/Index.aspx')
        time.sleep(4)
        
        resp = Selector(text=driver.page_source)
        if resp.xpath('//a[@onclick="Login();"]').get():
            logger.info("Login required, proceeding with authentication")
            driver.find_element(By.CSS_SELECTOR, 'a[onclick="Login();"]').click()
            time.sleep(3)
            
            resp = Selector(text=driver.page_source)
            if resp.xpath('//button[@value="login"]'):
                logger.info("Filling login credentials")
                driver.find_element(By.CSS_SELECTOR, 'input[aria-label="Username"]').send_keys('aazikodevteamleader@gmail.com')
                driver.find_element(By.CSS_SELECTOR, 'input[aria-label="Password"]').send_keys('Aaziko@123')
                time.sleep(1)
                driver.find_element(By.CSS_SELECTOR, 'label[class="switch switch-remember"]').click()
                driver.find_element(By.CSS_SELECTOR, 'button[value="login"]').click()
                time.sleep(5)
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
                table_ = resp.xpath('//table[@id="ctl00_PageContent_MyGridView1"]').get()
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
                table_ = resp.xpath('//table[@id="ctl00_PageContent_MyGridView1"]').get()
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

def ScrapeTrademap(hscode, country1, country2):
    driver = None
    try:
        logger.info(f"Starting TradeMap scraping for HS Code: {hscode}, {country1} -> {country2}")
        driver = InitializeDriver()
        driver.get('https://www.trademap.org/Index.aspx')
        time.sleep(5)
        DetectCaptcha(driver)
        GetCookies(driver)
        logger.info(f"Cookies obtained: {json_headers.get('Cookie', 'None')[:100]}...")
        resp = Selector(text=driver.page_source)
        viewgenerator = resp.xpath('//input[@name="__VIEWSTATEGENERATOR"]/@value').get()
        viewstate = resp.xpath('//input[@name="__VIEWSTATE"]/@value').get()
        logger.info(f"ViewState tokens extracted - VG: {viewgenerator}, VS length: {len(viewstate) if viewstate else 0}")
        
        # Get product information
        req = requests.get(f'https://www.trademap.org/Index.aspx?nvpm=1|||||||||||||||||&rcbID=ctl00_PageContent_RadComboBox_Product&rcbServerID=RadComboBox_Product&text={hscode}&comboText={hscode}&comboValue=&skin=WebBlue&clientDataString=P&timeStamp={int(datetime.datetime.now().timestamp())}',
            headers=json_headers)
        logger.info(f"Product search request: {req.url} - Status: {req.status_code}")
        
        if req.status_code != 200:
            logger.error(f"Product search failed with status {req.status_code}")
            return
            
        try:
            product_data = req.json()
            if not product_data.get('Items'):
                logger.error(f"No products found for HS code: {hscode}")
                return
                
            hsText = product_data['Items'][0]['Text']
            hsValue = product_data['Items'][0]['Value']
            logger.info(f"Product found: {hsText} ({hsValue})")
        except Exception as e:
            logger.error(f"Failed to parse product data: {e}")
            return
        
        cText1, cValue1 = ParseCountry(country1, hsValue)
        cText2, cValue2 = ParseCountry(country2, hsValue)
        
        if not all([cText1, cValue1, cText2, cValue2]):
            logger.error("Failed to resolve one or both countries")
            return
            
        logger.info(f"Countries resolved: {cText1} ({cValue1}) -> {cText2} ({cValue2})")
        
        codeList = [hsText, hsValue, cText1, cValue1, cText2, cValue2]
        
        logger.info("Starting data scraping for all types and modes")
        
        yearlyImport = ScrapeYearlyData(viewstate, viewgenerator, codeList, 'I')
        quarterlyImport = ScrapeQuarterlyData(viewstate, viewgenerator, codeList, 'I')
        monthlyImport = ScrapeMonthlyData(viewstate, viewgenerator, codeList, 'I')
        yearlyExport = ScrapeYearlyData(viewstate, viewgenerator, codeList, 'E')
        quarterlyExport = ScrapeQuarterlyData(viewstate, viewgenerator, codeList, 'E')
        monthlyExport = ScrapeMonthlyData(viewstate, viewgenerator, codeList, 'E')
        
        logger.info("Saving scraped data to database")
        MapData({"Yearly": yearlyImport, "Quarterly": quarterlyImport, "Monthly": monthlyImport},
                hscode, hsValue, hsText, country1, country2, "Import")
        MapData({"Yearly": yearlyExport, "Quarterly": quarterlyExport, "Monthly": monthlyExport},
                hscode, hsValue, hsText, country1, country2, "Export")
        
        logger.info(f"TradeMap scraping completed successfully for HS Code: {hscode}")
        
    except Exception as e:
        logger.error(f"TradeMap scraping failed: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise
    finally:
        if driver:
            try:
                driver.quit()
                logger.info("Driver closed successfully")
            except Exception as e:
                logger.error(f"Failed to close driver: {e}")


# if __name__ == "__main__":
#     hscode = '29211'
#     country1 = 'united states of america'
#     country2 = 'canada'
    
#     logger.info("Starting TradeMap scraper...")
#     ScrapeTrademap(hscode, country1, country2)