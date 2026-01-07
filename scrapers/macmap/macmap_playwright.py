"""
MacMap Playwright Scraper
Uses real browser automation to bypass anti-bot protection
"""
import json
import logging
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from pathlib import Path
import os
import datetime

# Setup logging
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"macmap_playwright_{datetime.datetime.now().strftime('%Y%m%d')}.log")
logger = logging.getLogger('macmap_playwright')
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


def get_macmap_data_playwright(reporter_id, partner_id, product_code, year):
    """
    Fetch MacMap tariff data using Playwright (real browser)
    
    Args:
        reporter_id: Country code for importing country
        partner_id: Country code for exporting country
        product_code: HS code
        year: Year for tariff data
        
    Returns:
        dict: JSON response from MacMap API or None if failed
    """
    logger.info(f"Starting Playwright scrape for {reporter_id}->{partner_id}, product: {product_code}, year: {year}")
    
    try:
        with sync_playwright() as p:
            # Launch browser in headless mode
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            page = context.new_page()
            
            # Navigate to MacMap homepage first (establish session)
            logger.info("Loading MacMap homepage...")
            page.goto('https://www.macmap.org/', wait_until='networkidle', timeout=30000)
            
            # Wait a bit to appear more human-like
            page.wait_for_timeout(1000)
            
            # Construct API URL
            api_url = f'https://www.macmap.org/api/results/custom-duties-by-year?reporter={reporter_id}&partner={partner_id}&product={product_code}&year={year}'
            logger.info(f"Fetching API data: {api_url}")
            
            # Navigate to API endpoint
            response = page.goto(api_url, wait_until='networkidle', timeout=30000)
            
            if response.status == 200:
                # Get JSON response
                content = page.content()
                # Extract JSON from <pre> tag or body
                json_text = page.evaluate('() => document.body.textContent')
                
                try:
                    data = json.loads(json_text)
                    logger.info(f"✅ Successfully fetched data: {len(data.get('CustomDuty', []))} items")
                    browser.close()
                    return data
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON: {e}")
                    logger.debug(f"Content: {json_text[:500]}")
                    browser.close()
                    return None
            else:
                logger.error(f"API request failed with status: {response.status}")
                browser.close()
                return None
                
    except PlaywrightTimeout as e:
        logger.error(f"Playwright timeout: {e}")
        return None
    except Exception as e:
        logger.error(f"Playwright error: {e}")
        return None


def get_macmap_fta_details_playwright(reporter_id, partner_id, product_code, fta_id):
    """
    Fetch MacMap FTA details using Playwright
    
    Args:
        reporter_id: Country code for importing country
        partner_id: Country code for exporting country
        product_code: HS code
        fta_id: Free Trade Agreement ID
        
    Returns:
        dict: JSON response from MacMap API or None if failed
    """
    logger.info(f"Fetching FTA details for {fta_id} via Playwright")
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            page = context.new_page()
            
            # Construct API URL
            api_url = f'https://www.macmap.org/api/results/fta?reporter={reporter_id}&partner={partner_id}&product={product_code}&ftaId={fta_id}'
            logger.info(f"Fetching FTA API: {api_url}")
            
            response = page.goto(api_url, wait_until='networkidle', timeout=30000)
            
            if response.status == 200:
                json_text = page.evaluate('() => document.body.textContent')
                try:
                    data = json.loads(json_text)
                    logger.info(f"✅ Successfully fetched FTA data")
                    browser.close()
                    return data
                except json.JSONDecodeError:
                    browser.close()
                    return None
            else:
                browser.close()
                return None
                
    except Exception as e:
        logger.error(f"FTA Playwright error: {e}")
        return None


def get_macmap_roo_playwright(reporter_id, partner_id, fta_id):
    """
    Fetch MacMap Rules of Origin using Playwright
    """
    logger.info(f"Fetching ROO for {fta_id} via Playwright")
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            page = context.new_page()
            
            api_url = f'https://www.macmap.org/api/results/roo-by-fta?reporter={reporter_id}&partner={partner_id}&ftaId={fta_id}'
            logger.info(f"Fetching ROO API: {api_url}")
            
            response = page.goto(api_url, wait_until='networkidle', timeout=30000)
            
            if response.status == 200:
                json_text = page.evaluate('() => document.body.textContent')
                try:
                    data = json.loads(json_text)
                    logger.info(f"✅ Successfully fetched ROO data")
                    browser.close()
                    return data
                except json.JSONDecodeError:
                    browser.close()
                    return None
            else:
                browser.close()
                return None
                
    except Exception as e:
        logger.error(f"ROO Playwright error: {e}")
        return None


