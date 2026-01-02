#!/usr/bin/env python3
"""
Script to remove duplicate URLs from product_urls.csv
This will create a clean CSV file with unique URLs only
"""

import csv
import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('csv_cleanup.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def clean_csv_duplicates(input_file, output_file):
    """Remove duplicate URLs from CSV file"""
    
    logger.info(f"Starting CSV cleanup: {input_file} -> {output_file}")
    
    seen_urls = set()
    unique_rows = []
    total_rows = 0
    duplicate_count = 0
    
    try:
        # Read and process CSV
        with open(input_file, 'r', encoding='utf-8') as infile:
            csv_reader = csv.reader(infile)
            
            for row_num, row in enumerate(csv_reader, 1):
                total_rows += 1
                
                if len(row) >= 4:
                    product_url = row[3].strip()
                    
                    if product_url not in seen_urls:
                        seen_urls.add(product_url)
                        unique_rows.append(row)
                    else:
                        duplicate_count += 1
                else:
                    # Keep malformed rows as-is
                    unique_rows.append(row)
                
                # Progress logging
                if row_num % 100000 == 0:
                    logger.info(f"Processed: {row_num:,} rows, Unique: {len(unique_rows):,}, Duplicates: {duplicate_count:,}")
        
        # Write clean CSV
        logger.info(f"Writing clean CSV with {len(unique_rows):,} unique rows...")
        
        with open(output_file, 'w', encoding='utf-8', newline='') as outfile:
            csv_writer = csv.writer(outfile)
            
            for row in unique_rows:
                csv_writer.writerow(row)
        
        # Summary
        logger.info("=" * 60)
        logger.info("CSV CLEANUP SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total rows processed: {total_rows:,}")
        logger.info(f"Unique rows kept: {len(unique_rows):,}")
        logger.info(f"Duplicate rows removed: {duplicate_count:,}")
        logger.info(f"Duplicate percentage: {(duplicate_count/total_rows)*100:.2f}%")
        logger.info(f"Clean file created: {output_file}")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Error during CSV cleanup: {e}")
        raise

def main():
    input_file = "product_urls.csv"
    output_file = "product_urls_clean.csv"
    
    if not Path(input_file).exists():
        logger.error(f"Input file not found: {input_file}")
        sys.exit(1)
    
    clean_csv_duplicates(input_file, output_file)
    logger.info("CSV cleanup completed successfully!")

if __name__ == "__main__":
    main()
