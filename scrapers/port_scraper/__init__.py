"""
Port Scraper Package
Scrapes maritime port data from SeaRates.com

Includes:
- Main scraper (port_scraper.py)
- CLI runner (port_scraper_runner.py)
- Task creator (portScraperTaskCreator.py) - MongoDB version
"""
import sys
import os

# Add parent directories to path for core module imports
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from .port_scraper import (
    PortScraper,
    ScrapePortsStartFresh,
    ScrapePortsResumeFrom,
    ScrapePortsUpdateExisting,
    GetPortStatistics,
    StopPortScraperByTaskId,
    GetActiveScrapers
)

__all__ = [
    'PortScraper',
    'ScrapePortsStartFresh',
    'ScrapePortsResumeFrom',
    'ScrapePortsUpdateExisting',
    'GetPortStatistics',
    'StopPortScraperByTaskId',
    'GetActiveScrapers'
]
