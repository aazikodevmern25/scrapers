#!/usr/bin/env python3
"""
Bulk MacMap Tariff Task Creator
Creates thousands of tasks directly without web form limitations
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from celery_app.tasks import scrape_macmap_tariff
import json
from pathlib import Path

def load_countries():
    """Load MacMap country list"""
    macmap_dir = Path(__file__).parent / "scrapers" / "macmap" / "macmap_countries"
    countries_file = macmap_dir / "countries.json"
    
    with open(countries_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def create_bulk_tasks(
    importing_countries,
    exporting_countries,
    hs_codes,
    year=2024
):
    """
    Create bulk MacMap tariff tasks directly
    
    Args:
        importing_countries: List of importing country names
        exporting_countries: List of exporting country names
        hs_codes: List of HS codes
        year: Year for tariff data (default: 2024)
    
    Returns:
        dict with task_ids and total count
    """
    
    print("=" * 80)
    print("BULK MACMAP TARIFF TASK CREATOR")
    print("=" * 80)
    print()
    
    # Calculate total tasks
    total_tasks = len(importing_countries) * len(exporting_countries) * len(hs_codes)
    
    print(f"Configuration:")
    print(f"  Importing Countries: {len(importing_countries)}")
    print(f"  Exporting Countries: {len(exporting_countries)}")
    print(f"  HS Codes: {len(hs_codes)}")
    print(f"  Year: {year}")
    print(f"  Total Tasks: {total_tasks:,}")
    print()
    
    if total_tasks > 50000:
        print("⚠️  WARNING: Creating more than 50,000 tasks!")
        print("   This may take a while to process.")
        response = input("   Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Cancelled.")
            return None
    
    print(f"Creating {total_tasks:,} tasks...")
    print("-" * 80)
    
    task_ids = []
    created_count = 0
    
    for i, hscode in enumerate(hs_codes, 1):
        for j, importing_country in enumerate(importing_countries, 1):
            for k, exporting_country in enumerate(exporting_countries, 1):
                try:
                    # Create task
                    task = scrape_macmap_tariff.delay(
                        importing_country.strip(),
                        exporting_country.strip(),
                        year,
                        hscode.strip()
                    )
                    task_ids.append(task.id)
                    created_count += 1
                    
                    # Progress update every 100 tasks
                    if created_count % 100 == 0:
                        print(f"  Created {created_count:,} / {total_tasks:,} tasks ({created_count/total_tasks*100:.1f}%)")
                    
                except Exception as e:
                    print(f"  ❌ Error creating task: {importing_country} <- {exporting_country} HS:{hscode}: {e}")
                    continue
    
    print()
    print("=" * 80)
    print(f"✅ COMPLETED: {created_count:,} tasks created and queued!")
    print("=" * 80)
    print()
    print("Tasks are now in Redis queue and will be processed by workers.")
    print("Monitor progress with: redis-cli LLEN macmap_tariff")
    print()
    
    return {
        "status": "success",
        "total_tasks": created_count,
        "task_ids": task_ids[:100]  # Only return first 100 IDs to avoid memory issues
    }


def main():
    """Main function with example usage"""
    
    print()
    print("MacMap Bulk Task Creator")
    print("=" * 80)
    print()
    print("This script creates thousands of tasks directly without web form.")
    print()
    
    # Example configurations
    print("Example configurations:")
    print()
    print("1. Small test (18 tasks)")
    print("   - 3 importing countries × 2 exporting × 3 HS codes")
    print()
    print("2. Medium batch (600 tasks)")
    print("   - 10 importing × 10 exporting × 6 HS codes")
    print()
    print("3. Large batch (10,000 tasks)")
    print("   - 20 importing × 25 exporting × 20 HS codes")
    print()
    print("4. Custom configuration")
    print()
    
    choice = input("Select option (1-4): ").strip()
    
    if choice == "1":
        # Small test
        importing = ["China", "United Arab Emirates", "Netherlands"]
        exporting = ["India", "Bangladesh"]
        hs_codes = ["120791", "120799", "120810"]
        year = 2024
        
    elif choice == "2":
        # Medium batch
        importing = [
            "China", "United Arab Emirates", "Netherlands", "Germany", "Italy",
            "United Kingdom", "France", "Spain", "Belgium", "Poland"
        ]
        exporting = [
            "India", "Bangladesh", "Vietnam", "Thailand", "Indonesia",
            "Pakistan", "Sri Lanka", "Myanmar", "Cambodia", "Philippines"
        ]
        hs_codes = ["120791", "120799", "120810", "120890", "121490", "130219"]
        year = 2024
        
    elif choice == "3":
        # Large batch - 10k tasks
        importing = [
            "China", "United Arab Emirates", "Netherlands", "Germany", "Italy",
            "United Kingdom", "France", "Spain", "Belgium", "Poland",
            "Austria", "Sweden", "Denmark", "Norway", "Finland",
            "Switzerland", "Ireland", "Portugal", "Greece", "Czech Republic"
        ]
        exporting = [
            "India", "Bangladesh", "Vietnam", "Thailand", "Indonesia",
            "Pakistan", "Sri Lanka", "Myanmar", "Cambodia", "Philippines",
            "Malaysia", "Singapore", "Nepal", "Bhutan", "Maldives",
            "Afghanistan", "Laos", "Mongolia", "Uzbekistan", "Kazakhstan",
            "Kyrgyzstan", "Tajikistan", "Turkmenistan", "Armenia", "Georgia"
        ]
        hs_codes = [
            "120791", "120799", "120810", "120890", "121490", "130219",
            "230400", "230990", "284920", "284990", "285000", "030379",
            "030499", "030559", "030617", "030695", "030749", "030899",
            "160414", "160419"
        ]
        year = 2024
        
    elif choice == "4":
        # Custom
        print()
        print("Enter countries separated by commas:")
        importing_input = input("Importing countries: ").strip()
        exporting_input = input("Exporting countries: ").strip()
        hs_input = input("HS codes: ").strip()
        year_input = input("Year (default 2024): ").strip()
        
        importing = [c.strip() for c in importing_input.split(',') if c.strip()]
        exporting = [c.strip() for c in exporting_input.split(',') if c.strip()]
        hs_codes = [h.strip() for h in hs_input.split(',') if h.strip()]
        year = int(year_input) if year_input else 2024
        
    else:
        print("Invalid option")
        return
    
    # Confirm and create
    total = len(importing) * len(exporting) * len(hs_codes)
    print()
    print(f"Ready to create {total:,} tasks")
    confirm = input("Proceed? (yes/no): ").strip().lower()
    
    if confirm == 'yes':
        result = create_bulk_tasks(importing, exporting, hs_codes, year)
        if result:
            print()
            print("✅ Tasks queued successfully!")
            print(f"   Total: {result['total_tasks']:,} tasks")
            print()
            print("Workers will start processing immediately.")
    else:
        print("Cancelled")


if __name__ == "__main__":
    main()
