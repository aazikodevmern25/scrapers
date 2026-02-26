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

WEBSHARE_API_KEY = 'woztjikqob64wp3ocajvh8dagkxlc42xbtw7tmky'
_webshare_proxies_cache = []

def _fetch_webshare_proxies(count=50):
    """Fetch proxy list from Webshare API"""
    global _webshare_proxies_cache
    if _webshare_proxies_cache:
        return _webshare_proxies_cache
    try:
        import urllib.request
        req = urllib.request.Request(
            f'https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page=1&page_size={count}',
            headers={'Authorization': f'Token {WEBSHARE_API_KEY}'}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        proxies = []
        for p in data.get('results', []):
            if p.get('valid'):
                proxies.append({
                    'host': p['proxy_address'],
                    'port': p['port'],
                    'username': p['username'],
                    'password': p['password']
                })
        _webshare_proxies_cache = proxies
        logger.info(f"Fetched {len(proxies)} Webshare proxies")
        return proxies
    except Exception as e:
        logger.warning(f"Failed to fetch Webshare proxies: {e}")
        return []

def get_webshare_proxy():
    """Get a random Webshare proxy dict with host/port/user/pass"""
    proxies = _fetch_webshare_proxies()
    if not proxies:
        return None
    return random.choice(proxies)

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

def driver_is_alive(driver):
    """Check if the Selenium driver is still connected and responsive"""
    if driver is None:
        return False
    try:
        _ = driver.current_url
        return True
    except:
        return False

def _create_proxy_extension(proxy_host, proxy_port, proxy_user, proxy_pass):
    """Create a Chrome extension for proxy authentication"""
    import zipfile
    import tempfile
    manifest = json.dumps({
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Proxy Auth",
        "permissions": ["proxy", "tabs", "unlimitedStorage", "storage", "<all_urls>", "webRequest", "webRequestBlocking"],
        "background": {"scripts": ["background.js"]},
        "minimum_chrome_version": "22.0.0"
    })
    background = """var config = {mode:"fixed_servers",rules:{singleProxy:{scheme:"http",host:"%s",port:parseInt(%s)},bypassList:["localhost"]}};
chrome.proxy.settings.set({value:config,scope:"regular"},function(){});
function callbackFn(details){return{authCredentials:{username:"%s",password:"%s"}};}
chrome.webRequest.onAuthRequired.addListener(callbackFn,{urls:["<all_urls>"]},["blocking"]);""" % (proxy_host, proxy_port, proxy_user, proxy_pass)
    
    ext_path = tempfile.mktemp(suffix='.zip')
    with zipfile.ZipFile(ext_path, 'w') as zp:
        zp.writestr("manifest.json", manifest)
        zp.writestr("background.js", background)
    return ext_path

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
        captcha_img_el = None
        try:
            captcha_img_el = driver.find_element(By.XPATH, '//div[@class="div_captchaImg"]/img')
        except:
            pass
        
        if captcha_img_el:
            # Use Selenium element screenshot - no HTTP request needed
            captcha_img_el.screenshot('captcha.jpeg')
            logger.info("CAPTCHA image captured via Selenium screenshot")
            
            code = solver()
            driver.find_element(By.CSS_SELECTOR, 'input[id="ctl00_PageContent_CaptchaAnswer"]').send_keys(code)
            time.sleep(1)
            driver.find_element(By.CSS_SELECTOR, 'input[value="Validate"]').click()
            time.sleep(3)
            logger.info("CAPTCHA validation completed")
        else:
            logger.warning("No CAPTCHA image element found on page")
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

def InitializeDriver(email=None, password=None):
    try:
        # Use provided credentials or defaults
        login_email = email or 'chhabinrai2017@gmail.com'
        login_password = password or 'Test@1234'
        
        logger.info(f"Initializing Selenium driver (headless mode) with email: {login_email}")
        
        chrome_options = Options()
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        # Stability flags to prevent crashes
        chrome_options.add_argument('--disable-background-networking')
        chrome_options.add_argument('--disable-default-apps')
        chrome_options.add_argument('--disable-sync')
        chrome_options.add_argument('--disable-translate')
        chrome_options.add_argument('--metrics-recording-only')
        chrome_options.add_argument('--no-first-run')
        chrome_options.add_argument('--safebrowsing-disable-auto-update')
        chrome_options.add_argument('--disable-renderer-backgrounding')
        chrome_options.add_argument('--disable-backgrounding-occluded-windows')
        chrome_options.add_argument('--js-flags=--max-old-space-size=512')
        chrome_options.page_load_strategy = 'eager'
        
        chrome_options.add_argument('--disable-extensions')
        
        # Pre-resolve DNS to avoid Chrome DNS failures
        import socket
        try:
            tm_ip = socket.gethostbyname('www.trademap.org')
            itc_ip = socket.gethostbyname('idserv.marketanalysis.intracen.org')
            chrome_options.add_argument(f'--host-resolver-rules=MAP www.trademap.org {tm_ip},MAP idserv.marketanalysis.intracen.org {itc_ip}')
            logger.info(f"DNS pre-resolved: trademap={tm_ip}, itc={itc_ip}")
        except Exception as dns_err:
            logger.warning(f"DNS pre-resolve failed, using default: {dns_err}")
        chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(60)
        driver.set_script_timeout(60)
        logger.info("Driver initialized successfully (headless mode, eager strategy)")
        driver.get('https://www.trademap.org/Index.aspx')
        
        # Wait for page to be interactive - look for Login button or logged-in indicator
        needs_login = False
        try:
            WebDriverWait(driver, 15).until(
                lambda d: d.find_elements(By.CSS_SELECTOR, 'a[onclick="Login();"]') or 
                          d.find_elements(By.CSS_SELECTOR, 'a[onclick="Logout();"]') or
                          'access_token' in str(d.get_cookies())
            )
            needs_login = bool(driver.find_elements(By.CSS_SELECTOR, 'a[onclick="Login();"]'))
        except:
            # Timeout - check page state
            needs_login = bool(driver.find_elements(By.CSS_SELECTOR, 'a[onclick="Login();"]'))
            if not needs_login:
                # Check if we have auth cookies
                cookies = driver.get_cookies()
                has_token = any('access_token' in c.get('name', '') for c in cookies)
                if not has_token:
                    needs_login = True
                    logger.warning("No Login button and no auth token - forcing login")
        
        logger.info(f"Login check: needs_login={needs_login}, URL={driver.current_url}")
        
        if needs_login:
            logger.info("Login required, proceeding with authentication")
            
            # Retry login up to 3 times
            for login_attempt in range(3):
                logger.info(f"Login attempt {login_attempt + 1}/3")
                
                if login_attempt > 0:
                    # Re-navigate to Index to get fresh login link
                    driver.get('https://www.trademap.org/Index.aspx')
                    time.sleep(5)
                    resp = Selector(text=driver.page_source)
                    if not resp.xpath('//a[@onclick="Login();"]').get():
                        logger.info("Already logged in after re-navigation")
                        break
                
                try:
                    login_btn = WebDriverWait(driver, 15).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, 'a[onclick="Login();"]'))
                    )
                    login_btn.click()
                except:
                    # Login button not found - wait for full page load and retry
                    logger.warning("Login button not clickable, waiting for full page load...")
                    time.sleep(8)
                    try:
                        driver.find_element(By.CSS_SELECTOR, 'a[onclick="Login();"]').click()
                    except:
                        # Navigate fresh and try one more time
                        logger.warning("Retrying with fresh page load...")
                        driver.get('https://www.trademap.org/Index.aspx')
                        time.sleep(10)
                        try:
                            driver.find_element(By.CSS_SELECTOR, 'a[onclick="Login();"]').click()
                        except:
                            logger.warning("Still no Login button, navigating to ITC login directly")
                            driver.get('https://idserv.marketanalysis.intracen.org/Account/Login?ReturnUrl=%2Fconnect%2Fauthorize%2Fcallback%3Fclient_id%3DTradeMap%26scope%3Dopenid%2520email%2520profile%2520offline_access%2520ActivityLog%26redirect_uri%3Dhttps%253A%252F%252Fwww.trademap.org%252FLoginCallback.aspx%26response_type%3Dcode%2520id_token%26response_mode%3Dform_post')
                time.sleep(5)
                
                # Wait for login form to load
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'button[value="login"]'))
                    )
                except:
                    pass
                
                resp = Selector(text=driver.page_source)
                if resp.xpath('//button[@value="login"]'):
                    logger.info(f"Filling login credentials for: {login_email}")
                    driver.find_element(By.CSS_SELECTOR, 'input[aria-label="Username"]').send_keys(login_email)
                    driver.find_element(By.CSS_SELECTOR, 'input[aria-label="Password"]').send_keys(login_password)
                    time.sleep(1)
                    try:
                        driver.find_element(By.CSS_SELECTOR, 'label[class="switch switch-remember"]').click()
                    except:
                        pass
                    driver.find_element(By.CSS_SELECTOR, 'button[value="login"]').click()
                    time.sleep(8)
                    logger.info(f"Login submitted, current URL: {driver.current_url}")
                    
                    # Check if login succeeded
                    post_login_url = driver.current_url.lower()
                    if 'index' in post_login_url and 'trademap.org' in post_login_url:
                        logger.info("Login succeeded - on Index.aspx")
                        break
                    elif 'login' in post_login_url and 'idserv' not in post_login_url and 'callback' not in post_login_url:
                        logger.warning(f"Login may have failed, still on: {driver.current_url}")
                        continue
                elif Selector(text=driver.page_source).xpath('//div[@class="div_captchaImg"]').get():
                    CaptchaSolver(driver)
                    break
        
        # Wait for any login redirects to complete (LoginCallback.aspx -> Index.aspx)
        for wait_attempt in range(8):
            current_url = driver.current_url.lower()
            if 'callback' in current_url or 'idserv' in current_url:
                logger.info(f"Waiting for login redirect to complete... ({driver.current_url})")
                time.sleep(3)
            else:
                break
        
        # If still on callback or login page, force navigate to Index
        current = driver.current_url.lower()
        if 'callback' in current or ('login' in current and 'trademap.org' in current):
            logger.warning(f"Stuck on {driver.current_url}, forcing navigation to Index.aspx")
            driver.get('https://www.trademap.org/Index.aspx')
            time.sleep(5)
        
        # Handle post-login CAPTCHA (stCaptcha.aspx page)
        max_captcha_retries = 5
        for captcha_attempt in range(max_captcha_retries):
            current_url = driver.current_url.lower()
            page_source = driver.page_source
            resp = Selector(text=page_source)
            
            # Check if we're on the CAPTCHA page
            if 'captcha' in current_url or resp.xpath('//div[@class="div_captchaImg"]').get() or resp.xpath('//input[@id="ctl00_PageContent_CaptchaAnswer"]').get():
                logger.info(f"CAPTCHA page detected (attempt {captcha_attempt+1}/{max_captcha_retries}), solving...")
                try:
                    CaptchaSolver(driver)
                    time.sleep(3)
                    # After solving, check if we moved away from captcha page
                    new_url = driver.current_url.lower()
                    if 'captcha' not in new_url:
                        logger.info(f"CAPTCHA solved, redirected to: {driver.current_url}")
                        # Navigate to Index to confirm we're logged in
                        if 'index' not in new_url:
                            driver.get('https://www.trademap.org/Index.aspx')
                            time.sleep(3)
                        break
                except Exception as captcha_err:
                    logger.warning(f"CAPTCHA solve attempt {captcha_attempt+1} failed: {captcha_err}")
                    if captcha_attempt < max_captcha_retries - 1:
                        time.sleep(3)
                        driver.refresh()
                        time.sleep(3)
                        continue
                    else:
                        raise Exception(f"Failed to solve CAPTCHA after {max_captcha_retries} attempts")
            else:
                # No CAPTCHA, we're good
                logger.info(f"No CAPTCHA detected, current URL: {driver.current_url}")
                break
        
        # Final verification: make sure we're on a valid TradeMap page
        final_url = driver.current_url.lower()
        if 'idserv' in final_url or 'stcaptcha' in final_url:
            logger.error(f"Still on login/captcha page after initialization: {driver.current_url}")
            raise Exception("Failed to complete login - stuck on login/captcha page")
        
        # If still on Login.aspx, force navigate to Index
        if 'login' in final_url and 'trademap.org' in final_url:
            logger.warning(f"Still on Login page, forcing Index navigation: {driver.current_url}")
            driver.get('https://www.trademap.org/Index.aspx')
            time.sleep(5)
        
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

