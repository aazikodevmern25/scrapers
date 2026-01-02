"""
Indiamart Product Scraper - Integrated with Celery Task Queue
Scrapes product data from Indiamart and stores in MongoDB
Enhanced with advanced performance optimization and state synchronization
"""
import time
import requests
import pandas as pd
import json
import sys
import signal
import threading
import random
import asyncio
import aiohttp
import queue
import ssl
import certifi
from contextlib import asynccontextmanager
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from scrapy import Selector
from bs4 import BeautifulSoup
from pymongo import MongoClient
import pymongo
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlparse
import os
import uuid
import logging
from pathlib import Path
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from .indiamart_mongodb import IndiamartMongoDB
from utils import get_proxies

# Import performance optimization modules
from celery_app.performance_optimizer import PerformanceOptimizer, PerformanceConfig, get_global_optimizer
from celery_app.state_synchronizer import (
    StateSynchronizer, ScraperState, get_global_synchronizer, 
    with_state_sync
)

# Configure logging
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"indiamart_scraper_{datetime.now().strftime('%Y%m%d')}.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('indiamart_scraper')

# Global registry for active scrapers
_active_scrapers = {}
_scrapers_lock = threading.Lock()

def kill_scraper_processes():
    """Kill any hanging scraper processes"""
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

class ScrapingConfig:
    """Configuration for high-performance scraping - Enhanced"""
    max_workers: int = 50  # Reduced for stability
    max_concurrent_requests: int = 50  # Reduced for stability
    batch_size: int = 500  # Reduced for faster feedback
    request_timeout: int = 30  # Increased timeout
    connection_pool_size: int = 100  # Reduced for stability
    max_retries: int = 3  # Balanced retries
    backoff_factor: float = 0.2  # Optimized backoff
    rate_limit_delay: float = 0.005  # Minimal delay for max speed
    cache_ttl: int = 7200  # 2 hour cache for better performance
    enable_compression: bool = True
    use_session_pool: bool = True
    async_enabled: bool = True
    # New performance settings
    memory_threshold: float = 0.85
    gc_frequency: int = 1000
    burst_limit: int = 50

