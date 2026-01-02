"""
SQLite Database Manager for IndiaMART Scraper
Handles URL management, tracking, and status updates with high-performance optimizations
"""

import sqlite3
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import pandas as pd
from contextlib import contextmanager
import threading
import queue
import time
from concurrent.futures import ThreadPoolExecutor
import hashlib

logger = logging.getLogger('indiamart_db')

class ConnectionPool:
    """High-performance SQLite connection pool"""
    
    def __init__(self, db_path: str, pool_size: int = 10):
        self.db_path = db_path
        self.pool_size = pool_size
        self.pool = queue.Queue(maxsize=pool_size)
        self.lock = threading.Lock()
        self._initialize_pool()
    
    def _initialize_pool(self):
        """Initialize connection pool"""
        for _ in range(self.pool_size):
            conn = sqlite3.connect(
                self.db_path, 
                timeout=30.0,
                check_same_thread=False,
                isolation_level=None  # Autocommit mode for better performance
            )
            conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrent access
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=10000")
            conn.execute("PRAGMA temp_store=MEMORY")
            conn.execute("PRAGMA mmap_size=268435456")  # 256MB
            self.pool.put(conn)
    
    @contextmanager
    def get_connection(self):
        """Get connection from pool"""
        conn = None
        try:
            conn = self.pool.get(timeout=10)
            yield conn
        finally:
            if conn:
                self.pool.put(conn)