def set_product_in_session(driver, hscode, hsText, hsValue):
    """Set the HS code product in the TradeMap server session using requests POST.
    Uses the same cookies as Selenium so the session is shared.
    This is required so that subsequent Selenium URL navigations use the correct product."""
    try:
        logger.info(f"Setting product in session via POST: {hscode} ({hsText})")
        
        # Make sure we're on the Index page to get ViewState
        if 'index' not in driver.current_url.lower():
            driver.get('https://www.trademap.org/Index.aspx')
            time.sleep(3)
        
        # Get ViewState from current page
        resp = Selector(text=driver.page_source)
        vs = resp.xpath('//input[@name="__VIEWSTATE"]/@value').get()
        vg = resp.xpath('//input[@name="__VIEWSTATEGENERATOR"]/@value').get()
        
        if not vs or not vg:
            logger.warning("Could not get ViewState from Index page")
            return False
        
        # Build form POST payload (same approach as ScrapeYearlyData)
        yearly_payload = copy.deepcopy(payload1)
        yearly_payload['__VIEWSTATE'] = vs
        yearly_payload['__VIEWSTATEGENERATOR'] = vg
        yearly_payload['ctl00$PageContent$RadComboBox_Product_Input'] = hsText
        yearly_payload['ctl00$PageContent$RadComboBox_Product_value'] = hsValue
        yearly_payload['ctl00$PageContent$RadComboBox_Product_text'] = hsText
        yearly_payload['ctl00$PageContent$RadioButton_TradeType'] = 'E'
        # Clear country fields so session doesn't default to specific countries
        yearly_payload['ctl00$PageContent$RadComboBox_Country_Input'] = ''
        yearly_payload['ctl00$PageContent$RadComboBox_Country_value'] = ''
        yearly_payload['ctl00$PageContent$RadComboBox_Country_text'] = ''
        yearly_payload['ctl00$PageContent$RadComboBox_Partner_Input'] = ''
        yearly_payload['ctl00$PageContent$RadComboBox_Partner_value'] = ''
        yearly_payload['ctl00$PageContent$RadComboBox_Partner_text'] = ''
        yearly_payload = urlencode(yearly_payload)
        
        # POST via Selenium JS fetch (more reliable than curl_cffi on flaky networks)
        post_result = driver.execute_async_script("""
            var callback = arguments[arguments.length - 1];
            fetch('https://www.trademap.org/Index.aspx', {
                method: 'POST',
                credentials: 'include',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: arguments[0],
                redirect: 'follow'
            })
            .then(r => callback(JSON.stringify({status: r.status, url: r.url})))
            .catch(e => callback('ERROR:' + e.message));
        """, yearly_payload)
        
        logger.info(f"Product session POST result: {post_result}")
        
        if post_result and not post_result.startswith('ERROR:'):
            result_data = json.loads(post_result)
            if result_data.get('status') == 200 and hsValue in result_data.get('url', ''):
                logger.info(f"Product {hsValue} successfully set in server session")
                return True
            else:
                logger.warning(f"Product session POST may not have worked: {post_result}")
                return False
        else:
            logger.warning(f"Product session POST failed: {post_result}")
            return False
        
    except Exception as e:
        logger.warning(f"set_product_in_session failed: {e}")
        return False

