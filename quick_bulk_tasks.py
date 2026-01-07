#!/usr/bin/env python3
"""
Quick Bulk Task Creator - No prompts, just run
Creates 10,000+ MacMap tasks instantly
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from celery_app.tasks import scrape_macmap_tariff
import time

# CONFIGURATION - EDIT THESE LISTS
# =================================

IMPORTING_COUNTRIES = [
    "China", "United Arab Emirates", "Netherlands", "Germany", "Italy",
    "United Kingdom", "France", "Spain", "Belgium", "Poland",
    "Austria", "Sweden", "Denmark", "Norway", "Finland",
    "Switzerland", "Ireland", "Portugal", "Greece", "Czech Republic",
    "Romania", "Hungary", "Slovakia", "Bulgaria", "Croatia"
]

EXPORTING_COUNTRIES = [
    "India", "Bangladesh", "Vietnam", "Thailand", "Indonesia",
    "Pakistan", "Sri Lanka", "Myanmar", "Cambodia", "Philippines",
    "Malaysia", "Singapore", "Nepal", "Bhutan", "Maldives",
    "Afghanistan", "Laos", "Mongolia", "Uzbekistan", "Kazakhstan",
    "Kyrgyzstan", "Tajikistan", "Turkmenistan", "Armenia", "Georgia"
]

HS_CODES = [
    "120791", "120799", "120810", "120890", "121490", "130219",
    "230400", "230990", "284920", "284990", "285000", "030379",
    "030499", "030559", "030617", "030695", "030749", "030899",
    "160414", "160419"
]

YEAR = 2024

# =================================

def create_tasks():
    """Create all task combinations"""
    
    total_tasks = len(IMPORTING_COUNTRIES) * len(EXPORTING_COUNTRIES) * len(HS_CODES)
    
    print("=" * 80)
    print("QUICK BULK TASK CREATOR")
    print("=" * 80)
    print(f"Importing Countries: {len(IMPORTING_COUNTRIES)}")
    print(f"Exporting Countries: {len(EXPORTING_COUNTRIES)}")
    print(f"HS Codes: {len(HS_CODES)}")
    print(f"Year: {YEAR}")
    print(f"Total Tasks: {total_tasks:,}")
    print("=" * 80)
    print()
    
    start_time = time.time()
    created = 0
    errors = 0
    
    print("Creating tasks...")
    
    for hscode in HS_CODES:
        for importing in IMPORTING_COUNTRIES:
            for exporting in EXPORTING_COUNTRIES:
                try:
                    scrape_macmap_tariff.delay(
                        importing.strip(),
                        exporting.strip(),
                        YEAR,
                        hscode.strip()
                    )
                    created += 1
                    
                    if created % 500 == 0:
                        elapsed = time.time() - start_time
                        rate = created / elapsed
                        remaining = (total_tasks - created) / rate
                        print(f"  {created:,}/{total_tasks:,} ({created/total_tasks*100:.1f}%) | "
                              f"{rate:.0f} tasks/sec | ETA: {remaining:.0f}s")
                        
                except Exception as e:
                    errors += 1
                    if errors <= 10:  # Only show first 10 errors
                        print(f"  ⚠️  Error: {importing}<-{exporting} HS:{hscode}: {e}")
    
    elapsed = time.time() - start_time
    
    print()
    print("=" * 80)
    print(f"✅ COMPLETED in {elapsed:.1f} seconds")
    print(f"   Tasks Created: {created:,}")
    print(f"   Errors: {errors}")
    print(f"   Rate: {created/elapsed:.0f} tasks/second")
    print("=" * 80)
    print()
    print("Tasks are queued and workers will process them automatically.")
    print()

if __name__ == "__main__":
    
    total = len(IMPORTING_COUNTRIES) * len(EXPORTING_COUNTRIES) * len(HS_CODES)
    
    if len(sys.argv) > 1 and sys.argv[1] == "--auto":
        # Auto mode - no confirmation
        create_tasks()
    else:
        # Ask for confirmation
        print(f"Ready to create {total:,} MacMap tariff tasks")
        print(f"Countries: {len(IMPORTING_COUNTRIES)} importing × {len(EXPORTING_COUNTRIES)} exporting")
        print(f"HS Codes: {len(HS_CODES)}")
        print(f"Year: {YEAR}")
        print()
        response = input("Proceed? (yes/no): ").strip().lower()
        
        if response == 'yes':
            create_tasks()
        else:
            print("Cancelled")
