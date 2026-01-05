from concurrent.futures import ThreadPoolExecutor
import requests as pdf_req
import pandas as pd
import json
from scrapy import Selector
import os
import sys
import datetime
import scraper_helper
import itertools
import logging
from pathlib import Path
from utils import obj_storage, client, db, SendGetRequests, DownloadPdf

# Import HS code expander service
services_dir = Path(__file__).parent.parent.parent / "services"
if str(services_dir) not in sys.path:
    sys.path.insert(0, str(services_dir))

try:
    from hscode_expander import hscode_expander
    HSCODE_EXPANDER_AVAILABLE = True
except ImportError:
    logger.warning("HS Code Expander not available. 6-digit expansion will be disabled.")
    HSCODE_EXPANDER_AVAILABLE = False



log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"macmap_tariff_{datetime.datetime.now().strftime('%Y%m%d')}.log")
logger = logging.getLogger('macmap_tariff')
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)



os.makedirs("pdf_files", exist_ok=True)
cwd = os.getcwd()


headers = """Accept: application/json, text/javascript, */*; q=0.01
Accept-Encoding: gzip, deflate, br, zstd
Accept-Language: en-GB,en-US;q=0.9,en;q=0.8
Cache-Control: no-cache
Connection: keep-alive
Content-Type: application/json; charset=utf-8
DNT: 1
Host: www.macmap.org
Pragma: no-cache
Referer: https://www.macmap.org/
Sec-Fetch-Dest: empty
Sec-Fetch-Mode: cors
Sec-Fetch-Site: same-origin
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36
X-Requested-With: XMLHttpRequest
sec-ch-ua: "Google Chrome";v="131", "Not-A.Brand";v="8", "Chromium";v="131"
sec-ch-ua-mobile: ?0
sec-ch-ua-platform: "Windows"
"""
headers = scraper_helper.get_dict(headers)

# Separate collections for each Macmap scraper (using db from utils)
macmap_tariff_collection = db["macmap_tariff"]
macmap_trade_remedies_collection = db["macmap_trade_remedies"]
macmap_regulatory_collection = db["macmap_regulatory"]
macmap_compare_market_collection = db["macmap_compare_market"]
macmap_competitors_collection = db["macmap_competitors"]
macmap_products_collection = db["macmap_products"]
macmap_full_tariff_collection = db["macmap_full_tariff"]

logger.info("Loading countries and HS codes data")
# Get the directory where this file is located
import pathlib
_current_dir = pathlib.Path(__file__).parent
countries_json = countries = {
    i["Name"]: i["Code"]
    for i in json.load(open(_current_dir / "macmap_countries" / "countries.json", "r", encoding="utf-8"))
}
countries_lower_map = {name.lower(): code for name, code in countries.items()}
hscodes_full = {
    i["Code"]: i["Name"] for i in json.load(open(_current_dir.parent.parent / "payloads" / "hscodes.json", "r", encoding="utf-8"))
}
logger.info(f"Loaded {len(countries)} countries and {len(hscodes_full)} HS codes")

def get_country_code(country_name):
    """Return country code using case-insensitive lookup."""
    if country_name in countries:
        return countries[country_name]

    normalized = country_name.strip().lower()
    if normalized in countries_lower_map:
        return countries_lower_map[normalized]

    raise KeyError(f"Unknown country '{country_name}'. Available sample: {list(countries)[:5]}")


def NormalizeFtaData(response_json):
    logger.info("Normalizing FTA data")
    normalized_data = []

    key_map = {
        "RulesOfOrigin": "Title",
        "CertificateName": "Title",
        "RooUrl": "FileName",
        "CertificateDesc": "FileName",
        "RooLink": "HtmlLink",
        "CertificateLink": "HtmlLink",
    }

    for entry in response_json.get("RooDataViewModel", []):
        for section_key, items in entry.items():
            if isinstance(items, list):
                for item in items:
                    normalized_item = {"Section": section_key}
                    for k, v in item.items():
                        unified_key = key_map.get(k, k)  # fallback to original key
                        normalized_item[unified_key] = v
                    normalized_data.append(normalized_item)

    logger.info(f"Normalized {len(normalized_data)} FTA data items")
    return normalized_data


