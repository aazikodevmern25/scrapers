"""
Migration script to move IndiaMART data from SQLite to MongoDB
Run this script to migrate existing data to the new MongoDB database
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('indiamart_migration')

def migrate_sqlite_to_mongodb():
    """Migrate all IndiaMART data from SQLite to MongoDB"""
    
    try:
        # Import both database managers
        from indiamart_db import IndiamartDB as SQLiteDB
        from indiamart_mongodb import IndiamartMongoDB
        
        logger.info("=" * 80)
        logger.info("IndiaMART SQLite to MongoDB Migration")
        logger.info("=" * 80)
        
        # Initialize connections
        logger.info("Connecting to SQLite database...")
        sqlite_db = SQLiteDB()
        
        logger.info("Connecting to MongoDB database...")
        mongo_db = IndiamartMongoDB()
        
        # Get statistics from SQLite
        logger.info("\nGetting SQLite statistics...")
        sqlite_stats = sqlite_db.get_statistics()
        logger.info(f"SQLite Database Stats:")
        logger.info(f"  - Total Categories: {sqlite_stats.get('total_categories', 0)}")
        logger.info(f"  - Total URLs: {sqlite_stats.get('total_urls', 0)}")
        logger.info(f"  - Pending URLs: {sqlite_stats.get('pending_urls', 0)}")
        logger.info(f"  - Completed URLs: {sqlite_stats.get('completed_urls', 0)}")
        logger.info(f"  - Scraped Products: {sqlite_stats.get('scraped_products', 0)}")
        logger.info(f"  - Scraped Sellers: {sqlite_stats.get('scraped_sellers', 0)}")
        
        # Migrate categories
        logger.info("\n" + "=" * 80)
        logger.info("Migrating Categories...")
        logger.info("=" * 80)
        categories = sqlite_db.get_categories()
        if categories:
            logger.info(f"Found {len(categories)} categories to migrate")
            inserted = mongo_db.insert_categories(categories)
            mongo_db.force_flush_buffers()  # Ensure all buffered data is written
            logger.info(f"✓ Migrated {len(categories)} categories (inserted: {inserted})")
        else:
            logger.info("No categories to migrate")
        
        # Migrate product URLs in chunks
        logger.info("\n" + "=" * 80)
        logger.info("Migrating Product URLs...")
        logger.info("=" * 80)
        
        total_urls_migrated = 0
        chunk_size = 5000
        
        for chunk_num, urls_chunk in enumerate(sqlite_db.get_pending_urls_chunked(chunk_size=chunk_size), 1):
            logger.info(f"Processing chunk {chunk_num} ({len(urls_chunk)} URLs)...")
            
            # Convert SQLite format to MongoDB format
            urls_data = []
            for url in urls_chunk:
                urls_data.append({
                    'category': url.get('category', ''),
                    'subcategory': url.get('subcategory', ''),
                    'category_url': url.get('category_url', ''),
                    'product_url': url.get('product_url', '')
                })
            
            if urls_data:
                mongo_db.insert_product_urls(urls_data)
                total_urls_migrated += len(urls_data)
                logger.info(f"  ✓ Processed {total_urls_migrated} URLs so far...")
        
        # Flush any remaining buffered URLs
        mongo_db.force_flush_buffers()
        logger.info(f"✓ Migrated {total_urls_migrated} product URLs")
        
        # Migrate scraped products
        logger.info("\n" + "=" * 80)
        logger.info("Migrating Scraped Products...")
        logger.info("=" * 80)
        
        scraped_products = sqlite_db.get_scraped_products_set()
        if scraped_products:
            logger.info(f"Found {len(scraped_products)} scraped products to migrate")
            count = 0
            for product_url in scraped_products:
                mongo_db.add_scraped_product(product_url)
                count += 1
                if count % 1000 == 0:
                    logger.info(f"  Processed {count}/{len(scraped_products)} products...")
            logger.info(f"✓ Migrated {len(scraped_products)} scraped products")
        else:
            logger.info("No scraped products to migrate")
        
        # Migrate scraped sellers
        logger.info("\n" + "=" * 80)
        logger.info("Migrating Scraped Sellers...")
        logger.info("=" * 80)
        
        scraped_sellers = sqlite_db.get_scraped_sellers_set()
        if scraped_sellers:
            logger.info(f"Found {len(scraped_sellers)} scraped sellers to migrate")
            count = 0
            for seller_url in scraped_sellers:
                mongo_db.add_scraped_seller(seller_url)
                count += 1
                if count % 1000 == 0:
                    logger.info(f"  Processed {count}/{len(scraped_sellers)} sellers...")
            logger.info(f"✓ Migrated {len(scraped_sellers)} scraped sellers")
        else:
            logger.info("No scraped sellers to migrate")
        
        # Get final MongoDB statistics
        logger.info("\n" + "=" * 80)
        logger.info("Migration Complete!")
        logger.info("=" * 80)
        
        mongo_stats = mongo_db.get_statistics()
        logger.info(f"\nMongoDB Database Stats:")
        logger.info(f"  - Total Categories: {mongo_stats.get('total_categories', 0)}")
        logger.info(f"  - Total URLs: {mongo_stats.get('total_urls', 0)}")
        logger.info(f"  - Pending URLs: {mongo_stats.get('pending_urls', 0)}")
        logger.info(f"  - Completed URLs: {mongo_stats.get('completed_urls', 0)}")
        logger.info(f"  - Scraped Products: {mongo_stats.get('scraped_products', 0)}")
        logger.info(f"  - Scraped Sellers: {mongo_stats.get('scraped_sellers', 0)}")
        
        logger.info("\n✓ Migration completed successfully!")
        logger.info("\nNext steps:")
        logger.info("1. Verify the data in MongoDB")
        logger.info("2. Test the scrapers with MongoDB")
        logger.info("3. Backup and archive the SQLite database")
        
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return False


def verify_migration():
    """Verify that migration was successful by comparing counts"""
    
    try:
        from indiamart_db import IndiamartDB as SQLiteDB
        from indiamart_mongodb import IndiamartMongoDB
        
        logger.info("\n" + "=" * 80)
        logger.info("Verifying Migration...")
        logger.info("=" * 80)
        
        sqlite_db = SQLiteDB()
        mongo_db = IndiamartMongoDB()
        
        sqlite_stats = sqlite_db.get_statistics()
        mongo_stats = mongo_db.get_statistics()
        
        # Compare counts
        checks = [
            ('Categories', 'total_categories'),
            ('Total URLs', 'total_urls'),
            ('Pending URLs', 'pending_urls'),
            ('Scraped Products', 'scraped_products'),
            ('Scraped Sellers', 'scraped_sellers')
        ]
        
        all_match = True
        for name, key in checks:
            sqlite_count = sqlite_stats.get(key, 0)
            mongo_count = mongo_stats.get(key, 0)
            match = "✓" if sqlite_count == mongo_count else "✗"
            logger.info(f"{match} {name}: SQLite={sqlite_count}, MongoDB={mongo_count}")
            if sqlite_count != mongo_count:
                all_match = False
        
        if all_match:
            logger.info("\n✓ All counts match! Migration verified successfully.")
        else:
            logger.warning("\n⚠ Some counts don't match. Please review the migration.")
        
        return all_match
        
    except Exception as e:
        logger.error(f"Verification failed: {e}", exc_info=True)
        return False


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Migrate IndiaMART data from SQLite to MongoDB')
    parser.add_argument('--verify-only', action='store_true', help='Only verify migration, do not migrate')
    args = parser.parse_args()
    
    if args.verify_only:
        success = verify_migration()
    else:
        success = migrate_sqlite_to_mongodb()
        if success:
            # Also run verification
            verify_migration()
    
    sys.exit(0 if success else 1)
