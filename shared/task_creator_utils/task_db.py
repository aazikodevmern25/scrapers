#!/usr/bin/env python3
"""
Task Database Module - MongoDB Only
Provides unified task storage using MongoDB

Usage:
    from shared.task_creator_utils.task_db import TaskDatabase, get_task_db, get_scraper_db
    
    # Get database for a scraper
    db = get_scraper_db('indiantradeportal')
    
    # Or create directly
    db = TaskDatabase("IndianTradePortal")
"""

import os
from typing import Dict, List, Any, Optional
from shared.task_creator_utils.mongodb_base import MongoDBScraperBase, get_database


def get_task_db(scraper_name: str) -> MongoDBScraperBase:
    """
    Get task database for a scraper
    
    Args:
        scraper_name: Name of the scraper
    
    Returns:
        MongoDBScraperBase instance
    """
    return MongoDBScraperBase("scraper_tasks", scraper_name)


class TaskDatabase:
    """
    Wrapper class for MongoDB task database
    """
    
    def __init__(self, scraper_name: str):
        self._db = MongoDBScraperBase("scraper_tasks", scraper_name)
        self.scraper_name = scraper_name
    
    def __getattr__(self, name):
        """Delegate all method calls to underlying database"""
        return getattr(self._db, name)
    
    @property
    def backend_type(self) -> str:
        """Return the type of backend being used"""
        return "mongodb"


# Mapping of scraper IDs to their display names
SCRAPER_DB_MAPPING = {
    'comparemarket': 'CompareMarket',
    'competitors': 'Competitors',
    'eximpedia': 'EximPedia',
    'fulltariff': 'FullTariff',
    'indiantradeportal': 'IndianTradePortal',
    'macmapproduct': 'MacMapProduct',
    'macmapregulatory': 'MacMapRegulatory',
    'macmaptariff': 'MacMapTariff',
    'trademap': 'TradeMap',
    'traderemedies': 'TradeRemedies',
    'portscraper': 'PortScraper',
    'indiamart_products': 'IndiaMartProducts',
    'indiamart_categories': 'IndiaMartCategories',
}


def get_scraper_db(scraper_id: str) -> TaskDatabase:
    """
    Get task database for a specific scraper by ID
    
    Args:
        scraper_id: Scraper identifier (e.g., 'indiantradeportal')
    
    Returns:
        TaskDatabase instance
    """
    if scraper_id not in SCRAPER_DB_MAPPING:
        raise ValueError(f"Unknown scraper ID: {scraper_id}")
    
    scraper_name = SCRAPER_DB_MAPPING[scraper_id]
    return TaskDatabase(scraper_name)


def get_all_scrapers_stats() -> Dict[str, Dict]:
    """Get stats for all configured scrapers"""
    stats = {}
    for scraper_id, scraper_name in SCRAPER_DB_MAPPING.items():
        try:
            db = TaskDatabase(scraper_name)
            stats[scraper_id] = db.get_database_stats()
        except Exception as e:
            stats[scraper_id] = {
                "error": str(e),
                "total_tasks": 0,
                "pending_tasks": 0,
                "completed_tasks": 0,
                "failed_tasks": 0
            }
    return stats
