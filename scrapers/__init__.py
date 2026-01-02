"""
Scrapers package - Contains all data extraction scrapers organized by source
"""
import sys
import os

# Add parent directory to path so scrapers can import core modules
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