def get_trademap_url_params(time_series, view_type, value_type):
    """
    Map time_series, view_type, value_type to TradeMap URL parameters
    Returns: (frequency, indicator_code, view_code) tuple
    """
    freq_map = {"yearly": "1", "quarterly": "3", "monthly": "5", "trade_indicators": "1"}
    indicator_map = {"values": "1", "quantities": "2", "growth_value": "3", "growth_quantity": "4", "share_value": "5", "unit_values": "6", "growth_unit_values": "7", "index_values": "8", "index_unit_values": "9"}
    view_map = {"by_country": "2", "by_product": "4", "by_service": "6"}
    return freq_map.get(time_series, "1"), indicator_map.get(value_type, "1"), view_map.get(view_type, "2")

# Mapping from internal value_type to TradeMap dropdown visible text
INDICATOR_DROPDOWN_TEXT = {
    "values": "Values",
    "quantities": "Quantities",
    "growth_value": "Growth in value",
    "growth_quantity": "Growth in quantity",
    "share_value": "Share in value in %",
    "unit_values": "Unit values",
    "growth_unit_values": "Growth on unit values",
    "index_values": "Index on values",
    "index_unit_values": "Index on unit values"
}

def _select_indicator_dropdown(driver, value_type):
    """Select the indicator (Values/Quantities/Growth/etc.) from the TS_Indicator dropdown."""
    target = INDICATOR_DROPDOWN_TEXT.get(value_type, "Values")
    result = _select_dropdown_with_retry(
        driver, 'ctl00_NavigationControl_DropDownList_TS_Indicator', target
    )
    if result:
        logger.info(f"Indicator set to: {result}")
    else:
        logger.warning(f"Could not set indicator to {target}")
    return result