def ProcessTradeAgreement(js, c1_id, c2_id, year, hsc):
    ftaid = js["FtaId"]
    logger.info(f"Processing trade agreement: {ftaid} for countries {c1_id}, {c2_id}, year {year}, HS code {hsc}")
    req = SendGetRequests(
        f"https://www.macmap.org/api/results/fta?reporter={c1_id}&partner={c2_id}&product={hsc}&ftaId={ftaid}",
        headers,
        use_proxy=False
    )
    logger.info(f"FTA request: {req.url}, status: {req.status_code}")
    if req.status_code == 200:
        dt = req.json()
        dt["pdf_urls"] = []
        req1 = SendGetRequests(
            f"https://www.macmap.org/api/results/roo-by-fta?reporter={c1_id}&partner={c2_id}&ftaId={ftaid}",
            headers,
            use_proxy=False
        )
        logger.info(f"ROO by FTA request: {req1.url}, status: {req1.status_code}")
        r1_data = NormalizeFtaData(req1.json())
        logger.info(f"Processing {len(r1_data)} ROO items for FTA: {ftaid}")
        for i in r1_data:
            pdf_url = Selector(text=i["HtmlLink"]).xpath("//a/@href").get()
            pdf_name = f"{c1_id} {c2_id} {year} {hsc} {i['Section']} {i['FileName']}"
            i["PdfFileName"] = pdf_name
            i["PdfUrl"] = pdf_url
            del i["HtmlLink"]
            dt["pdf_urls"].append(i)
            logger.info(f"Downloading PDF: {pdf_url}")
            DownloadPdf(pdf_url, pdf_name)

        logger.info(f"Completed processing trade agreement: {ftaid}")
        return dt
    else:
        logger.warning(f"Failed to process trade agreement: {ftaid}, status code: {req.status_code}")
        return js


def ScrapeMacmapTariff(country1, country2, year, hsc):
    logger.info(f"Scraping Macmap tariff for countries: {country1}, {country2}, year: {year}, HS code: {hsc}")
    c1_id = countries[country1]
    c2_id = countries[country2]
    item = hscodes_full[hsc]
    req = SendGetRequests(
        f"https://www.macmap.org/api/results/custom-duties-by-year?reporter={c1_id}&partner={c2_id}&product={hsc}&year={year}",
        headers,
        use_proxy=False  # MacMap doesn't require proxy and blocks proxy IPs
    )
    
    # Check if request was successful
    if req is None:
        logger.error(f"Failed to fetch data from MacMap API for {country1} -> {country2}, HS: {hsc}")
        raise Exception(f"MacMap API request failed after retries")
    
    logger.info(f"Custom duties request: {req.url}, status: {req.status_code}")
    
    # Check status code
    if req.status_code != 200:
        logger.error(f"MacMap API returned status {req.status_code} for {country1} -> {country2}, HS: {hsc}")
        raise Exception(f"MacMap API returned status {req.status_code}")
    
    custom_tariff_data = []
    json_data = req.json()
    logger.info(f"Found {len(json_data['CustomDuty'])} custom duty items")
    for i in json_data["CustomDuty"]:
        if i["ShowDetailLink"]:
            logger.info("Processing custom duty with detail link")
            custom_tariff_data.append(ProcessTradeAgreement(i, c1_id, c2_id, year, hsc))
        else:
            logger.info("Adding custom duty without detail link")
            custom_tariff_data.append(i)
    data = {}
    data["ScraperName"] = "macmap_tariff_scraper"
    data["HsCode"] = hsc
    data["ProductName"] = item
    data["ImportingCountry"] = country1
    data["ExportingCountry"] = country2
    data["Source"] = "Macmap"
    data["TargetYear"] = year
    data["Mode"] = None
    data["Month"] = datetime.datetime.now().strftime("%b")
    data["Year"] = datetime.datetime.now().strftime("%Y")
    data["Data"] = custom_tariff_data
    data["DateCreated"] = datetime.datetime.now()
    data["DateUpdated"] = datetime.datetime.now()
    logger.info("Inserting tariff data into macmap_tariff collection")
    macmap_tariff_collection.insert_one(data)
    logger.info(f"Completed scraping Macmap tariff for countries: {country1}, {country2}, year: {year}, HS code: {hsc}")


