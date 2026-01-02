"""
High-Performance Scraper Optimization Module
Provides advanced performance optimizations for all scrapers in the data-extractor system
"""

import asyncio
import aiohttp
import time
import threading
import queue
import logging
import psutil
import gc
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import ssl
import certifi
from urllib.parse import urlparse
import hashlib
import json
import os
from datetime import datetime, timedelta

# Import curl_cffi for bypassing bot detection
try:
    from curl_cffi import requests as curl_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False
    curl_requests = None

logger = logging.getLogger('performance_optimizer')

@dataclass
class PerformanceConfig:
    """Advanced performance configuration"""
    # Connection settings
    max_workers: int = 100
    max_concurrent_requests: int = 200
    connection_pool_size: int = 500
    connection_timeout: int = 10
    read_timeout: int = 30
    
    # Batch processing
    batch_size: int = 5000
    chunk_size: int = 1000
    
    # Rate limiting
    rate_limit_delay: float = 0.005  # 5ms between requests
    burst_limit: int = 50
    
    # Retry settings
    max_retries: int = 3
    backoff_factor: float = 0.2
    retry_statuses: List[int] = field(default_factory=lambda: [429, 500, 502, 503, 504])
    
    # Caching
    cache_ttl: int = 7200  # 2 hours
    max_cache_size: int = 100000
    
    # Memory management
    memory_threshold: float = 0.85  # 85% memory usage threshold
    gc_frequency: int = 1000  # Run GC every N operations
    
    # Async settings
    async_enabled: bool = True
    semaphore_limit: int = 100
    
    # Compression and optimization
    enable_compression: bool = True
    enable_keep_alive: bool = True
    enable_http2: bool = True

class AdvancedConnectionPool:
    """High-performance connection pool with intelligent session management"""
    
    def __init__(self, config: PerformanceConfig):
        self.config = config
        self.session_pool = queue.Queue(maxsize=config.connection_pool_size)
        self.pool_lock = threading.Lock()
        self.session_stats = {}
        self.created_sessions = 0
        
        # Initialize session pool
        self._initialize_pool()
        
        # Async session management
        self.async_connector = None
        self.async_session = None
        
    def _initialize_pool(self):
        """Initialize the connection pool with optimized sessions"""
        for _ in range(min(50, self.config.connection_pool_size)):  # Start with 50 sessions
            session = self._create_optimized_session()
            self.session_pool.put(session)
    
    def _create_optimized_session(self) -> requests.Session:
        """Create a highly optimized requests session"""
        session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=self.config.max_retries,
            backoff_factor=self.config.backoff_factor,
            status_forcelist=self.config.retry_statuses,
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
        )
        
        # Configure adapter with connection pooling
        adapter = HTTPAdapter(
            pool_connections=20,
            pool_maxsize=50,
            max_retries=retry_strategy,
            pool_block=False
        )
        
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Set headers for optimization
        session.headers.update({
            'User-Agent': self._get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate' if self.config.enable_compression else 'identity',
            'Connection': 'keep-alive' if self.config.enable_keep_alive else 'close',
            'Upgrade-Insecure-Requests': '1',
        })
        
        # Configure timeouts
        session.timeout = (self.config.connection_timeout, self.config.read_timeout)
        
        self.created_sessions += 1
        return session
    
    def _get_random_user_agent(self) -> str:
        """Get a random user agent for better success rates"""
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0'
        ]
        import random
        return random.choice(user_agents)
    
    def get_session(self) -> requests.Session:
        """Get a session from the pool"""
        try:
            return self.session_pool.get_nowait()
        except queue.Empty:
            # Pool is empty, create new session
            return self._create_optimized_session()
    
    def return_session(self, session: requests.Session):
        """Return a session to the pool"""
        try:
            self.session_pool.put_nowait(session)
        except queue.Full:
            # Pool is full, close the session
            session.close()
    
    @asynccontextmanager
    async def get_async_session(self):
        """Get an async session with optimized connector"""
        if not self.async_session:
            # Create optimized connector
            connector = aiohttp.TCPConnector(
                limit=self.config.connection_pool_size,
                limit_per_host=50,
                ttl_dns_cache=300,
                use_dns_cache=True,
                keepalive_timeout=30,
                enable_cleanup_closed=True,
                ssl=ssl.create_default_context(cafile=certifi.where())
            )
            
            # Create session with optimized settings
            timeout = aiohttp.ClientTimeout(
                total=self.config.read_timeout,
                connect=self.config.connection_timeout
            )
            
            self.async_session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={
                    'User-Agent': self._get_random_user_agent(),
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Encoding': 'gzip, deflate' if self.config.enable_compression else 'identity',
                }
            )
        
        try:
            yield self.async_session
        finally:
            pass  # Keep session alive for reuse
    
    async def close_async_session(self):
        """Close the async session"""
        if self.async_session:
            await self.async_session.close()
            self.async_session = None