def ScrapeDataByTypeSelenium(driver, mode, country1_code, country2_code, hs_code, time_series="yearly", view_type="by_country", value_type="values", max_retries=3):
    """Universal scraping function for all combinations of time_series, view_type, and value_type.
    Handles: yearly/quarterly/monthly time series, trade indicators,
    by_country/by_product views, and all value types (values/quantities/growth/etc.).
    Uses dropdowns to set indicator after page navigation."""
    for attempt in range(max_retries):
        try:
            logger.info(f"ScrapeDataByTypeSelenium (attempt {attempt+1}/{max_retries}): mode={mode}, ts={time_series}, view={view_type}, value={value_type}")
            frequency, indicator, view = get_trademap_url_params(time_series, view_type, value_type)
            trade_type = "1" if mode == "I" else "2"
            
            digit_level = str(len(hs_code)) if hs_code and hs_code.isdigit() else "6"
            is_ts = time_series != "trade_indicators"
            ts_suffix = "_TS" if is_ts else ""
            
            # Determine page name based on view_type
            if view_type == "by_product":
                page_base = "Product_SelCountry"
            elif view_type == "by_service":
                page_base = "Service_SelCountry"
            else:
                page_base = "Country_SelProduct"
            
            page_name = f"{page_base}{ts_suffix}.aspx"
            
            # Build URL based on country mode
            if is_ts:
                # Time series pages: positions 11-12 = 2|2 for TS layout
                nvpm_tail = f"{digit_level}%7c{frequency}%7c{trade_type}%7c2%7c2%7c1%7c{view}%7c1%7c%7c1"
            else:
                # Trade indicators pages: positions 11-12 = 1|indicator
                nvpm_tail = f"{digit_level}%7c{frequency}%7c{trade_type}%7c1%7c{indicator}%7c1%7c{view}%7c1%7c1%7c1"
            
            if country1_code in ("000", "", None) and country2_code in ("000", "", None):
                url = f"https://www.trademap.org/{page_name}?nvpm=1%7c%7c%7c%7c%7c{hs_code}%7c%7c%7c{nvpm_tail}"
            elif country1_code in ("000", "", None):
                url = f"https://www.trademap.org/{page_name}?nvpm=1%7c%7c%7c{country2_code}%7c%7c{hs_code}%7c%7c%7c{nvpm_tail}"
            elif country2_code in ("000", "", None):
                url = f"https://www.trademap.org/{page_name}?nvpm=1%7c{country1_code}%7c%7c%7c%7c{hs_code}%7c%7c%7c{nvpm_tail}"
            else:
                # Both countries specified - use bilateral view
                url = f"https://www.trademap.org/Bilateral{ts_suffix}.aspx?nvpm=1%7c{country2_code}%7c%7c{country1_code}%7c%7c{hs_code}%7c%7c%7c4%7c{frequency}%7c{trade_type}%7c2%7c{indicator}%7c1%7c{view}%7c1%7c1%7c1"
            
            logger.info(f"Navigating to: {url}")
            driver.get(url)
            time.sleep(4)
            
            # Check for login/captcha issues
            check_and_reauth(driver)
            
            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "ctl00_PageContent_MyGridView1")))
            except:
                logger.warning(f"Table not found after navigation, checking page state...")
                # Check if we got redirected to login
                if 'login' in driver.current_url.lower() or 'captcha' in driver.page_source.lower():
                    logger.warning("Redirected to login/captcha page, re-authenticating...")
                    check_and_reauth(driver)
                    driver.get(url)
                    time.sleep(4)
            
            # Set page size and time period dropdowns
            if is_ts:
                select_20_per_page(driver)
            else:
                # Trade indicators: only set PageSize (no NumTimePeriod)
                _select_dropdown_with_retry(
                    driver, 'ctl00_PageContent_GridViewPanelControl_DropDownList_PageSize', '_last_'
                )
            
            # Set the indicator dropdown for different value types
            if value_type != "values":
                _select_indicator_dropdown(driver, value_type)
            
            time.sleep(2)
            
            # Wait for table
            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "ctl00_PageContent_MyGridView1")))
            except:
                pass
            
            resp = Selector(text=driver.page_source)
            table_ = resp.xpath('//table[@id="ctl00_PageContent_MyGridView1"]').get()
            if not table_:
                table_ = resp.xpath('//table[contains(@id, "GridView")]').get()
            if table_:
                data = parse_trademap_table_flexible(table_)
                if data and data.get('products') and len(data['products']) > 0:
                    logger.info(f"Successfully scraped: {time_series}/{view_type}/{value_type} for mode {mode} - {len(data['products'])} rows, {len(data.get('years', []))} years")
                    return data
                else:
                    logger.warning(f"Table found but no data rows for: {time_series}/{view_type}/{value_type}")
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying in 5 seconds...")
                        time.sleep(5)
                        continue
                    return data
            else:
                logger.warning(f"No table found for: {time_series}/{view_type}/{value_type} (attempt {attempt+1})")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in 5 seconds...")
                    time.sleep(5)
                    continue
                return {"format": "no_data", "trade_descriptions": [], "years": [], "products": []}
        except Exception as e:
            logger.error(f"ScrapeDataByTypeSelenium failed (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                logger.info(f"Retrying in 5 seconds...")
                time.sleep(5)
                continue
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





def _select_dropdown_with_retry(driver, dropdown_id, target_text, max_retries=4):
    """Helper: find a dropdown and select a value, with retries for stale elements."""
    from selenium.webdriver.support.ui import Select
    for attempt in range(max_retries):
        try:
            # Wait for the dropdown to be present in DOM
            try:
                elem = WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located((By.ID, dropdown_id))
                )
            except:
                time.sleep(2)
                elem = driver.find_element(By.ID, dropdown_id)
            sel = Select(elem)
            current = sel.first_selected_option.text
            if target_text in current:
                return "already_set"
            # Get table ref before change to detect reload
            try:
                old_table = driver.find_element(By.ID, "ctl00_PageContent_MyGridView1")
            except:
                old_table = None
            # Select the target
            if target_text == '_last_':
                opts = sel.options
                if opts:
                    sel.select_by_index(len(opts) - 1)
                    selected_text = opts[-1].text
                else:
                    continue
            else:
                sel.select_by_visible_text(target_text)
                selected_text = target_text
            # Wait for page reload
            if old_table:
                try:
                    WebDriverWait(driver, 10).until(EC.staleness_of(old_table))
                except:
                    pass
            time.sleep(2)
            try:
                WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "ctl00_PageContent_MyGridView1")))
            except:
                time.sleep(3)
            return selected_text
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                logger.warning(f"Failed to set {dropdown_id} after {max_retries} attempts: {e}")
    return None

