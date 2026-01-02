#!/usr/bin/env python3
"""
Migration script to import product URLs from CSV to IndiaMART database
Handles duplicate detection and batch processing for large datasets
"""

import csv
import sqlite3
import hashlib
import logging
import time
from datetime import datetime
from pathlib import Path
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('migration.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class CSVToDBMigrator:
    def __init__(self, csv_file_path, db_path, batch_size=10000):
        self.csv_file_path = Path(csv_file_path)
        self.db_path = Path(db_path)
        self.batch_size = batch_size
        self.stats = {
            'total_rows': 0,
            'processed_rows': 0,
            'inserted_rows': 0,
            'duplicate_rows': 0,
            'error_rows': 0,
            'start_time': None,
            'end_time': None
        }
        
    def generate_url_hash(self, url):
        """Generate a hash for the URL to help with duplicate detection"""
        return hashlib.md5(url.encode('utf-8')).hexdigest()
    
    def connect_db(self):
        """Create database connection with optimizations for bulk insert"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=10000")
        conn.execute("PRAGMA temp_store=MEMORY")
        return conn
    
    def prepare_database(self):
        """Prepare database for migration - create indexes if needed"""
        conn = self.connect_db()
        try:
            # Check if url_hash column exists, add if not
            cursor = conn.execute("PRAGMA table_info(product_urls)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'url_hash' not in columns:
                logger.info("Adding url_hash column to product_urls table")
                conn.execute("ALTER TABLE product_urls ADD COLUMN url_hash TEXT")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_product_urls_hash ON product_urls(url_hash)")
                conn.commit()
            
            # Update existing records with url_hash if they don't have it
            cursor = conn.execute("SELECT COUNT(*) FROM product_urls WHERE url_hash IS NULL")
            null_hash_count = cursor.fetchone()[0]
            
            if null_hash_count > 0:
                logger.info(f"Updating {null_hash_count} existing records with url_hash")
                conn.execute("""
                    UPDATE product_urls 
                    SET url_hash = substr(
                        lower(hex(randomblob(16))), 1, 32
                    ) 
                    WHERE url_hash IS NULL
                """)
                conn.commit()
                
        except Exception as e:
            logger.error(f"Error preparing database: {e}")
            raise
        finally:
            conn.close()
    
    def count_csv_rows(self):
        """Count total rows in CSV file"""
        logger.info("Counting CSV rows...")
        with open(self.csv_file_path, 'r', encoding='utf-8') as file:
            # Use a more efficient counting method for large files
            row_count = sum(1 for _ in file)
        self.stats['total_rows'] = row_count
        logger.info(f"Total rows in CSV: {row_count:,}")
        return row_count
    
    def parse_csv_row(self, row):
        """Parse a CSV row and return structured data"""
        try:
            # CSV format: category, subcategory, category_url, product_url
            if len(row) >= 4:
                category = row[0].strip().strip('"')
                subcategory = row[1].strip() if row[1] else None
                category_url = row[2].strip()
                product_url = row[3].strip()
                
                # Generate URL hash
                url_hash = self.generate_url_hash(product_url)
                
                return {
                    'category': category,
                    'subcategory': subcategory,
                    'category_url': category_url,
                    'product_url': product_url,
                    'url_hash': url_hash,
                    'status': 'pending',
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat()
                }
            else:
                logger.warning(f"Invalid row format: {row}")
                return None
                
        except Exception as e:
            logger.error(f"Error parsing row {row}: {e}")
            return None
    
    def batch_insert(self, conn, batch_data):
        """Insert a batch of data with proper duplicate URL checking"""
        if not batch_data:
            return 0, 0
        
        inserted_count = 0
        duplicate_count = 0
        
        try:
            # First, remove duplicates within the batch itself
            seen_urls_in_batch = set()
            unique_batch_data = []
            
            for item in batch_data:
                if item['product_url'] not in seen_urls_in_batch:
                    seen_urls_in_batch.add(item['product_url'])
                    unique_batch_data.append(item)
                else:
                    duplicate_count += 1
            
            # Now check which URLs already exist in the database
            urls_to_check = [item['product_url'] for item in unique_batch_data]
            
            if not urls_to_check:
                return inserted_count, duplicate_count
            
            # Create placeholders for the IN clause
            placeholders = ','.join('?' * len(urls_to_check))
            check_sql = f"SELECT product_url FROM product_urls WHERE product_url IN ({placeholders})"
            
            cursor = conn.execute(check_sql, urls_to_check)
            existing_urls = set(row[0] for row in cursor.fetchall())
            
            # Filter out database duplicates and prepare data for insertion
            insert_data = []
            for item in unique_batch_data:
                if item['product_url'] in existing_urls:
                    duplicate_count += 1
                else:
                    insert_data.append((
                        item['category'],
                        item['subcategory'],
                        item['category_url'],
                        item['product_url'],
                        item['url_hash'],
                        item['status'],
                        item['created_at'],
                        item['updated_at']
                    ))
            
            # Insert only new URLs
            if insert_data:
                insert_sql = """
                    INSERT INTO product_urls 
                    (category, subcategory, category_url, product_url, url_hash, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """
                cursor = conn.executemany(insert_sql, insert_data)
                inserted_count = cursor.rowcount
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error in batch insert: {e}")
            conn.rollback()
            raise
        
        return inserted_count, duplicate_count
    
    def migrate(self, test_mode=False, test_rows=1000):
        """Main migration function"""
        self.stats['start_time'] = time.time()
        logger.info("Starting CSV to Database migration...")
        
        # Prepare database
        self.prepare_database()
        
        # Count total rows
        total_rows = self.count_csv_rows()
        
        if test_mode:
            logger.info(f"Running in test mode - processing only {test_rows} rows")
            total_rows = min(total_rows, test_rows)
        
        # Connect to database
        conn = self.connect_db()
        
        try:
            batch_data = []
            
            with open(self.csv_file_path, 'r', encoding='utf-8') as csvfile:
                csv_reader = csv.reader(csvfile)
                
                for row_num, row in enumerate(csv_reader, 1):
                    if test_mode and row_num > test_rows:
                        break
                    
                    # Parse row
                    parsed_data = self.parse_csv_row(row)
                    
                    if parsed_data:
                        batch_data.append(parsed_data)
                    else:
                        self.stats['error_rows'] += 1
                    
                    # Process batch when it reaches batch_size
                    if len(batch_data) >= self.batch_size:
                        inserted, duplicates = self.batch_insert(conn, batch_data)
                        self.stats['inserted_rows'] += inserted
                        self.stats['duplicate_rows'] += duplicates
                        self.stats['processed_rows'] += len(batch_data)
                        
                        # Log progress
                        progress = (self.stats['processed_rows'] / total_rows) * 100
                        logger.info(f"Progress: {progress:.1f}% - Processed: {self.stats['processed_rows']:,}, "
                                  f"Inserted: {self.stats['inserted_rows']:,}, "
                                  f"Duplicates: {self.stats['duplicate_rows']:,}")
                        
                        batch_data = []
                
                # Process remaining batch
                if batch_data:
                    inserted, duplicates = self.batch_insert(conn, batch_data)
                    self.stats['inserted_rows'] += inserted
                    self.stats['duplicate_rows'] += duplicates
                    self.stats['processed_rows'] += len(batch_data)
        
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            raise
        finally:
            conn.close()
        
        self.stats['end_time'] = time.time()
        self.print_migration_summary()
    
    def print_migration_summary(self):
        """Print migration statistics"""
        duration = self.stats['end_time'] - self.stats['start_time']
        
        logger.info("=" * 60)
        logger.info("MIGRATION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total CSV rows: {self.stats['total_rows']:,}")
        logger.info(f"Processed rows: {self.stats['processed_rows']:,}")
        logger.info(f"Successfully inserted: {self.stats['inserted_rows']:,}")
        logger.info(f"Duplicates skipped: {self.stats['duplicate_rows']:,}")
        logger.info(f"Error rows: {self.stats['error_rows']:,}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info(f"Processing rate: {self.stats['processed_rows']/duration:.0f} rows/second")
        logger.info("=" * 60)

def main():
    """Main function with command line argument handling"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Migrate CSV data to IndiaMART database')
    parser.add_argument('--csv-file', default='product_urls.csv', help='Path to CSV file')
    parser.add_argument('--db-file', default='indiamart.db', help='Path to database file')
    parser.add_argument('--batch-size', type=int, default=10000, help='Batch size for processing')
    parser.add_argument('--test', action='store_true', help='Run in test mode with limited rows')
    parser.add_argument('--test-rows', type=int, default=1000, help='Number of rows for test mode')
    
    args = parser.parse_args()
    
    # Validate files exist
    if not Path(args.csv_file).exists():
        logger.error(f"CSV file not found: {args.csv_file}")
        sys.exit(1)
    
    if not Path(args.db_file).exists():
        logger.error(f"Database file not found: {args.db_file}")
        sys.exit(1)
    
    # Create migrator and run
    migrator = CSVToDBMigrator(args.csv_file, args.db_file, args.batch_size)
    
    try:
        migrator.migrate(test_mode=args.test, test_rows=args.test_rows)
        logger.info("Migration completed successfully!")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()