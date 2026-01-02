#!/usr/bin/env python3
"""
Easy Runner for Port Scraper
This script provides an easy interface to run the port scraper manually
with various options and configurations.
"""

import sys
import os
from scrapers.port_scraper import (
    ScrapePortsStartFresh,
    ScrapePortsResumeFrom,
    ScrapePortsUpdateExisting,
    GetPortStatistics
)

def show_menu():
    """Show the main menu options."""
    print("🚢 PORT SCRAPER - SeaRates.com")
    print("=" * 80)
    print("Choose an option:")
    print()
    print("1. 🚀 Start Fresh - Scrape all countries from beginning")
    print("2. 📍 Resume from Country - Continue from a specific country")
    print("3. 🔢 Limited Run - Scrape only a few countries for testing")
    print("4. 🔄 Update Existing - Re-scrape countries that already exist")
    print("5. 📊 View Statistics - Check current database status")
    print("6. 🚪 Exit")
    print("=" * 80)

def get_user_choice():
    """Get and validate user choice."""
    while True:
        try:
            choice = input("\nEnter your choice (1-6): ").strip()
            if choice in ['1', '2', '3', '4', '5', '6']:
                return int(choice)
            else:
                print("❌ Invalid choice. Please enter a number between 1-6.")
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            sys.exit(0)
        except:
            print("❌ Invalid input. Please enter a number between 1-6.")

def get_headless_mode():
    """Get headless mode preference from user."""
    headless_input = input("Run in headless mode (no browser window)? (Y/n): ").strip().lower()
    return headless_input != 'n'

def option_1_start_fresh():
    """Option 1: Start fresh scraping."""
    print("\n🚀 STARTING FRESH SCRAPING")
    print("This will scrape ALL countries from the beginning.")
    print("Countries that already exist will be SKIPPED.")
    
    confirm = input("\nContinue? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Operation cancelled.")
        return
    
    headless = get_headless_mode()
    
    try:
        stats = ScrapePortsStartFresh(headless=headless, countries_limit=None)
        print(f"\n✅ Scraping completed! Stats: {stats}")
    except Exception as e:
        print(f"\n❌ Error: {e}")

def option_2_resume_from_country():
    """Option 2: Resume from specific country."""
    print("\n📍 RESUME FROM SPECIFIC COUNTRY")
    
    start_country = input("Enter country code or name to start from: ").strip()
    if not start_country:
        print("❌ No country specified.")
        return
    
    print(f"Will start scraping from: {start_country}")
    print("Countries that already exist will be SKIPPED.")
    
    confirm = input("\nContinue? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Operation cancelled.")
        return
    
    headless = get_headless_mode()
    
    try:
        stats = ScrapePortsResumeFrom(start_country, headless=headless, countries_limit=None)
        print(f"\n✅ Scraping completed! Stats: {stats}")
    except Exception as e:
        print(f"\n❌ Error: {e}")

def option_3_limited_run():
    """Option 3: Limited run for testing."""
    print("\n🔢 LIMITED RUN FOR TESTING")
    
    try:
        limit = int(input("How many countries to scrape? ").strip())
        if limit <= 0:
            print("❌ Invalid number.")
            return
    except:
        print("❌ Invalid number.")
        return
    
    start_country = input("Start from which country? (press Enter for beginning): ").strip()
    
    print(f"Will scrape {limit} countries starting from: {start_country or 'beginning'}")
    
    confirm = input("\nContinue? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Operation cancelled.")
        return
    
    headless = get_headless_mode()
    
    try:
        if start_country:
            stats = ScrapePortsResumeFrom(start_country, headless=headless, countries_limit=limit)
        else:
            stats = ScrapePortsStartFresh(headless=headless, countries_limit=limit)
        print(f"\n✅ Scraping completed! Stats: {stats}")
    except Exception as e:
        print(f"\n❌ Error: {e}")

def option_4_update_existing():
    """Option 4: Update existing countries."""
    print("\n🔄 UPDATE EXISTING COUNTRIES")
    print("This will RE-SCRAPE countries that already exist in the database.")
    print("⚠️  WARNING: This will overwrite existing data!")
    
    start_country = input("Start from which country? (press Enter for beginning): ").strip()
    if not start_country:
        start_country = None
    
    limit_input = input("Limit number of countries? (press Enter for all): ").strip()
    countries_limit = None
    if limit_input.isdigit():
        countries_limit = int(limit_input)
    
    print(f"Will update countries starting from: {start_country or 'beginning'}")
    if countries_limit:
        print(f"Limited to: {countries_limit} countries")
    
    confirm = input("\n⚠️  This will OVERWRITE existing data. Continue? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Operation cancelled.")
        return
    
    headless = get_headless_mode()
    
    try:
        stats = ScrapePortsUpdateExisting(
            start_country=start_country,
            headless=headless,
            countries_limit=countries_limit
        )
        print(f"\n✅ Update completed! Stats: {stats}")
    except Exception as e:
        print(f"\n❌ Error: {e}")

def option_5_view_statistics():
    """Option 5: View current statistics."""
    print("\n📊 VIEWING DATABASE STATISTICS")
    
    try:
        stats = GetPortStatistics()
        
        if stats:
            print("\n" + "=" * 60)
            print("📊 CURRENT DATABASE STATISTICS")
            print("=" * 60)
            print(f"🌍 Total countries: {stats['total_countries']}")
            print(f"🚢 Total ports: {stats['total_ports']}")
            print(f"📋 Detailed ports scraped: {stats['total_detailed_ports']}")
            print(f"🗺️  Countries with detailed ports: {stats['countries_with_detailed_ports']}")
            print(f"📍 Ports with coordinates: {stats['ports_with_coordinates']}")
            
            print(f"\n🏆 Top 10 countries by port count:")
            for i, country in enumerate(stats['top_countries'], 1):
                print(f"   {i:2d}. {country['_id']} ({country['country_code']}): {country['count']} ports")
            
            # Calculate completion percentage
            if stats['total_countries'] > 0:
                completion_pct = (stats['countries_with_detailed_ports'] / stats['total_countries']) * 100
                print(f"\n📈 Completion: {completion_pct:.1f}% ({stats['countries_with_detailed_ports']}/{stats['total_countries']} countries)")
            
        else:
            print("❌ Could not retrieve statistics.")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")

def main():
    """Main function with menu loop."""
    while True:
        try:
            show_menu()
            choice = get_user_choice()
            
            if choice == 1:
                option_1_start_fresh()
            elif choice == 2:
                option_2_resume_from_country()
            elif choice == 3:
                option_3_limited_run()
            elif choice == 4:
                option_4_update_existing()
            elif choice == 5:
                option_5_view_statistics()
            elif choice == 6:
                print("\n👋 Goodbye!")
                break
            
            input("\nPress Enter to continue...")
                
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")
            input("Press Enter to continue...")

if __name__ == "__main__":
    print("=" * 80)
    print("🚢 PORT SCRAPER - SeaRates.com Maritime Port Data Scraper")
    print("=" * 80)
    print("\n📝 IMPORTANT NOTES:")
    print("   • This scraper collects comprehensive port data from SeaRates.com")
    print("   • Data is stored in MongoDB database: 'scraper'")
    print("   • Collections: ports, ports_countries, ports_detailed")
    print("   • Full scraping can take many hours (200+ countries)")
    print("   • Recommended: Start with Option 3 (Limited Run) to test")
    print("\n⚙️  MONGODB CONNECTION:")
    print("   • Using the same MongoDB connection from utils.py")
    print("   • Make sure MongoDB is running before starting")
    print("\n")
    
    main()

