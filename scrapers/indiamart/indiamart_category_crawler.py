"""
Indiamart Category Crawler - Integrated with Celery Task Queue
Crawls categories from Indiamart and generates product URLs for scraping
"""
import os
import requests
import pandas as pd
import json
import sys
import signal
import threading
import time
import logging
import asyncio
import aiohttp
import queue
import ssl
from contextlib import asynccontextmanager
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from scrapy import Selector
from pathlib import Path
from datetime import datetime
from .indiamart_mongodb import IndiamartMongoDB
from celery.exceptions import TaskRevokedError
from utils import get_proxies
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import random

# Import performance optimization modules
from celery_app.performance_optimizer import PerformanceOptimizer
from celery_app.state_synchronizer import StateSynchronizer

# Configure logging
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"indiamart_category_crawler_{datetime.now().strftime('%Y%m%d')}.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('indiamart_category_crawler')

# Global registry for active crawlers
_active_crawlers = {}
_crawlers_lock = threading.Lock()

@dataclass
class CrawlerConfig:
    """Configuration for the category crawler - Optimized for huge data and speed"""
    # ADJUST THESE VALUES BASED ON YOUR NEEDS:
    # - For maximum speed (powerful hardware): 200 workers, 400 requests
    # - For balanced performance (current): 150 workers, 300 requests  
    # - For reliability (slower): 50 workers, 100 requests
    
    max_workers: int = 150  # ← CHANGE THIS: Number of concurrent category processors
    max_concurrent_requests: int = 300  # ← CHANGE THIS: HTTP requests at once
    batch_size: int = 1000  # ← CHANGE THIS: Categories per batch
    request_timeout: int = 8  # Reduced for faster failures and retries
    connection_pool_size: int = 500  # Increased for more concurrent connections
    max_retries: int = 5  # Increased for better reliability with 403 errors
    backoff_factor: float = 0.05  # Reduced for faster retries
    rate_limit_delay: float = 0.0005  # Minimal delay for maximum speed
    cache_ttl: int = 3600
    enable_compression: bool = True
    use_session_pool: bool = True
    async_enabled: bool = True
    max_concurrent_pages: int = 30  # ← CHANGE THIS: Pages per category concurrently
    semaphore_limit: int = 250  # ← CHANGE THIS: Overall concurrency control
    
    # Performance optimization parameters
    enable_performance_optimizer: bool = True
    enable_state_synchronizer: bool = True
    memory_threshold_mb: int = 2048  # Increased for handling huge data
    gc_frequency: int = 200  # Less frequent GC for speed
    cache_size: int = 20000  # Increased cache for huge data
    burst_limit: int = 100  # Increased burst for speed
    rate_window: int = 60