def ScrapeMacmapTradeRemedies(country1, country2, year, hs):
    logger.info(f"Scraping Macmap trade remedies for countries: {country1}, {country2}, year: {year}, HS code: {hs}")
    c1_id = countries[country1]
    c2_id = countries[country2]
    req1 = SendGetRequests(
        f"https://www.macmap.org/api/tr-products?remedytype=All&reporterCode={c1_id}&level=8&year={year}&partnerCode={c2_id}&productCode={hs}",
        headers,
        use_proxy=False
    )
    logger.info(f"Trade remedies request: {req1.url}, status: {req1.status_code}")
    
    for sr in req1.json():
        hsc = sr["Code"]
        item = sr["Name"]
        req = SendGetRequests(
            f"https://www.macmap.org/api/results/trade-remedy-by-year?remedytype=All&reporter={c1_id}&year={year}&partner={c2_id}&product={hsc}",
            headers,
            use_proxy=False
        )
        logger.info(f"Trade remedies request: {req.url}, status: {req.status_code}")
        if req.status_code == 200:
            json_data = req.json()
            logger.info(f"Found {len(json_data['TradeRemedyData'])} trade remedy items")
            data = {}
            data["ScraperName"] = "macmap_trade_remedies_scraper"
            data["HsCodeSearched"] = hs
            data["HsCode"] = hsc
            data["ProductName"] = item
            data["ImportingCountry"] = country1
            data["ExportingCountry"] = country2
            data["Source"] = "Macmap"
            data["TargetYear"] = year
            data["Mode"] = None
            data["Month"] = datetime.datetime.now().strftime("%b")
            data["Year"] = datetime.datetime.now().strftime("%Y")
            data["Data"] = json_data["TradeRemedyData"]
            data["DateCreated"] = datetime.datetime.now()
            data["DateUpdated"] = datetime.datetime.now()
            logger.info("Inserting trade remedies data into macmap_trade_remedies collection")
            macmap_trade_remedies_collection.insert_one(data)
            logger.info("Completed scraping Macmap trade remedies")
        else:
            logger.error(f"Failed to scrape trade remedies, status code: {req.status_code}")


