#!/usr/bin/env python3
"""
Test Trade Agreements Scraper directly
"""
import sys
sys.path.insert(0, '.')

from celery_app.tasks import scrape_trade_agreements

# Test with one country
print("Testing Trade Agreements scraper with China...")
result = scrape_trade_agreements.apply_async(args=['China'])
print(f"Task ID: {result.id}")
print(f"Task submitted successfully!")

# Submit all 3 countries
countries = ["China", "Netherlands", "United Arab Emirates"]
task_ids = []

for country in countries:
    result = scrape_trade_agreements.apply_async(args=[country])
    task_ids.append(result.id)
    print(f"✅ Submitted task for {country}: {result.id}")

print(f"\n📊 Total tasks submitted: {len(task_ids)}")
print("\n💡 Monitor with: tail -f logs/celery_trade_agreements.log")
