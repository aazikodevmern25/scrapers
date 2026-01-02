"""
Indiamart Product Scraper - MongoDB Integrated
Scrapes product and seller data from Indiamart URLs stored in MongoDB
Follows the same format as the original scraper with start/stop controls
"""
import time
import requests
import json
import sys
import signal
import threading
import random
import os
import uuid
import logging
from typing import Optional, Dict, List
from scrapy import Selector
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from .indiamart_mongodb import IndiamartMongoDB
from utils import get_proxies, SendGetRequests

# Configure logging
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"indiamart_product_scraper_{datetime.now().strftime('%Y%m%d')}.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('indiamart_product_scraper')

# Global registry for active scrapers
_active_scrapers = {}
_scrapers_lock = threading.Lock()


def kill_scraper_processes():
    """Kill any hanging scraper processes"""
    try:
        import psutil
        current_process = psutil.Process()
        for child in current_process.children(recursive=True):
            try:
                child.kill()
            except:
                pass
    except:
        pass


class ProductScraperConfig:
    """Configuration for product scraper"""
    max_workers: int = 10
    batch_size: int = 100
    request_timeout: int = 30
    max_retries: int = 3
    rate_limit_delay: float = 0.1


class IndiamartProductScraperV2:
    """
    Product scraper that reads URLs from MongoDB and saves scraped data back
    Follows the original scraper format with enhanced MongoDB integration
    """
    
    def __init__(self, task_id: str = None, config: ProductScraperConfig = None):
        self.task_id = task_id or f"product_scraper_{int(time.time())}"
        self.config = config or ProductScraperConfig()
        self.db = IndiamartMongoDB()
        
        # Control flags
        self.interrupted = False
        self.running = False
        self.celery_task = None
        
        # Statistics
        self.stats = {
            'start_time': None,
            'total_urls': 0,
            'processed_urls': 0,
            'successful_urls': 0,
            'failed_urls': 0,
            'products_scraped': 0,
            'sellers_scraped': 0,
            'errors': 0
        }
        self.stats_lock = threading.Lock()
        
        # Register signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Register in global registry
        with _scrapers_lock:
            _active_scrapers[self.task_id] = self
        
        logger.info(f"IndiaMART Product Scraper V2 initialized (task_id: {self.task_id})")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        sig_name = 'SIGTERM' if signum == signal.SIGTERM else 'SIGINT'
        logger.warning(f"Received {sig_name}, stopping scraper...")
        self.stop()
        
        if signum == signal.SIGTERM:
            kill_scraper_processes()
            sys.exit(0)
        else:
            kill_scraper_processes()
            sys.exit(1)
    
    def _check_task_revoked(self):
        """Check if Celery task has been revoked"""
        if self.celery_task and hasattr(self.celery_task, 'request'):
            try:
                task_id = self.celery_task.request.id
                if not task_id:
                    self.interrupted = True
                    logger.warning("Task ID is None, stopping scraper")
            except Exception as e:
                logger.debug(f"Error checking task status: {e}")
                self.interrupted = True
    
    def _update_stats(self, **kwargs):
        """Thread-safe stats update"""
        with self.stats_lock:
            for key, value in kwargs.items():
                if key in self.stats:
                    self.stats[key] += value
    
    def _get_headers(self) -> Dict:
        """Get request headers"""
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        ]
        return {
            'User-Agent': random.choice(user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    
    def _get_categories(self, raw_js: Dict) -> Dict:
        """Extract category information from JSON data"""
        cats = {}
        try:
            data = raw_js['props']['pageProps']['serviceRes']['Data'][0]
            cats['mainCategory'] = data.get('BRD_CAT_NAME', '')
            
            if data.get('PARENT_MCAT'):
                cats['subCategory'] = data['PARENT_MCAT'].get('GLCAT_MCAT_NAME', '')
            else:
                cats['subCategory'] = data.get('BRD_MCAT_NAME', '')
            
            cats['childCategory'] = data.get('BRD_MCAT_NAME', '')
        except Exception as e:
            logger.error(f"Error extracting categories: {e}")
            cats = {'mainCategory': '', 'subCategory': '', 'childCategory': ''}
        return cats
    
    def _get_company_details(self, resp: Selector, raw_js: Dict) -> Dict:
        """Extract company details from response"""
        company_details = {}
        try:
            data = raw_js['props']['pageProps']['serviceRes']['Data'][0]
            
            # Basic information
            for sr in data.get('Basic_Information', []):
                if sr.get('TITLE') == '':
                    company_details['owner'] = sr.get('DATA', '')
                elif isinstance(sr.get('TITLE'), list):
                    company_details[str(sr['TITLE'])] = ','.join(sr.get('DATA', []))
                else:
                    company_details[sr.get('TITLE', '')] = sr.get('DATA', '')
            
            # Statutory profile
            for sr in data.get('Statutory_Profile', []):
                company_details[sr.get('TITLE', '')] = sr.get('DATA', '')
            
            # Export countries
            export_countries = [x.get('name', '') for x in data.get('TOP_EXPORT_COUNTRIES', [])]
            company_details['exportCountries'] = ','.join(export_countries)
            
            # Location details
            company_details['city'] = data.get('CITY', '')
            company_details['latitude'] = data.get('GLUSR_USR_LATITUDE', '')
            company_details['longitude'] = data.get('GLUSR_USR_LONGITUDE', '')
            company_details['memberSince'] = data.get('GLUSR_USR_MEMBERSINCE', '')
            company_details['zipcode'] = data.get('GLUSR_USR_ZIP', '')
            company_details['companyType'] = data.get('GL_LEGAL_STATUS_VAL', '')
            company_details['locality'] = data.get('LOCALITY', '')
            company_details['mobile'] = data.get('MOBILE_PNS')
            
            # Rating parameters
            rating_params = data.get('RATING_INFLU_PARAM')
            if rating_params:
                company_details['response'] = rating_params.get('Response', '').split(',')[0] if rating_params.get('Response') else None
                company_details['delivery'] = rating_params.get('Delivery', '').split(',')[0] if rating_params.get('Delivery') else None
                company_details['quality'] = rating_params.get('Quality', '').split(',')[0] if rating_params.get('Quality') else None
            else:
                company_details['response'] = None
                company_details['delivery'] = None
                company_details['quality'] = None
            
            # Additional details from HTML
            company_details['trustSEAL'] = resp.xpath('//div/span[contains(text(),"TrustSEAL")]/text()').get()
            company_details['exporter'] = resp.xpath('//div/span[contains(text(),"Verified Exporter")]/text()').get()
            company_details['type'] = resp.xpath('//div/span[contains(text(),"Manufacturer")]/text()').get()
            company_details['responseRate'] = ''.join(resp.xpath('//div[contains(@class,"View_Mobile_Number")]/div/span[last()]//text()').getall())
            
        except Exception as e:
            logger.error(f"Error extracting company details: {e}")
        
        return company_details
    
    def _get_product_details(self, resp: Selector, raw_js: Dict) -> Dict:
        """Extract product details from response"""
        product_details = {}
        try:
            data = raw_js['props']['pageProps']['serviceRes']['Data'][0]
            
            for sr in data.get('ISQ', []):
                if sr.get('FK_IM_SPEC_MASTER_DESC'):
                    product_details[sr['FK_IM_SPEC_MASTER_DESC']] = sr.get('SUPPLIER_RESPONSE_DETAIL', '')
            
            product_details['price'] = ''.join(resp.xpath('//span[contains(@class,"price-")]/text()').getall())
            product_details['unit'] = resp.xpath('//span[contains(@class,"units")]/text()').get()
            
        except Exception as e:
            logger.error(f"Error extracting product details: {e}")
        
        return product_details
    
    def _get_video_and_images(self, raw_js: Dict) -> tuple:
        """Extract video and image URLs"""
        videos = []
        images = []
        try:
            data = raw_js['props']['pageProps']['serviceRes']['Data'][0]
            videos = [x.get('MCAT_VIDEO', '') for x in data.get('BRD_PRIME_MCAT_VIDEO_URLS', [])]
            images = [x.get('IMAGE_ORIGINAL', '') for x in data.get('0', [])]
        except:
            pass
        return videos, images
    
    def _get_seller_address(self, raw_js: Dict) -> Dict:
        """Extract seller address"""
        address = {}
        try:
            data = raw_js['props']['pageProps']['serviceRes']['Data'][0]
            address['addressLine1'] = data.get('ADDRESS', '')
            address['state'] = data.get('GLUSR_USR_STATE', '')
            address['country'] = 'India'
            address['city'] = data.get('CITY', '')
            address['pincode'] = data.get('GLUSR_USR_ZIP', '')
        except Exception as e:
            logger.error(f"Error extracting seller address: {e}")
        return address
    
    def _scrape_product(self, url_data: Dict) -> bool:
        """Scrape a single product URL"""
        product_url = url_data.get('product_url', '')
        
        if not product_url:
            return False
        
        try:
            # Make request
            headers = self._get_headers()
            response = SendGetRequests(product_url, headers, use_proxy=True, max_403_retries=2)
            
            if not response or response.status_code != 200:
                status = response.status_code if response else 'None'
                logger.warning(f"Failed to fetch {product_url}: Status {status}")
                return False
            
            logger.info(f"Fetched: {product_url[:60]}... Status: {response.status_code}")
            
            resp = Selector(text=response.text)
            
            # Extract JSON data
            raw_js_text = resp.xpath('//script[@id="__NEXT_DATA__"]/text()').get()
            if not raw_js_text:
                logger.warning(f"No JSON data found for {product_url}")
                return False
            
            raw_js = json.loads(raw_js_text)
            data = raw_js['props']['pageProps']['serviceRes']['Data'][0]
            
            # Extract basic info
            phone = data.get('MOBILE_PNS')
            rating = data.get('SELLER_RATING_COUNTS', {}).get('avg_rating')
            reviews = data.get('SELLER_RATING_COUNTS', {}).get('total_count')
            
            # Extract GST - try multiple methods
            gst = resp.xpath('//div/span[contains(text(),"GST") and not(contains(text(),"GST Registration Date"))]/following-sibling::span/text()').get()
            
            # Build company details first to check for GST there
            company_details = self._get_company_details(resp, raw_js)
            
            # If GST not found in HTML, try company_details
            if not gst:
                gst = company_details.get('GST No.') or company_details.get('GST Number') or company_details.get('GST No')
            
            # Extract seller name - try multiple methods
            seller_name = resp.xpath('//div[@id="supp_nm"]/text()').get()
            if not seller_name:
                # Try alternative selectors
                seller_name = resp.xpath('//span[@itemprop="name"]/text()').get()
            if not seller_name:
                # Try from JSON data
                seller_name = data.get('GLUSR_USR_NAME') or data.get('CONTACT_PERSON_NAME')
            if not seller_name:
                # Try from company_details after building it
                seller_name = company_details.get('owner') or company_details.get('Company CEO')
            
            # If still no seller_name, use company_name as fallback
            company_name = resp.xpath('//a/h2/text()').get()
            if not seller_name and company_name:
                seller_name = company_name
            
            # Extract company address - try multiple methods
            company_address = ' '.join(resp.xpath('//div[@id="directions"]/p//text()').getall()).strip()
            if not company_address:
                # Try from JSON data
                company_address = data.get('ADDRESS', '')
            
            # Build full address from seller_address if company_address is empty
            if not company_address:
                seller_addr = self._get_seller_address(raw_js)
                address_parts = [
                    seller_addr.get('addressLine1', ''),
                    seller_addr.get('city', ''),
                    seller_addr.get('state', ''),
                    seller_addr.get('pincode', ''),
                    seller_addr.get('country', '')
                ]
                company_address = ', '.join([p for p in address_parts if p]).strip()
            
            # Build seller data
            seller_data = {
                'seller_name': seller_name,
                'company_name': company_name,
                'company_address': company_address,
                'company_description': data.get('GLUSR_USR_DESC', ''),
                'company_website_link': resp.xpath('(//h3[contains(text(),"Seller Contact Details")]/following-sibling::div//a[contains(@href,"https") and not(contains(@href,"google"))]/@href)[last()]').get(),
                'company_details': company_details,
                'company_video_url': '',
                'hsn_codes': '',
                'company_images': data.get('GLUSR_USR_LOGO_IMG', ''),
                'why_us': data.get('GLUSR_USR_DESC', ''),
                'rating': rating,
                'Testimonial': data.get('TESTIMONIAL_URL', ''),
                'brochure_link': '',
                'gst': gst,
                'scraped_at': datetime.now(),
                'scraper_id': self.task_id
            }
            
            # Store seller if GST is available
            if gst:
                self._store_seller(gst, seller_data)
                logger.info(f"✓ Seller data prepared for GST: {gst}")
            else:
                logger.debug(f"No GST found for product: {product_url[:60]}...")
            
            # Get videos and images
            videos, images = self._get_video_and_images(raw_js)
            
            # Build product data
            product_data = {
                'product_url': product_url,
                'product_main_img_url': resp.xpath('//img[@id="img_id"]/@src').get(),
                'product_img_url': images,
                'product_video_url': videos,
                'product_name': resp.xpath('//h1/text()').get(),
                'seller_name': seller_data['seller_name'],
                'full_address': seller_data['company_address'],
                'seller_address': self._get_seller_address(raw_js),
                'company_name': seller_data['company_name'],
                'company_website_link': seller_data['company_website_link'],
                'product_description': data.get('PC_ITEM_DESC_SMALL', ''),
                'company_details': seller_data['company_details'],
                'product_details': self._get_product_details(resp, raw_js),
                'contact_details': {
                    'GST_No': gst,
                    'company_name': seller_data['company_name'],
                    'address_element': seller_data['company_address'],
                    'phone_element': phone,
                    'rating': rating,
                    'Reviews_from_the_web': reviews
                },
                'category': url_data.get('category', ''),
                'subcategory': url_data.get('subcategory', ''),
                'categoryTree': self._get_categories(raw_js),
                'product_main_img_name': '',
                'product_img_name': [],
                'scraped_at': datetime.now(),
                'scraper_id': self.task_id
            }
            
            # Store product
            self._store_product(product_url, product_data)
            
            self._update_stats(products_scraped=1)
            logger.info(f"✓ Scraped product: {product_data.get('product_name', 'Unknown')[:50]}")
            
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for {product_url}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error scraping {product_url}: {e}")
            return False
    
    def _store_seller(self, gst: str, seller_data: Dict):
        """Store seller data in MongoDB"""
        try:
            # Validate GST
            if not gst or gst.strip() == '':
                logger.debug("Skipping seller storage - no valid GST")
                return
            
            gst = gst.strip()
            
            # Check if seller already exists
            existing = self.db.scraped_sellers_collection.find_one({'gst': gst})
            if not existing:
                doc = {
                    'gst': gst,
                    'data': seller_data,
                    'created_at': datetime.now(),
                    '__v': 0
                }
                self.db.scraped_sellers_collection.insert_one(doc)
                self._update_stats(sellers_scraped=1)
                logger.info(f"✓ Stored new seller: {seller_data.get('company_name', 'Unknown')[:30]} (GST: {gst})")
            else:
                logger.debug(f"Seller already exists for GST: {gst}")
        except Exception as e:
            logger.error(f"Error storing seller: {e}")
    
    def _store_product(self, product_url: str, product_data: Dict):
        """Store product data in MongoDB"""
        try:
            # Use upsert to avoid duplicates
            self.db.scraped_products_collection.update_one(
                {'product_url': product_url},
                {'$set': product_data, '$setOnInsert': {'created_at': datetime.now(), '__v': 0}},
                upsert=True
            )
            
            # Mark URL as scraped
            self.db.mark_urls_scraped_batch([(product_url, True, "")])
            
        except Exception as e:
            logger.error(f"Error storing product: {e}")
    
    def _process_batch(self, urls: List[Dict]):
        """Process a batch of URLs"""
        if not urls:
            return
        
        logger.info(f"Processing batch of {len(urls)} URLs")
        
        for idx, url_data in enumerate(urls):
            if self.interrupted:
                logger.info("Scraper interrupted, stopping batch processing")
                break
            
            self._check_task_revoked()
            if self.interrupted:
                break
            
            success = self._scrape_product(url_data)
            
            if success:
                self._update_stats(successful_urls=1)
            else:
                self._update_stats(failed_urls=1)
                # Mark as failed
                product_url = url_data.get('product_url', '')
                if product_url:
                    self.db.mark_urls_scraped_batch([(product_url, False, "Scraping failed")])
            
            self._update_stats(processed_urls=1)
            
            # Rate limiting
            time.sleep(self.config.rate_limit_delay)
            
            # Log progress every 10 URLs
            if (idx + 1) % 10 == 0:
                self._log_progress()
    
    def _log_progress(self):
        """Log current progress"""
        with self.stats_lock:
            processed = self.stats['processed_urls']
            total = self.stats['total_urls']
            success = self.stats['successful_urls']
            products = self.stats['products_scraped']
            sellers = self.stats['sellers_scraped']
        
        if total > 0:
            progress = (processed / total) * 100
            logger.info(
                f"Progress: {progress:.1f}% ({processed}/{total}) | "
                f"Success: {success} | Products: {products} | Sellers: {sellers}"
            )
    
    def run(self):
        """Main execution method"""
        try:
            self.running = True
            self.interrupted = False
            self.stats['start_time'] = datetime.now()
            
            logger.info("=" * 60)
            logger.info("Starting IndiaMART Product Scraper V2")
            logger.info("=" * 60)
            
            # Get pending URLs from MongoDB
            urls = self.db.get_pending_urls(limit=10000)
            
            if not urls:
                logger.warning("No pending URLs found to scrape")
                return {'status': 'no_urls', 'message': 'No pending URLs found'}
            
            self.stats['total_urls'] = len(urls)
            logger.info(f"Found {len(urls)} pending URLs to scrape")
            
            # Process in batches
            batch_size = self.config.batch_size
            
            for i in range(0, len(urls), batch_size):
                if self.interrupted:
                    logger.info("Scraper interrupted, stopping")
                    break
                
                batch = urls[i:i + batch_size]
                batch_num = i // batch_size + 1
                total_batches = (len(urls) + batch_size - 1) // batch_size
                
                logger.info(f"Processing batch {batch_num}/{total_batches}")
                
                # Use ThreadPoolExecutor for parallel processing
                with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
                    futures = []
                    for url_data in batch:
                        if self.interrupted:
                            break
                        futures.append(executor.submit(self._scrape_product, url_data))
                    
                    # Wait for all futures and collect results
                    for future, url_data in zip(futures, batch):
                        if self.interrupted:
                            break
                        try:
                            success = future.result(timeout=self.config.request_timeout * 2)
                            if success:
                                self._update_stats(successful_urls=1)
                            else:
                                self._update_stats(failed_urls=1)
                                product_url = url_data.get('product_url', '')
                                if product_url:
                                    self.db.mark_urls_scraped_batch([(product_url, False, "Scraping failed")])
                        except Exception as e:
                            logger.error(f"Future error: {e}")
                            self._update_stats(failed_urls=1)
                        
                        self._update_stats(processed_urls=1)
                
                self._log_progress()
            
            # Final stats
            logger.info("=" * 60)
            logger.info("Scraping completed!")
            self._log_progress()
            logger.info("=" * 60)
            
            return {
                'status': 'success',
                'stats': self.stats.copy()
            }
            
        except Exception as e:
            logger.error(f"Error in scraper: {e}")
            return {'status': 'error', 'message': str(e)}
        finally:
            self.running = False
            self.close()
    
    def stop(self):
        """Stop the scraper gracefully"""
        logger.info(f"Stopping scraper (task_id: {self.task_id})...")
        self.interrupted = True
    
    def close(self):
        """Cleanup resources"""
        logger.info(f"Cleaning up scraper (task_id: {self.task_id})")
        
        # Flush any pending database operations
        try:
            self.db.force_flush_buffers()
        except:
            pass
        
        # Unregister from global registry
        with _scrapers_lock:
            _active_scrapers.pop(self.task_id, None)
        
        logger.info("Cleanup completed")
    
    def get_stats(self) -> Dict:
        """Get current statistics"""
        with self.stats_lock:
            return self.stats.copy()


# Convenience function for Celery task
def ScrapeIndiamartProducts(task_id: str = None, max_workers: int = 10, batch_size: int = 100):
    """
    Convenience function to run the product scraper
    
    Args:
        task_id: Optional task ID for tracking
        max_workers: Number of concurrent workers
        batch_size: Number of URLs per batch
    
    Returns:
        dict: Scraping results and statistics
    """
    config = ProductScraperConfig()
    config.max_workers = max_workers
    config.batch_size = batch_size
    
    scraper = IndiamartProductScraperV2(task_id=task_id, config=config)
    return scraper.run()


# For running directly
if __name__ == '__main__':
    result = ScrapeIndiamartProducts(max_workers=5, batch_size=50)
    print(f"Result: {result}")