def ScrapeMacmapRegulatoryRequirements(country1, country2, hsc, regtype):
    logger.info(f"Scraping Macmap regulatory requirements for countries: {country1}, {country2}, HS code: {hsc}, regtype: {regtype}")
    c1_id = countries[country1]
    c2_id = countries[country2]
    
    # Check if HS code is 6-digit and expand to 8-digit codes
    hsc_codes_to_scrape = []
    
    # Determine which country's HS codes to use based on regulation type
    # The MacMap API uses reporter={country1} for both import and export regulations
    # - Import regulations (I): Regulations country1 imposes on imports FROM country2
    # - Export regulations (E): Regulations country1 imposes on exports TO country2
    # In both cases, we need country1's (reporter's) HS code list
    expansion_country_id = c1_id
    expansion_country_name = country1
    
    # Pre-check: Ensure HS codes are cached for BOTH countries before scraping
    # We cache both because:
    # - Import regulations: Use importing country's (country1) HS codes
    # - Export regulations: Use exporting country's (country2) HS codes for comprehensive data
    if len(hsc) == 6 and HSCODE_EXPANDER_AVAILABLE:
        countries_to_cache = [
            (c1_id, country1, "reporter/importing"),
            (c2_id, country2, "partner/exporting")
        ]
        
        for country_id, country_name, role in countries_to_cache:
            logger.info(f"🔍 Pre-check: Verifying HS code cache for {country_name} ({role})...")
            print(f"🔍 Pre-check: Verifying HS code cache for {country_name} ({role})...")
            
            cache_status = hscode_expander.check_cache_status(country_id)
            
            if not cache_status['exists']:
                logger.warning(f"⚠️  HS code cache not found for {country_name}. Fetching from MacMap API...")
                print(f"⚠️  HS code cache not found for {country_name}. Fetching from MacMap API...")
                
                fetched = hscode_expander.fetch_and_cache_country(country_id, country_name)
                
                if fetched:
                    logger.info(f"✅ Successfully cached {fetched} HS codes for {country_name}")
                    print(f"✅ Successfully cached {fetched} HS codes for {country_name}")
                else:
                    logger.error(f"❌ Failed to fetch HS codes for {country_name}")
                    print(f"❌ Failed to fetch HS codes for {country_name}")
            else:
                logger.info(f"✅ HS code cache exists for {country_name} ({cache_status['total_codes']} codes)")
                print(f"✅ HS code cache exists for {country_name} ({cache_status['total_codes']} codes)")
        
        # For expansion, use the appropriate country based on regulation type
        # Import: Use country1 (importing country)
        # Export: Use country2 (exporting country) for more comprehensive results
        if regtype.lower() == 'e':
            expansion_country_id = c2_id
            expansion_country_name = country2
            logger.info(f"📦 Export regulations: Using {expansion_country_name}'s HS codes for expansion")
            print(f"📦 Export regulations: Using {expansion_country_name}'s HS codes for expansion")
        else:
            expansion_country_id = c1_id
            expansion_country_name = country1
            logger.info(f"📦 Import regulations: Using {expansion_country_name}'s HS codes for expansion")
            print(f"📦 Import regulations: Using {expansion_country_name}'s HS codes for expansion")
    
    if len(hsc) == 6 and HSCODE_EXPANDER_AVAILABLE:
        logger.info(f"🔍 6-digit HS code detected: {hsc}. Expanding using {expansion_country_name}'s HS codes (regtype: {regtype.upper()})")
        try:
            # Expand 6-digit codes using the appropriate country's HS code list
            expanded_codes = hscode_expander.expand_6digit_to_8digit(hsc, expansion_country_id)
            
            if expanded_codes:
                logger.info(f"✅ Expanded {hsc} to {len(expanded_codes)} 8-digit codes")
                print(f"✅ Expanded {hsc} to {len(expanded_codes)} 8-digit codes")
                hsc_codes_to_scrape = [(item['code'], item['name']) for item in expanded_codes]
            else:
                logger.warning(f"⚠️  No 8-digit codes found for {hsc}. Using original 6-digit code.")
                print(f"⚠️  No 8-digit codes found for {hsc}. Using original 6-digit code.")
                item = hscodes_full.get(hsc, f"HS Code {hsc}")
                hsc_codes_to_scrape = [(hsc, item)]
        except Exception as e:
            logger.error(f"❌ Error expanding HS code: {e}. Using original 6-digit code.")
            item = hscodes_full.get(hsc, f"HS Code {hsc}")
            hsc_codes_to_scrape = [(hsc, item)]
    else:
        # Use the provided HS code as-is (8-digit or expansion not available)
        if len(hsc) == 6:
            logger.info(f"ℹ️  HS Code Expander not available. Using 6-digit code as-is: {hsc}")
        item = hscodes_full.get(hsc, f"HS Code {hsc}")
        hsc_codes_to_scrape = [(hsc, item)]
    
    # Scrape data for each HS code
    logger.info(f"📊 Scraping {len(hsc_codes_to_scrape)} HS code(s)")
    successful_scrapes = 0
    failed_scrapes = 0
    
    for idx, (hsc_code, product_name) in enumerate(hsc_codes_to_scrape, 1):
        logger.info(f"🔄 [{idx}/{len(hsc_codes_to_scrape)}] Processing HS code: {hsc_code}")
        
        # Construct and print the URL
        url = f"https://www.macmap.org/api/results/ntm-measure-by-regulation?reporter={c1_id}&partner={c2_id}&product={hsc_code}&regType={regtype.upper()}"
        logger.info(f"🌐 Scraping URL: {url}")
        print(f"🌐 MacMap Regulatory URL [{idx}/{len(hsc_codes_to_scrape)}]: {url}")
        
        try:
            req = SendGetRequests(url, headers, use_proxy=False)
            logger.info(f"📡 Response status: {req.status_code}")
            
            if req.status_code == 200:
                regulatory_data = req.json()
                data_count = len(regulatory_data) if isinstance(regulatory_data, list) else 1
                logger.info(f"✅ Retrieved {data_count} regulatory measure(s) for {hsc_code}")
                
                # Check if this exact data already exists to prevent duplicates
                existing = macmap_regulatory_collection.find_one({
                    "HsCode": hsc_code,
                    "ImportingCountry": country1,
                    "ExportingCountry": country2,
                    "Mode": "Import" if regtype.lower() == "i" else "Export"
                })
                
                if existing:
                    logger.info(f"⏭️  Skipping {hsc_code} - already exists in database")
                    print(f"⏭️  Skipping {hsc_code} - already exists in database")
                    successful_scrapes += 1
                    continue
                
                data = {}
                data["ScraperName"] = "macmap_regulatory_requirements_scraper"
                data["HsCode"] = hsc_code
                data["HsCode6Digit"] = hsc if len(hsc) == 6 else hsc_code[:6]  # Store original 6-digit code
                data["ProductName"] = product_name
                data["ImportingCountry"] = country1
                data["ExportingCountry"] = country2
                data["Source"] = "Macmap"
                data["TargetYear"] = None
                data["Mode"] = "Import" if regtype.lower() == "i" else "Export"
                data["Month"] = datetime.datetime.now().strftime("%b")
                data["Year"] = datetime.datetime.now().strftime("%Y")
                data["Data"] = regulatory_data
                data["DateCreated"] = datetime.datetime.now()
                data["DateUpdated"] = datetime.datetime.now()
                
                macmap_regulatory_collection.insert_one(data)
                logger.info(f"💾 Stored regulatory data for {hsc_code}")
                successful_scrapes += 1
            else:
                logger.error(f"❌ Failed to scrape {hsc_code}, status code: {req.status_code}")
                failed_scrapes += 1
        except Exception as e:
            logger.error(f"❌ Error scraping {hsc_code}: {e}")
            failed_scrapes += 1
    
    # Summary
    logger.info(f"🎉 Completed scraping: {successful_scrapes} successful, {failed_scrapes} failed out of {len(hsc_codes_to_scrape)} total")


