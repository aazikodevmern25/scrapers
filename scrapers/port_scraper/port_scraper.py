"""
SeaRates Port Scraper
Comprehensive scraper for maritime port data from SeaRates.com
Integrated with the data-extractor scraper system
"""

import os
import logging
import datetime
import time
import re
import signal
import sys
import threading
import psutil
from typing import Dict, List, Optional, Tuple
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from utils import client
import chromedriver_autoinstaller

# Global registry to track active scraper instances
_active_scrapers = {}
_scrapers_lock = threading.Lock()


def kill_chrome_processes():
    """Kill all Chrome and chromedriver processes to ensure cleanup."""
    killed_count = 0
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                name = proc.info['name'].lower() if proc.info['name'] else ''
                cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                
                # Kill chrome and chromedriver processes
                if ('chrome' in name or 'chromedriver' in name) and \
                   ('--enable-automation' in cmdline or 'chromedriver' in cmdline):
                    logger.warning(f"Killing Chrome process: PID {proc.info['pid']} - {name}")
                    proc.kill()
                    killed_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except Exception as e:
        logger.error(f"Error killing Chrome processes: {e}")
    
    if killed_count > 0:
        logger.info(f"✅ Killed {killed_count} Chrome/chromedriver processes")
    return killed_count

# Configure logging
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"port_scraper_{datetime.datetime.now().strftime('%Y%m%d')}.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('port_scraper')

# Port Scraper uses a separate database
PORT_SCRAPER_DB = os.getenv('PORT_SCRAPER_DB', 'ports_database')
port_db = client[PORT_SCRAPER_DB]

logger.info(f"Port Scraper using database: {PORT_SCRAPER_DB}")

# MongoDB collections for port scraper in separate database
ports_collection = port_db['ports']
countries_collection = port_db['ports_countries']
detailed_ports_collection = port_db['ports_detailed']
scraping_sessions_collection = port_db['ports_scraping_sessions']
scraping_progress_collection = port_db['ports_scraping_progress']

# Create comprehensive indexes for better query performance
def _create_mongodb_indexes():
    """Create comprehensive MongoDB indexes for efficient querying."""
    try:
        # Detailed ports indexes
        detailed_ports_collection.create_index([("country_code", 1), ("port_name", 1)], unique=True)
        detailed_ports_collection.create_index("coordinates.decimal")
        detailed_ports_collection.create_index("coordinates.latitude")
        detailed_ports_collection.create_index("coordinates.longitude")
        detailed_ports_collection.create_index("general_info.un_locode")
        detailed_ports_collection.create_index("shipping_lines")
        detailed_ports_collection.create_index("general_info.port_authority")
        detailed_ports_collection.create_index("general_info.port_type")
        detailed_ports_collection.create_index("port_details.region")
        detailed_ports_collection.create_index("last_updated")
        
        # Progress tracking indexes
        scraping_progress_collection.create_index([("session_id", 1), ("country_code", 1)], unique=True)
        
        # Basic collections indexes
        ports_collection.create_index([("country_code", 1), ("code", 1)], unique=True)
        countries_collection.create_index("country_code", unique=True)
        scraping_sessions_collection.create_index("start_time")
        
        logger.info("✅ MongoDB indexes created successfully")
    except Exception as e:
        logger.warning(f"Some indexes may already exist: {e}")

# Create indexes on module load
_create_mongodb_indexes()