class ConnectionManager:
    """Manages HTTP connections with pooling and session reuse"""
    
    def __init__(self, config: ScrapingConfig):
        self.config = config
        self.session_pool = queue.Queue(maxsize=config.connection_pool_size)
        self.async_session = None
        self._initialize_sessions()

    def _initialize_sessions(self):
        """Initialize session pool"""
        # Create SSL context for better performance
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        # Initialize sync sessions
        for _ in range(self.config.connection_pool_size):
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
        """Get async session with connection pooling and proxy support"""
        if not self.async_session:
            # Get proxy configuration
            try:
                auth, proxy_dict = get_proxies()
                proxy_url = None
                if proxy_dict and 'http' in proxy_dict:
                    proxy_url = proxy_dict['http']
                    # Convert requests proxy format to aiohttp format
                    if auth:
                        # Extract proxy URL and add auth
                        proxy_parts = proxy_url.replace('http://', '').split(':')
                        if len(proxy_parts) >= 2:
                            proxy_url = f"http://{auth.username}:{auth.password}@{proxy_parts[0]}:{proxy_parts[1]}"
            except Exception as e:
                logger.warning(f"Failed to get proxy configuration: {e}")
                proxy_url = None
            
            connector = aiohttp.TCPConnector(
                limit=self.config.max_concurrent_requests,
                limit_per_host=50,
                ttl_dns_cache=300,
                use_dns_cache=True,
                ssl=False,  # Disable SSL verification for speed
                enable_cleanup_closed=True
            )
            
            timeout = aiohttp.ClientTimeout(
                total=self.config.request_timeout,
                connect=5,
                sock_read=10
            )
            
            session_kwargs = {
                'connector': connector,
                'timeout': timeout,
                'headers': {
                    'User-Agent': self._get_random_user_agent(),
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Encoding': 'gzip, deflate' if self.config.enable_compression else 'identity',
                }
            }
            
            # Add proxy if available
            if proxy_url:
                session_kwargs['connector'] = aiohttp.TCPConnector(
                    limit=self.config.max_concurrent_requests,
                    limit_per_host=50,
                    ttl_dns_cache=300,
                    use_dns_cache=True,
                    ssl=False,
                    enable_cleanup_closed=True
                )
                # Note: aiohttp proxy is set per request, not per session
                self._proxy_url = proxy_url
            else:
                self._proxy_url = None
            
            self.async_session = aiohttp.ClientSession(**session_kwargs)
        
        yield self.async_session
    
    def get_session(self):
        """Get session from pool"""
        try:
            return self.session_pool.get_nowait()
        except Empty:
            # Create new session if pool is empty
            return self._create_new_session()
    
    def return_session(self, session):
        """Return session to pool"""
        try:
            self.session_pool.put_nowait(session)
        except:
            # Pool is full, close the session
            session.close()
    
    def _create_new_session(self):
        """Create new session when pool is empty with proxy support"""
        session = requests.Session()
        
        # Get proxy configuration
        try:
            auth, proxy_dict = get_proxies()
            if proxy_dict:
                session.proxies.update(proxy_dict)
            if auth:
                session.auth = auth
        except Exception as e:
            logger.warning(f"Failed to configure proxy for session: {e}")
        
        retry_strategy = Retry(
            total=self.config.max_retries,
            backoff_factor=self.config.backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        session.headers.update({
            'User-Agent': self._get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        })
        
        return session
    
    async def close_async_session(self):
        """Close async session"""
        if self.async_session:
            await self.async_session.close()

class ResponseCache:
    """High-performance response cache with TTL"""
    
    def __init__(self, ttl: int = 3600):
        self.cache = {}
        self.timestamps = {}
        self.ttl = ttl
        self.lock = threading.Lock()
    
    def _get_cache_key(self, url: str) -> str:
        """Generate cache key for URL"""
        return hashlib.md5(url.encode()).hexdigest()
    
    def get(self, url: str) -> Optional[str]:
        """Get cached response"""
        key = self._get_cache_key(url)
        
        with self.lock:
            if key in self.cache:
                if time.time() - self.timestamps[key] < self.ttl:
                    return self.cache[key]
                else:
                    # Expired, remove from cache
                    del self.cache[key]
                    del self.timestamps[key]
        
        return None
    
    def set(self, url: str, content: str):
        """Set cached response"""
        key = self._get_cache_key(url)
        
        with self.lock:
            self.cache[key] = content
            self.timestamps[key] = time.time()
    
    def clear_expired(self):
        """Clear expired cache entries"""
        current_time = time.time()
        
        with self.lock:
            expired_keys = [
                key for key, timestamp in self.timestamps.items()
                if current_time - timestamp >= self.ttl
            ]
            
            for key in expired_keys:
                del self.cache[key]
                del self.timestamps[key]

class IndiamartProductScraper:
    """Enhanced high-performance Indiamart product scraper with state synchronization"""
    
    def __init__(self, db_manager, config: Optional[ScrapingConfig] = None):
        self.db_manager = db_manager
        self.config = config or ScrapingConfig()
        
        # Initialize performance optimizer
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
            memory_threshold=self.config.memory_threshold,
            gc_frequency=self.config.gc_frequency,
            burst_limit=self.config.burst_limit,
            async_enabled=self.config.async_enabled
        )
        
        self.performance_optimizer = get_global_optimizer(perf_config)
        
        # Initialize state synchronizer
        self.scraper_id = f"indiamart_scraper_{uuid.uuid4().hex[:8]}"
        self.state_synchronizer = get_global_synchronizer()
        self.state_synchronizer.register_scraper(self.scraper_id, ScraperState.STOPPED)
        
        # Legacy components (kept for compatibility)
        self.connection_manager = ConnectionManager(self.config)
        self.cache = ResponseCache(ttl=self.config.cache_ttl)
        
        # Enhanced performance tracking
        self.stats = {
            'start_time': None,
            'end_time': None,
            'total_urls': 0,
            'processed_urls': 0,
            'successful_urls': 0,
            'failed_urls': 0,
            'products_found': 0,
            'sellers_found': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'requests_per_second': 0.0,
            'average_response_time': 0.0,
            'memory_usage_mb': 0.0,
            'error_rate': 0.0
        }
        self.stats_lock = threading.Lock()
        
        # Control flags
        self.running = False
        self.should_stop = False
        self.rate_limit_lock = threading.Lock()
        self.last_request_time = 0
        
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Register with global scrapers
        with _scrapers_lock:
            _active_scrapers[self.scraper_id] = self
        
        logger.info(f"Enhanced IndiaMART scraper initialized: {self.scraper_id}")

    def _signal_handler(self, signum, frame):
        """Enhanced signal handler with state synchronization"""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.should_stop = True
        self.state_synchronizer.update_scraper_state(self.scraper_id, ScraperState.STOPPING)

    def _update_stats(self, **kwargs):
        """Thread-safe stats update - simplified for performance"""
        with self.stats_lock:
            for key, value in kwargs.items():
                if key in self.stats:
                    if key in ['requests_per_second', 'average_response_time', 'error_rate']:
                        # Calculate running averages
                        if self.stats['processed_urls'] > 0:
                            current_avg = self.stats[key]
                            count = self.stats['processed_urls']
                            self.stats[key] = ((current_avg * (count - 1)) + value) / count
                        else:
                            self.stats[key] = value
                    else:
                        self.stats[key] += value

    def _calculate_progress(self) -> float:
        """Calculate scraping progress percentage"""
        if self.stats['total_urls'] == 0:
            return 0.0
        return min(100.0, (self.stats['processed_urls'] / self.stats['total_urls']) * 100.0)

    async def _fetch_async_optimized(self, url: str) -> Optional[str]:
        """Enhanced async fetch using SendGetRequests from utils.py (proven to work)"""
        try:
            from utils import SendGetRequests
            
            start_time = time.time()
            
            # Use SendGetRequests in a thread pool for async compatibility
            loop = asyncio.get_running_loop()
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            def fetch_url():
                try:
                    return SendGetRequests(url, headers, use_proxy=True, max_403_retries=1)
                except Exception as e:
                    logger.error(f"SendGetRequests error for {url}: {e}")
                    return None
            
            response = await loop.run_in_executor(None, fetch_url)
            
            if response and response.status_code == 200:
                content = response.text
                response_time = time.time() - start_time
                self._update_stats(
                    successful_urls=1,
                    average_response_time=response_time
                )
                return content
            elif response and response.status_code == 403:
                # Skip 403 errors - URL stays pending for retry later
                logger.debug(f"Skipping 403 for {url} - will retry later")
                return None
            elif response:
                logger.warning(f"HTTP {response.status_code} for {url}")
                self._update_stats(failed_urls=1)
                return None
            else:
                self._update_stats(failed_urls=1)
                return None
                
        except Exception as e:
            logger.error(f"Async fetch error for {url}: {e}")
            self._update_stats(failed_urls=1)
            return None

    def _fetch_sync_optimized(self, url: str) -> Optional[str]:
        """Enhanced sync fetch using SendGetRequests from utils.py (proven to work)"""
        try:
            from utils import SendGetRequests
            
            start_time = time.time()
            
            # Use SendGetRequests which is proven to work with IndiaMART
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            response = SendGetRequests(url, headers, use_proxy=True, max_403_retries=1)
            
            if response and response.status_code == 200:
                content = response.text
                response_time = time.time() - start_time
                self._update_stats(
                    successful_urls=1,
                    average_response_time=response_time
                )
                return content
            elif response and response.status_code == 403:
                # Skip 403 errors - URL stays pending for retry later
                logger.debug(f"Skipping 403 for {url} - will retry later")
                return None
            elif response:
                logger.warning(f"HTTP {response.status_code} for {url}")
                self._update_stats(failed_urls=1)
                return None
            else:
                self._update_stats(failed_urls=1)
                return None
                
        except Exception as e:
            logger.error(f"Sync fetch error for {url}: {e}")
            self._update_stats(failed_urls=1)
            return None

    def _scrape_urls_batch(self, urls: List[Dict]) -> List[Tuple[str, bool, str]]:
        """Process URLs using ThreadPoolExecutor - simple and reliable"""
        if not urls:
            return []
        
        logger.info(f"Starting to process batch of {len(urls)} URLs")
        
        from utils import SendGetRequests
        
        processed_results = []
        success_count = 0
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        
        # Process URLs one by one
        for idx, url_data in enumerate(urls):
            if self.should_stop:
                logger.info("Stop requested, breaking loop")
                break
            
            url = url_data.get('product_url') or url_data.get('url')
            if not url:
                logger.warning(f"No URL found in url_data at index {idx}")
                continue
            
            try:
                logger.info(f"[{idx+1}/{len(urls)}] Fetching: {url[:70]}...")
                response = SendGetRequests(url, headers, use_proxy=True, max_403_retries=1)
                
                if response and response.status_code == 200:
                    logger.info(f"[{idx+1}] Got 200, processing...")
                    success = self._process_product_content_sync(response.text, url, url_data)
                    if success:
                        success_count += 1
                        logger.info(f"[{idx+1}] ✓ Success! Total: {success_count}")
                    else:
                        logger.warning(f"[{idx+1}] Processing returned False")
                    processed_results.append((url, success, "OK"))
                elif response and response.status_code == 403:
                    logger.info(f"[{idx+1}] Got 403, skipping (will retry later)")
                    processed_results.append((url, False, "403"))
                else:
                    status = response.status_code if response else "None"
                    logger.info(f"[{idx+1}] Got {status}, skipping")
                    processed_results.append((url, False, f"Status {status}"))
                
                self._update_stats(processed_urls=1)
                
                # Small delay between requests to avoid rate limiting
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"[{idx+1}] Error: {e}", exc_info=True)
                processed_results.append((url, False, str(e)))
                self._update_stats(processed_urls=1, failed_urls=1)
        
        logger.info(f"Batch complete: {len(processed_results)}/{len(urls)} processed, {success_count} successful")
        return processed_results
    
    def _process_product_content_sync(self, content: str, product_url: str, url_data: Dict) -> bool:
        """Sync version of product content processing"""
        try:
            logger.info(f"Parsing HTML content ({len(content)} bytes)...")
            soup = BeautifulSoup(content, 'html.parser')
            
            # Extract product information
            product_name = self._extract_product_name(soup)
            logger.info(f"Extracted product name: {product_name[:50] if product_name else 'None'}")
            
            if not product_name:
                logger.warning(f"No product name found for {product_url}")
                return False
            
            # Store product data
            product_data = {
                'url': product_url,
                'product_name': product_name,
                'category': url_data.get('category', 'Unknown'),
                'subcategory': url_data.get('subcategory', 'Unknown'),
                'scraped_at': datetime.now(),
                'scraper_id': self.scraper_id
            }
            
            # Store in database
            logger.info(f"Storing product: {product_name[:30]}...")
            self.db_manager.store_product(product_data)
            self._update_stats(products_found=1)
            logger.info(f"Product stored successfully!")
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing product content: {e}", exc_info=True)
            return False

    async def _process_product_content_async_optimized(self, content: str, product_url: str, url_data: Dict) -> bool:
        """Enhanced async product content processing"""
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # Extract product information
            product_name = self._extract_product_name(soup)
            if not product_name:
                return False
            
            # Extract seller URLs
            seller_urls = self._extract_seller_urls(soup, product_url)
            
            # Process sellers asynchronously if found
            if seller_urls:
                await self._process_sellers_async_optimized(seller_urls)
            
            # Store product data
            product_data = {
                'url': product_url,
                'product_name': product_name,
                'category': url_data.get('category', 'Unknown'),
                'subcategory': url_data.get('subcategory', 'Unknown'),
                'seller_count': len(seller_urls),
                'scraped_at': datetime.now(),
                'scraper_id': self.scraper_id
            }
            
            # Store in database
            self.db_manager.store_product(product_data)
            self._update_stats(products_found=1)
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing product content: {e}")
            return False

    async def _process_sellers_async_optimized(self, seller_urls: List[str]):
        """Enhanced async seller processing using proven SendGetRequests"""
        if not seller_urls:
            return
        
        # Process sellers with limited concurrency
        semaphore = asyncio.Semaphore(5)  # Limit to 5 concurrent seller requests
        
        async def fetch_seller(url):
            async with semaphore:
                if self.should_stop:
                    return
                
                try:
                    content = await self._fetch_async_optimized(url)
                    
                    if content:
                        soup = BeautifulSoup(content, 'html.parser')
                        seller_name = self._extract_seller_name(soup)
                        company_name = self._extract_company_name(soup)
                        
                        if seller_name or company_name:
                            seller_data = {
                                'url': url,
                                'seller_name': seller_name,
                                'company_name': company_name,
                                'scraped_at': datetime.now(),
                                'scraper_id': self.scraper_id
                            }
                            
                            self.db_manager.store_seller(seller_data)
                            self._update_stats(sellers_found=1)
                            
                except Exception as e:
                    logger.error(f"Error processing seller {url}: {e}")
        
        # Process all sellers concurrently
        tasks = [fetch_seller(url) for url in seller_urls]
        await asyncio.gather(*tasks, return_exceptions=True)

    @with_state_sync("indiamart_scraper")
    async def run_async_optimized(self):
        """Enhanced async main execution with state synchronization"""
        try:
            self.running = True
            self.should_stop = False
            self.stats['start_time'] = datetime.now()
            
            logger.info("Starting enhanced IndiaMART scraper with maximum performance optimization")
            
            # Update state to running
            self.state_synchronizer.update_scraper_state(self.scraper_id, ScraperState.RUNNING)
            
            # Get URLs to scrape
            urls = self.db_manager.get_urls_to_scrape()
            if not urls:
                logger.warning("No URLs found to scrape")
                return
            
            self.stats['total_urls'] = len(urls)
            logger.info(f"Found {len(urls)} URLs to scrape")
            
            # Process URLs in optimized batches
            batch_size = self.config.batch_size
            
            for i in range(0, len(urls), batch_size):
                if self.should_stop:
                    logger.info("Stopping scraper as requested")
                    break
                
                batch = urls[i:i + batch_size]
                logger.info(f"Processing batch {i//batch_size + 1}/{(len(urls) + batch_size - 1)//batch_size}")
                
                # Process batch (sync method - simpler and more reliable)
                self._scrape_urls_batch(batch)
                
                # Log progress
                self._log_progress()
            
            self.stats['end_time'] = datetime.now()
            logger.info("Enhanced scraping completed successfully")
            
        except Exception as e:
            logger.error(f"Error in enhanced async scraper: {e}")
            self.state_synchronizer.update_scraper_state(
                self.scraper_id, 
                ScraperState.ERROR, 
                error_message=str(e)
            )
            raise
        finally:
            self.running = False
            self._cleanup_optimized()

    def run_sync_optimized(self):
        """Enhanced sync execution wrapper"""
        try:
            self.running = True
            self.should_stop = False
            self.stats['start_time'] = datetime.now()
            
            logger.info("Starting enhanced IndiaMART scraper (sync mode)")
            
            # Update state to running
            self.state_synchronizer.update_scraper_state(self.scraper_id, ScraperState.RUNNING)
            
            # Get URLs to scrape
            urls = self.db_manager.get_urls_to_scrape()
            if not urls:
                logger.warning("No URLs found to scrape")
                return
            
            self.stats['total_urls'] = len(urls)
            logger.info(f"Found {len(urls)} URLs to scrape")
            
            # Process URLs in batches using sync methods
            batch_size = self.config.batch_size
            
            for i in range(0, len(urls), batch_size):
                if self.should_stop:
                    logger.info("Stopping scraper as requested")
                    break
                
                batch = urls[i:i + batch_size]
                logger.info(f"Processing batch {i//batch_size + 1}/{(len(urls) + batch_size - 1)//batch_size}")
                
                # Process batch synchronously with optimization
                self._scrape_urls_sync_batch_optimized(batch)
                
                # Log progress
                self._log_progress()
                
                # Brief pause
                if not self.should_stop:
                    time.sleep(0.1)
            
            self.stats['end_time'] = datetime.now()
            logger.info("Enhanced sync scraping completed successfully")
            
        except Exception as e:
            logger.error(f"Error in enhanced sync scraper: {e}")
            self.state_synchronizer.update_scraper_state(
                self.scraper_id, 
                ScraperState.ERROR, 
                error_message=str(e)
            )
            raise
        finally:
            self.running = False
            self._cleanup_optimized()

    def _scrape_urls_sync_batch_optimized(self, urls: List[Dict]) -> List[Tuple[str, bool, str]]:
        """Enhanced sync batch processing"""
        if not urls:
            return []
        
        logger.info(f"Processing batch of {len(urls)} URLs synchronously with optimization")
        
        results = []
        
        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            # Submit all fetch tasks - MongoDB uses 'product_url' key
            future_to_url = {}
            for url_data in urls:
                if self.should_stop:
                    break
                url = url_data.get('product_url') or url_data.get('url')
                future = executor.submit(self._fetch_sync_optimized, url)
                future_to_url[future] = url_data
            
            # Process completed futures
            for future in future_to_url:
                if self.should_stop:
                    break
                
                url_data = future_to_url[future]
                url = url_data.get('product_url') or url_data.get('url')
                
                try:
                    content = future.result(timeout=self.config.request_timeout)
                    
                    if content:
                        success = self._process_product_content_sync_optimized(content, url, url_data)
                        results.append((url, success, "Success" if success else "Processing failed"))
                    else:
                        results.append((url, False, "Failed to fetch content"))
                    
                    self._update_stats(processed_urls=1)
                    
                except Exception as e:
                    logger.error(f"Error processing {url}: {e}")
                    results.append((url, False, f"Error: {str(e)}"))
                    self._update_stats(processed_urls=1, failed_urls=1)
        
        return results

    def _process_product_content_sync_optimized(self, content: str, product_url: str, url_data: Dict) -> bool:
        """Enhanced sync product content processing"""
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # Extract product information
            product_name = self._extract_product_name(soup)
            if not product_name:
                return False
            
            # Extract seller URLs
            seller_urls = self._extract_seller_urls(soup, product_url)
            
            # Process sellers synchronously if found
            if seller_urls:
                self._process_sellers_sync_optimized(seller_urls)
            
            # Store product data
            product_data = {
                'url': product_url,
                'product_name': product_name,
                'category': url_data.get('category', 'Unknown'),
                'subcategory': url_data.get('subcategory', 'Unknown'),
                'seller_count': len(seller_urls),
                'scraped_at': datetime.now(),
                'scraper_id': self.scraper_id
            }
            
            # Store in database
            self.db_manager.store_product(product_data)
            self._update_stats(products_found=1)
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing product content: {e}")
            return False

    def _process_sellers_sync_optimized(self, seller_urls: List[str]):
        """Enhanced sync seller processing"""
        if not seller_urls:
            return
        
        # Use ThreadPoolExecutor for parallel seller processing
        with ThreadPoolExecutor(max_workers=min(20, len(seller_urls))) as executor:
            future_to_url = {
                executor.submit(self._fetch_sync_optimized, url): url 
                for url in seller_urls
            }
            
            for future in future_to_url:
                if self.should_stop:
                    break
                
                url = future_to_url[future]
                
                try:
                    content = future.result(timeout=self.config.request_timeout)
                    
                    if content:
                        soup = BeautifulSoup(content, 'html.parser')
                        seller_name = self._extract_seller_name(soup)
                        company_name = self._extract_company_name(soup)
                        
                        if seller_name or company_name:
                            seller_data = {
                                'url': url,
                                'seller_name': seller_name,
                                'company_name': company_name,
                                'scraped_at': datetime.now(),
                                'scraper_id': self.scraper_id
                            }
                            
                            self.db_manager.store_seller(seller_data)
                            self._update_stats(sellers_found=1)
                            
                except Exception as e:
                    logger.error(f"Error processing seller {url}: {e}")

    def run(self):
        """Main entry point - chooses optimal execution mode"""
        try:
            if self.config.async_enabled:
                # Run async version for maximum performance
                asyncio.run(self.run_async_optimized())
            else:
                # Run sync version
                self.run_sync_optimized()
        except Exception as e:
            logger.error(f"Error in main run method: {e}")
            self.state_synchronizer.update_scraper_state(
                self.scraper_id, 
                ScraperState.ERROR, 
                error_message=str(e)
            )
            raise

    def stop(self):
        """Enhanced stop method with immediate state synchronization"""
        logger.info(f"Stop requested for scraper {self.scraper_id}")
        self.should_stop = True
        self.state_synchronizer.update_scraper_state(self.scraper_id, ScraperState.STOPPING)

    def _log_progress(self):
        """Enhanced progress logging with performance metrics"""
        if self.stats['total_urls'] > 0:
            progress = (self.stats['processed_urls'] / self.stats['total_urls']) * 100
            
            # Calculate performance metrics
            if self.stats['start_time']:
                elapsed = (datetime.now() - self.stats['start_time']).total_seconds()
                rps = self.stats['processed_urls'] / max(elapsed, 1)
                self.stats['requests_per_second'] = rps
            
            # Calculate error rate
            if self.stats['processed_urls'] > 0:
                error_rate = (self.stats['failed_urls'] / self.stats['processed_urls']) * 100
                self.stats['error_rate'] = error_rate
            
            # Get performance stats from optimizer
            perf_stats = self.performance_optimizer.get_performance_stats()
            
            logger.info(
                f"Progress: {progress:.1f}% "
                f"({self.stats['processed_urls']}/{self.stats['total_urls']}) | "
                f"Products: {self.stats['products_found']} | "
                f"Sellers: {self.stats['sellers_found']} | "
                f"RPS: {self.stats['requests_per_second']:.2f} | "
                f"Cache Hit Rate: {perf_stats.get('cache_hit_rate', 0):.1f}% | "
                f"Error Rate: {self.stats['error_rate']:.1f}% | "
                f"Memory: {self.stats['memory_usage_mb']:.1f}MB"
            )

    def _cleanup_optimized(self):
        """Enhanced cleanup with state synchronization"""
        logger.info("Starting enhanced cleanup...")
        
        try:
            # Update state to stopped
            self.state_synchronizer.update_scraper_state(self.scraper_id, ScraperState.STOPPED)
            
            # Cleanup connection manager
            if hasattr(self, 'connection_manager'):
                asyncio.create_task(self.connection_manager.close_async_session())
            
            # Clear cache
            if hasattr(self, 'cache'):
                self.cache.clear_expired()
            
            # Remove from global registry
            with _scrapers_lock:
                _active_scrapers.pop(self.scraper_id, None)
            
            logger.info("Enhanced cleanup completed")
            
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

    def _extract_product_name(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract product name from HTML"""
        try:
            # Try multiple selectors for product name
            selectors = [
                'h1',
                '.product-name',
                '[data-testid="product-name"]',
                '.pdp-product-name'
            ]
            
            for selector in selectors:
                element = soup.select_one(selector)
                if element and element.get_text(strip=True):
                    return element.get_text(strip=True)
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting product name: {e}")
            return None
    
    def _extract_seller_urls(self, soup: BeautifulSoup, product_url: str) -> List[str]:
        """Extract seller URLs from product page"""
        try:
            seller_urls = []
            
            # Try multiple selectors for seller links
            selectors = [
                'a[href*="/company/"]',
                'a[href*="/seller/"]',
                '.seller-link',
                '[data-testid="seller-link"]'
            ]
            
            for selector in selectors:
                elements = soup.select(selector)
                for element in elements:
                    href = element.get('href')
                    if href:
                        # Convert relative URLs to absolute
                        if href.startswith('/'):
                            base_url = urlparse(product_url)
                            href = f"{base_url.scheme}://{base_url.netloc}{href}"
                        
                        if href not in seller_urls:
                            seller_urls.append(href)
            
            return seller_urls[:5]  # Limit to 5 sellers per product
            
        except Exception as e:
            logger.error(f"Error extracting seller URLs: {e}")
            return []
    
    def _extract_seller_name(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract seller name from seller page"""
        try:
            # Try multiple selectors for seller name
            selectors = [
                '.seller-name',
                '.company-contact-person',
                '[data-testid="seller-name"]',
                'h1',
                '.contact-person'
            ]
            
            for selector in selectors:
                element = soup.select_one(selector)
                if element and element.get_text(strip=True):
                    return element.get_text(strip=True)
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting seller name: {e}")
            return None
    
    def _extract_company_name(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract company name from seller page"""
        try:
            # Try multiple selectors for company name
            selectors = [
                '.company-name',
                '.seller-company',
                '[data-testid="company-name"]',
                'h2',
                '.business-name'
            ]
            
            for selector in selectors:
                element = soup.select_one(selector)
                if element and element.get_text(strip=True):
                    return element.get_text(strip=True)
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting company name: {e}")
            return None