def select_20_per_page(driver):
    """Select 20 time periods (year columns) and max rows (country rows) from the dropdowns."""
    try:
        # Wait for table to load first
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "ctl00_PageContent_MyGridView1")))
        except:
            time.sleep(3)
        
        # 1. Set NumTimePeriod to 20 (controls year COLUMNS)
        result1 = _select_dropdown_with_retry(
            driver, 'ctl00_PageContent_GridViewPanelControl_DropDownList_NumTimePeriod', '20 per page'
        )
        if result1:
            logger.info(f"NumTimePeriod: {result1}")
        
        # 2. Set PageSize to max (controls country ROWS)
        result2 = _select_dropdown_with_retry(
            driver, 'ctl00_PageContent_GridViewPanelControl_DropDownList_PageSize', '_last_'
        )
        if result2:
            logger.info(f"PageSize: {result2}")
        
        return True
    except Exception as e:
        logger.warning(f"Error in select_20_per_page: {e}")
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
    """Check if we're on a login/captcha page and re-authenticate if needed"""
    try:
        current_url = driver.current_url.lower()
        page_source = driver.page_source
        resp = Selector(text=page_source)
        
        # Check for CAPTCHA page (stCaptcha.aspx or captcha div)
        is_captcha = ('captcha' in current_url or 
                      resp.xpath('//div[@class="div_captchaImg"]').get() or 
                      resp.xpath('//input[@id="ctl00_PageContent_CaptchaAnswer"]').get())
        
        # Check for actual login page (idserv login form, NOT just any page containing "login" text)
        is_login = ('idserv' in current_url or 
                    resp.xpath('//button[@value="login"]').get() is not None)
        
        # Check if page is essentially empty (session expired)
        is_empty = len(page_source) < 500
        
        if is_captcha:
            logger.warning("CAPTCHA page detected during navigation, solving...")
            try:
                CaptchaSolver(driver)
                time.sleep(3)
            except Exception as e:
                logger.warning(f"CAPTCHA solve failed during reauth: {e}")
            return True
        
        if is_login or is_empty:
            logger.warning("Login page or empty page detected, re-navigating to Index...")
            driver.get('https://www.trademap.org/Index.aspx')
            time.sleep(3)
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