def ScrapeMacmapCompareMarket(country, hsc):
    logger.info(f"Scraping Macmap compare market for country: {country}, HS code: {hsc}")
    try:
        c1_id = get_country_code(country)
    except KeyError as err:
        logger.error(str(err))
        raise
    item = hscodes_full[hsc]
    req = SendGetRequests(
        f"https://www.macmap.org/api/results/importerview?reporter=All&partner={c1_id}&product={hsc}",
        headers,
        use_proxy=False
    )
    logger.info(f"Compare market request: {req.url}, status: {req.status_code}")
    if req.status_code == 200:
        json_data = req.json()
        logger.info(f"Found {len(json_data['ImporterViewData'])} importer view items")
        data = {}
        data["ScraperName"] = "macmap_compare_market_scraper"
        data["HsCode"] = hsc
        data["ProductName"] = item
        data["ImportingCountry"] = None
        data["ExportingCountry"] = country
        data["Source"] = "Macmap"
        data["TargetYear"] = None
        data["Mode"] = None
        data["Month"] = datetime.datetime.now().strftime("%b")
        data["Year"] = datetime.datetime.now().strftime("%Y")
        data["Data"] = json_data["ImporterViewData"]
        data["DateCreated"] = datetime.datetime.now()
        data["DateUpdated"] = datetime.datetime.now()
        logger.info("Inserting compare market data into macmap_compare_market collection")
        macmap_compare_market_collection.insert_one(data)
        logger.info("Completed scraping Macmap compare market")
    else:
        logger.error(f"Failed to scrape compare market, status code: {req.status_code}")


def ScrapeMacmapCompetitors(country, hsc):
    logger.info(f"Scraping Macmap competitors for country: {country}, HS code: {hsc}")
    c1_id = countries[country]
    try:
        item = hscodes_full[hsc]
    except:
        item = hsc
    req = SendGetRequests(
        f"https://www.macmap.org/api/results/exporterview?reporter={c1_id}&partner=All&product={hsc}",
        headers,
        use_proxy=False
    )
    logger.info(f"Competitors request: {req.url}, status: {req.status_code}")
    if req.status_code == 200:
        json_data = req.json()
        logger.info(f"Found {len(json_data['ExporterViewData'])} importer view items")
        data = {}
        data["ScraperName"] = "macmap_competitors_scraper"
        data["HsCode"] = hsc
        data["ProductName"] = item
        data["ImportingCountry"] = country
        data["ExportingCountry"] = None
        data["Source"] = "Macmap"
        data["TargetYear"] = None
        data["Mode"] = None
        data["Month"] = datetime.datetime.now().strftime("%b")
        data["Year"] = datetime.datetime.now().strftime("%Y")
        data["Data"] = json_data["ExporterViewData"]
        data["DateCreated"] = datetime.datetime.now()
        data["DateUpdated"] = datetime.datetime.now()
        logger.info("Inserting competitors data into macmap_competitors collection")
        macmap_competitors_collection.insert_one(data)
        logger.info("Completed scraping Macmap competitors")
    else:
        logger.error(f"Failed to scrape competitors, status code: {req.status_code}")


