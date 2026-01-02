"""
Eximpedia Scraper Package
Scrapes trade data from Eximpedia

Includes:
- Main scraper (eximpedia.py)
- Task creator (eximPediaTaskCreator.py) - MongoDB version
- Payload creator (eximPediaPayloadCreator.py)
- Payloads (payloads/)
"""
import sys
import os

# Add parent directories to path for core module imports
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from .eximpedia import (
    ScrapeEximpedia,
    ScrapeEximpediaBatch,
    ParseDates,
    AuthenticateSession
)

__all__ = [
    'ScrapeEximpedia',
    'ScrapeEximpediaBatch',
    'ParseDates',
    'AuthenticateSession'
]