def _setup_driver_and_product(hscode, email, password):
    """Initialize driver, login, search for product, set session. Returns (driver, hsText, hsValue) or raises."""
    driver = InitializeDriver(email=email, password=password)
    driver.get('https://www.trademap.org/Index.aspx')
    time.sleep(3)
    DetectCaptcha(driver)
    GetCookies(driver)
    
    # Type HS code into RadComboBox and use autocomplete
    logger.info(f"Searching for product via UI: {hscode}")
    product_input = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, 'ctl00_PageContent_RadComboBox_Product_Input'))
    )
    product_input.clear()
    product_input.send_keys(hscode)
    time.sleep(3)
    
    # Wait for autocomplete dropdown
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '#ctl00_PageContent_RadComboBox_Product_DropDown .rcbItem'))
        )
    except:
        logger.warning("Autocomplete dropdown did not appear, retrying...")
        product_input.clear()
        time.sleep(1)
        product_input.send_keys(hscode)
        time.sleep(5)
    
    # Click the first autocomplete result
    try:
        first_item = driver.find_element(By.CSS_SELECTOR, '#ctl00_PageContent_RadComboBox_Product_DropDown .rcbItem')
        first_item.click()
        time.sleep(2)
    except:
        items = driver.find_elements(By.CSS_SELECTOR, '.rcbList .rcbItem')
        if items:
            items[0].click()
            time.sleep(2)
    
    # Extract selected product text and value
    hsText = driver.execute_script(
        "return document.getElementById('ctl00_PageContent_RadComboBox_Product_Input').value"
    ) or ""
    hsValue = driver.execute_script("""
        var hidden = document.getElementById('ctl00_PageContent_RadComboBox_Product_ClientState');
        if (hidden && hidden.value) {
            try { var s = JSON.parse(hidden.value); return s.value || ''; } catch(e) {}
        }
        try { return $find('ctl00_PageContent_RadComboBox_Product').get_value(); } catch(e) {}
        return '';
    """) or hscode
    
    if not hsText:
        hsText = f"{hscode} - Product"
        hsValue = hscode
        logger.warning(f"Could not get product text, using fallback: {hsText}")
    
    logger.info(f"Product resolved: {hsText} ({hsValue})")
    
    if not hsValue:
        raise ValueError(f"No products found for HS code: {hscode}")
    
    # Set the product in the TradeMap session
    set_product_in_session(driver, hscode, hsText, hsValue)
    return driver, hsText, hsValue

