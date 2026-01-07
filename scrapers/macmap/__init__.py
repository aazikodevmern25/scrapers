"""
MacMap Scraper Package
Scrapes tariff and trade data from MacMap

Includes:
- Main scraper (macmap_tariff.py)
- Task creators (MongoDB versions):
  - macmapTariffTaskCreator.py
  - macmapproductTaskCreator.py
  - macmapregulatoryTaskCreator.py
  - comparemarketTaskCreator.py
  - competitorsTaskCreator.py
  - fulltariffTaskCreator.py
  - tradeRemediesTaskCreator.py
- Payload creators (task_creators/)
- Country data (macmap_countries/)
"""
import sys
import os

# Add parent directories to path for core module imports
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from .macmap_tariff import (
    ScrapeMacmapTariff,
    ScrapeMacmapTradeRemedies,
    ScrapeMacmapRegulatoryRequirements,
    ScrapeMacmapCompareMarket,
    ScrapeMacmapCompetitors,
    ScrapeMacmapProducts,
    ScrapeTarrifFull,
    ScrapeMacmapTradeAgreements
)

__all__ = [
    'ScrapeMacmapTariff',
    'ScrapeMacmapTradeRemedies',
    'ScrapeMacmapRegulatoryRequirements',
    'ScrapeMacmapCompareMarket',
    'ScrapeMacmapCompetitors',
    'ScrapeMacmapProducts',
    'ScrapeTarrifFull',
    'ScrapeMacmapTradeAgreements'
]