class PortScraper:
    """
    Comprehensive SeaRates Port Scraper (matches comprehensive_country_by_country_scraper.py)
    """
    
    BASE_URL = "https://www.searates.com/maritime"  # Changed to match comprehensive scraper
    
    def __init__(self, headless: bool = True, task_id: Optional[str] = None):
        """Initialize the port scraper."""
        self.headless = headless
        self.driver = None
        self.wait = None
        self.session_id = None
        self.interrupted = False
        self.task_id = task_id or f"scraper_{id(self)}"
        
        # Register this scraper instance globally
        with _scrapers_lock:
            _active_scrapers[self.task_id] = self
        
        # Setup signal handlers for graceful interruption
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)  # Handle Celery termination
        
        logger.info(f"Initializing PortScraper (headless={headless}, task_id={self.task_id})")
    
    def _signal_handler(self, sig, frame):
        """Handle interrupt signals (Ctrl+C, SIGTERM) gracefully."""
        signal_name = "SIGTERM" if sig == signal.SIGTERM else "SIGINT"
        
        if not self.interrupted:
            logger.warning("\n" + "="*80)
            logger.warning(f"🛑 STOP SIGNAL RECEIVED ({signal_name}) - STOPPING NOW!")
            logger.warning("="*80)
            logger.warning("⏸️  Finishing current page load and stopping...")
            logger.warning("⏸️  Please wait a moment for cleanup...")
            logger.warning("="*80)
            self.interrupted = True
            
            # For SIGTERM (Celery termination), force cleanup immediately
            if sig == signal.SIGTERM:
                logger.warning("⚠️  SIGTERM received - forcing immediate cleanup")
                try:
                    if self.driver:
                        self.driver.quit()
                        logger.info("✅ Browser closed successfully")
                except Exception as e:
                    logger.error(f"Error closing browser: {e}")
                
                # Force kill all Chrome processes
                logger.warning("🔪 Force killing all Chrome processes...")
                kill_chrome_processes()
                
                # Exit immediately
                sys.exit(0)
        else:
            # If user presses Ctrl+C again, force quit
            logger.error("\n" + "="*80)
            logger.error("❌ FORCE QUIT - Stopping immediately")
            logger.error("="*80)
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
            
            # Force kill all Chrome processes
            kill_chrome_processes()
            sys.exit(1)
        
    def _initialize_driver(self):
        """Initialize the Selenium driver (matches comprehensive scraper)."""
        if self.driver is None:
            try:
                from selenium.webdriver.chrome.options import Options
                
                logger.info("Initializing Chrome driver")
                
                # Auto-install matching ChromeDriver version
                chromedriver_autoinstaller.install()
                logger.info("ChromeDriver auto-installed/verified")
                
                chrome_options = Options()
                if self.headless:
                    chrome_options.add_argument("--headless")
                
                # Enhanced Chrome options for better performance
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument("--disable-gpu")
                chrome_options.add_argument("--disable-extensions")
                chrome_options.add_argument("--disable-plugins")
                chrome_options.add_argument("--disable-images")  # Faster loading
                chrome_options.add_argument("--disable-javascript")  # If not needed
                chrome_options.add_argument("--memory-pressure-off")
                chrome_options.add_argument("--max_old_space_size=4096")
                
                # Performance optimizations
                chrome_options.add_experimental_option("useAutomationExtension", False)
                chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                
                self.driver = webdriver.Chrome(options=chrome_options)
                self.driver.set_page_load_timeout(60)  # Increased timeout
                self.driver.implicitly_wait(10)
                
                self.wait = WebDriverWait(self.driver, 20)  # Increased wait time
                
                logger.info("✅ Enhanced Chrome driver initialized successfully")
                
            except Exception as e:
                logger.error(f"Failed to initialize Chrome driver: {e}")
                raise
                
    def close(self):
        """Close the Selenium driver and cleanup resources."""
        # Unregister this scraper from global registry
        with _scrapers_lock:
            if self.task_id in _active_scrapers:
                del _active_scrapers[self.task_id]
                logger.info(f"Unregistered scraper {self.task_id}")
        
        if self.driver:
            try:
                self.driver.quit()
                logger.info("Driver closed successfully")
            except Exception as e:
                logger.error(f"Error closing driver: {e}")
            finally:
                self.driver = None
        
        # Force kill any remaining Chrome processes
        logger.info("Checking for orphaned Chrome processes...")
        kill_chrome_processes()
    
    def stop(self):
        """Enhanced stop method with immediate state synchronization"""
        logger.info(f"Stop requested for port scraper {self.scraper_id}")
        self.should_stop = True
        self.interrupted = True
        self.state_synchronizer.update_scraper_state(self.scraper_id, ScraperState.STOPPING)

    def _cleanup_optimized(self):
        """Enhanced cleanup with state synchronization"""
        logger.info("Starting enhanced port scraper cleanup...")
        
        try:
            # Update state to stopped
            self.state_synchronizer.update_scraper_state(self.scraper_id, ScraperState.STOPPED)
            
            # Close browser
            if self.driver:
                try:
                    self.driver.quit()
                    logger.info("✅ Browser closed successfully")
                except Exception as e:
                    logger.error(f"Error closing browser: {e}")
            
            # Kill Chrome processes
            kill_chrome_processes()
            
            # Remove from global registry
            with _scrapers_lock:
                _active_scrapers.pop(self.task_id, None)
            
            logger.info("Enhanced port scraper cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def get_performance_stats(self) -> Dict:
        """Enhanced performance statistics"""
        with self.stats_lock:
            base_stats = self.stats.copy()
        
        # Get optimizer stats
        optimizer_stats = self.performance_optimizer.get_performance_stats()
        
        # Get state info
        state_info = self.state_synchronizer.get_scraper_status(self.scraper_id)
        
        return {
            'scraper_id': self.scraper_id,
            'scraper_stats': base_stats,
            'optimizer_stats': optimizer_stats,
            'state_info': state_info.to_dict() if state_info else None,
            'is_running': self.running,
            'should_stop': self.should_stop
        }

    def _create_scraping_session(self) -> str:
        """Create a new scraping session and return session ID."""
        session_data = {
            "start_time": datetime.datetime.now(),
            "end_time": None,
            "status": "running",
            "countries_scraped": 0,
            "ports_discovered": 0,
            "detailed_ports_scraped": 0,
            "errors": []
        }
        result = scraping_sessions_collection.insert_one(session_data)
        self.session_id = str(result.inserted_id)
        logger.info(f"Created scraping session: {self.session_id}")
        return self.session_id
        
    def _update_scraping_session(self, updates: dict):
        """Update the current scraping session."""
        if self.session_id:
            scraping_sessions_collection.update_one(
                {"_id": self.session_id},
                {"$set": updates}
            )
            
    def _save_progress(self, country_name: str, country_code: str, status: str, message: str = ""):
        """Save scraping progress for a country."""
        progress_data = {
            "session_id": self.session_id,
            "country_name": country_name,
            "country_code": country_code,
            "status": status,
            "message": message,
            "timestamp": datetime.datetime.now()
        }
        scraping_progress_collection.insert_one(progress_data)
        
    def get_all_countries(self) -> List[Dict]:
        """Get all countries from SeaRates dropdown (matches comprehensive scraper)."""
        self._initialize_driver()
        
        try:
            from selenium.webdriver.support.ui import Select
            
            if self.interrupted:
                logger.warning("⚠️  Interrupted before getting countries")
                return []
            
            logger.info(f"Navigating to base URL: {self.BASE_URL}")
            self.driver.get(self.BASE_URL)
            
            # Interruptible sleep
            for _ in range(30):  # 3 seconds in 0.1s intervals
                if self.interrupted:
                    return []
                time.sleep(0.1)
            
            # Get country dropdown (matches comprehensive scraper)
            country_select = self.wait.until(
                EC.presence_of_element_located((By.ID, "country-content"))
            )
            
            select = Select(country_select)
            options = select.options
            
            countries = []
            for option in options[1:]:  # Skip first empty option
                country_code = option.get_attribute("value")
                country_name = option.text.strip()
                
                if country_code and country_name:
                    countries.append({
                        'country_code': country_code,
                        'country_name': country_name,
                        'session_id': self.session_id,
                        'discovered_at': datetime.datetime.now()
                    })
            
            logger.info(f"Found {len(countries)} countries from dropdown")
            
            # Save countries to MongoDB (matches comprehensive scraper format)
            for country in countries:
                countries_collection.update_one(
                    {'country_code': country['country_code']},
                    {'$set': country},
                    upsert=True
                )
            
            return countries
            
        except Exception as e:
            logger.error(f"Error getting countries: {e}")
            logger.exception("Full traceback:")
            return []
            
    def get_country_ports(self, country_code: str, country_name: str) -> Tuple[List[Dict], List[Dict]]:
        """Get all ports and nearby countries for a specific country (matches comprehensive scraper)."""
        try:
            from selenium.webdriver.support.ui import Select
            
            if self.interrupted:
                logger.warning("⚠️  Interrupted before getting ports")
                return [], []
            
            logger.info(f"Getting ports for {country_name} ({country_code})")
            
            # Navigate to base URL and select country from dropdown
            self.driver.get(self.BASE_URL)
            
            # Interruptible sleep
            for _ in range(20):  # 2 seconds in 0.1s intervals
                if self.interrupted:
                    return [], []
                time.sleep(0.1)
            
            if self.interrupted:
                return [], []
            
            # Select country from dropdown
            country_select = self.wait.until(
                EC.presence_of_element_located((By.ID, "country-content"))
            )
            select = Select(country_select)
            select.select_by_value(country_code)
            
            # Interruptible sleep
            for _ in range(30):  # 3 seconds in 0.1s intervals
                if self.interrupted:
                    return [], []
                time.sleep(0.1)
            
            # Get all port elements from the port list
            port_elements = self.driver.find_elements(By.CSS_SELECTOR, "#plist li a")
            
            ports = []
            for port_element in port_elements:
                try:
                    port_name = port_element.text.strip()
                    port_url = port_element.get_attribute("href")
                    
                    if port_name and port_url:
                        ports.append({
                            'country_code': country_code,
                            'country_name': country_name,
                            'port_name': port_name,
                            'port_url': port_url,
                            'session_id': self.session_id,
                            'discovered_at': datetime.datetime.now()
                        })
                except Exception as e:
                    logger.warning(f"Error extracting port info: {e}")
                    continue
            
            # Extract nearby countries (from country info section)
            nearby_countries = []
            try:
                # Look for nearby countries links
                nearby_links = self.driver.find_elements(By.CSS_SELECTOR, ".nearby-countries a, .related-countries a, a[href*='/maritime/']")
                seen_countries = set()
                
                for link in nearby_links:
                    try:
                        href = link.get_attribute("href")
                        name = link.text.strip()
                        
                        if href and name and '/maritime/' in href and name not in seen_countries:
                            # Avoid self-reference and generic pages
                            if name != country_name and name.lower() not in ['port', 'services', 'rates']:
                                nearby_countries.append({
                                    'name': name,
                                    'url': href
                                })
                                seen_countries.add(name)
                    except:
                        continue
                        
                # Limit to reasonable number
                nearby_countries = nearby_countries[:15]
                
            except Exception as e:
                logger.warning(f"Could not extract nearby countries: {e}")
            
            logger.info(f"Found {len(ports)} ports and {len(nearby_countries)} nearby countries for {country_name}")
            
            # Save ports to MongoDB (matches comprehensive scraper format)
            for port in ports:
                ports_collection.update_one(
                    {
                        'country_code': port['country_code'],
                        'port_name': port['port_name']
                    },
                    {'$set': port},
                    upsert=True
                )
            
            return ports, nearby_countries
            
        except Exception as e:
            logger.error(f"Error getting ports for {country_name}: {e}")
            return [], []
            
    def extract_field_value_correctly(self, field_name: str) -> str:
        """Extract field value with CORRECT icon detection."""
        try:
            xpaths_to_try = [
                f"//span[contains(@class, 'incoterms-block__text_color') and contains(text(), '{field_name}')]/following-sibling::span[1]",
                f"//span[contains(@class, 'incoterms-block__text_color') and text()='{field_name}']/following-sibling::span[1]",
                f"//span[contains(@class, 'incoterms-block__text_color') and normalize-space(text())='{field_name}']/following-sibling::span[1]",
                f"//p[contains(@class, 'incoterms-block__item')]//span[contains(text(), '{field_name}')]/following-sibling::span[1]",
                f"//*[contains(text(), '{field_name}')]/following-sibling::*[1]//span"
            ]
            
            for xpath in xpaths_to_try:
                try:
                    element = self.driver.find_element(By.XPATH, xpath)
                    element_html = element.get_attribute('innerHTML') or ""
                    element_text = element.text.strip()
                    
                    # CORRECT LOGIC for icon detection
                    if 'fa-circle point-grey' in element_html:
                        return 'available'
                    elif 'fa-circle point-green' in element_html:
                        return 'available'
                    elif 'fa-circle point-red' in element_html:
                        return 'not_available'
                    elif element_text == '-':
                        return 'not_available'
                    elif element_text and element_text != '' and element_text != '-':
                        # Handle special cases
                        if 'mailto:' in element_html:
                            email_match = re.search(r'mailto:([^"]+)', element_html)
                            if email_match:
                                return email_match.group(1)
                        elif 'http' in element_html and 'href' in element_html:
                            url_match = re.search(r'href="([^"]+)"', element_html)
                            if url_match:
                                return url_match.group(1)
                        elif '<br>' in element_html:
                            # Handle multi-line text (like addresses)
                            value = element_html.replace('<br>', '\n').strip()
                            # Remove HTML tags
                            value = re.sub(r'<[^>]+>', '', value).strip()
                            return value
                        return element_text
                    else:
                        return 'unknown'
                except:
                    continue
            return 'unknown'
        except:
            return 'unknown'
    
    def scrape_port_details(self, port_url: str, port_name: str, country_name: str, country_code: str) -> Optional[Dict]:
        """Scrape comprehensive detailed information for a specific port (matches comprehensive scraper)."""
        try:
            if self.interrupted:
                logger.warning("⚠️  Interrupted before scraping port details")
                return None
            
            logger.info(f"Scraping details for port: {port_name}")
            self.driver.get(port_url)
            
            # Interruptible sleep
            for _ in range(30):  # 3 seconds in 0.1s intervals
                if self.interrupted:
                    return None
                time.sleep(0.1)
            
            port_data = {
                'url': port_url,
                'scraped_at': datetime.datetime.now(),
                'session_id': self.session_id,
                'general_info': {},
                'coordinates': {},
                'port_details': {},
                'entrance_restrictions': {},
                'water_depth': {},
                'harbor_characteristics': {},
                'pilotage': {},
                'supplies': {},
                'lifts_cranes': {},
                'loading_unloading': {},
                'tugs': {},
                'quarantine': {},
                'port_services': {},
                'repairs_services': {},
                'communications': {},
                'shipping_lines': [],
                'nearby_ports': [],
                'icon_correction_applied': True,
                'icon_correction_date': datetime.datetime.now()
            }
            
            # Extract basic port information
            try:
                title_element = self.driver.find_element(By.CSS_SELECTOR, ".reference-title")
                port_data['port_name'] = title_element.text.replace("Port", "").strip()
                
                country_element = self.driver.find_element(By.CSS_SELECTOR, ".reference-subtitle")
                port_data['country_name'] = country_element.text.strip()
                
                # Extract country code from flag
                flag_element = self.driver.find_element(By.CSS_SELECTOR, ".flag-icon")
                flag_class = flag_element.get_attribute("class")
                port_data['country_code'] = flag_class.split("flag-icon-")[-1].upper()
                
            except Exception as e:
                logger.warning(f"Could not extract basic info: {e}")
                # Use provided values as fallback
                port_data['port_name'] = port_name
                port_data['country_name'] = country_name
                port_data['country_code'] = country_code
            
            # Extract general information with enhanced fields
            general_info_fields = [
                ('Address', 'address'),
                ('Port Authority', 'port_authority'),
                ('Phone', 'phone'),
                ('Fax', 'fax'),
                ('Email', 'email'),
                ('Coordinates', 'coordinates_text'),
                ('Decimal', 'decimal_coordinates'),
                ('UN/LOCODE', 'un_locode'),
                ('Port Type', 'port_type'),
                ('Port Size', 'port_size'),
                ('Website', 'website'),
                ('Terminal', 'terminal')
            ]
            
            for display_name, field_key in general_info_fields:
                port_data['general_info'][field_key] = self.extract_field_value_correctly(display_name)
            
            # Parse coordinates
            if port_data['general_info'].get('decimal_coordinates'):
                coords_text = port_data['general_info']['decimal_coordinates']
                if coords_text and coords_text != 'unknown':
                    coords_match = re.search(r'([-\d.]+),\s*([-\d.]+)', coords_text)
                    if coords_match:
                        port_data['coordinates'] = {
                            'latitude': float(coords_match.group(1)),
                            'longitude': float(coords_match.group(2)),
                            'decimal': coords_text
                        }
            
            # Extract all detailed sections with comprehensive field mappings
            sections = [
                ('port_details', [('Region', 'region'), ('Inland port', 'inland_port')]),
                ('entrance_restrictions', [('Tide', 'tide'), ('Overhead Limit', 'overhead_limit'), ('Swell', 'swell')]),
                ('water_depth', [('Channel', 'channel'), ('Cargo Pier', 'cargo_pier'), ('Mean Tide', 'mean_tide'), ('Anchorage', 'anchorage'), ('Oil Terminal', 'oil_terminal')]),
                ('harbor_characteristics', [('Harbor Size', 'harbor_size'), ('Shelter', 'shelter'), ('Max Vessel Size', 'max_vessel_size'), ('Harbor Type', 'harbor_type'), ('Turning Area', 'turning_area')]),
                ('pilotage', [('Compulsory', 'compulsory'), ('Available', 'available'), ('Advisable', 'advisable'), ('Local Assist', 'local_assist')]),
                ('supplies', [('Provisions', 'provisions'), ('Fuel Oil', 'fuel_oil'), ('Deck', 'deck'), ('Water', 'water'), ('Diesel Oil', 'diesel_oil'), ('Engine', 'engine')]),
                ('lifts_cranes', [('0-24 Ton Lifts', 'lifts_0_24'), ('25-49 Ton Lifts', 'lifts_25_49'), ('50-100 Ton Lifts', 'lifts_50_100'), ('100+ Ton Lifts', 'lifts_100_plus'), ('Fixed Cranes', 'fixed_cranes'), ('Mobile Cranes', 'mobile_cranes'), ('Floating Cranes', 'floating_cranes')]),
                ('loading_unloading', [('Wharves', 'wharves'), ('Med Moor', 'med_moor'), ('Ice', 'ice'), ('Anchor', 'anchor'), ('Beach', 'beach')]),
                ('tugs', [('Assist', 'assist'), ('Salvage', 'salvage')]),
                ('quarantine', [('Pratique', 'pratique'), ('Deratt Cert', 'deratt_cert')]),
                ('port_services', [('Longshore', 'longshore'), ('Electrical Repair', 'electrical_repair'), ('Steam', 'steam'), ('Electrical', 'electrical'), ('Navigation Eq', 'navigation_eq')]),
                ('repairs_services', [('Ship Repairs', 'ship_repairs'), ('Marine Railroad', 'marine_railroad'), ('Degauss', 'degauss'), ('Drydock Size', 'drydock_size'), ('Garbage Disposal', 'garbage_disposal'), ('Dirty Ballast', 'dirty_ballast')]),
                ('communications', [('Telephone', 'telephone'), ('Radio', 'radio'), ('Air', 'air'), ('Telegraph', 'telegraph'), ('Radio Tel', 'radio_tel'), ('Rail', 'rail')])
            ]
            
            for section_key, fields in sections:
                if self.interrupted:
                    logger.warning("⚠️  Interrupted during field extraction")
                    return None
                for display_name, field_key in fields:
                    port_data[section_key][field_key] = self.extract_field_value_correctly(display_name)
            
            # Extract shipping lines
            try:
                # Try multiple methods to find shipping lines
                shipping_lines_found = False
                
                # Method 1: Look for h4 with shipping lines text
                try:
                    shipping_section = self.driver.find_element(By.XPATH, "//h4[contains(text(), 'shipping lines')]/following-sibling::text()[1] | //h4[contains(text(), 'shipping lines')]/parent::*/text()[position()>1]")
                    shipping_text = shipping_section.text.strip()
                    if shipping_text:
                        port_data['shipping_lines'] = [line.strip() for line in shipping_text.split(',') if line.strip()]
                        shipping_lines_found = True
                except:
                    pass
                
                # Method 2: Look in the reference text section
                if not shipping_lines_found:
                    try:
                        reference_text = self.driver.find_element(By.CSS_SELECTOR, ".reference-subtitle.reference-text")
                        text_content = reference_text.text
                        if "shipping lines" in text_content.lower():
                            lines_text = text_content.split('\n')[-1]  # Get last line
                            if lines_text and not lines_text.startswith('List'):
                                port_data['shipping_lines'] = [line.strip() for line in lines_text.split(',') if line.strip()]
                                shipping_lines_found = True
                    except:
                        pass
                
            except Exception as e:
                logger.warning(f"Could not extract shipping lines: {e}")
            
            # Extract nearby ports
            try:
                nearby_port_elements = self.driver.find_elements(By.CSS_SELECTOR, ".ports-item a")
                for port_element in nearby_port_elements:
                    nearby_port_name = port_element.text.strip()
                    nearby_port_url = port_element.get_attribute("href")
                    if nearby_port_name and nearby_port_url:
                        port_data['nearby_ports'].append({
                            'name': nearby_port_name,
                            'url': nearby_port_url
                        })
            except Exception as e:
                logger.warning(f"Could not extract nearby ports: {e}")
            
            # Extract vessel schedules link if available
            try:
                schedule_link = self.driver.find_element(By.CSS_SELECTOR, ".port-schedule-link")
                port_data['vessel_schedules_url'] = schedule_link.get_attribute("href")
            except:
                pass
            
            logger.info(f"Successfully scraped comprehensive details for port: {port_name}")
            return port_data
            
        except Exception as e:
            logger.error(f"Error scraping port details for {port_name} ({port_code}): {e}")
            logger.exception("Full traceback:")
            return None
            
    def scrape_countries_in_order(
        self,
        start_from_country: Optional[str] = None,
        skip_existing: bool = True,
        countries_limit: Optional[int] = None
    ) -> Dict:
        """Enhanced main scraping method with performance optimization and state synchronization"""
        try:
            self.running = True
            self.should_stop = False
            self.interrupted = False
            self.stats['start_time'] = datetime.datetime.now()
            
            # Update state to running
            self.state_synchronizer.update_scraper_state(self.scraper_id, ScraperState.RUNNING)
            
            logger.info("🚀 Starting enhanced port scraping with maximum performance optimization")
            
            # Initialize driver
            self._initialize_driver()
            
            # Create scraping session
            self.session_id = self._create_scraping_session()
            
            # Get all countries
            countries = self.get_all_countries()
            if not countries:
                logger.error("❌ No countries found to scrape")
                return {"status": "error", "message": "No countries found"}
            
            # Apply country limit and starting point
            if start_from_country:
                start_index = next((i for i, c in enumerate(countries) if c['name'].lower() == start_from_country.lower()), 0)
                countries = countries[start_index:]
                logger.info(f"📍 Starting from country: {start_from_country} (index {start_index})")
            
            if countries_limit:
                countries = countries[:countries_limit]
                logger.info(f"🔢 Limited to {countries_limit} countries")
            
            self.stats['total_countries'] = len(countries)
            logger.info(f"📊 Total countries to process: {len(countries)}")
            
            # Process countries with enhanced performance
            successful_countries = 0
            failed_countries = 0
            
            for i, country in enumerate(countries):
                if self.should_stop or self.interrupted:
                    logger.info("🛑 Stopping scraper as requested")
                    break
                
                country_name = country['name']
                country_code = country['code']
                
                logger.info(f"\n{'='*80}")
                logger.info(f"🌍 Processing country {i+1}/{len(countries)}: {country_name} ({country_code})")
                logger.info(f"{'='*80}")
                
                try:
                    start_time = time.time()
                    
                    # Check if country already processed (if skip_existing is True)
                    if skip_existing and self._is_country_processed(country_code):
                        logger.info(f"⏭️  Skipping {country_name} - already processed")
                        continue
                    
                    # Get ports for this country with enhanced error handling
                    ports, failed_ports = self.get_country_ports_optimized(country_code, country_name)
                    
                    if ports:
                        self.stats['total_ports'] += len(ports)
                        
                        # Process ports with performance optimization
                        for port in ports:
                            if self.should_stop or self.interrupted:
                                break
                            
                            try:
                                port_start_time = time.time()
                                
                                # Scrape port details with caching
                                port_details = self.scrape_port_details_optimized(
                                    port['url'], port['name'], country_name, country_code
                                )
                                
                                port_load_time = time.time() - port_start_time
                                self._update_stats(
                                    processed_ports=1,
                                    average_page_load_time=port_load_time
                                )
                                
                                if port_details:
                                    self._update_stats(successful_ports=1)
                                else:
                                    self._update_stats(failed_ports=1)
                                
                                # Log progress periodically
                                if self.stats['processed_ports'] % 10 == 0:
                                    self._log_progress()
                                
                            except Exception as e:
                                logger.error(f"❌ Error processing port {port['name']}: {e}")
                                self._update_stats(processed_ports=1, failed_ports=1)
                        
                        successful_countries += 1
                        country_time = time.time() - start_time
                        logger.info(f"✅ {country_name} completed in {country_time:.2f}s - {len(ports)} ports processed")
                        
                    else:
                        logger.warning(f"⚠️  No ports found for {country_name}")
                        failed_countries += 1
                    
                    # Save progress
                    self._save_progress(country_name, country_code, "completed")
                    self._update_stats(processed_countries=1)
                    
                    # Brief pause between countries to prevent overwhelming
                    if not self.should_stop:
                        time.sleep(2)
                    
                except Exception as e:
                    logger.error(f"❌ Error processing country {country_name}: {e}")
                    failed_countries += 1
                    self._save_progress(country_name, country_code, "failed", str(e))
            
            # Final statistics
            self.stats['end_time'] = datetime.datetime.now()
            total_time = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
            
            final_stats = {
                "status": "completed" if not self.interrupted else "interrupted",
                "session_id": self.session_id,
                "total_time_seconds": total_time,
                "countries_processed": successful_countries,
                "countries_failed": failed_countries,
                "total_ports_processed": self.stats['processed_ports'],
                "successful_ports": self.stats['successful_ports'],
                "failed_ports": self.stats['failed_ports'],
                "success_rate": (self.stats['successful_ports'] / max(self.stats['processed_ports'], 1)) * 100,
                "average_page_load_time": self.stats['average_page_load_time'],
                "memory_usage_mb": self.stats['memory_usage_mb']
            }
            
            logger.info(f"\n{'='*80}")
            logger.info("🎉 ENHANCED SCRAPING COMPLETED!")
            logger.info(f"📊 Final Statistics: {final_stats}")
            logger.info(f"{'='*80}")
            
            # Update session with final stats
            self._update_scraping_session(final_stats)
            
            return final_stats
            
        except Exception as e:
            logger.error(f"❌ Error in enhanced scraping: {e}")
            self.state_synchronizer.update_scraper_state(
                self.scraper_id, 
                ScraperState.ERROR, 
                error_message=str(e)
            )
            raise
        finally:
            self.running = False
            self._cleanup_optimized()

    def get_country_ports_optimized(self, country_code: str, country_name: str) -> Tuple[List[Dict], List[Dict]]:
        """Enhanced country ports extraction with performance optimization"""
        try:
            start_time = time.time()
            
            # Check cache first
            cache_key = f"country_ports_{country_code}"
            cached_result = self.performance_optimizer.cache.get(cache_key)
            if cached_result:
                self._update_stats(cache_hits=1)
                logger.info(f"📦 Using cached data for {country_name}")
                return cached_result
            
            self._update_stats(cache_misses=1)
            
            # Navigate to country page
            country_url = f"{self.BASE_URL}/{country_code.lower()}"
            logger.info(f"🌐 Loading country page: {country_url}")
            
            self.driver.get(country_url)
            
            # Wait for page to load with enhanced error handling
            try:
                self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "port-item")))
            except TimeoutException:
                logger.warning(f"⚠️  Timeout waiting for ports to load for {country_name}")
                return [], []
            
            # Extract ports with enhanced parsing
            ports = []
            failed_ports = []
            
            try:
                port_elements = self.driver.find_elements(By.CLASS_NAME, "port-item")
                logger.info(f"🔍 Found {len(port_elements)} port elements for {country_name}")
                
                for element in port_elements:
                    try:
                        # Extract port information with better error handling
                        port_link = element.find_element(By.TAG_NAME, "a")
                        port_name = port_link.text.strip()
                        port_url = port_link.get_attribute("href")
                        
                        if port_name and port_url:
                            ports.append({
                                "name": port_name,
                                "url": port_url,
                                "country_code": country_code,
                                "country_name": country_name
                            })
                        else:
                            failed_ports.append({"error": "Missing name or URL", "element": str(element)})
                            
                    except Exception as e:
                        failed_ports.append({"error": str(e), "element": str(element)})
                        logger.warning(f"⚠️  Failed to extract port info: {e}")
                
                # Cache the result
                result = (ports, failed_ports)
                self.performance_optimizer.cache.set(cache_key, result)
                
                load_time = time.time() - start_time
                logger.info(f"✅ {country_name}: {len(ports)} ports found, {len(failed_ports)} failed in {load_time:.2f}s")
                
                return result
                
            except Exception as e:
                logger.error(f"❌ Error extracting ports for {country_name}: {e}")
                return [], []
                
        except Exception as e:
            logger.error(f"❌ Error loading country page for {country_name}: {e}")
            return [], []

    def scrape_port_details_optimized(self, port_url: str, port_name: str, country_name: str, country_code: str) -> Optional[Dict]:
        """Enhanced port details scraping with caching and performance optimization"""
        try:
            start_time = time.time()
            
            # Check cache first
            cache_key = f"port_details_{country_code}_{port_name}"
            cached_result = self.performance_optimizer.cache.get(cache_key)
            if cached_result:
                self._update_stats(cache_hits=1)
                return cached_result
            
            self._update_stats(cache_misses=1)
            
            logger.info(f"🔍 Scraping port details: {port_name}")
            
            # Navigate to port page
            self.driver.get(port_url)
            
            # Wait for page to load
            try:
                self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "port-details")))
            except TimeoutException:
                logger.warning(f"⚠️  Timeout loading port details for {port_name}")
                return None
            
            # Extract comprehensive port information
            port_data = {
                "port_name": port_name,
                "country_name": country_name,
                "country_code": country_code,
                "port_url": port_url,
                "scraped_at": datetime.datetime.now(),
                "scraper_id": self.scraper_id
            }
            
            # Extract various port details with enhanced error handling
            try:
                # General information
                general_info = self._extract_general_info_optimized()
                if general_info:
                    port_data["general_info"] = general_info
                
                # Coordinates
                coordinates = self._extract_coordinates_optimized()
                if coordinates:
                    port_data["coordinates"] = coordinates
                
                # Port details
                details = self._extract_port_details_optimized()
                if details:
                    port_data["port_details"] = details
                
                # Shipping lines
                shipping_lines = self._extract_shipping_lines_optimized()
                if shipping_lines:
                    port_data["shipping_lines"] = shipping_lines
                
                # Store in database
                self._store_port_data_optimized(port_data)
                
                # Cache the result
                self.performance_optimizer.cache.set(cache_key, port_data)
                
                load_time = time.time() - start_time
                logger.info(f"✅ {port_name} details scraped in {load_time:.2f}s")
                
                return port_data
                
            except Exception as e:
                logger.error(f"❌ Error extracting details for {port_name}: {e}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error scraping port details for {port_name}: {e}")
            return None

    def _extract_general_info_optimized(self) -> Optional[Dict]:
        """Enhanced general info extraction with better error handling"""
        try:
            general_info = {}
            
            # Extract various fields with enhanced selectors
            info_fields = {
                "un_locode": [".un-locode", "[data-field='un_locode']", ".locode"],
                "port_authority": [".port-authority", "[data-field='authority']", ".authority"],
                "port_type": [".port-type", "[data-field='type']", ".type"],
                "timezone": [".timezone", "[data-field='timezone']", ".tz"]
            }
            
            for field, selectors in info_fields.items():
                for selector in selectors:
                    try:
                        element = self.driver.find_element(By.CSS_SELECTOR, selector)
                        if element and element.text.strip():
                            general_info[field] = element.text.strip()
                            break
                    except NoSuchElementException:
                        continue
            
            return general_info if general_info else None
            
        except Exception as e:
            logger.warning(f"⚠️  Error extracting general info: {e}")
            return None

    def _extract_coordinates_optimized(self) -> Optional[Dict]:
        """Enhanced coordinates extraction"""
        try:
            coordinates = {}
            
            # Try multiple selectors for coordinates
            coord_selectors = [
                ".coordinates", ".lat-lng", "[data-lat]", ".location-coords"
            ]
            
            for selector in coord_selectors:
                try:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if element:
                        # Extract latitude and longitude
                        lat_attr = element.get_attribute("data-lat")
                        lng_attr = element.get_attribute("data-lng")
                        
                        if lat_attr and lng_attr:
                            coordinates["latitude"] = float(lat_attr)
                            coordinates["longitude"] = float(lng_attr)
                            coordinates["decimal"] = f"{lat_attr},{lng_attr}"
                            break
                        
                        # Try text parsing
                        coord_text = element.text.strip()
                        if coord_text:
                            # Parse coordinate text (various formats)
                            coord_match = re.search(r'(-?\d+\.?\d*),\s*(-?\d+\.?\d*)', coord_text)
                            if coord_match:
                                coordinates["latitude"] = float(coord_match.group(1))
                                coordinates["longitude"] = float(coord_match.group(2))
                                coordinates["decimal"] = coord_text
                                break
                                
                except (NoSuchElementException, ValueError):
                    continue
            
            return coordinates if coordinates else None
            
        except Exception as e:
            logger.warning(f"⚠️  Error extracting coordinates: {e}")
            return None

    def _extract_port_details_optimized(self) -> Optional[Dict]:
        """Enhanced port details extraction"""
        try:
            details = {}
            
            # Extract various port details
            detail_fields = {
                "region": [".region", "[data-field='region']"],
                "max_vessel_size": [".max-vessel", "[data-field='max_vessel']"],
                "draft": [".draft", "[data-field='draft']"],
                "facilities": [".facilities", "[data-field='facilities']"]
            }
            
            for field, selectors in detail_fields.items():
                for selector in selectors:
                    try:
                        element = self.driver.find_element(By.CSS_SELECTOR, selector)
                        if element and element.text.strip():
                            details[field] = element.text.strip()
                            break
                    except NoSuchElementException:
                        continue
            
            return details if details else None
            
        except Exception as e:
            logger.warning(f"⚠️  Error extracting port details: {e}")
            return None

    def _extract_shipping_lines_optimized(self) -> Optional[List[str]]:
        """Enhanced shipping lines extraction"""
        try:
            shipping_lines = []
            
            # Try multiple selectors for shipping lines
            line_selectors = [
                ".shipping-line", ".carrier", "[data-field='shipping_lines'] li"
            ]
            
            for selector in line_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        line_name = element.text.strip()
                        if line_name and line_name not in shipping_lines:
                            shipping_lines.append(line_name)
                except NoSuchElementException:
                    continue
            
            return shipping_lines if shipping_lines else None
            
        except Exception as e:
            logger.warning(f"⚠️  Error extracting shipping lines: {e}")
            return None

    def _store_port_data_optimized(self, port_data: Dict):
        """Enhanced port data storage with better error handling"""
        try:
            # Store in detailed ports collection with upsert
            detailed_ports_collection.update_one(
                {
                    "country_code": port_data["country_code"],
                    "port_name": port_data["port_name"]
                },
                {"$set": port_data},
                upsert=True
            )
            
        except Exception as e:
            logger.error(f"❌ Error storing port data: {e}")

    def _is_country_processed(self, country_code: str) -> bool:
        """Check if country has already been processed"""
        try:
            count = detailed_ports_collection.count_documents({"country_code": country_code})
            return count > 0
        except Exception as e:
            logger.warning(f"⚠️  Error checking if country processed: {e}")
            return False

    def stop(self):
        """Enhanced stop method with immediate state synchronization"""
        logger.info(f"Stop requested for port scraper {self.scraper_id}")
        self.should_stop = True
        self.interrupted = True
        self.state_synchronizer.update_scraper_state(self.scraper_id, ScraperState.STOPPING)

    def _cleanup_optimized(self):
        """Enhanced cleanup with state synchronization"""
        logger.info("Starting enhanced port scraper cleanup...")
        
        try:
            # Update state to stopped
            self.state_synchronizer.update_scraper_state(self.scraper_id, ScraperState.STOPPED)
            
            # Close browser
            if self.driver:
                try:
                    self.driver.quit()
                    logger.info("✅ Browser closed successfully")
                except Exception as e:
                    logger.error(f"Error closing browser: {e}")
            
            # Kill Chrome processes
            kill_chrome_processes()
            
            # Remove from global registry
            with _scrapers_lock:
                _active_scrapers.pop(self.task_id, None)
            
            logger.info("Enhanced port scraper cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def get_performance_stats(self) -> Dict:
        """Enhanced performance statistics"""
        with self.stats_lock:
            base_stats = self.stats.copy()
        
        # Get optimizer stats
        optimizer_stats = self.performance_optimizer.get_performance_stats()
        
        # Get state info
        state_info = self.state_synchronizer.get_scraper_status(self.scraper_id)
        
        return {
            'scraper_id': self.scraper_id,
            'scraper_stats': base_stats,
            'optimizer_stats': optimizer_stats,
            'state_info': state_info.to_dict() if state_info else None,
            'is_running': self.running,
            'should_stop': self.should_stop
        }


def ScrapePortsStartFresh(headless: bool = True, countries_limit: Optional[int] = None, task_id: Optional[str] = None) -> Dict:
    """
    Start fresh port scraping - scrape all countries from the beginning.
    Skip countries that already exist.
    
    Args:
        headless: Run browser in headless mode
        countries_limit: Limit number of countries to scrape (None = all)
        task_id: Optional task ID for tracking (used by Celery)
        
    Returns:
        Dict with scraping statistics
    """
    logger.info("=" * 80)
    logger.info("STARTING FRESH PORT SCRAPING")
    logger.info("=" * 80)
    logger.info("💡 Press Ctrl+C to stop gracefully at any time")
    logger.info("=" * 80)
    
    scraper = PortScraper(headless=headless, task_id=task_id)
    
    try:
        stats = scraper.scrape_countries_in_order(
            start_from_country=None,
            skip_existing=True,
            countries_limit=countries_limit
        )
        return stats
    except KeyboardInterrupt:
        logger.warning("\n⚠️  Scraping interrupted by user")
        logger.info("✅ Data saved up to interruption point")
        return {"status": "interrupted", "message": "Scraping stopped by user"}
    except Exception as e:
        logger.error(f"Error in ScrapePortsStartFresh: {e}")
        logger.exception("Full traceback:")
        return {"error": str(e)}
    finally:
        logger.info("🔄 Closing browser and cleaning up...")
        scraper.close()
        logger.info("✅ Cleanup complete")


def ScrapePortsResumeFrom(start_country: str, headless: bool = True, countries_limit: Optional[int] = None, task_id: Optional[str] = None) -> Dict:
    """
    Resume port scraping from a specific country.
    
    Args:
        start_country: Country code or name to start from
        headless: Run browser in headless mode
        countries_limit: Limit number of countries to scrape (None = all)
        task_id: Optional task ID for tracking (used by Celery)
        
    Returns:
        Dict with scraping statistics
    """
    logger.info("=" * 80)
    logger.info(f"RESUMING PORT SCRAPING FROM: {start_country}")
    logger.info("=" * 80)
    logger.info("💡 Press Ctrl+C to stop gracefully at any time")
    logger.info("=" * 80)
    
    scraper = PortScraper(headless=headless, task_id=task_id)
    
    try:
        stats = scraper.scrape_countries_in_order(
            start_from_country=start_country,
            skip_existing=True,
            countries_limit=countries_limit
        )
        return stats
    except KeyboardInterrupt:
        logger.warning("\n⚠️  Scraping interrupted by user")
        logger.info("✅ Data saved up to interruption point")
        return {"status": "interrupted", "message": "Scraping stopped by user"}
    except Exception as e:
        logger.error(f"Error in ScrapePortsResumeFrom: {e}")
        logger.exception("Full traceback:")
        return {"error": str(e)}
    finally:
        logger.info("🔄 Closing browser and cleaning up...")
        scraper.close()
        logger.info("✅ Cleanup complete")


def ScrapePortsUpdateExisting(start_country: Optional[str] = None, headless: bool = True, countries_limit: Optional[int] = None, task_id: Optional[str] = None) -> Dict:
    """
    Update existing ports - re-scrape countries that already exist.
    
    Args:
        start_country: Country code or name to start from (None = start from beginning)
        headless: Run browser in headless mode
        countries_limit: Limit number of countries to scrape (None = all)
        task_id: Optional task ID for tracking (used by Celery)
        
    Returns:
        Dict with scraping statistics
    """
    logger.info("=" * 80)
    logger.info("UPDATING EXISTING PORTS")
    logger.info("=" * 80)
    logger.info("💡 Press Ctrl+C to stop gracefully at any time")
    logger.info("=" * 80)
    
    scraper = PortScraper(headless=headless, task_id=task_id)
    
    try:
        stats = scraper.scrape_countries_in_order(
            start_from_country=start_country,
            skip_existing=False,  # Don't skip existing
            countries_limit=countries_limit
        )
        return stats
    except KeyboardInterrupt:
        logger.warning("\n⚠️  Scraping interrupted by user")
        logger.info("✅ Data saved up to interruption point")
        return {"status": "interrupted", "message": "Scraping stopped by user"}
    except Exception as e:
        logger.error(f"Error in ScrapePortsUpdateExisting: {e}")
        logger.exception("Full traceback:")
        return {"error": str(e)}
    finally:
        logger.info("🔄 Closing browser and cleaning up...")
        scraper.close()
        logger.info("✅ Cleanup complete")


def GetPortStatistics() -> Optional[Dict]:
    """
    Get current port scraping statistics.
    
    Returns:
        Dict with statistics or None if error
    """
    scraper = PortScraper(headless=True)
    try:
        return scraper.get_scraping_statistics()
    except Exception as e:
        logger.error(f"Error in GetPortStatistics: {e}")
        return None
    finally:
        scraper.close()


def StopPortScraperByTaskId(task_id: str) -> bool:
    """
    Stop a running port scraper by task ID.
    
    Args:
        task_id: The task ID of the scraper to stop
        
    Returns:
        True if scraper was found and stopped, False otherwise
    """
    with _scrapers_lock:
        if task_id in _active_scrapers:
            scraper = _active_scrapers[task_id]
            scraper.stop()
            logger.info(f"Stop signal sent to port scraper {task_id}")
            return True
        else:
            logger.warning(f"No active port scraper found with task_id: {task_id}")
            return False


def GetActiveScrapers() -> List[str]:
    """
    Get list of active scraper task IDs.
    
    Returns:
        List of task IDs for currently active scrapers
    """
    with _scrapers_lock:
        return list(_active_scrapers.keys())


if __name__ == "__main__":
    # Test with limited run
    try:
        logger.info("Testing port scraper with 2 countries...")
        logger.info("💡 Press Ctrl+C to stop at any time")
        stats = ScrapePortsStartFresh(headless=True, countries_limit=2)
        logger.info(f"Test completed: {stats}")
    except KeyboardInterrupt:
        logger.warning("\n⚠️  Test interrupted by user")
    except Exception as e:
        logger.error(f"Test failed: {e}")
        logger.exception("Full traceback:")

