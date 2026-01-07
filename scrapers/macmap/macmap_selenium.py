"""
MACMAP Trade Agreements Scraper using Selenium with Undetected ChromeDriver
This bypasses anti-bot detection better than Playwright
"""

import logging
import time
import random
from typing import List, Dict

logger = logging.getLogger(__name__)


def get_trade_agreements_selenium(reporter_code: str, country_name: str, relation: str = 'exporter', partner: str = 'All') -> List[Dict]:
    """
    Scrape trade agreements from MACMAP using Selenium with undetected-chromedriver.
    
    Args:
        reporter_code: Country code (e.g., 156 for China)
        country_name: Country name for logging
        relation: 'exporter' or 'importer'
        partner: Partner country code or 'All'
    
    Returns:
        List of trade agreement dictionaries
    """
    agreements = []
    
    try:
        import undetected_chromedriver as uc
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait, Select
        from selenium.webdriver.support import expected_conditions as EC
        from selenium_stealth import stealth
        
        logger.info(f"Launching undetected Chrome for {country_name} (as {relation})...")
        
        # Configure Chrome options
        options = uc.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--disable-gpu')
        options.add_argument(f'--window-size=1920,1080')
        
        # Create undetected Chrome driver
        driver = uc.Chrome(options=options, use_subprocess=False)
        
        # Apply stealth techniques
        stealth(driver,
                languages=["en-US", "en"],
                vendor="Google Inc.",
                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True)
        
        try:
            url = 'https://www.macmap.org/en/query/trade-agreements'
            logger.info(f"Navigating to: {url}")
            
            driver.get(url)
            time.sleep(5)  # Wait for page to load
            
            # Wait for page to be ready
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            logger.info("Page loaded successfully!")
            
            # Try to find and fill the form
            try:
                # Wait for country dropdown - try multiple selectors
                logger.info("Looking for country dropdown...")
                country_select = None
                
                # Try different selectors
                selectors = [
                    "select[name='country']",
                    "select#country",
                    "select.country-select",
                    "//select[contains(@class, 'country')]"
                ]
                
                for selector in selectors:
                    try:
                        if selector.startswith("//"):
                            country_select = WebDriverWait(driver, 5).until(
                                EC.presence_of_element_located((By.XPATH, selector))
                            )
                        else:
                            country_select = WebDriverWait(driver, 5).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                            )
                        logger.info(f"Found country dropdown with selector: {selector}")
                        break
                    except:
                        continue
                
                if country_select:
                    logger.info(f"Selecting country code: {reporter_code}")
                    Select(country_select).select_by_value(str(reporter_code))
                    time.sleep(3)
                else:
                    logger.error("Could not find country dropdown")
                    raise Exception("Country dropdown not found")
                
                # Select relation
                try:
                    relation_select = driver.find_element(By.CSS_SELECTOR, "select#relation, select[name='relation']")
                    relation_text = f"As {relation}"
                    Select(relation_select).select_by_visible_text(relation_text)
                    logger.info(f"Selected relation: {relation_text}")
                    time.sleep(2)
                except Exception as e:
                    logger.warning(f"Could not select relation: {e}")
                
                # Select partner
                try:
                    partner_select = driver.find_element(By.CSS_SELECTOR, "select#partner, select[name='partner']")
                    Select(partner_select).select_by_visible_text("All")
                    logger.info("Selected partner: All")
                    time.sleep(2)
                except Exception as e:
                    logger.warning(f"Could not select partner: {e}")
                
                # Click search button
                try:
                    search_button = driver.find_element(By.CSS_SELECTOR, "button:contains('SEARCH'), input[type='submit'], button[type='submit']")
                    search_button.click()
                    logger.info("Clicked SEARCH button")
                    time.sleep(5)  # Wait for results
                except Exception as e:
                    logger.warning(f"Could not click search: {e}")
                
                # Extract results from table
                try:
                    # Wait for results table
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "table, .results, .agreement-list"))
                    )
                    
                    # Find all table rows
                    rows = driver.find_elements(By.CSS_SELECTOR, "tr, .agreement-row")
                    logger.info(f"Found {len(rows)} rows in results")
                    
                    for row in rows:
                        try:
                            cells = row.find_elements(By.CSS_SELECTOR, "td, .cell")
                            
                            if len(cells) >= 2:
                                year = cells[0].text.strip()
                                agreement_name = cells[1].text.strip()
                                status = cells[2].text.strip() if len(cells) > 2 else ""
                                partners = cells[3].text.strip() if len(cells) > 3 else ""
                                
                                if agreement_name and year and year.isdigit():
                                    agreement = {
                                        "name": agreement_name,
                                        "year": year,
                                        "status": status,
                                        "relation": relation,
                                        "partner": partner,
                                        "partners_text": partners
                                    }
                                    agreements.append(agreement)
                                    logger.info(f"Extracted: {year} - {agreement_name}")
                        except Exception as row_err:
                            logger.debug(f"Error parsing row: {row_err}")
                            continue
                    
                    # If no structured data, try alternative extraction
                    if not agreements:
                        logger.info("No structured data found, trying text extraction...")
                        page_text = driver.find_element(By.TAG_NAME, "body").text
                        logger.info(f"Page text sample: {page_text[:500]}")
                        
                        # Look for agreement patterns
                        import re
                        lines = page_text.split('\n')
                        for line in lines:
                            # Look for year patterns followed by agreement names
                            if re.match(r'^\d{4}', line.strip()):
                                parts = line.strip().split()
                                if len(parts) >= 2:
                                    year = parts[0]
                                    name = ' '.join(parts[1:])
                                    if name:
                                        agreements.append({
                                            "name": name,
                                            "year": year,
                                            "relation": relation,
                                            "partner": partner
                                        })
                                        logger.info(f"Extracted from text: {year} - {name}")
                    
                except Exception as extract_err:
                    logger.error(f"Error extracting results: {extract_err}")
                    
                    # Take screenshot for debugging
                    try:
                        screenshot_path = f"/tmp/macmap_{country_name}_{relation}.png"
                        driver.save_screenshot(screenshot_path)
                        logger.info(f"Saved screenshot to: {screenshot_path}")
                    except:
                        pass
                
            except Exception as form_err:
                logger.error(f"Error filling form: {form_err}")
                
                # Log page source for debugging
                try:
                    page_source = driver.page_source[:1000]
                    logger.info(f"Page source sample: {page_source}")
                except:
                    pass
            
        finally:
            driver.quit()
            logger.info("Browser closed")
        
    except Exception as e:
        logger.error(f"Error in Selenium scraper: {str(e)}", exc_info=True)
    
    return agreements