class ConnectionManager:
    """Manages HTTP connections with pooling and proxy support"""
    
    def __init__(self, config: CrawlerConfig):
        self.config = config
        self.session_pool = queue.Queue(maxsize=config.connection_pool_size)
        self.async_session = None
        self._initialize_sessions()
    
    def _initialize_sessions(self):
        """Initialize session pool"""
        # Initialize sync sessions
        for _ in range(self.config.connection_pool_size):
            session = self._create_new_session()
            self.session_pool.put(session)
    
    def _get_random_user_agent(self) -> str:
        """Get random user agent for better anonymity"""
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0'
        ]
        return random.choice(user_agents)
    
    @asynccontextmanager
    async def get_async_session(self):
        """Get async session with optimized connection pooling and proxy support"""
        if not self.async_session:
            # Get proxy configuration
            try:
                auth, proxy_dict = get_proxies()
                proxy_url = None
                
                if proxy_dict and 'http' in proxy_dict:
                    proxy_url = proxy_dict['http']
                    if auth:
                        proxy_url = proxy_url.replace('http://', f'http://{auth[0]}:{auth[1]}@')
                
                # Create optimized connector with increased limits
                connector = aiohttp.TCPConnector(
                    limit=self.config.connection_pool_size * 2,  # Increased total connections
                    limit_per_host=self.config.max_concurrent_requests,  # Increased per-host connections
                    ttl_dns_cache=300,  # DNS cache for 5 minutes
                    use_dns_cache=True,
                    keepalive_timeout=60,  # Keep connections alive longer
                    enable_cleanup_closed=True,
                    force_close=False,  # Reuse connections
                    ssl=False  # Disable SSL verification for speed (if acceptable)
                )
                
                # Optimized timeout settings
                timeout = aiohttp.ClientTimeout(
                    total=self.config.request_timeout,
                    connect=5,  # Fast connection timeout
                    sock_read=self.config.request_timeout
                )
                
                # Create session with optimized settings
                self.async_session = aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout,
                    headers={
                        'User-Agent': self._get_random_user_agent(),
                        'Accept-Encoding': 'gzip, deflate, br',
                        'Connection': 'keep-alive',
                        'Cache-Control': 'no-cache'
                    },
                    trust_env=True,
                    auto_decompress=True  # Automatic decompression
                )
                
            except Exception as e:
                logger.warning(f"Failed to setup proxy: {e}")
                # Fallback to direct connection with optimized settings
                connector = aiohttp.TCPConnector(
                    limit=self.config.connection_pool_size * 2,
                    limit_per_host=self.config.max_concurrent_requests,
                    ttl_dns_cache=300,
                    use_dns_cache=True,
                    keepalive_timeout=60,
                    enable_cleanup_closed=True,
                    force_close=False,
                    ssl=False
                )
                
                timeout = aiohttp.ClientTimeout(
                    total=self.config.request_timeout,
                    connect=5,
                    sock_read=self.config.request_timeout
                )
                
                self.async_session = aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout,
                    headers={
                        'User-Agent': self._get_random_user_agent(),
                        'Accept-Encoding': 'gzip, deflate, br',
                        'Connection': 'keep-alive'
                    },
                    auto_decompress=True
                )
        
        yield self.async_session
    
    def get_session(self):
        """Get session from pool"""
        try:
            return self.session_pool.get_nowait()
        except queue.Empty:
            return self._create_new_session()
    
    def return_session(self, session):
        """Return session to pool"""
        try:
            self.session_pool.put_nowait(session)
        except queue.Full:
            session.close()
    
    def _create_new_session(self):
        """Create new session with optimized settings"""
        session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=self.config.max_retries,
            backoff_factor=self.config.backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        
        # Configure adapters
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=20,
            pool_maxsize=50,
            pool_block=False
        )
        
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Set headers
        session.headers.update({
            'User-Agent': self._get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate' if self.config.enable_compression else 'identity',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
        # Add proxy configuration
        try:
            auth, proxy_dict = get_proxies()
            if proxy_dict:
                session.proxies.update(proxy_dict)
                if auth:
                    session.auth = auth
        except Exception as e:
            logger.warning(f"Failed to configure proxy for session: {e}")
        
        return session
    
    async def close_async_session(self):
        """Close async session"""
        if self.async_session:
            await self.async_session.close()
            self.async_session = None


def kill_crawler_processes():
    """Kill any hanging crawler processes"""
    import psutil
    current_process = psutil.Process()
    try:
        for child in current_process.children(recursive=True):
            try:
                child.kill()
            except:
                pass
    except:
        pass


class IndiamartCategoryCrawler:
    """
    Optimized Crawler for Indiamart categories to generate product URLs with async support
    """
    
    def __init__(self, task_id=None):
        self.task_id = task_id or f"crawler_{int(time.time())}"
        self.config = CrawlerConfig()
        self.connection_manager = ConnectionManager(self.config)
        self.db = IndiamartMongoDB()
        self.interrupted = False
        self.pages_per_category = 0  # 0 means unlimited
        self.celery_task = None  # Store reference to Celery task for revocation checking
        
        # Initialize performance optimizer
        if self.config.enable_performance_optimizer:
            from celery_app.performance_optimizer import PerformanceOptimizer, PerformanceConfig
            perf_config = PerformanceConfig(
                max_workers=self.config.max_workers,
                max_concurrent_requests=self.config.max_concurrent_requests,
                batch_size=self.config.batch_size,
                connection_timeout=10,
                read_timeout=self.config.request_timeout,
                rate_limit_delay=self.config.rate_limit_delay,
                cache_ttl=self.config.cache_ttl,
                connection_pool_size=self.config.connection_pool_size,
                max_retries=self.config.max_retries,
                backoff_factor=self.config.backoff_factor,
                memory_threshold=self.config.memory_threshold_mb / 1024.0,  # Convert MB to GB
                gc_frequency=self.config.gc_frequency,
                burst_limit=self.config.burst_limit,
                async_enabled=self.config.async_enabled
            )
            self.performance_optimizer = PerformanceOptimizer(config=perf_config)
        else:
            self.performance_optimizer = None
        
        # Initialize state synchronizer
        if self.config.enable_state_synchronizer:
            self.state_synchronizer = StateSynchronizer()
            self.state_synchronizer.register_scraper(
                scraper_id=self.task_id
            )
        else:
            self.state_synchronizer = None
        
        # Performance tracking
        self.stats = {
            'start_time': time.time(),
            'categories_processed': 0,
            'products_found': 0,
            'requests_made': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'errors': 0
        }
        self.stats_lock = threading.Lock()
        
        # Create semaphore for controlling overall concurrency
        self.semaphore = asyncio.Semaphore(self.config.semaphore_limit)
        
        # Signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Register this crawler
        with _crawlers_lock:
            _active_crawlers[self.task_id] = self
        
        # File paths
        self.url_files_dir = Path("url_files")
        self.url_files_dir.mkdir(exist_ok=True)
        self.cookies_file = "cookies.txt"
        
        # Register in global registry
        if task_id:
            with _crawlers_lock:
                _active_crawlers[task_id] = self
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Initialize database
        self.db = IndiamartMongoDB()
        
        # Log initialization details
        logger.info(f"Initialized IndiaMART Category Crawler (task_id: {task_id}) - Unlimited page crawling enabled with MongoDB")
        
        # Initialize paths (keeping for backward compatibility)
        self.base_path = Path('.')
        self.url_files_path = self.base_path / 'url_files'
        self.url_files_path.mkdir(exist_ok=True, parents=True)
        
        self.category_urls_file = self.url_files_path / 'category_urls.csv'
        self.product_urls_file = self.url_files_path / 'product_urls.csv'
        self.cookies_file = self.base_path / 'cookies.json'
        
        logger.info(f"Indiamart Category Crawler initialized with MongoDB (task_id: {task_id})")
    
    def _check_task_revoked(self):
        """Check if the Celery task has been revoked and set interrupted flag if so."""
        if self.celery_task and hasattr(self.celery_task, 'request'):
            try:
                # Simple check - if the task request exists and we can access it, continue
                # The main revocation will be handled by Celery's signal system
                task_id = self.celery_task.request.id
                if not task_id:
                    self.interrupted = True
                    logger.warning("Task ID is None, stopping crawler")
            except Exception as e:
                logger.debug(f"Error checking task status: {e}")
                # If we can't access the task, assume it might be revoked
                self.interrupted = True
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals with optimized cleanup"""
        sig_name = 'SIGTERM' if signum == signal.SIGTERM else 'SIGINT'
        logger.warning(f"Received {sig_name}, stopping crawler...")
        
        # Update state synchronizer
        if self.state_synchronizer:
            self.state_synchronizer.update_scraper_state(self.task_id, "stopping")
        
        self.stop()
        
        if signum == signal.SIGTERM:
            kill_crawler_processes()
            sys.exit(0)
        else:
            kill_crawler_processes()
            sys.exit(1)
    
    def stop(self):
        """Stop the crawler gracefully with optimized cleanup"""
        logger.info(f"Stopping Indiamart category crawler (task_id: {self.task_id})...")
        self.interrupted = True
        
        # Update state synchronizer
        if self.state_synchronizer:
            self.state_synchronizer.update_scraper_state(self.task_id, "stopped")
        
        # Force cleanup of any lingering processes
        try:
            import subprocess
            # Kill any Chrome processes that might be running
            subprocess.run(['pkill', '-f', 'chrome'], check=False, capture_output=True)
            logger.info("Chrome processes cleanup completed")
        except Exception as e:
            logger.warning(f"Chrome cleanup failed: {e}")
        
        self.close()
    
    def close(self):
        """Cleanup resources with performance optimizer cleanup"""
        logger.info(f"Cleaning up resources for crawler (task_id: {self.task_id})")
        
        # Cleanup performance optimizer
        if self.performance_optimizer:
            try:
                self.performance_optimizer.cleanup()
                logger.info("Performance optimizer cleanup completed")
            except Exception as e:
                logger.warning(f"Performance optimizer cleanup failed: {e}")
        
        # Cleanup state synchronizer
        if self.state_synchronizer:
            try:
                self.state_synchronizer.unregister_scraper(self.task_id)
                logger.info("State synchronizer cleanup completed")
            except Exception as e:
                logger.warning(f"State synchronizer cleanup failed: {e}")
        
        # Unregister from global registry
        if self.task_id:
            with _crawlers_lock:
                removed = _active_crawlers.pop(self.task_id, None)
                if removed:
                    logger.info(f"Removed crawler {self.task_id} from active registry")
        
        # Additional cleanup
        kill_crawler_processes()
        
        logger.info(f"Cleanup completed for crawler (task_id: {self.task_id})")
    
    def get_headers(self):
        """Get request headers"""
        return {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36'
        }
    
    def get_json_headers(self):
        """Get JSON request headers"""
        headers = {
            'accept': '*/*',
            'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
            'x-requested-with': 'XMLHttpRequest'
        }
        return headers
    
    def get_glid(self):
        """Extract glid from cookies"""
        try:
            if not self.cookies_file.exists():
                logger.warning("Cookies file not found")
                return None
            
            cookies_data = json.load(open(self.cookies_file, 'r', encoding='utf-8'))
            for row in cookies_data:
                if row.get('name') == 'ImeshVisitor':
                    from urllib.parse import unquote
                    import re
                    
                    cookie_string = unquote(row['value'])
                    pattern = r'glid=(\d+)'
                    match = re.search(pattern, cookie_string)
                    
                    if match:
                        glid = match.group(1)
                        logger.info(f"Extracted glid: {glid}")
                        return glid
            
            logger.warning("glid not found in cookies")
            return None
        except Exception as e:
            logger.error(f"Error extracting glid: {e}")
            return None
    
    def crawl_main_categories(self):
        """Crawl main category pages to get subcategories"""
        main_categories = [
            'https://dir.indiamart.com/industry/apparel-garments.html',
            'https://dir.indiamart.com/industry/builders-hardware.html',
            'https://dir.indiamart.com/industry/electronic-goods.html',
            'https://dir.indiamart.com/industry/drugs-medicines.html',
            'https://dir.indiamart.com/industry/plant-machinery.html',
            'https://dir.indiamart.com/industry/industrial-supplies.html',
            'https://dir.indiamart.com/industry/agro-farm.html',
            'https://dir.indiamart.com/industry/medical-pharma.html',
            'https://dir.indiamart.com/industry/packaging-material.html',
            'https://dir.indiamart.com/industry/chemicals-fertilizers.html',
            'https://dir.indiamart.com/industry/mechanical-components.html',
            'https://dir.indiamart.com/industry/scientific-instruments.html',
            'https://dir.indiamart.com/industry/furniture.html',
            'https://dir.indiamart.com/industry/automobiles-spares.html',
            'https://dir.indiamart.com/industry/home-supplies.html',
            'https://dir.indiamart.com/industry/ores-metals.html',
            'https://dir.indiamart.com/industry/hand-tools.html',
            'https://dir.indiamart.com/industry/handicrafts-gifts.html',
            'https://dir.indiamart.com/industry/kitchen-utensils-cookware.html',
            'https://dir.indiamart.com/industry/textiles-yarn.html',
            'https://dir.indiamart.com/industry/cosmetics-toiletries.html',
            'https://dir.indiamart.com/industry/home-furnishings.html',
            'https://dir.indiamart.com/industry/gems-jewellery.html',
            'https://dir.indiamart.com/industry/computer-hardware.html',
            'https://dir.indiamart.com/industry/fashion-accessories.html',
            'https://dir.indiamart.com/industry/sports-goods.html',
            'https://dir.indiamart.com/industry/paper.html',
            'https://dir.indiamart.com/industry/bags-belts-wallets.html'
        ]
        
        category_urls = []
        headers = self.get_headers()
        
        for cat in main_categories:
            if self.interrupted or self._check_task_revoked():
                break
            
            max_retries = 3
            retry = 0
            success = False
            
            while retry < max_retries and not success:
                try:
                    # Get proxy configuration (gets a new random proxy each time)
                    auth, proxy = get_proxies()
                    req = requests.get(cat, headers=headers, proxies=proxy, auth=auth, timeout=30)
                    logger.info(f"Crawling: {cat} - Status: {req.status_code}")
                    
                    # If we get 403, try with a different proxy
                    if req.status_code == 403 and retry < max_retries - 1:
                        logger.warning(f"Got 403 for {cat}, retrying with different proxy (attempt {retry + 1}/{max_retries})")
                        retry += 1
                        continue
                    
                    if req.status_code != 200:
                        break
                    
                    resp = Selector(text=req.text)
                    
                    for row in resp.xpath('//div[@class="mid"]/ul/li'):
                        cat_name = row.xpath('./a/text()').get()
                        for srow in row.xpath('./span/a'):
                            sub_cat = srow.xpath('./text()').get()
                            cat_url = srow.xpath('./@href').get()
                            
                            if cat_url:
                                if not cat_url.startswith('http'):
                                    cat_url = f'https://dir.indiamart.com{cat_url}'
                                
                                category_urls.append({
                                    'cat_name': cat_name,
                                    'sub_cat': sub_cat,
                                    'cat_url': cat_url
                                })
                    
                    success = True
                
                except Exception as e:
                    logger.error(f"Error crawling {cat} (attempt {retry + 1}/{max_retries}): {e}")
                    retry += 1
                    if retry < max_retries:
                        logger.info(f"Retrying with different proxy...")

        
        # Save category URLs to SQLite database
        if category_urls:
            inserted = self.db.insert_categories(category_urls)
            logger.info(f"Saved {inserted} category URLs to database")
        
        return category_urls
    
    def export_product_urls(self, row, product_urls):
        """Export product URLs to SQLite database"""
        try:
            # Prepare URLs data for batch insert
            urls_data = []
            for purl in product_urls:
                urls_data.append({
                    'category': row.get('cat_name', ''),
                    'subcategory': row.get('sub_cat', ''),
                    'category_url': row.get('cat_url', ''),
                    'product_url': purl
                })
            
            # Insert into SQLite database
            if urls_data:
                inserted = self.db.insert_product_urls(urls_data)
                logger.info(f"Inserted {inserted} product URLs to database")
                
        except Exception as e:
            logger.error(f"Error exporting product URLs to database: {e}")
            logger.error(f"Row data: {row}")  # Debug info
    
    async def crawl_category_products_async(self, category_row):
        """Async version of category product crawling with optimized proxy support and speed"""
        if self.interrupted:
            return
        
        try:
            # Increased retries for better reliability with huge data
            max_retries = 5
            retry = 0
            success = False
            
            while retry < max_retries and not success:
                try:
                    # Get proxy configuration (gets a new random proxy each time)
                    auth, proxy = get_proxies()
                    
                    # Use curl_cffi to impersonate Chrome and avoid 403 blocks
                    from curl_cffi import requests as curl_requests
                    response = curl_requests.get(
                        category_row['cat_url'], 
                        headers=self.get_headers(), 
                        proxies=proxy,
                        impersonate="chrome131",
                        timeout=15  # Reduced from 30 for faster failures
                    )
                    
                    # If we get 403, immediately try with a different proxy
                    if response.status_code == 403:
                        logger.warning(f"Got 403 for {category_row['cat_url']}, trying different proxy (attempt {retry + 1}/{max_retries})")
                        retry += 1
                        await asyncio.sleep(0.5)  # Brief delay before retry
                        continue
                    
                    if response.status_code != 200:
                        logger.warning(f"Failed to fetch category: {category_row['cat_url']} - Status: {response.status_code}")
                        if retry < max_retries - 1:
                            retry += 1
                            await asyncio.sleep(0.5)
                            continue
                        return
                    
                    content = response.text
                    resp = Selector(text=content)
                    mcat_id = resp.xpath('//div[@class="msec"]/@data-click').get()
                    
                    if not mcat_id:
                        logger.warning(f"No mcat_id found for {category_row['cat_url']}")
                        return
                    
                    mcat_id = mcat_id.split('|')[-2]
                    
                    # Get products from first page
                    product_urls = resp.xpath('//span[@data-click="^Prod0Name"]/a/@href').getall()
                    if product_urls:
                        self.export_product_urls(category_row, product_urls)
                        self.stats['products_found'] += len(product_urls)
                        logger.info(f"✓ Found {len(product_urls)} products on page 1 for {category_row['cat_url']}")
                    
                    # Async pagination with optimized speed
                    await self._crawl_pagination_async_with_proxy(category_row, mcat_id)
                    
                    success = True
                    
                except Exception as e:
                    logger.error(f"Error crawling category {category_row['cat_url']} (attempt {retry + 1}/{max_retries}): {e}")
                    retry += 1
                    if retry < max_retries:
                        await asyncio.sleep(0.5)
            
            if not success:
                logger.error(f"Failed to crawl {category_row['cat_url']} after {max_retries} attempts")
                        
        except Exception as e:
            logger.error(f"Fatal error crawling category {category_row['cat_url']}: {e}")
    
    async def _crawl_pagination_async_with_proxy(self, category_row, mcat_id):
        """Handle pagination asynchronously with optimized proxy support and speed"""
        srt = 29
        end = 56
        frsc = 28
        mcatName = category_row['cat_url'].split('/')[-1].split('.html')[0]
        glid = self.get_glid()
        
        page_num = 2
        max_pages = self.pages_per_category if self.pages_per_category > 0 else float('inf')
        
        # Optimized: Process pages in batches for better speed with huge data
        batch_size = 30  # Process 30 pages at a time
        current_page = 2
        consecutive_empty = 0
        max_consecutive_empty = 5  # Stop after 5 consecutive empty batches
        
        async with self.connection_manager.get_async_session() as session:
            while (max_pages == float('inf') or current_page <= max_pages) and consecutive_empty < max_consecutive_empty:
                if self.interrupted:
                    break
                
                # Create batch of page tasks
                tasks = []
                # Calculate end page for this batch
                if max_pages == float('inf'):
                    end_page = current_page + batch_size
                else:
                    end_page = min(current_page + batch_size, int(max_pages) + 1)
                
                for page in range(current_page, end_page):
                    if page == 2:
                        page_url = f'https://dir.indiamart.com/impcat/next?pageViewStatus=grid&nmonlyMyposTrack=0&dynHandSecNmonly=0&mcatId={mcat_id}&prod_serv=P&utm_source=&mcatName={mcatName}&srt={srt}&end={end}&ims_flag=&cityID=&prc_cnt_flg=1&fcilp=0&spec=&pr=0&randomizer=211&pg={page}&frsc={frsc}&video='
                    else:
                        if not glid:
                            break
                        page_url = f'https://dir.indiamart.com/impcat/next?glid={glid}&pageViewStatus=grid&nmonlyMyposTrack=0&dynHandSecNmonly=0&mcatId={mcat_id}&prod_serv=P&utm_source=&mcatName={mcatName}&srt={srt}&end={end}&ims_flag=&cityID=&prc_cnt_flg=1&fcilp=0&spec=&pr=0&randomizer=211&pg={page}&frsc={frsc}&video='
                    
                    tasks.append(self._fetch_page_async_with_retry(session, page_url, page, category_row))
                    
                    # Update pagination parameters
                    srt = end + 1
                    frsc = end
                    end += 20
                
                if not tasks:
                    break
                
                # Execute batch concurrently
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Check results
                batch_products = 0
                for result in results:
                    if isinstance(result, Exception):
                        logger.error(f"Pagination error: {result}")
                    elif isinstance(result, int):
                        batch_products += result
                
                if batch_products == 0:
                    consecutive_empty += 1
                    logger.info(f"Empty batch {consecutive_empty}/{max_consecutive_empty} for {category_row['cat_url']}")
                else:
                    consecutive_empty = 0  # Reset on successful batch
                    logger.info(f"✓ Batch pages {current_page}-{current_page + len(tasks) - 1}: {batch_products} products")
                
                current_page += batch_size
                
                # Brief delay between batches for politeness
                await asyncio.sleep(0.1)
    
    async def _fetch_page_async_optimized(self, session, page_url, page_num, category_row):
        """Optimized async page fetching with performance optimizer"""
        try:
            # Use performance optimizer if available
            if self.performance_optimizer:
                response_data = await self.performance_optimizer.fetch_async(
                    url=page_url,
                    headers={
                        'Accept': 'application/json, text/javascript, */*; q=0.01',
                        'X-Requested-With': 'XMLHttpRequest',
                        'Referer': category_row['cat_url'],
                        'Accept-Encoding': 'gzip, deflate, br',
                        'Connection': 'keep-alive'
                    }
                )
                
                if response_data:
                    with self.stats_lock:
                        self.stats['requests_made'] += 1
                        self.stats['cache_hits'] += 1 if response_data.get('from_cache') else 0
                        self.stats['cache_misses'] += 0 if response_data.get('from_cache') else 1
                    
                    content = response_data.get('content', '')
                    if content:
                        resp = Selector(text=content)
                        page_products = resp.xpath('//span[@data-click="^Prod0Name"]/a/@href').getall()
                        
                        if page_products:
                            self.export_product_urls(category_row, page_products)
                            with self.stats_lock:
                                self.stats['products_found'] += len(page_products)
                            logger.info(f"Page {page_num}: Found {len(page_products)} products (optimized)")
                            return len(page_products)
                        else:
                            logger.info(f"Page {page_num}: No products found (optimized)")
                            return 0
                else:
                    with self.stats_lock:
                        self.stats['errors'] += 1
                    logger.warning(f"Page {page_num}: No response data (optimized)")
                    return 0
            else:
                # Fallback to original method
                return await self._fetch_page_async(session, page_url, page_num, category_row)
                
        except Exception as e:
            with self.stats_lock:
                self.stats['errors'] += 1
            logger.error(f"Error fetching page {page_num} (optimized): {e}")
            return 0

    async def _fetch_page_async_with_retry(self, session, page_url, page_num, category_row):
        """Fetch a single pagination page with automatic proxy retry on 403 using curl_cffi"""
        max_retries = 5
        
        for retry in range(max_retries):
            try:
                # Get new proxy for each attempt
                auth, proxy_dict = get_proxies()
                
                # Use curl_cffi for better browser impersonation
                from curl_cffi import requests as curl_requests
                
                headers = {
                    'Accept': 'application/json, text/javascript, */*; q=0.01',
                    'X-Requested-With': 'XMLHttpRequest',
                    'Referer': category_row['cat_url'],
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                }
                
                # Make request with curl_cffi (runs in thread pool to avoid blocking)
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: curl_requests.get(
                        page_url,
                        headers=headers,
                        proxies=proxy_dict,
                        impersonate="chrome131",
                        timeout=8
                    )
                )
                
                with self.stats_lock:
                    self.stats['requests_made'] += 1
                
                # Handle 403 with immediate retry using different proxy
                if response.status_code == 403:
                    if retry < max_retries - 1:
                        logger.warning(f"Page {page_num}: Got 403, trying different proxy (attempt {retry + 1}/{max_retries})")
                        await asyncio.sleep(0.3)
                        continue
                    else:
                        logger.error(f"Page {page_num}: Failed after {max_retries} 403 errors")
                        return 0
                
                if response.status_code == 200:
                    data = response.json()
                    content = data.get('content', '')
                    if content:
                        resp = Selector(text=content)
                        page_products = resp.xpath('//span[@data-click="^Prod0Name"]/a/@href').getall()
                        
                        if page_products:
                            self.export_product_urls(category_row, page_products)
                            with self.stats_lock:
                                self.stats['products_found'] += len(page_products)
                            logger.info(f"Page {page_num}: Found {len(page_products)} products")
                            return len(page_products)
                    return 0
                else:
                    if retry < max_retries - 1:
                        logger.warning(f"Page {page_num}: HTTP {response.status_code}, retrying...")
                        await asyncio.sleep(0.3)
                        continue
                    return 0
                    
            except Exception as e:
                if retry < max_retries - 1:
                    logger.warning(f"Page {page_num}: Error {e}, retrying...")
                    await asyncio.sleep(0.2)
                    continue
                with self.stats_lock:
                    self.stats['errors'] += 1
                logger.error(f"Page {page_num}: Failed after {max_retries} attempts: {e}")
                return 0
        
        return 0
    
    async def _fetch_page_async(self, session, page_url, page_num, category_row):
        """Fetch a single pagination page asynchronously with optimized settings"""
        try:
            headers = {
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': category_row['cat_url'],
                'Accept-Encoding': 'gzip, deflate, br',  # Enable compression
                'Connection': 'keep-alive'  # Keep connections alive
            }
            
            # Use reduced timeout for faster processing
            timeout = aiohttp.ClientTimeout(total=self.config.request_timeout)
            
            async with session.get(page_url, headers=headers, timeout=timeout) as response:
                with self.stats_lock:
                    self.stats['requests_made'] += 1
                
                if response.status == 200:
                    data = await response.json()
                    content = data.get('content', '')
                    if content:
                        resp = Selector(text=content)
                        page_products = resp.xpath('//span[@data-click="^Prod0Name"]/a/@href').getall()
                        
                        if page_products:
                            self.export_product_urls(category_row, page_products)
                            with self.stats_lock:
                                self.stats['products_found'] += len(page_products)
                            logger.info(f"Page {page_num}: Found {len(page_products)} products")
                            return len(page_products)
                        else:
                            logger.info(f"Page {page_num}: No products found")
                            return 0
                else:
                    logger.warning(f"Page {page_num}: HTTP {response.status}")
                    return 0
        except asyncio.TimeoutError:
            with self.stats_lock:
                self.stats['errors'] += 1
            logger.warning(f"Page {page_num}: Request timeout")
            return 0
        except Exception as e:
            with self.stats_lock:
                self.stats['errors'] += 1
            logger.error(f"Error fetching page {page_num}: {e}")
            return 0
    
    def _update_stats(self, **kwargs):
        """Thread-safe stats update"""
        with self.stats_lock:
            for key, value in kwargs.items():
                if key in self.stats:
                    self.stats[key] += value
    
    def get_performance_stats(self):
        """Get comprehensive performance statistics"""
        with self.stats_lock:
            base_stats = self.stats.copy()
        
        # Add performance optimizer stats if available
        if self.performance_optimizer:
            perf_stats = self.performance_optimizer.get_stats()
            base_stats.update({
                'optimizer_cache_hits': perf_stats.get('cache_hits', 0),
                'optimizer_cache_misses': perf_stats.get('cache_misses', 0),
                'optimizer_requests_per_second': perf_stats.get('requests_per_second', 0),
                'optimizer_memory_usage_mb': perf_stats.get('memory_usage_mb', 0)
            })
        
        # Calculate runtime and rates
        runtime = time.time() - base_stats['start_time']
        base_stats.update({
            'runtime_seconds': runtime,
            'categories_per_second': base_stats['categories_processed'] / max(runtime, 1),
            'products_per_second': base_stats['products_found'] / max(runtime, 1),
            'requests_per_second': base_stats['requests_made'] / max(runtime, 1)
        })
        
        return base_stats

    def crawl_category_products(self, category_row, sess):
        """Crawl products from a category"""
        if self.interrupted:
            return
        
        try:
            headers = self.get_headers()
            json_headers = self.get_json_headers()
            
            # Get proxy configuration for category page request
            auth, proxy = get_proxies()
            req = sess.get(category_row['cat_url'], headers=headers, proxies=proxy, auth=auth, timeout=30)
            logger.info(f"Crawling category: {category_row['cat_url']} - Status: {req.status_code}")
            
            if req.status_code != 200:
                return
            
            resp = Selector(text=req.text)
            mcat_id = resp.xpath('//div[@class="msec"]/@data-click').get()
            
            if not mcat_id:
                logger.warning(f"No mcat_id found for {category_row['cat_url']}")
                return
            
            mcat_id = mcat_id.split('|')[-2]
            
            # Get products from first page
            product_urls = resp.xpath('//span[@data-click="^Prod0Name"]/a/@href').getall()
            self.export_product_urls(category_row, product_urls)
            logger.info(f"Found {len(product_urls)} products on page 1")
            
            # Pagination - crawl all available pages
            srt = 29
            end = 56
            frsc = 28
            mcatName = category_row['cat_url'].split('/')[-1].split('.html')[0]
            glid = self.get_glid()
            
            page_num = 2
            max_pages = self.pages_per_category if self.pages_per_category > 0 else float('inf')
            consecutive_empty_pages = 0
            max_consecutive_empty = 3  # Stop after 3 consecutive empty pages
            
            while page_num <= max_pages and consecutive_empty_pages < max_consecutive_empty:
                if self.interrupted or self._check_task_revoked():
                    break
                
                try:
                    if page_num == 2:
                        page_url = f'https://dir.indiamart.com/impcat/next?pageViewStatus=grid&nmonlyMyposTrack=0&dynHandSecNmonly=0&mcatId={mcat_id}&prod_serv=P&utm_source=&mcatName={mcatName}&srt={srt}&end={end}&ims_flag=&cityID=&prc_cnt_flg=1&fcilp=0&spec=&pr=0&randomizer=211&pg={page_num}&frsc={frsc}&video='
                    else:
                        if not glid:
                            logger.warning("No glid available, skipping pagination")
                            break
                        page_url = f'https://dir.indiamart.com/impcat/next?glid={glid}&pageViewStatus=grid&nmonlyMyposTrack=0&dynHandSecNmonly=0&mcatId={mcat_id}&prod_serv=P&utm_source=&mcatName={mcatName}&srt={srt}&end={end}&ims_flag=&cityID=&prc_cnt_flg=1&fcilp=0&spec=&pr=0&randomizer=211&pg={page_num}&frsc={frsc}&video='
                    
                    # Get proxy configuration for pagination requests
                    auth, proxy = get_proxies()
                    req1 = sess.get(page_url, headers=json_headers, proxies=proxy, auth=auth, timeout=30)
                    logger.info(f"Page {page_num}: {req1.status_code}")
                    
                    if req1.status_code == 200:
                        content = req1.json().get('content', '')
                        if content:
                            resp = Selector(text=content)
                            page_products = resp.xpath('//span[@data-click="^Prod0Name"]/a/@href').getall()
                            
                            if page_products:
                                self.export_product_urls(category_row, page_products)
                                logger.info(f"Found {len(page_products)} products on page {page_num}")
                                consecutive_empty_pages = 0  # Reset counter
                            else:
                                consecutive_empty_pages += 1
                                logger.info(f"No products found on page {page_num} (empty page {consecutive_empty_pages}/{max_consecutive_empty})")
                        else:
                            consecutive_empty_pages += 1
                            logger.info(f"Empty content on page {page_num} (empty page {consecutive_empty_pages}/{max_consecutive_empty})")
                        
                        srt = end + 1
                        frsc = end
                        end += 20
                    else:
                        # Non-200 status code might indicate end of pages
                        consecutive_empty_pages += 1
                        logger.info(f"Non-200 status ({req1.status_code}) on page {page_num} (empty page {consecutive_empty_pages}/{max_consecutive_empty})")
                    
                    page_num += 1
                    time.sleep(2)  # Polite delay
                
                except Exception as e:
                    logger.error(f"Error crawling page {page_num}: {e}")
                    consecutive_empty_pages += 1
                    page_num += 1
            
            if consecutive_empty_pages >= max_consecutive_empty:
                logger.info(f"Stopped pagination after {consecutive_empty_pages} consecutive empty pages")
            elif page_num > max_pages:
                logger.info(f"Reached maximum pages limit: {max_pages}")
        
        except Exception as e:
            logger.error(f"Error crawling category products: {e}")
    
    async def run_async(self):
        """Async main crawler loop with improved performance and state synchronization"""
        logger.info("Starting optimized Indiamart category crawler...")
        
        # Update state synchronizer
        if self.state_synchronizer:
            self.state_synchronizer.update_scraper_state(self.task_id, "running")
        
        cycle = 1
        while not self.interrupted and not self._check_task_revoked():
            try:
                logger.info(f"=== Starting crawling cycle {cycle} ===")
                
                # Update stats
                self._update_stats(categories_processed=0)
                
                # Crawl main categories (keep sync for now)
                logger.info("Crawling main categories...")
                self.crawl_main_categories()
                
                if self.interrupted or self._check_task_revoked():
                    break
                
                # Get categories from database
                logger.info("Loading categories from database...")
                categories = self.db.get_categories()
                
                if not categories:
                    logger.warning("No categories found in database")
                    await asyncio.sleep(60)
                    continue
                
                logger.info(f"Processing {len(categories)} categories with async optimization")
                
                # Process categories in batches asynchronously with increased concurrency
                batch_size = self.config.batch_size
                total_batches = (len(categories) + batch_size - 1) // batch_size
                
                async with self.connection_manager.get_async_session() as session:
                    for batch_idx in range(0, len(categories), batch_size):
                        if self.interrupted or self._check_task_revoked():
                            break
                        
                        batch = categories[batch_idx:batch_idx + batch_size]
                        batch_num = (batch_idx // batch_size) + 1
                        
                        logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} categories)")
                        
                        # Create tasks for concurrent category processing
                        tasks = []
                        for category_row in batch:
                            if self.interrupted or self._check_task_revoked():
                                break
                            task = self.crawl_category_products_async(category_row)
                            tasks.append(task)
                        
                        if tasks:
                            # Execute batch with semaphore control
                            results = await asyncio.gather(*tasks, return_exceptions=True)
                            
                            # Process results and update stats
                            successful = 0
                            for i, result in enumerate(results):
                                if isinstance(result, Exception):
                                    logger.error(f"Category processing error: {result}")
                                    self._update_stats(errors=1)
                                else:
                                    successful += 1
                            
                            self._update_stats(categories_processed=successful)
                            logger.info(f"Batch {batch_num} completed: {successful}/{len(batch)} categories successful")
                        
                        # Performance optimizer memory management
                        if self.performance_optimizer and batch_num % 10 == 0:
                            self.performance_optimizer.cleanup_memory()
                        
                        # Brief pause between batches
                        if not self.interrupted:
                            await asyncio.sleep(self.config.rate_limit_delay * 10)
                
                # Log cycle completion stats
                stats = self.get_performance_stats()
                logger.info(f"Cycle {cycle} completed - Categories: {stats['categories_processed']}, "
                          f"Products: {stats['products_found']}, "
                          f"Requests: {stats['requests_made']}, "
                          f"Rate: {stats['requests_per_second']:.2f} req/s")
                
                cycle += 1
                
                # Wait before next cycle
                if not self.interrupted:
                    logger.info("Waiting 5 minutes before next cycle...")
                    await asyncio.sleep(300)
                
            except Exception as e:
                logger.error(f"Error in crawling cycle {cycle}: {e}")
                self._update_stats(errors=1)
                if not self.interrupted:
                    await asyncio.sleep(60)
                cycle += 1
        
        # Update final state
        if self.state_synchronizer:
            final_state = "stopped" if self.interrupted else "completed"
            self.state_synchronizer.update_scraper_state(self.task_id, final_state)
        
        logger.info("Indiamart category crawler finished")
        await self.connection_manager.close_async_session()

    def run(self):
        """Main crawler loop - now uses async for better performance"""
        try:
            # Run the async version
            asyncio.run(self.run_async())
        except Exception as e:
            logger.error(f"Error in async crawler: {e}")
            # Fallback to sync version if needed
            self._run_sync_fallback()
    
    def _run_sync_fallback(self):
        """Fallback sync version of the crawler"""
        logger.info("Starting Indiamart category crawler (sync fallback)...")
        
        cycle = 1
        while not self.interrupted and not self._check_task_revoked():
            try:
                logger.info(f"=== Starting crawling cycle {cycle} ===")
                
                # Crawl main categories
                logger.info("Crawling main categories...")
                self.crawl_main_categories()
                
                if self.interrupted or self._check_task_revoked():
                    break
                
                # Get categories directly from database
                logger.info("Loading categories from database...")
                categories = self.db.get_categories()
                
                if not categories:
                    logger.warning("No categories found in database")
                    time.sleep(60)
                    continue
                
                logger.info(f"Processing {len(categories)} categories")
                
                # Crawl products from each category using connection pool
                for idx, row in enumerate(categories):
                    if self.interrupted or self._check_task_revoked():
                        break
                    
                    logger.info(f"Processing category {idx + 1}/{len(categories)}")
                    
                    # Use connection manager for better performance
                    session = self.connection_manager.get_session()
                    try:
                        self.crawl_category_products(row, session)
                        self.stats['categories_processed'] += 1
                    finally:
                        self.connection_manager.return_session(session)
                    
                    time.sleep(0.1)  # Reduced delay
                
                if self.interrupted or self._check_task_revoked():
                    break
                
                logger.info(f"=== Completed crawling cycle {cycle} ===")
                cycle += 1
                
                # Wait 2 hours before next cycle
                logger.info("Waiting 2 hours before next cycle...")
                for _ in range(7200):  # 2 hours
                    if self.interrupted or self._check_task_revoked():
                        break
                    time.sleep(1)
            
            except Exception as e:
                logger.error(f"Error in crawler cycle: {e}")
                if not self.interrupted:
                    time.sleep(60)
        
        logger.info("Indiamart category crawler stopped")
        self.close()


def CrawlIndiamartCategories(task_id=None, celery_task=None):
    """Run the Indiamart category crawler with unlimited page crawling"""
    # Generate a task_id if not provided (for manual execution consistency)
    if task_id is None:
        import uuid
        task_id = f"manual_{uuid.uuid4().hex[:8]}"
        logger.info(f"Generated task_id for manual execution: {task_id}")
    
    crawler = IndiamartCategoryCrawler(task_id=task_id)
    
    # Set the Celery task reference for revocation checking
    if celery_task:
        crawler.celery_task = celery_task
    
    try:
        crawler.run()
    except KeyboardInterrupt:
        logger.info("Crawler interrupted by user")
        crawler.stop()
    except Exception as e:
        logger.error(f"Fatal error in crawler: {e}")
        crawler.stop()
        raise


def StopIndiamartCategoryCrawlerByTaskId(task_id):
    """Stop a specific crawler by task ID"""
    logger.info(f"Attempting to stop IndiaMART category crawler with task_id: {task_id}")
    
    with _crawlers_lock:
        crawler = _active_crawlers.get(task_id)
        if crawler:
            logger.info(f"Found active crawler {task_id}, stopping...")
            crawler.stop()
            return True
        else:
            logger.warning(f"No active crawler found with task_id: {task_id}")
            return False


def StopAllIndiamartCategoryCrawlers():
    """Stop all active IndiaMART category crawlers"""
    logger.info("Stopping all active IndiaMART category crawlers...")
    
    with _crawlers_lock:
        active_task_ids = list(_active_crawlers.keys())
        
    if not active_task_ids:
        logger.info("No active crawlers to stop")
        return {"stopped_count": 0, "message": "No active crawlers to stop"}
    
    stopped_count = 0
    for task_id in active_task_ids:
        success = StopIndiamartCategoryCrawlerByTaskId(task_id)
        if success:
            stopped_count += 1
    
    logger.info(f"Stopped {stopped_count} active crawlers")
    return {"stopped_count": stopped_count, "message": f"Stopped {stopped_count} active crawlers"}


def GetActiveIndiamartCrawlers():
    """Get list of active crawler task IDs"""
    with _crawlers_lock:
        return list(_active_crawlers.keys())


if __name__ == '__main__':
    CrawlIndiamartCategories()