def ScrapeMacmapProducts(country1, country2, hsc_lvl):
    logger.info(f"Scraping Macmap products for countries: {country1}, {country2}, HS level: {hsc_lvl}")
    c1_id = countries[country1]
    c2_id = countries[country2]
    req = SendGetRequests(
        f"https://www.macmap.org/api/results/productview?reporter={c1_id}&partner={c2_id}&product=All&level={hsc_lvl}",
        headers,
        use_proxy=False
    )
    logger.info(f"Products request: {req.url}, status: {req.status_code}")
    if req.status_code == 200:
        json_data = req.json()
        logger.info(f"Found {len(json_data['ProductViewData'])} product view items")
        data = {}
        data["ScraperName"] = "macmap_products_scraper"
        data["HsCode"] = "all"
        data["ProductName"] = "all"
        data["ImportingCountry"] = country1
        data["ExportingCountry"] = country2
        data["Source"] = "Macmap"
        data["TargetYear"] = None
        data["Mode"] = None
        data["Month"] = datetime.datetime.now().strftime("%b")
        data["Year"] = datetime.datetime.now().strftime("%Y")
        data["Data"] = json_data["ProductViewData"]
        data["DateCreated"] = datetime.datetime.now()
        data["DateUpdated"] = datetime.datetime.now()
        logger.info(f"Inserting products data into macmap_products collection")
        macmap_products_collection.insert_one(data)
        logger.info(f"Completed scraping Macmap products")
    else:
        logger.error(f"Failed to scrape products, status code: {req.status_code}")


def SCTariff(row):
    hsc_, year, c1_id, country = row
    hsc, item = hsc_
    logger.info(f"Scraping single country tariff for country: {country}, year: {year}, HS code: {hsc}")
    req = SendGetRequests(
        f"https://www.macmap.org/api/results/custom-duties-by-year?reporter={c1_id}&partner=all&product={hsc}&year={year}",
        headers,
        use_proxy=False
    )
    logger.info(f"Custom duties request: {req.url}, status: {req.status_code}")
    custom_tariff_data = []
    if req.status_code == 200:
        json_data = req.json()
        logger.info(f"Found {len(json_data['CustomDuty'])} custom duty items")
        if json_data['CustomDuty']:
            for i in json_data["CustomDuty"]:
                if i["ShowDetailLink"]:
                    logger.info(f"Processing custom duty with detail link")
                    custom_tariff_data.append(
                        ProcessTradeAgreement(i, c1_id, "all", year, hsc)
                    )
                else:
                    logger.info(f"Adding custom duty without detail link")
                    custom_tariff_data.append(i)
    else:
        logger.error(f"Failed to get custom duties, status code: {req.status_code}")
        return
        
    data = {}
    data["ScraperName"] = "macmap_tariff_scraper"
    data["HsCode"] = hsc
    data["ProductName"] = item
    data["ImportingCountry"] = country
    data["ExportingCountry"] = "All"
    data["Source"] = "Macmap"
    data["TargetYear"] = year
    data["Mode"] = None
    data["Month"] = datetime.datetime.now().strftime("%b")
    data["Year"] = datetime.datetime.now().strftime("%Y")
    data["Data"] = custom_tariff_data
    data["DateCreated"] = datetime.datetime.now()
    data["DateUpdated"] = datetime.datetime.now()
    logger.info(f"Inserting single country tariff data into macmap_full_tariff collection")
    macmap_full_tariff_collection.insert_one(data)
    logger.info(f"Completed scraping single country tariff")


def ScrapeTarrifFull(country):
    logger.info(f"Scraping full tariff for country: {country}")
    try:
        c1_id = countries[country]
        req = SendGetRequests(
            f"https://www.macmap.org/api/getyears?datatype=Tariff&reporters={c1_id}",
            headers,
            use_proxy=False
        )
        
        # Check if request was successful
        if req is None:
            logger.error(f"Failed to fetch years for country {country}")
            return
        
        logger.info(f"Get years request: {req.url}, status: {req.status_code}")
        all_combinations = []
        if req.status_code == 200:
            years = [x["Year"] for x in req.json()]
            logger.info(f"Found {len(years)} years: {years}")
            for year in years:
                req = SendGetRequests(
                    f'https://www.macmap.org/api/customs-duties-products?countryCode={c1_id}&level=8&year={year}',
                    headers,
                    use_proxy=False
                )
                if len(req.json()) > 0:
                    # Get all HS codes for this year (no filtering)
                    for i in req.json():
                        print(i['Code'], "processing")
                        hs = [i['Code'], i["Name"]]
                        x = [hs, year, c1_id, country]
                        all_combinations.append(x)
                else:
                    # If no products found, create a generic entry
                    x = ["", year, c1_id, country]
                    all_combinations.append(x)
                    
                    
            logger.info(f"Starting thread pool with {len(all_combinations)} tasks")
            with ThreadPoolExecutor(max_workers=3) as executor:
                executor.map(SCTariff, all_combinations)
            logger.info(f"Completed all thread pool tasks")
        else:
            logger.error(f"Failed to get years, status code: {req.status_code}")
    except Exception as e:
        logger.error(f"Error in ScrapeTarrifFull: {str(e)}", exc_info=True)