class IndiamartDB:
    """High-performance SQLite database manager for IndiaMART scraper operations"""
    
    def __init__(self, db_path: str = "/data/data-extractor/indiamart.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        
        # Initialize connection pool
        self.pool = ConnectionPool(str(self.db_path), pool_size=15)
        
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
        
        self.init_database()
        
        # Start background buffer flush thread
        self._flush_thread = threading.Thread(target=self._background_flush, daemon=True)
        self._flush_thread.start()
    
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
    
    def init_database(self):
        """Initialize database tables with optimized schema"""
        with self.pool.get_connection() as conn:
            # Categories table with optimized schema
            conn.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY,
                    cat_name TEXT NOT NULL,
                    sub_cat TEXT,
                    cat_url TEXT NOT NULL UNIQUE,
                    created_at INTEGER DEFAULT (strftime('%s', 'now')),
                    updated_at INTEGER DEFAULT (strftime('%s', 'now'))
                )
            """)
            
            # Add url_hash column if it doesn't exist
            try:
                conn.execute("ALTER TABLE categories ADD COLUMN url_hash TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            
            # Product URLs table with optimized schema
            conn.execute("""
                CREATE TABLE IF NOT EXISTS product_urls (
                    id INTEGER PRIMARY KEY,
                    category TEXT NOT NULL,
                    subcategory TEXT,
                    category_url TEXT NOT NULL,
                    product_url TEXT NOT NULL UNIQUE,
                    status INTEGER DEFAULT 0,  -- 0=pending, 1=completed, 2=failed
                    scraped_at INTEGER NULL,
                    error_count INTEGER DEFAULT 0,
                    last_error TEXT NULL,
                    created_at INTEGER DEFAULT (strftime('%s', 'now')),
                    updated_at INTEGER DEFAULT (strftime('%s', 'now'))
                )
            """)
            
            # Add url_hash column if it doesn't exist
            try:
                conn.execute("ALTER TABLE product_urls ADD COLUMN url_hash TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            
            # Scraped products tracking with optimized schema
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scraped_products (
                    id INTEGER PRIMARY KEY,
                    product_url TEXT NOT NULL UNIQUE,
                    product_name TEXT,
                    category TEXT,
                    subcategory TEXT,
                    scraped_at INTEGER DEFAULT (strftime('%s', 'now')),
                    success INTEGER DEFAULT 1
                )
            """)
            
            # Add url_hash column if it doesn't exist
            try:
                conn.execute("ALTER TABLE scraped_products ADD COLUMN url_hash TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            
            # Scraped sellers tracking with optimized schema
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scraped_sellers (
                    id INTEGER PRIMARY KEY,
                    seller_url TEXT NOT NULL UNIQUE,
                    seller_name TEXT,
                    company_name TEXT,
                    scraped_at INTEGER DEFAULT (strftime('%s', 'now')),
                    success INTEGER DEFAULT 1
                )
            """)
            
            # Add url_hash column if it doesn't exist
            try:
                conn.execute("ALTER TABLE scraped_sellers ADD COLUMN url_hash TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            
            # Create optimized indexes (only if columns exist)
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_product_urls_status ON product_urls(status)",
                "CREATE INDEX IF NOT EXISTS idx_product_urls_category ON product_urls(category)",
                "CREATE INDEX IF NOT EXISTS idx_product_urls_created ON product_urls(created_at)",
                "CREATE INDEX IF NOT EXISTS idx_product_urls_compound ON product_urls(status, category)",
            ]
            
            # Try to create hash-based indexes only if columns exist
            try:
                conn.execute("SELECT url_hash FROM product_urls LIMIT 1")
                indexes.extend([
                    "CREATE INDEX IF NOT EXISTS idx_product_urls_hash ON product_urls(url_hash)",
                    "CREATE INDEX IF NOT EXISTS idx_scraped_products_hash ON scraped_products(url_hash)",
                    "CREATE INDEX IF NOT EXISTS idx_scraped_sellers_hash ON scraped_sellers(url_hash)",
                    "CREATE INDEX IF NOT EXISTS idx_categories_hash ON categories(url_hash)",
                ])
            except sqlite3.OperationalError:
                logger.info("Hash columns not available, skipping hash-based indexes")
            
            for index_sql in indexes:
                try:
                    conn.execute(index_sql)
                except sqlite3.OperationalError as e:
                    logger.warning(f"Could not create index: {e}")
            
            conn.commit()
            logger.info("High-performance database initialized successfully")
    
    def _get_url_hash(self, url: str) -> str:
        """Generate hash for URL for faster lookups"""
        return hashlib.md5(url.encode()).hexdigest()
    
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
        
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            inserted = 0
            
            # Prepare bulk data
            bulk_data = []
            for cat in categories_data:
                url_hash = self._get_url_hash(cat['cat_url'])
                bulk_data.append((
                    cat['cat_name'],
                    cat.get('sub_cat'),
                    cat['cat_url'],
                    url_hash
                ))
            
            try:
                cursor.executemany("""
                    INSERT OR IGNORE INTO categories (cat_name, sub_cat, cat_url, url_hash)
                    VALUES (?, ?, ?, ?)
                """, bulk_data)
                
                inserted = cursor.rowcount
                conn.commit()
                self._operation_stats['inserts'] += inserted
                
            except Exception as e:
                logger.error(f"Error in bulk category insert: {e}")
                conn.rollback()
            
            logger.info(f"Bulk inserted {inserted} new categories")
            return inserted
    
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
        
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            inserted = 0
            
            # Get existing URL hashes in bulk
            url_hashes = [self._get_url_hash(url_data['product_url']) for url_data in urls_data]
            
            # Check existing URLs in bulk
            placeholders = ','.join(['?' for _ in url_hashes])
            cursor.execute(f"""
                SELECT url_hash FROM product_urls WHERE url_hash IN ({placeholders})
                UNION
                SELECT url_hash FROM scraped_products WHERE url_hash IN ({placeholders})
            """, url_hashes + url_hashes)
            
            existing_hashes = {row[0] for row in cursor.fetchall()}
            
            # Prepare bulk insert data for new URLs only
            bulk_data = []
            for url_data in urls_data:
                url_hash = self._get_url_hash(url_data['product_url'])
                if url_hash not in existing_hashes:
                    bulk_data.append((
                        url_data['category'],
                        url_data.get('subcategory'),
                        url_data['category_url'],
                        url_data['product_url'],
                        url_hash
                    ))
            
            if bulk_data:
                try:
                    cursor.executemany("""
                        INSERT INTO product_urls 
                        (category, subcategory, category_url, product_url, url_hash)
                        VALUES (?, ?, ?, ?, ?)
                    """, bulk_data)
                    
                    inserted = cursor.rowcount
                    conn.commit()
                    self._operation_stats['inserts'] += inserted
                    
                except Exception as e:
                    logger.error(f"Error in bulk URL insert: {e}")
                    conn.rollback()
            
            skipped = len(urls_data) - inserted
            logger.info(f"Bulk inserted {inserted} new URLs, skipped {skipped} existing URLs")
            return inserted
    
    def get_pending_urls(self, limit: int = 1000, offset: int = 0) -> List[Dict]:
        """Get pending URLs with caching and optimized query"""
        cache_key = self._get_cache_key("pending_urls", limit, offset)
        cached_result = self._get_from_cache(cache_key, ttl_seconds=60)  # 1 minute cache
        
        if cached_result is not None:
            return cached_result
        
        with self.pool.get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, category, subcategory, category_url, product_url
                FROM product_urls 
                WHERE status = 'pending' 
                ORDER BY id 
                LIMIT ? OFFSET ?
            """, (limit, offset))
            
            result = [dict(row) for row in cursor.fetchall()]
            self._operation_stats['selects'] += 1
            
            # Cache result
            self._set_cache(cache_key, result)
            
            return result
    
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
        
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            
            # Separate successful and failed URLs
            success_urls = []
            failed_urls = []
            
            for product_url, success, error_msg in urls_status:
                url_hash = self._get_url_hash(product_url)
                if success:
                    success_urls.append((url_hash,))
                else:
                    failed_urls.append((error_msg, url_hash))
            
            try:
                # Batch update successful URLs
                if success_urls:
                    cursor.executemany("""
                        UPDATE product_urls 
                        SET status = 'scraped', scraped_at = strftime('%s', 'now'), 
                            updated_at = strftime('%s', 'now')
                        WHERE url_hash = ?
                    """, success_urls)
                
                # Batch update failed URLs
                if failed_urls:
                    cursor.executemany("""
                        UPDATE product_urls 
                        SET status = 'failed', error_count = error_count + 1, 
                            last_error = ?, updated_at = strftime('%s', 'now')
                        WHERE url_hash = ?
                    """, failed_urls)
                
                conn.commit()
                self._operation_stats['updates'] += len(urls_status)
                
                # Clear relevant cache entries
                with self._cache_lock:
                    keys_to_remove = [k for k in self._cache.keys() if 'pending_urls' in k]
                    for key in keys_to_remove:
                        del self._cache[key]
                        del self._cache_ttl[key]
                
            except Exception as e:
                logger.error(f"Error in batch URL update: {e}")
                conn.rollback()
    
    def get_scraped_products_set(self) -> set:
        """Get set of scraped product URLs with caching"""
        cache_key = self._get_cache_key("scraped_products_set")
        cached_result = self._get_from_cache(cache_key, ttl_seconds=300)  # 5 minute cache
        
        if cached_result is not None:
            return cached_result
        
        with self.pool.get_connection() as conn:
            cursor = conn.execute("SELECT product_url FROM scraped_products")
            result = {row[0] for row in cursor.fetchall()}
            self._operation_stats['selects'] += 1
            
            # Cache result
            self._set_cache(cache_key, result)
            
            return result
    
    def get_scraped_sellers_set(self) -> set:
        """Get set of scraped seller URLs with caching"""
        cache_key = self._get_cache_key("scraped_sellers_set")
        cached_result = self._get_from_cache(cache_key, ttl_seconds=300)  # 5 minute cache
        
        if cached_result is not None:
            return cached_result
        
        with self.pool.get_connection() as conn:
            cursor = conn.execute("SELECT seller_url FROM scraped_sellers")
            result = {row[0] for row in cursor.fetchall()}
            self._operation_stats['selects'] += 1
            
            # Cache result
            self._set_cache(cache_key, result)
            
            return result
    
    def add_scraped_product(self, product_url: str, product_name: str = None, 
                           category: str = None, subcategory: str = None):
        """Add scraped product with optimized insertion"""
        url_hash = self._get_url_hash(product_url)
        
        with self.pool.get_connection() as conn:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO scraped_products 
                    (product_url, url_hash, product_name, category, subcategory)
                    VALUES (?, ?, ?, ?, ?)
                """, (product_url, url_hash, product_name, category, subcategory))
                
                conn.commit()
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
        
        with self.pool.get_connection() as conn:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO scraped_sellers 
                    (seller_url, url_hash, seller_name, company_name)
                    VALUES (?, ?, ?, ?)
                """, (seller_url, url_hash, seller_name, company_name))
                
                conn.commit()
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
        cached_result = self._get_from_cache(cache_key, ttl_seconds=600)  # 10 minute cache
        
        if cached_result is not None:
            return cached_result
        
        with self.pool.get_connection() as conn:
            cursor = conn.execute("""
                SELECT cat_name, sub_cat, cat_url 
                FROM categories 
                ORDER BY id
            """)
            
            result = [dict(row) for row in cursor.fetchall()]
            self._operation_stats['selects'] += 1
            
            # Cache result
            self._set_cache(cache_key, result)
            
            return result
    
    def get_statistics(self) -> Dict:
        """Get database statistics with caching"""
        cache_key = self._get_cache_key("statistics")
        cached_result = self._get_from_cache(cache_key, ttl_seconds=60)  # 1 minute cache
        
        if cached_result is not None:
            return cached_result
        
        with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get counts efficiently
            cursor.execute("SELECT COUNT(*) FROM product_urls")
            total_urls = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM product_urls WHERE status = 'pending'")
            pending_urls = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM product_urls WHERE status = 'scraped'")
            completed_urls = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM categories")
            total_categories = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM scraped_products")
            scraped_products = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM scraped_sellers")
            scraped_sellers = cursor.fetchone()[0]
            
            result = {
                'total_urls': total_urls,
                'pending_urls': pending_urls,
                'completed_urls': completed_urls,
                'failed_urls': total_urls - pending_urls - completed_urls,
                'total_categories': total_categories,
                'scraped_products': scraped_products,
                'scraped_sellers': scraped_sellers,
                'cache_hit_rate': (self._operation_stats['cache_hits'] / 
                                 max(1, self._operation_stats['cache_hits'] + self._operation_stats['cache_misses'])) * 100,
                'operation_stats': self._operation_stats.copy()
            }
            
            self._operation_stats['selects'] += 6
            
            # Cache result
            self._set_cache(cache_key, result)
            
            return result
    
    def cleanup_old_failed_urls(self, max_error_count: int = 5, days_old: int = 7):
        """Clean up old failed URLs to prevent database bloat"""
        cutoff_timestamp = int(time.time()) - (days_old * 24 * 60 * 60)
        
        with self.pool.get_connection() as conn:
            cursor = conn.execute("""
                DELETE FROM product_urls 
                WHERE status = 'failed' 
                AND error_count >= ? 
                AND updated_at < ?
            """, (max_error_count, cutoff_timestamp))
            
            deleted = cursor.rowcount
            conn.commit()
            
            logger.info(f"Cleaned up {deleted} old failed URLs")
            return deleted
    
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

    def migrate_from_csv(self, csv_files: Dict[str, str]):
        """Migrate existing CSV data to SQLite"""
        logger.info("Starting CSV to SQLite migration...")
        
        # Migrate categories
        if 'category_urls' in csv_files and Path(csv_files['category_urls']).exists():
            try:
                df = pd.read_csv(csv_files['category_urls'])
                categories_data = df.to_dict('records')
                self.insert_categories(categories_data)
            except Exception as e:
                logger.error(f"Error migrating categories: {e}")
        
        # Migrate product URLs
        if 'product_urls' in csv_files and Path(csv_files['product_urls']).exists():
            try:
                df = pd.read_csv(csv_files['product_urls'], 
                               names=['category', 'subcategory', 'category_url', 'product_url'],
                               header=None)
                urls_data = df.to_dict('records')
                self.insert_product_urls(urls_data)
            except Exception as e:
                logger.error(f"Error migrating product URLs: {e}")
        
        # Migrate scraped products
        if 'scraped_products' in csv_files and Path(csv_files['scraped_products']).exists():
            try:
                df = pd.read_csv(csv_files['scraped_products'])
                # Handle both single column and multi-column CSV formats
                if 'product_url' in df.columns:
                    for _, row in df.iterrows():
                        self.add_scraped_product(
                            row['product_url'],
                            row.get('product_name'),
                            row.get('category'),
                            row.get('subcategory')
                        )
                else:
                    # Assume first column is URL
                    for url in df.iloc[:, 0]:
                        if url and str(url).strip():
                            self.add_scraped_product(str(url).strip())
            except Exception as e:
                logger.error(f"Error migrating scraped products: {e}")
        
        # Migrate scraped sellers
        if 'scraped_sellers' in csv_files and Path(csv_files['scraped_sellers']).exists():
            try:
                df = pd.read_csv(csv_files['scraped_sellers'])
                # Handle both single column and multi-column CSV formats
                if 'seller_url' in df.columns:
                    for _, row in df.iterrows():
                        self.add_scraped_seller(
                            row['seller_url'],
                            row.get('seller_name'),
                            row.get('company_name')
                        )
                else:
                    # Assume first column is URL
                    for url in df.iloc[:, 0]:
                        if url and str(url).strip():
                            self.add_scraped_seller(str(url).strip())
            except Exception as e:
                logger.error(f"Error migrating scraped sellers: {e}")
        
        logger.info("CSV to SQLite migration completed")
        return self.get_statistics()

    def export_categories_to_csv(self, csv_file_path: str) -> int:
        """Export categories from SQLite database to CSV file"""
        try:
            with self.get_connection() as conn:
                # Query all categories from database
                df = pd.read_sql_query("""
                    SELECT cat_name, sub_cat, cat_url 
                    FROM categories 
                    ORDER BY created_at
                """, conn)
                
                if not df.empty:
                    # Ensure the directory exists
                    Path(csv_file_path).parent.mkdir(parents=True, exist_ok=True)
                    
                    # Export to CSV
                    df.to_csv(csv_file_path, index=False)
                    logger.info(f"Exported {len(df)} categories to {csv_file_path}")
                    return len(df)
                else:
                    logger.warning("No categories found in database to export")
                    return 0
                    
        except Exception as e:
            logger.error(f"Error exporting categories to CSV: {e}")
            return 0

    def get_categories(self) -> List[Dict]:
        """Get all categories directly from SQLite database"""
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT cat_name, sub_cat, cat_url 
                    FROM categories 
                    ORDER BY created_at
                """)
                
                categories = []
                for row in cursor.fetchall():
                    categories.append({
                        'cat_name': row[0],
                        'sub_cat': row[1],
                        'cat_url': row[2]
                    })
                
                logger.info(f"Retrieved {len(categories)} categories from database")
                return categories
                
        except Exception as e:
            logger.error(f"Error retrieving categories from database: {e}")
            return []