def get_trade_agreements_playwright(reporter_code, country_name, relation='exporter', partner='All'):
    """
    Scrape trade agreements from MACMAP website using Playwright.
    Uses the proper MACMAP Trade Agreements search form.
    
    Args:
        reporter_code: Country code (e.g., 156 for China)
        country_name: Country name for logging
        relation: 'exporter' or 'importer' (default: 'exporter')
        partner: Partner country code or 'All' (default: 'All')
    
    Returns:
        List of trade agreement dictionaries with year-wise data
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    
    agreements = []
    
    try:
        # Try WITHOUT proxy first - proxies are causing ERR_TUNNEL_CONNECTION_FAILED
        proxy_config = None
        logger.info("Attempting connection without proxy...")
        
        with sync_playwright() as p:
            logger.info(f"Launching browser for {country_name} trade agreements (as {relation} to {partner})...")
            browser = p.chromium.launch(headless=True)
            
            # Create context with proxy if available
            context_args = {
                'viewport': {'width': 1920, 'height': 1080},
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            if proxy_config:
                context_args['proxy'] = proxy_config
            
            context = browser.new_context(**context_args)
            page = context.new_page()
            
            # Navigate to main trade agreements page
            url = 'https://www.macmap.org/en/query/trade-agreements'
            logger.info(f"Navigating to: {url}")
            
            try:
                page.goto(url, wait_until='networkidle', timeout=60000)
                page.wait_for_timeout(3000)
                
                # Fill in the search form
                logger.info("Filling search form...")
                
                # 1. Select Country
                country_dropdown = page.wait_for_selector('select#country, [name="country"], [placeholder*="Country"]', timeout=10000)
                if country_dropdown:
                    page.select_option('select#country, [name="country"]', value=str(reporter_code))
                    logger.info(f"Selected country: {country_name} ({reporter_code})")
                    page.wait_for_timeout(1000)
                
                # 2. Select Relation (As exporter / As importer)
                relation_dropdown = page.wait_for_selector('select#relation, [name="relation"]', timeout=10000)
                if relation_dropdown:
                    relation_value = 'exporter' if relation.lower() == 'exporter' else 'importer'
                    page.select_option('select#relation, [name="relation"]', label=f"As {relation_value}")
                    logger.info(f"Selected relation: As {relation_value}")
                    page.wait_for_timeout(1000)
                
                # 3. Select Partner (All or specific)
                partner_dropdown = page.wait_for_selector('select#partner, [name="partner"]', timeout=10000)
                if partner_dropdown:
                    if partner == 'All':
                        page.select_option('select#partner, [name="partner"]', label="All")
                    else:
                        page.select_option('select#partner, [name="partner"]', value=str(partner))
                    logger.info(f"Selected partner: {partner}")
                    page.wait_for_timeout(1000)
                
                # 4. Click SEARCH button
                search_button = page.wait_for_selector('button:has-text("SEARCH"), input[type="submit"]', timeout=10000)
                if search_button:
                    logger.info("Clicking SEARCH button...")
                    search_button.click()
                    page.wait_for_timeout(5000)  # Wait for results to load
                
                # 5. Extract year-wise agreement data
                logger.info("Extracting agreement data...")
                
                # Look for agreement list/table
                page.wait_for_selector('table, .agreement-list, [class*="result"]', timeout=15000)
                
                # Extract all rows from results
                rows = page.query_selector_all('tr, .agreement-row, [class*="agreement"]')
                
                for row in rows:
                    try:
                        # Extract text content
                        text = row.inner_text().strip()
                        
                        if not text or text in ['Country', 'Relation', 'Partner', 'Year']:
                            continue
                        
                        # Try to extract structured data
                        cells = row.query_selector_all('td, .cell, span')
                        
                        if len(cells) >= 2:
                            # Extract year and agreement name
                            year = cells[0].inner_text().strip() if len(cells) > 0 else ""
                            agreement_name = cells[1].inner_text().strip() if len(cells) > 1 else ""
                            status = cells[2].inner_text().strip() if len(cells) > 2 else ""
                            partners_text = cells[3].inner_text().strip() if len(cells) > 3 else ""
                            
                            if agreement_name and year:
                                agreement = {
                                    "name": agreement_name,
                                    "year": year,
                                    "status": status,
                                    "relation": relation,
                                    "partner": partner,
                                    "partners_text": partners_text
                                }
                                agreements.append(agreement)
                                logger.info(f"Extracted: {year} - {agreement_name}")
                        
                    except Exception as row_error:
                        logger.debug(f"Error parsing row: {row_error}")
                        continue
                
                # If no structured data, try alternative extraction
                if not agreements:
                    logger.info("Trying alternative extraction method...")
                    all_text = page.inner_text('body')
                    
                    # Log sample of text for debugging
                    logger.info(f"Page text sample: {all_text[:500]}")
                    
                    # Look for year patterns (e.g., "2020", "2019")
                    import re
                    year_pattern = r'\b(19\d{2}|20\d{2})\b'
                    matches = re.finditer(year_pattern, all_text)
                    
                    for match in matches:
                        year = match.group(1)
                        # Get surrounding context
                        start = max(0, match.start() - 100)
                        end = min(len(all_text), match.end() + 200)
                        context = all_text[start:end]
                        
                        agreements.append({
                            "year": year,
                            "context": context.strip(),
                            "relation": relation,
                            "partner": partner
                        })
                
                logger.info(f"Successfully extracted {len(agreements)} trade agreements for {country_name}")
                
            except PlaywrightTimeout:
                logger.error(f"Timeout while loading trade agreements page for {country_name}")
            except Exception as e:
                logger.error(f"Error navigating to page: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
            
            browser.close()
            
    except Exception as e:
        logger.error(f"Error in get_trade_agreements_playwright: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
    
    return agreements


if __name__ == "__main__":
    # Test the scraper
    print("Testing MacMap Playwright scraper...")
    
    # Test: Saudi Arabia -> Singapore, HS: 381210, Year: 2025
    result = get_macmap_data_playwright(682, 702, '381210', 2025)
    
    if result:
        print(f"✅ SUCCESS! Got {len(result.get('CustomDuty', []))} items")
        print(f"Sample data: {json.dumps(result, indent=2)[:500]}...")
    else:
        print("❌ FAILED to fetch data")