def ScrapeTrademap(hscode, country1, country2, time_series_list=None, view_type_list=None, value_type_list=None, all_hs_codes=False, all_exporting=False, all_importing=False, email=None, password=None):
    """Enhanced ScrapeTrademap with crash recovery.
    If ChromeDriver crashes mid-scrape, restarts it and continues.
    Restarts Chrome between time_series changes to prevent memory buildup."""
    if time_series_list is None or isinstance(time_series_list, str):
        time_series_list = [time_series_list or 'yearly']
    if view_type_list is None or isinstance(view_type_list, str):
        view_type_list = [view_type_list or 'by_country']
    if value_type_list is None or isinstance(value_type_list, str):
        value_type_list = [value_type_list or 'values']
    
    total_combos = len(time_series_list) * len(view_type_list) * len(value_type_list) * 2
    logger.info(f"Starting TradeMap scrape: {hscode}, {country1} -> {country2}")
    logger.info(f"Will scrape {len(time_series_list)} ts × {len(view_type_list)} views × {len(value_type_list)} vals × 2 directions = {total_combos} total")
    
    # Resolve countries (static, no driver needed)
    if not country1 or country1.lower() == 'all':
        cText1, cValue1 = "World", "000"
    else:
        cText1, cValue1 = country1, country1
    if not country2 or country2.lower() == 'all':
        cText2, cValue2 = "World", "000"
    else:
        cText2, cValue2 = country2, country2
    
    logger.info(f"Countries: {cText1} ({cValue1}) -> {cText2} ({cValue2})")
    
    driver = None
    hsText = f"{hscode} - Product"
    hsValue = hscode
    all_data = {}
    scrape_count = 0
    
    try:
        # Initial driver setup
        driver, hsText, hsValue = _setup_driver_and_product(hscode, email, password)
        
        for ts_idx, ts in enumerate(time_series_list):
            ts_key = ts.replace('_', ' ').title()
            if ts_key not in all_data:
                all_data[ts_key] = {}
            
            # Restart driver between time_series to prevent memory buildup
            if ts_idx > 0:
                logger.info(f"Restarting driver before time_series={ts} to prevent memory buildup")
                try:
                    driver.quit()
                except:
                    pass
                driver = None
                time.sleep(2)
                driver, hsText, hsValue = _setup_driver_and_product(hscode, email, password)
            
            for vt in view_type_list:
                vt_key = vt.replace('_', ' ').title()
                if vt_key not in all_data[ts_key]:
                    all_data[ts_key][vt_key] = {}
                
                for val_t in value_type_list:
                    val_key = val_t.replace('_', ' ').title()
                    
                    logger.info(f"Scraping: {ts}/{vt}/{val_t}")
                    
                    combo_result = {'Import': None, 'Export': None}
                    
                    for mode, mode_label in [('I', 'Import'), ('E', 'Export')]:
                        # Check if driver is alive before each scrape
                        if not driver_is_alive(driver):
                            logger.warning(f"Driver crashed before {ts}/{vt}/{val_t}/{mode_label}. Restarting...")
                            try:
                                driver.quit()
                            except:
                                pass
                            driver = None
                            time.sleep(3)
                            try:
                                driver, hsText, hsValue = _setup_driver_and_product(hscode, email, password)
                            except Exception as restart_err:
                                logger.error(f"Driver restart failed: {restart_err}")
                                combo_result[mode_label] = {"format": "error", "error": str(restart_err), "trade_descriptions": [], "years": [], "products": []}
                                continue
                        
                        try:
                            data = ScrapeDataByTypeSelenium(driver, mode, cValue1, cValue2, hsValue, ts, vt, val_t)
                            combo_result[mode_label] = data
                            scrape_count += 1
                        except Exception as scrape_err:
                            err_str = str(scrape_err)
                            logger.error(f"Scrape failed {ts}/{vt}/{val_t}/{mode_label}: {err_str}")
                            combo_result[mode_label] = {"format": "error", "error": err_str, "trade_descriptions": [], "years": [], "products": []}
                            
                            # If it's a driver crash, restart
                            if 'MaxRetryError' in err_str or 'ConnectionRefused' in err_str or 'HTTPConnectionPool' in err_str or not driver_is_alive(driver):
                                logger.warning(f"Driver crashed during {ts}/{vt}/{val_t}/{mode_label}. Will restart for next scrape.")
                                try:
                                    driver.quit()
                                except:
                                    pass
                                driver = None
                    
                    all_data[ts_key][vt_key][val_key] = combo_result
            
            # Incremental save after each time_series to prevent data loss
            logger.info(f"Incremental save after time_series={ts}")
            try:
                SaveAllDataToMongoDB(all_data, hscode, hsValue, hsText, country1, country2, time_series_list, view_type_list, value_type_list)
                logger.info(f"Incremental save completed for time_series={ts}")
            except Exception as save_err:
                logger.error(f"Incremental save failed: {save_err}")
        
        # Count errors
        error_count = 0
        success_count = 0
        for ts_k, ts_v in all_data.items():
            for vt_k, vt_v in ts_v.items():
                for val_k, val_v in vt_v.items():
                    for dir_k, dir_v in val_v.items():
                        if dir_v and dir_v.get('format') == 'error':
                            error_count += 1
                        elif dir_v and dir_v.get('products'):
                            success_count += 1
        
        logger.info(f"Scraping complete: {success_count} successful, {error_count} errors out of {total_combos} total")
        
        logger.info("Saving all scraped data to database")
        SaveAllDataToMongoDB(all_data, hscode, hsValue, hsText, country1, country2, time_series_list, view_type_list, value_type_list)
        
        logger.info(f"TradeMap scraping completed for HS Code: {hscode}")
        
    except Exception as e:
        logger.error(f"TradeMap scraping failed: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        # Save whatever we have so far
        if all_data:
            try:
                logger.info("Saving partial data before exit...")
                SaveAllDataToMongoDB(all_data, hscode, hsValue, hsText, country1, country2, time_series_list, view_type_list, value_type_list)
            except:
                pass
        raise
    finally:
        if driver:
            try:
                driver.quit()
                logger.info("Driver closed successfully")
            except Exception as e:
                logger.error(f"Failed to close driver: {e}")