class IntelligentCache:
    """High-performance caching system with LRU eviction and compression"""
    
    def __init__(self, config: PerformanceConfig):
        self.config = config
        self.cache = {}
        self.access_times = {}
        self.cache_lock = threading.RLock()
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'size': 0
        }
    
    def _get_cache_key(self, url: str) -> str:
        """Generate cache key from URL"""
        return hashlib.md5(url.encode()).hexdigest()
    
    def get(self, url: str) -> Optional[str]:
        """Get cached content"""
        key = self._get_cache_key(url)
        
        with self.cache_lock:
            if key in self.cache:
                content, timestamp = self.cache[key]
                
                # Check if cache entry is still valid
                if time.time() - timestamp < self.config.cache_ttl:
                    self.access_times[key] = time.time()
                    self.stats['hits'] += 1
                    return content
                else:
                    # Remove expired entry
                    del self.cache[key]
                    del self.access_times[key]
                    self.stats['size'] -= 1
            
            self.stats['misses'] += 1
            return None
    
    def set(self, url: str, content: str):
        """Cache content with LRU eviction"""
        key = self._get_cache_key(url)
        current_time = time.time()
        
        with self.cache_lock:
            # Check if we need to evict entries
            if len(self.cache) >= self.config.max_cache_size:
                self._evict_lru()
            
            self.cache[key] = (content, current_time)
            self.access_times[key] = current_time
            self.stats['size'] += 1
    
    def _evict_lru(self):
        """Evict least recently used entries"""
        if not self.access_times:
            return
        
        # Find oldest entries to evict (evict 10% of cache)
        evict_count = max(1, len(self.cache) // 10)
        sorted_keys = sorted(self.access_times.items(), key=lambda x: x[1])
        
        for key, _ in sorted_keys[:evict_count]:
            if key in self.cache:
                del self.cache[key]
                del self.access_times[key]
                self.stats['evictions'] += 1
                self.stats['size'] -= 1

class RateLimiter:
    """Intelligent rate limiter with burst support"""
    
    def __init__(self, config: PerformanceConfig):
        self.config = config
        self.last_request_time = 0
        self.request_times = []
        self.lock = threading.Lock()
    
    def wait_if_needed(self):
        """Wait if rate limit would be exceeded"""
        if self.config.rate_limit_delay <= 0:
            return
        
        with self.lock:
            current_time = time.time()
            
            # Clean old request times (older than 1 second)
            self.request_times = [t for t in self.request_times if current_time - t < 1.0]
            
            # Check burst limit
            if len(self.request_times) >= self.config.burst_limit:
                sleep_time = 1.0 - (current_time - self.request_times[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    current_time = time.time()
            
            # Check rate limit
            time_since_last = current_time - self.last_request_time
            if time_since_last < self.config.rate_limit_delay:
                sleep_time = self.config.rate_limit_delay - time_since_last
                time.sleep(sleep_time)
                current_time = time.time()
            
            self.last_request_time = current_time
            self.request_times.append(current_time)

class MemoryManager:
    """Intelligent memory management and garbage collection"""
    
    def __init__(self, config: PerformanceConfig):
        self.config = config
        self.operation_count = 0
        self.last_gc_time = time.time()
    
    def check_memory_usage(self) -> bool:
        """Check if memory usage is within limits"""
        try:
            memory_percent = psutil.virtual_memory().percent / 100.0
            return memory_percent < self.config.memory_threshold
        except:
            return True  # Assume OK if can't check
    
    def maybe_run_gc(self):
        """Run garbage collection if needed"""
        self.operation_count += 1
        
        if self.operation_count % self.config.gc_frequency == 0:
            if not self.check_memory_usage():
                logger.info("Running garbage collection due to high memory usage")
                gc.collect()
                self.last_gc_time = time.time()

class PerformanceOptimizer:
    """Main performance optimization coordinator"""
    
    def __init__(self, config: Optional[PerformanceConfig] = None):
        self.config = config or PerformanceConfig()
        self.connection_pool = AdvancedConnectionPool(self.config)
        self.cache = IntelligentCache(self.config)
        self.rate_limiter = RateLimiter(self.config)
        self.memory_manager = MemoryManager(self.config)
        
        # Performance tracking
        self.stats = {
            'requests_made': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'start_time': time.time(),
            'total_bytes_downloaded': 0,
            'average_response_time': 0.0
        }
        self.stats_lock = threading.Lock()
        
        logger.info(f"Performance optimizer initialized with {self.config.max_workers} workers")
    
    def update_stats(self, **kwargs):
        """Thread-safe stats update"""
        with self.stats_lock:
            for key, value in kwargs.items():
                if key in self.stats:
                    if key == 'average_response_time':
                        # Calculate running average
                        current_avg = self.stats[key]
                        request_count = self.stats['requests_made']
                        if request_count > 0:
                            self.stats[key] = ((current_avg * (request_count - 1)) + value) / request_count
                        else:
                            self.stats[key] = value
                    else:
                        self.stats[key] += value
    
    async def fetch_async(self, url: str, **kwargs) -> Optional[str]:
        """High-performance async fetch using curl_cffi to bypass bot detection"""
        start_time = time.time()
        
        try:
            # Check cache first
            cached_content = self.cache.get(url)
            if cached_content:
                self.update_stats(cache_hits=1)
                return cached_content
            
            # Apply rate limiting
            self.rate_limiter.wait_if_needed()
            
            # Use curl_cffi in a thread pool for async compatibility
            if CURL_CFFI_AVAILABLE:
                loop = asyncio.get_event_loop()
                content = await loop.run_in_executor(
                    None,
                    lambda: self._fetch_with_curl_cffi(url)
                )
                
                if content:
                    # Cache the content
                    self.cache.set(url, content)
                    
                    # Update stats
                    response_time = time.time() - start_time
                    content_length = len(content.encode('utf-8'))
                    
                    self.update_stats(
                        requests_made=1,
                        successful_requests=1,
                        cache_misses=1,
                        total_bytes_downloaded=content_length,
                        average_response_time=response_time
                    )
                    
                    # Memory management
                    self.memory_manager.maybe_run_gc()
                    
                    return content
                else:
                    self.update_stats(requests_made=1, failed_requests=1)
                    return None
            else:
                # Fallback to aiohttp
                async with self.connection_pool.get_async_session() as session:
                    async with session.get(url, **kwargs) as response:
                        if response.status == 200:
                            content = await response.text()
                            
                            # Cache the content
                            self.cache.set(url, content)
                            
                            # Update stats
                            response_time = time.time() - start_time
                            content_length = len(content.encode('utf-8'))
                            
                            self.update_stats(
                                requests_made=1,
                                successful_requests=1,
                                cache_misses=1,
                                total_bytes_downloaded=content_length,
                                average_response_time=response_time
                            )
                            
                            # Memory management
                            self.memory_manager.maybe_run_gc()
                            
                            return content
                        else:
                            self.update_stats(requests_made=1, failed_requests=1)
                            logger.warning(f"HTTP {response.status} for {url}")
                            return None
                        
        except Exception as e:
            self.update_stats(requests_made=1, failed_requests=1)
            logger.error(f"Async fetch error for {url}: {e}")
            return None
    
    def _fetch_with_curl_cffi(self, url: str) -> Optional[str]:
        """Fetch URL using curl_cffi with browser impersonation and proxy rotation"""
        try:
            from utils import get_proxies
            
            # Headers required for IndiaMART - matching the working SendGetRequests
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0',
            }
            
            max_retries = 5  # Increased retries to match utils.py
            for retry in range(max_retries):
                try:
                    auth, proxy = get_proxies()
                    response = curl_requests.get(
                        url,
                        headers=headers,
                        impersonate="chrome131",
                        timeout=self.config.read_timeout,
                        proxies=proxy
                    )
                    
                    if response.status_code == 200:
                        return response.text
                    elif response.status_code == 403 and retry < max_retries - 1:
                        # Try with different proxy
                        logger.info(f"Got 403 for {url}, trying different proxy (attempt {retry + 1}/{max_retries})")
                        continue
                    else:
                        logger.warning(f"HTTP {response.status_code} for {url}")
                        return None
                        
                except Exception as e:
                    if retry < max_retries - 1:
                        logger.info(f"Request failed for {url}, retrying: {e}")
                        continue
                    raise
                    
            return None
                
        except Exception as e:
            logger.error(f"curl_cffi fetch error for {url}: {e}")
            return None
    
    def fetch_sync(self, url: str, **kwargs) -> Optional[str]:
        """High-performance sync fetch using curl_cffi with proxy rotation"""
        start_time = time.time()
        
        try:
            # Check cache first
            cached_content = self.cache.get(url)
            if cached_content:
                self.update_stats(cache_hits=1)
                return cached_content
            
            # Apply rate limiting
            self.rate_limiter.wait_if_needed()
            
            # Use curl_cffi with proxy rotation
            if CURL_CFFI_AVAILABLE:
                try:
                    from utils import get_proxies
                    
                    # Headers required for IndiaMART
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'none',
                        'Sec-Fetch-User': '?1',
                        'Cache-Control': 'max-age=0',
                    }
                    
                    max_retries = 5  # Increased retries
                    for retry in range(max_retries):
                        try:
                            auth, proxy = get_proxies()
                            response = curl_requests.get(
                                url, 
                                headers=headers,
                                impersonate="chrome131",
                                timeout=self.config.read_timeout,
                                proxies=proxy,
                                **kwargs
                            )
                            
                            if response.status_code == 200:
                                content = response.text
                                
                                # Cache the content
                                self.cache.set(url, content)
                                
                                # Update stats
                                response_time = time.time() - start_time
                                content_length = len(content.encode('utf-8'))
                                
                                self.update_stats(
                                    requests_made=1,
                                    successful_requests=1,
                                    cache_misses=1,
                                    total_bytes_downloaded=content_length,
                                    average_response_time=response_time
                                )
                                
                                # Memory management
                                self.memory_manager.maybe_run_gc()
                                
                                return content
                            elif response.status_code == 403 and retry < max_retries - 1:
                                # Try with different proxy
                                logger.info(f"Got 403 for {url}, trying different proxy (attempt {retry + 1}/{max_retries})")
                                continue
                            else:
                                self.update_stats(requests_made=1, failed_requests=1)
                                logger.warning(f"HTTP {response.status_code} for {url}")
                                return None
                                
                        except Exception as e:
                            if retry < max_retries - 1:
                                logger.info(f"Request failed for {url}, retrying: {e}")
                                continue
                            raise
                    
                    return None
                        
                except Exception as e:
                    self.update_stats(requests_made=1, failed_requests=1)
                    logger.error(f"curl_cffi fetch error for {url}: {e}")
                    return None
            else:
                # Fallback to standard requests
                session = self.connection_pool.get_session()
                
                try:
                    response = session.get(url, **kwargs)
                    
                    if response.status_code == 200:
                        content = response.text
                        
                        # Cache the content
                        self.cache.set(url, content)
                        
                        # Update stats
                        response_time = time.time() - start_time
                        content_length = len(content.encode('utf-8'))
                        
                        self.update_stats(
                            requests_made=1,
                            successful_requests=1,
                            cache_misses=1,
                            total_bytes_downloaded=content_length,
                            average_response_time=response_time
                        )
                        
                        # Memory management
                        self.memory_manager.maybe_run_gc()
                        
                        return content
                    else:
                        self.update_stats(requests_made=1, failed_requests=1)
                        logger.warning(f"HTTP {response.status_code} for {url}")
                        return None
                        
                finally:
                    # Return session to pool
                    self.connection_pool.return_session(session)
                
        except Exception as e:
            self.update_stats(requests_made=1, failed_requests=1)
            logger.error(f"Sync fetch error for {url}: {e}")
            return None
    
    async def batch_fetch_async(self, urls: List[str], callback: Optional[Callable] = None) -> List[Tuple[str, Optional[str]]]:
        """Batch fetch URLs with optimal concurrency"""
        semaphore = asyncio.Semaphore(self.config.semaphore_limit)
        
        async def fetch_single(url: str):
            async with semaphore:
                content = await self.fetch_async(url)
                if callback:
                    await callback(url, content)
                return (url, content)
        
        # Execute all requests concurrently
        tasks = [fetch_single(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Batch fetch exception: {result}")
                processed_results.append(("unknown", None))
            else:
                processed_results.append(result)
        
        return processed_results
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics"""
        with self.stats_lock:
            runtime = time.time() - self.stats['start_time']
            
            return {
                'runtime_seconds': runtime,
                'requests_per_second': self.stats['requests_made'] / max(runtime, 1),
                'success_rate': (self.stats['successful_requests'] / max(self.stats['requests_made'], 1)) * 100,
                'cache_hit_rate': (self.cache.stats['hits'] / max(self.cache.stats['hits'] + self.cache.stats['misses'], 1)) * 100,
                'average_response_time': self.stats['average_response_time'],
                'total_bytes_downloaded': self.stats['total_bytes_downloaded'],
                'memory_usage_percent': psutil.virtual_memory().percent,
                'cache_size': self.cache.stats['size'],
                'active_sessions': self.connection_pool.created_sessions,
                **self.stats,
                **self.cache.stats
            }
    
    async def cleanup(self):
        """Cleanup resources"""
        await self.connection_pool.close_async_session()
        logger.info("Performance optimizer cleanup completed")

# Global optimizer instance
_global_optimizer = None
_optimizer_lock = threading.Lock()

def get_global_optimizer(config: Optional[PerformanceConfig] = None) -> PerformanceOptimizer:
    """Get or create global performance optimizer instance"""
    global _global_optimizer
    
    with _optimizer_lock:
        if _global_optimizer is None:
            _global_optimizer = PerformanceOptimizer(config)
        return _global_optimizer

def reset_global_optimizer():
    """Reset global optimizer (useful for testing)"""
    global _global_optimizer
    
    with _optimizer_lock:
        if _global_optimizer:
            asyncio.create_task(_global_optimizer.cleanup())
        _global_optimizer = None