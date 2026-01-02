"""
MongoDB Database Manager for IndiaMART Scraper
Handles URL management, tracking, and status updates with high-performance optimizations
Replaces SQLite with MongoDB for better scalability and performance
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pymongo import MongoClient, UpdateOne, ASCENDING, DESCENDING
from pymongo.errors import BulkWriteError, DuplicateKeyError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger('indiamart_mongodb')

class IndiamartMongoDB:
    """High-performance MongoDB manager for IndiaMART scraper operations"""
    
    def __init__(self, mongo_uri: str = None, db_name: str = None, enable_background_flush: bool = True):
        """
        Initialize MongoDB connection for IndiaMART scraper
        
        Args:
            mongo_uri: MongoDB connection URI (defaults to env MONGO_URI)
            db_name: Database name (defaults to 'indiamart_data')
            enable_background_flush: Enable background buffer flushing (default: True, set False for read-only operations)
        """
        self.mongo_uri = mongo_uri or os.getenv('MONGO_URI', 'mongodb://localhost:27017/?authSource=admin')
        self.db_name = db_name or 'indiamart_data'  # Dedicated database for IndiaMART
        
        # Initialize MongoDB client
        self.client = MongoClient(self.mongo_uri)
        self.db = self.client[self.db_name]
        
        # Collections
        self.categories_collection = self.db['categories']
        self.product_urls_collection = self.db['product_urls']
        self.scraped_products_collection = self.db['scraped_products']
        self.scraped_sellers_collection = self.db['scraped_sellers']
        
        # Cache for frequently accessed data
        self._cache = {}
        self._cache_lock = threading.Lock()
        self._cache_ttl = {}
        
        # Bulk operation buffers
        self._bulk_buffer_size = 1000
        self._category_buffer = []
        self._url_buffer = []
        self._buffer_lock = threading.Lock()
        
        # Performance tracking
        self._operation_stats = {
            'inserts': 0,
            'updates': 0,
            'selects': 0,
            'cache_hits': 0,
            'cache_misses': 0
        }
        
        # Initialize database indexes
        self.init_database()
        
        # Start background buffer flush thread only if enabled
        self._flush_thread = None
        self._enable_background_flush = enable_background_flush
        if enable_background_flush:
            self._flush_thread = threading.Thread(target=self._background_flush, daemon=True)
            self._flush_thread.start()
        
        logger.info(f"IndiaMART MongoDB initialized - Database: {self.db_name}, Background flush: {enable_background_flush}")
    
    def _background_flush(self):
        """Background thread to flush buffers periodically"""
        while True:
            try:
                time.sleep(5)  # Flush every 5 seconds
                self._flush_buffers()
            except Exception as e:
                logger.error(f"Error in background flush: {e}")
    
    def _flush_buffers(self):
        """Flush pending bulk operations"""
        with self._buffer_lock:
            if self._category_buffer:
                self._bulk_insert_categories(self._category_buffer)
                self._category_buffer.clear()
            
            if self._url_buffer:
                self._bulk_insert_urls(self._url_buffer)
                self._url_buffer.clear()
    
    def _get_cache_key(self, operation: str, *args) -> str:
        """Generate cache key for operation"""
        key_data = f"{operation}:{':'.join(map(str, args))}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _get_from_cache(self, key: str, ttl_seconds: int = 300):
        """Get data from cache if not expired"""
        with self._cache_lock:
            if key in self._cache:
                if time.time() - self._cache_ttl.get(key, 0) < ttl_seconds:
                    self._operation_stats['cache_hits'] += 1
                    return self._cache[key]
                else:
                    # Expired, remove from cache
                    del self._cache[key]
                    del self._cache_ttl[key]
            
            self._operation_stats['cache_misses'] += 1
            return None
    
    def _set_cache(self, key: str, value):
        """Set data in cache"""
        with self._cache_lock:
            self._cache[key] = value
            self._cache_ttl[key] = time.time()
    
    def _get_url_hash(self, url: str) -> str:
        """Generate hash for URL for faster lookups"""
        return hashlib.md5(url.encode()).hexdigest()
    
    def init_database(self):
        """Initialize database collections and indexes"""
        try:
            # Categories collection indexes
            self.categories_collection.create_index([('cat_url', ASCENDING)], unique=True, background=True)
            self.categories_collection.create_index([('url_hash', ASCENDING)], background=True)
            self.categories_collection.create_index([('cat_name', ASCENDING)], background=True)
            self.categories_collection.create_index([('created_at', DESCENDING)], background=True)
            
            # Product URLs collection indexes
            self.product_urls_collection.create_index([('product_url', ASCENDING)], unique=True, background=True)
            self.product_urls_collection.create_index([('url_hash', ASCENDING)], background=True)
            self.product_urls_collection.create_index([('status', ASCENDING)], background=True)
            self.product_urls_collection.create_index([('category', ASCENDING)], background=True)
            self.product_urls_collection.create_index([('status', ASCENDING), ('category', ASCENDING)], background=True)
            self.product_urls_collection.create_index([('created_at', DESCENDING)], background=True)
            
            # Scraped products collection indexes
            self.scraped_products_collection.create_index([('product_url', ASCENDING)], unique=True, background=True)
            self.scraped_products_collection.create_index([('url_hash', ASCENDING)], background=True)
            self.scraped_products_collection.create_index([('category', ASCENDING)], background=True)
            self.scraped_products_collection.create_index([('scraped_at', DESCENDING)], background=True)
            
            # Scraped sellers collection indexes
            # Use GST as unique identifier instead of seller_url (sellers don't have dedicated URLs)
            self.scraped_sellers_collection.create_index([('gst', ASCENDING)], unique=True, sparse=True, background=True)
            self.scraped_sellers_collection.create_index([('scraped_at', DESCENDING)], background=True)
            
            logger.info("MongoDB indexes created successfully")
            
        except Exception as e:
            logger.error(f"Error creating indexes: {e}")
    
    def insert_categories(self, categories_data: List[Dict]) -> int:
        """Insert category data with high-performance bulk operations"""
        if not categories_data:
            return 0
        
        # Add to buffer for bulk processing
        with self._buffer_lock:
            self._category_buffer.extend(categories_data)
            
            # If buffer is full, flush immediately
            if len(self._category_buffer) >= self._bulk_buffer_size:
                result = self._bulk_insert_categories(self._category_buffer)
                self._category_buffer.clear()
                return result
        
        return 0  # Will be processed in background
    
    def _bulk_insert_categories(self, categories_data: List[Dict]) -> int:
        """Bulk insert categories with optimized performance"""
        if not categories_data:
            return 0
        
        try:
            operations = []
            for cat in categories_data:
                url_hash = self._get_url_hash(cat['cat_url'])
                doc = {
                    'cat_name': cat['cat_name'],
                    'sub_cat': cat.get('sub_cat'),
                    'cat_url': cat['cat_url'],
                    'url_hash': url_hash,
                    'created_at': datetime.utcnow()
                }
                
                # Use update_one with upsert to avoid duplicates
                operations.append(
                    UpdateOne(
                        {'cat_url': cat['cat_url']},
                        {
                            '$setOnInsert': doc,
                            '$set': {'updated_at': datetime.utcnow()}
                        },
                        upsert=True
                    )
                )
            
            if operations:
                result = self.categories_collection.bulk_write(operations, ordered=False)
                inserted = result.upserted_count
                self._operation_stats['inserts'] += inserted
                logger.info(f"Bulk inserted {inserted} new categories")
                return inserted
            
        except BulkWriteError as e:
            # Some documents may have been inserted
            inserted = e.details.get('nInserted', 0)
            upserted = e.details.get('nUpserted', 0)
            total_success = inserted + upserted
            self._operation_stats['inserts'] += total_success
            
            # Log first few errors for debugging
            write_errors = e.details.get('writeErrors', [])
            if write_errors:
                logger.error(f"Bulk insert errors (showing first 3):")
                for error in write_errors[:3]:
                    logger.error(f"  - Code {error.get('code')}: {error.get('errmsg')}")
            
            logger.warning(f"Bulk insert with some errors: {total_success} inserted/upserted, {len(write_errors)} errors")
            return total_success
        except Exception as e:
            logger.error(f"Error in bulk category insert: {e}")
            return 0
    
    def insert_product_urls(self, urls_data: List[Dict]) -> int:
        """Insert product URLs with high-performance bulk operations"""
        if not urls_data:
            return 0
        
        # Add to buffer for bulk processing
        with self._buffer_lock:
            self._url_buffer.extend(urls_data)
            
            # If buffer is full, flush immediately
            if len(self._url_buffer) >= self._bulk_buffer_size:
                result = self._bulk_insert_urls(self._url_buffer)
                self._url_buffer.clear()
                return result
        
        return len(urls_data)  # Return count of URLs added to buffer
    
    def _bulk_insert_urls(self, urls_data: List[Dict]) -> int:
        """Bulk insert URLs with optimized duplicate checking"""
        if not urls_data:
            return 0
        
        try:
            # Get existing URL hashes in bulk
            url_hashes = [self._get_url_hash(url_data['product_url']) for url_data in urls_data]
            
            # Check existing URLs in both collections
            existing_in_urls = set(
                doc['url_hash'] for doc in 
                self.product_urls_collection.find(
                    {'url_hash': {'$in': url_hashes}},
                    {'url_hash': 1}
                )
            )
            
            existing_in_scraped = set(
                doc['url_hash'] for doc in 
                self.scraped_products_collection.find(
                    {'url_hash': {'$in': url_hashes}},
                    {'url_hash': 1}
                )
            )
            
            existing_hashes = existing_in_urls | existing_in_scraped
            
            # Prepare bulk insert data for new URLs only
            operations = []
            for url_data in urls_data:
                url_hash = self._get_url_hash(url_data['product_url'])
                if url_hash not in existing_hashes:
                    doc = {
                        'category': url_data['category'],
                        'subcategory': url_data.get('subcategory'),
                        'category_url': url_data['category_url'],
                        'product_url': url_data['product_url'],
                        'url_hash': url_hash,
                        'status': 'pending',
                        'scraped_at': None,
                        'error_count': 0,
                        'last_error': None,
                        'created_at': datetime.utcnow(),
                        'updated_at': datetime.utcnow()
                    }
                    
                    operations.append(
                        UpdateOne(
                            {'product_url': url_data['product_url']},
                            {'$setOnInsert': doc},
                            upsert=True
                        )
                    )
            
            if operations:
                result = self.product_urls_collection.bulk_write(operations, ordered=False)
                inserted = result.upserted_count
                self._operation_stats['inserts'] += inserted
                skipped = len(urls_data) - inserted
                logger.info(f"Bulk inserted {inserted} new URLs, skipped {skipped} existing URLs")
                return inserted
            else:
                logger.info(f"All {len(urls_data)} URLs already exist, skipped")
                return 0
            
        except BulkWriteError as e:
            inserted = e.details.get('nInserted', 0) + e.details.get('nUpserted', 0)
            self._operation_stats['inserts'] += inserted
            logger.warning(f"Bulk insert with some errors: {inserted} inserted")
            return inserted
        except Exception as e:
            logger.error(f"Error in bulk URL insert: {e}")
            return 0
    
    def get_pending_urls(self, limit: int = 1000, offset: int = 0) -> List[Dict]:
        """Get pending URLs with caching and optimized query"""
        cache_key = self._get_cache_key("pending_urls", limit, offset)
        cached_result = self._get_from_cache(cache_key, ttl_seconds=60)
        
        if cached_result is not None:
            return cached_result
        
        try:
            cursor = self.product_urls_collection.find(
                {'status': 'pending'},
                {'_id': 0, 'category': 1, 'subcategory': 1, 'category_url': 1, 'product_url': 1}
            ).sort('created_at', ASCENDING).skip(offset).limit(limit)
            
            result = list(cursor)
            self._operation_stats['selects'] += 1
            
            # Cache result
            self._set_cache(cache_key, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting pending URLs: {e}")
            return []
    
    def get_pending_urls_chunked(self, chunk_size: int = 1000):
        """Generator for chunked pending URLs with optimized memory usage"""
        offset = 0
        while True:
            urls = self.get_pending_urls(limit=chunk_size, offset=offset)
            if not urls:
                break
            yield urls
            offset += chunk_size
    
    def mark_urls_scraped_batch(self, urls_status: List[Tuple[str, bool, str]]):
        """Mark multiple URLs as scraped in optimized batch operation"""
        if not urls_status:
            return
        
        try:
            operations = []
            
            for product_url, success, error_msg in urls_status:
                url_hash = self._get_url_hash(product_url)
                
                if success:
                    operations.append(
                        UpdateOne(
                            {'url_hash': url_hash},
                            {
                                '$set': {
                                    'status': 'scraped',
                                    'scraped_at': datetime.utcnow(),
                                    'updated_at': datetime.utcnow()
                                }
                            }
                        )
                    )
                else:
                    operations.append(
                        UpdateOne(
                            {'url_hash': url_hash},
                            {
                                '$set': {
                                    'status': 'failed',
                                    'last_error': error_msg,
                                    'updated_at': datetime.utcnow()
                                },
                                '$inc': {'error_count': 1}
                            }
                        )
                    )
            
            if operations:
                result = self.product_urls_collection.bulk_write(operations, ordered=False)
                self._operation_stats['updates'] += result.modified_count
                
                # Clear relevant cache entries
                with self._cache_lock:
                    keys_to_remove = [k for k in self._cache.keys() if 'pending_urls' in k]
                    for key in keys_to_remove:
                        if key in self._cache:
                            del self._cache[key]
                            del self._cache_ttl[key]
                
        except Exception as e:
            logger.error(f"Error in batch URL update: {e}")
    
    def get_scraped_products_set(self) -> set:
        """Get set of scraped product URLs with caching"""
        cache_key = self._get_cache_key("scraped_products_set")
        cached_result = self._get_from_cache(cache_key, ttl_seconds=300)
        
        if cached_result is not None:
            return cached_result
        
        try:
            cursor = self.scraped_products_collection.find({}, {'product_url': 1})
            result = {doc['product_url'] for doc in cursor}
            self._operation_stats['selects'] += 1
            
            # Cache result
            self._set_cache(cache_key, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting scraped products set: {e}")
            return set()
    
    def get_scraped_sellers_set(self) -> set:
        """Get set of scraped seller URLs with caching"""
        cache_key = self._get_cache_key("scraped_sellers_set")
        cached_result = self._get_from_cache(cache_key, ttl_seconds=300)
        
        if cached_result is not None:
            return cached_result
        
        try:
            cursor = self.scraped_sellers_collection.find({}, {'seller_url': 1})
            result = {doc['seller_url'] for doc in cursor}
            self._operation_stats['selects'] += 1
            
            # Cache result
            self._set_cache(cache_key, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting scraped sellers set: {e}")
            return set()
    
    def add_scraped_product(self, product_url: str, product_name: str = None, 
                           category: str = None, subcategory: str = None):
        """Add scraped product with optimized insertion"""
        url_hash = self._get_url_hash(product_url)
        
        try:
            doc = {
                'product_url': product_url,
                'url_hash': url_hash,
                'product_name': product_name,
                'category': category,
                'subcategory': subcategory,
                'scraped_at': datetime.utcnow(),
                'success': True
            }
            
            self.scraped_products_collection.update_one(
                {'product_url': product_url},
                {'$setOnInsert': doc},
                upsert=True
            )
            
            self._operation_stats['inserts'] += 1
            
            # Clear cache
            cache_key = self._get_cache_key("scraped_products_set")
            with self._cache_lock:
                if cache_key in self._cache:
                    del self._cache[cache_key]
                    del self._cache_ttl[cache_key]
            
        except Exception as e:
            logger.error(f"Error adding scraped product: {e}")
    
    def add_scraped_seller(self, seller_url: str, seller_name: str = None, 
                          company_name: str = None):
        """Add scraped seller with optimized insertion"""
        url_hash = self._get_url_hash(seller_url)
        
        try:
            doc = {
                'seller_url': seller_url,
                'url_hash': url_hash,
                'seller_name': seller_name,
                'company_name': company_name,
                'scraped_at': datetime.utcnow(),
                'success': True
            }
            
            self.scraped_sellers_collection.update_one(
                {'seller_url': seller_url},
                {'$setOnInsert': doc},
                upsert=True
            )
            
            self._operation_stats['inserts'] += 1
            
            # Clear cache
            cache_key = self._get_cache_key("scraped_sellers_set")
            with self._cache_lock:
                if cache_key in self._cache:
                    del self._cache[cache_key]
                    del self._cache_ttl[cache_key]
            
        except Exception as e:
            logger.error(f"Error adding scraped seller: {e}")
    
    def get_categories(self) -> List[Dict]:
        """Get categories with caching"""
        cache_key = self._get_cache_key("categories")
        cached_result = self._get_from_cache(cache_key, ttl_seconds=600)
        
        if cached_result is not None:
            return cached_result
        
        try:
            cursor = self.categories_collection.find(
                {},
                {'_id': 0, 'cat_name': 1, 'sub_cat': 1, 'cat_url': 1}
            ).sort('created_at', ASCENDING)
            
            result = list(cursor)
            self._operation_stats['selects'] += 1
            
            # Cache result
            self._set_cache(cache_key, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting categories: {e}")
            return []
    
    def get_statistics(self) -> Dict:
        """Get database statistics with caching"""
        cache_key = self._get_cache_key("statistics")
        cached_result = self._get_from_cache(cache_key, ttl_seconds=60)
        
        if cached_result is not None:
            return cached_result
        
        try:
            # Get counts efficiently using count_documents
            total_urls = self.product_urls_collection.count_documents({})
            pending_urls = self.product_urls_collection.count_documents({'status': 'pending'})
            completed_urls = self.product_urls_collection.count_documents({'status': 'scraped'})
            failed_urls = self.product_urls_collection.count_documents({'status': 'failed'})
            total_categories = self.categories_collection.count_documents({})
            scraped_products = self.scraped_products_collection.count_documents({})
            scraped_sellers = self.scraped_sellers_collection.count_documents({})
            
            result = {
                'total_urls': total_urls,
                'pending_urls': pending_urls,
                'completed_urls': completed_urls,
                'failed_urls': failed_urls,
                'total_categories': total_categories,
                'scraped_products': scraped_products,
                'scraped_sellers': scraped_sellers,
                'cache_hit_rate': (self._operation_stats['cache_hits'] / 
                                 max(1, self._operation_stats['cache_hits'] + self._operation_stats['cache_misses'])) * 100,
                'operation_stats': self._operation_stats.copy()
            }
            
            self._operation_stats['selects'] += 7
            
            # Cache result
            self._set_cache(cache_key, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return {}
    
    def save_crawler_settings(self, max_workers: int, max_concurrent_requests: int, batch_size: int):
        """Save crawler configuration settings to MongoDB"""
        try:
            settings_collection = self.db['crawler_settings']
            
            settings_doc = {
                'max_workers': max_workers,
                'max_concurrent_requests': max_concurrent_requests,
                'batch_size': batch_size,
                'updated_at': datetime.utcnow()
            }
            
            # Upsert settings (update if exists, insert if not)
            settings_collection.update_one(
                {'_id': 'indiamart_crawler_config'},
                {'$set': settings_doc},
                upsert=True
            )
            
            # Clear cache so new settings are fetched
            cache_key = self._get_cache_key("crawler_settings")
            with self._cache_lock:
                if cache_key in self._cache:
                    del self._cache[cache_key]
                    del self._cache_ttl[cache_key]
            
            logger.info(f"Saved crawler settings: max_workers={max_workers}, max_concurrent_requests={max_concurrent_requests}, batch_size={batch_size}")
            
        except Exception as e:
            logger.error(f"Error saving crawler settings: {e}")
    
    def get_crawler_settings(self) -> Optional[Dict]:
        """Get crawler configuration settings from MongoDB with caching"""
        cache_key = self._get_cache_key("crawler_settings")
        cached_result = self._get_from_cache(cache_key, ttl_seconds=300)
        
        if cached_result is not None:
            return cached_result
        
        try:
            settings_collection = self.db['crawler_settings']
            settings = settings_collection.find_one({'_id': 'indiamart_crawler_config'})
            
            if settings:
                result = {
                    'max_workers': settings.get('max_workers', 150),
                    'max_concurrent_requests': settings.get('max_concurrent_requests', 300),
                    'batch_size': settings.get('batch_size', 1000),
                    'updated_at': settings.get('updated_at')
                }
                
                # Cache result
                self._set_cache(cache_key, result)
                
                return result
            else:
                # Return defaults if no settings found
                return {
                    'max_workers': 150,
                    'max_concurrent_requests': 300,
                    'batch_size': 1000
                }
            
        except Exception as e:
            logger.error(f"Error getting crawler settings: {e}")
            return None
    
    def cleanup_old_failed_urls(self, max_error_count: int = 5, days_old: int = 7):
        """Clean up old failed URLs to prevent database bloat"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days_old)
            
            result = self.product_urls_collection.delete_many({
                'status': 'failed',
                'error_count': {'$gte': max_error_count},
                'updated_at': {'$lt': cutoff_date}
            })
            
            deleted = result.deleted_count
            logger.info(f"Cleaned up {deleted} old failed URLs")
            return deleted
            
        except Exception as e:
            logger.error(f"Error cleaning up old failed URLs: {e}")
            return 0
    
    def force_flush_buffers(self):
        """Force flush all pending buffers"""
        self._flush_buffers()
    
    def get_performance_stats(self) -> Dict:
        """Get performance statistics"""
        return {
            'operation_stats': self._operation_stats.copy(),
            'cache_size': len(self._cache),
            'buffer_sizes': {
                'categories': len(self._category_buffer),
                'urls': len(self._url_buffer)
            }
        }
    
    def close(self):
        """Close MongoDB connection and cleanup"""
        try:
            # Flush any pending buffers
            self.force_flush_buffers()
            
            # Close MongoDB client
            self.client.close()
            logger.info("MongoDB connection closed")
            
        except Exception as e:
            logger.error(f"Error closing MongoDB connection: {e}")
    
    def get_urls_to_scrape(self, limit: int = 10000) -> List[Dict]:
        """
        Get pending product URLs to scrape
        Compatible with product scraper interface
        """
        return self.get_pending_urls(limit=limit)
    
    def store_product(self, product_data: Dict):
        """
        Store scraped product data
        Compatible with product scraper interface
        
        Args:
            product_data: Dictionary containing product information
        """
        try:
            product_url = product_data.get('url')
            if not product_url:
                logger.warning("Product data missing URL, skipping")
                return
            
            # Add to scraped products
            self.add_scraped_product(
                product_url=product_url,
                product_name=product_data.get('product_name'),
                category=product_data.get('category'),
                subcategory=product_data.get('subcategory')
            )
            
            # Mark URL as scraped
            self.mark_urls_scraped_batch([(product_url, True, "")])
            
        except Exception as e:
            logger.error(f"Error storing product: {e}")
    
    def store_seller(self, seller_data: Dict):
        """
        Store scraped seller data
        Compatible with product scraper interface
        
        Args:
            seller_data: Dictionary containing seller information
        """
        try:
            seller_url = seller_data.get('url')
            if not seller_url:
                logger.warning("Seller data missing URL, skipping")
                return
            
            # Add to scraped sellers
            self.add_scraped_seller(
                seller_url=seller_url,
                seller_name=seller_data.get('seller_name'),
                company_name=seller_data.get('company_name')
            )
            
        except Exception as e:
            logger.error(f"Error storing seller: {e}")


# Backward compatibility alias
IndiamartDB = IndiamartMongoDB
