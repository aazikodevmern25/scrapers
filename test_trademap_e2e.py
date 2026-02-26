#!/usr/bin/env python3
"""E2E test for TradeMap scraper with all parameter combinations."""
import sys
import os
import logging

os.environ['PYTHONUNBUFFERED'] = '1'

log_file = '/tmp/trademap_test.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, mode='w'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting E2E test...")
    
    from scrapers.trademap.trademap import ScrapeTrademap
    
    logger.info("=== E2E Test: HS 380300, ALL time series, ALL view types, ALL value types ===")
    try:
        ScrapeTrademap(
            hscode='380300',
            country1='all',
            country2='all',
            time_series_list=['yearly', 'quarterly', 'monthly', 'trade_indicators'],
            view_type_list=['by_country', 'by_product'],
            value_type_list=['values', 'quantities', 'growth_value', 'growth_quantity', 'share_value', 'unit_values', 'growth_unit_values', 'index_values', 'index_unit_values'],
            email='chhabinrai2017@gmail.com',
            password='Test@1234'
        )
        logger.info("=== SCRAPING COMPLETED ===")
    except Exception as e:
        import traceback
        logger.error(f"=== FAILED: {e} ===")
        logger.error(traceback.format_exc())
        sys.exit(1)

    # Verify data in MongoDB
    logger.info("=== Verifying MongoDB data ===")
    try:
        from pymongo import MongoClient
        client = MongoClient('mongodb://admin:Aaziko%21%40%23123@43.249.231.93:27017/?authSource=admin')
        db = client['Dhruval']
        col = db['trademap']
        doc = col.find_one({'HsCode': '380300', 'Data.Country1': 'all', 'Data.Country2': 'all'})
        if doc:
            data = doc.get('Data', {})
            error_count = 0
            success_count = 0
            for ts_k, ts_v in data.items():
                if not isinstance(ts_v, dict) or ts_k in ('Country1', 'Country2', 'ScrapingParams'):
                    continue
                for vt_k, vt_v in ts_v.items():
                    if not isinstance(vt_v, dict):
                        continue
                    for val_k, val_v in vt_v.items():
                        if not isinstance(val_v, dict):
                            continue
                        for dir_k, dir_v in val_v.items():
                            if not isinstance(dir_v, dict):
                                continue
                            fmt = dir_v.get('format', '')
                            prods = len(dir_v.get('products', []))
                            years = len(dir_v.get('years', []))
                            if fmt == 'error':
                                error_count += 1
                                logger.error(f"  ERROR: {ts_k}/{vt_k}/{val_k}/{dir_k}: {dir_v.get('error', '')[:80]}")
                            else:
                                success_count += 1
                                logger.info(f"  OK: {ts_k}/{vt_k}/{val_k}/{dir_k}: {prods} products, {years} years")
            logger.info(f"=== VERIFICATION: {success_count} OK, {error_count} ERRORS ===")
            if error_count > 0:
                sys.exit(1)
        else:
            logger.error("No document found in MongoDB!")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
