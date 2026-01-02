"""
IndiaMART Scraper Package
Scrapes product and seller data from IndiaMART
"""
import sys
import os

# Add parent directories to path for core module imports
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from .indiamart_scraper import IndiamartProductScraper, ScrapingConfig
from .indiamart_db import IndiamartDB
from .indiamart_category_crawler import *
from .indiamart_product_scraper import IndiamartProductScraperV2, ScrapeIndiamartProducts, ProductScraperConfig

__all__ = [
    'IndiamartProductScraper', 
    'ScrapingConfig', 
    'IndiamartDB',
    'IndiamartProductScraperV2',
    'ScrapeIndiamartProducts',
    'ProductScraperConfig'
]
