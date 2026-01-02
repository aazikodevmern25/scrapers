from urllib.parse import quote
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import logging
import os
from datetime import datetime
from utils import SendGetRequests,SendPostRequests,DownloadPdf,client,db
import requests
import json
from scrapy import Selector
import datetime


log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"indiantradeportal_{datetime.datetime.now().strftime('%Y%m%d')}.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('indiantradeportal')

itp_collection = db["indiantradeportal"]


itp_headers = {
  'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
  'accept-language': 'en-US,en;q=0.5',
  'cache-control': 'no-cache',
  'content-type': 'application/x-www-form-urlencoded',
  'dnt': '1',
  'origin': 'https://indiantradeportal.in',
  'pragma': 'no-cache',
  'priority': 'u=0, i',
  'referer': 'https://indiantradeportal.in/vs.jsp?pid=3&txthscode=7862',
  'sec-ch-ua': '"Not;A=Brand";v="99", "Brave";v="139", "Chromium";v="139"',
  'sec-ch-ua-mobile': '?0',
  'sec-ch-ua-platform': '"Linux"',
  'sec-fetch-dest': 'document',
  'sec-fetch-mode': 'navigate',
  'sec-fetch-site': 'same-origin',
  'sec-fetch-user': '?1',
  'sec-gpc': '1',
  'upgrade-insecure-requests': '1',
  'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
  'Cookie': 'user_visit_new=1; JSESSIONID=2AFF79AC3B1FF116C0A2260A0C5BE6DF'
}


headers = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en-US,en;q=0.9",
    "priority": "u=0, i",
    "referer": "https://indiantradeportal.in/vs.jsp?pid=2&productID=16284",
    "sec-ch-ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
}

short_headers  = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en-US,en;q=0.9",
    "priority": "u=1, i",
    "referer": "https://indiantradeportal.in/vs.jsp?pid=3&txthscode=3098",
    "sec-ch-ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "x-requested-with": "XMLHttpRequest"
}


def CleanFilename(fn):
    logger.info(f"Cleaning filename: {fn}")
    j = fn
    extra_shit = '/.\\,(){}[]'
    for i in extra_shit:
        j = j.replace(i,'')
    logger.info(f"Cleaned filename: {j}")
    return j



def ParseGstDetails(hsc_full,csrf_token,mode):
    logger.info(f"Parsing GST details for HSC: {hsc_full}, mode: {mode}")
    req = SendGetRequests(f'https://indiantradeportal.in/apps/ajaxIGST.jsp?hscode={hsc_full}&reqtype={mode}&reqfrom={mode}&country=&csrftoken={csrf_token}',
        headers,use_proxy=False)
    logger.info(f"GST details request: {req.url}, status: {req.status_code}")
    resp = Selector(text=req.text)
    data = {}
    data['ItcHsCode'] = resp.xpath('//table//tr[not(@style)][1]/td[1]/text()').get()
    data['Description'] = ' '.join(resp.xpath('//table//tr[not(@style)][1]/td[2]//text()').getall())
    data['Details'] = []
    data['RawHtmlResponse'] = req.text
    for _,i in enumerate(resp.xpath('//table//tr[not(@style)]'),start=1):
        if _ == 1:
            hsc = i.xpath('./td[3]/text()').get()
            desc = i.xpath('./td[4]/text()').get()
            gstrate = i.xpath('./td[5]/text()').get()
            gsturl = i.xpath('./td[5]/div/a/@href').get()
            gsturlname = i.xpath('./td[5]/div/a/text()').get()
            gstcompensation = i.xpath('./td[6]/text()').get()
            specialadditionduty = i.xpath('./td[8]/text()').get()
            exemption = i.xpath('./td[7]/a/text()').get()
            exemptionurl = i.xpath('./td[7]/a/@href').get()
        else:
            hsc = i.xpath('./td[1]/text()').get()
            desc = i.xpath('./td[2]/text()').get()
            gstrate = i.xpath('./td[3]/text()').get()
            gsturl = i.xpath('./td[3]/div/a/@href').get()
            gsturlname = i.xpath('./td[3]/div/a/text()').get()
            gstcompensation = i.xpath('./td[4]/text()').get()
            specialadditionduty = i.xpath('./td[6]/text()').get()
            exemption = i.xpath('./td[5]/a/text()').get()
            exemptionurl = i.xpath('./td[5]/a/@href').get()

        fname = CleanFilename(f'{hsc_full}_{hsc}_{exemption}')
        fname = f'{fname}.pdf'
        gfn = CleanFilename(f'{hsc_full}_{hsc}_{desc}')
        gfn = f'{gfn}.pdf'
        if exemptionurl:
            logger.info(f"Downloading exemption PDF: {exemptionurl}")
            # DownloadPdf(exemptionurl,gfn)
        dt = {}
        dt['GstHSCode'] = hsc
        dt['GstDescription'] = desc
        dt['GstRate'] = gstrate
        dt['GstRateUrl'] = gsturl
        dt['GstRateUrlName'] = gsturlname
        dt['GstPdfName'] = gfn
        dt['GstCompensation'] = gstcompensation
        dt['SpecialAdditionalDuty'] = specialadditionduty
        dt['Exemption'] = exemption
        dt['ExemptionUrl'] = exemptionurl
        dt['ExemptionPdfName'] = fname
        data['Details'].append(dt)
        print(dt)
    logger.info(f"Completed parsing GST details for HSC: {hsc_full}")
    
    return data



def ParseImportExportPolicy(id_,csrf_token,mode):
    logger.info(f"Parsing {mode} policy for ID: {id_}")
    import_req = SendGetRequests(f'https://indiantradeportal.in/apps/ajaxPolicy.jsp?hscode={id_}&reqtype={mode}&reqfrom={mode}&country=&csrftoken={csrf_token}',
        headers,use_proxy=False)
    logger.info(f"Policy request: {import_req.url}, status: {import_req.status_code}")
    resp =Selector(text=import_req.text)
    if mode != 'export':
        data = []
        
        for _,sr in enumerate(resp.xpath('//table//tr')):
            if _ == 0:continue
            d = {}
            d['ItcHsCode'] = sr.xpath('./td[1]/text()').get()
            d['Description'] = ' '.join(sr.xpath('./td[2]//text()').getall())
            d['Policy'] = sr.xpath('./td[3]/text()').get()
            d['Restriction'] = sr.xpath('./td[4]/text()').get()
            d['Explanation'] = sr.xpath('./td[5]/text()').get()
            d['Documents'] = []
            for a in sr.xpath('./td[5]/div/a'):
                dt = {}
                pdf_url  = a.xpath('./@href').get()
                t = a.xpath('./text()').get()
                pdf_name = f'{d["ItcHsCode"]}_{t}_{int(datetime.datetime.now().timestamp())}'
                pdf_name = f'{CleanFilename(pdf_name)}.pdf'
                logger.info(f"Downloading policy document: {pdf_url}")
                # DownloadPdf(pdf_url,pdf_name)
                dt['PdfUrl'] = pdf_url
                dt['Title'] = t
                dt['Filename'] = pdf_name
                d['Documents'].append(dt)
            data.append(d)
    else:
        data = []
        htscode = None
        description = None
        for _,sr in enumerate(resp.xpath('//table//tr')):
            d = {}
            if _ == 0:continue
            if _ == 1:
                htscode = sr.xpath('./td[1]/text()').get()
                description = ' '.join(sr.xpath('./td[2]//text()').getall())
                d['ItcHsCode'] = htscode
                d['Description'] = description
                d['PolicyDescription'] = ' '.join(sr.xpath('./td[3]//text()').getall())
                d['Unit'] = sr.xpath('./td[4]/text()').get()
                d['Policy'] = sr.xpath('./td[5]/text()').get()
                d['Restriction'] = sr.xpath('./td[6]/text()').get()
                d['Documents'] = []
                for a in sr.xpath('./td[6]//a'):
                    dt = {}
                    pdf_url  = a.xpath('./@href').get()
                    t = a.xpath('./text()').get()
                    pdf_name = f'{d["ItcHsCode"]}_{t}_{int(datetime.datetime.now().timestamp())}'
                    pdf_name = f'{CleanFilename(pdf_name)}.pdf'
                    logger.info(f"Downloading policy document: {pdf_url}")
                    # DownloadPdf(pdf_url,pdf_name)
                    dt['PdfUrl'] = pdf_url
                    dt['Title'] = t
                    dt['Filename'] = pdf_name
                    d['Documents'].append(dt)
                data.append(d)
            else:
                d['ItcHsCode'] = htscode
                d['Description'] = description
                d['PolicyDescription'] = ' '.join(sr.xpath('./td[1]//text()').getall())
                d['Unit'] = sr.xpath('./td[2]/text()').get()
                d['Policy'] = sr.xpath('./td[3]/text()').get()
                d['Restriction'] = sr.xpath('./td[4]/text()').get()
                d['Documents'] = []
                for a in sr.xpath('./td[4]//a'):
                    dt = {}
                    pdf_url  = a.xpath('./@href').get()
                    t = a.xpath('./text()').get()
                    pdf_name = f'{d["ItcHsCode"]}_{t}_{int(datetime.datetime.now().timestamp())}'
                    pdf_name = f'{CleanFilename(pdf_name)}.pdf'
                    logger.info(f"Downloading policy document: {pdf_url}")
                    # DownloadPdf(pdf_url,pdf_name)
                    dt['PdfUrl'] = pdf_url
                    dt['Title'] = t
                    dt['Filename'] = pdf_name
                    d['Documents'].append(dt)
                data.append(d)


    logger.info(f"Completed parsing {mode} policy for ID: {id_}")
    return data


def ParseSBS(hsc_full,country_code):
    logger.info(f"Parsing SBS for HSC: {hsc_full}, country code: {country_code}")
    sbs_req = SendGetRequests(f"https://indiantradeportal.in/apps/ajaxSPSTBT.jsp?country={country_code}&hscode={hsc_full}",headers,use_proxy=False)
    logger.info(f"SBS request: {sbs_req.url}, status: {sbs_req.status_code}")
    resp =Selector(text=sbs_req.text)
    sbs_data = []
    for row in resp.xpath('//tr'):
        a = row.xpath('./td[1]/text()').get()
        b = row.xpath('./td[2]/text()').get()
        c = row.xpath('./td[3]/text()').get()
        d = row.xpath('./td[4]/a/@href').get()
        pdf_name = f'{b}{c}{int(datetime.datetime.now().timestamp())}'
        pdf_name = f'{CleanFilename(pdf_name)}.pdf'
        if a:
            logger.info(f"Downloading SBS document: {d}")
            # DownloadPdf(d,pdf_name)
            e = {}
            e['Hscode'] = a
            e['Document'] = b
            e['TypeOfDocuement'] = c
            e['DocumentUrl'] = d
            e['DocumentName'] = pdf_name
            sbs_data.append(e)

    logger.info(f"Completed parsing SBS for HSC: {hsc_full}, found {len(sbs_data)} documents")
    return sbs_data



def ParseHtml(text,hsc):
    logger.info(f"Parsing HTML for HSC: {hsc}")
    title = Selector(text=text).xpath('//tr[@class="sarrcProductName"]/td/text()').get()
    hsc_full = title.split('|')[0]
    logger.info(f"Title: {title}, HSC full: {hsc_full}")
    soup = BeautifulSoup(text, 'html.parser')
    base_url = "https://indiantradeportal.in"

    data_with_links = {}
    current_country = None

    extra_keys= ["CC","CTH","CTSH","RVC","HS Code","","Product",]

    for row in soup.find_all('tr'):
        classes = row.get('class', [])

        if 'sarrc-country' in classes:
            td = row.find('td')
            if td and td.contents:
                current_country = td.contents[0].strip()
                data_with_links[current_country] = {}
        elif current_country:
            cells = row.find_all('td')
            if len(cells) == 2:
                key = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                if key not in extra_keys:
                    # Check for link
                    link_tag = cells[1].find('a', href=True)
                    if link_tag:
                        pdf_url = urljoin(base_url, link_tag['href'])
                        # pdf_url =  link_tag['href']
                        pdf_name = f'{hsc}_{current_country}_{int(datetime.datetime.now().timestamp())}.pdf'
                        logger.info(f"Downloading PDF for {current_country}: {pdf_url}")
                        # DownloadPdf(pdf_url,pdf_name)
                        data_with_links[current_country][key] = {
                            "value": value,
                            "PdfUrl": pdf_url,
                            "Filename":pdf_name
                        }

                    else:
                        data_with_links[current_country][key] = value


    for row in soup.find_all('tr', class_='sarrc-country'):
        td = row.find('td')
        if td and td.contents:
            country_name = td.contents[0].strip()
            next_row = row.find_next_sibling('tr')
            date_str = next_row.get('data-date', '').strip()
            if date_str:
                if country_name in data_with_links:
                    data_with_links[country_name]['AsOfDate'] = date_str
    data_with_links['Title'] = title
    data_with_links['HSCodeFull'] = hsc_full

    logger.info(f"Completed parsing HTML for HSC: {hsc}")
    return data_with_links



def ScrapeImportData(row):
    logger.info(f"Scraping import data for HSC: {row['hsc']}, item: {row['item']}")
    req = SendGetRequests(f'https://indiantradeportal.in/{row["import"]}',headers,use_proxy=False)
    logger.info(f"Import request: {req.url}, status: {req.status_code}")
    resp = Selector(text=req.text)
    ids_ = resp.xpath('//table[@class="tblhs"]//input[@name="txthscode"]/@value').getall()
    logger.info(f"Found IDs: {ids_}")
    pid = resp.xpath('//form[@id="productSelection"]//input[@name="pid"]/@value').get()
    id_ = resp.xpath('//table[@class="tblhs"]//input[@name="txthscode"]/@value').get()
    url = f'https://indiantradeportal.in/vs.jsp?pid={pid}&txthscode={id_}'
    req = SendGetRequests(url,headers,use_proxy=False)
    logger.info(f"Product selection request: {req.url}, status: {req.status_code}")
    resp = Selector(text=req.text)

    cpid = resp.xpath('//form[@id="frmCountryAgreement"]//input[@name="pid"]/@value').get()
    countries = []

    for sr in resp.xpath('//tr[@class="top25Countries"]//table//tr'):
        country = sr.xpath('.//input[@class="getListCountry"]/@data-lang').get()
        cid = sr.xpath('.//input[@class="getListCountry"]/@value').get()
        req1 = SendGetRequests(f"https://indiantradeportal.in/apps/ajaxAgreement.jsp?type=1&countryID={cid}",short_headers,use_proxy=False)
        logger.info(f"Country agreement request: {req1.url}, status: {req1.status_code}")
        agreement_ids = Selector(text=req1.text).xpath('//input/@value').getall()
        agreement_ids.extend([cid,country])
        countries.append(agreement_ids)
    payload = f'pid=4&hscode={id_}&chkTop25Region=on&'
    for o in countries:
        o = [x for x in o if '-' in x and 'agt' not in x]
        for x in o:
            payload += f'agreement1={x}&'
        if payload[-1] == '&':
            payload= payload[:-1]

    logger.info(f"Sending main request with payload size: {len(payload)}")
    main_req = SendPostRequests('https://indiantradeportal.in/vs.jsp',itp_headers,payload,use_proxy=False)
    logger.info(f"Main request: {main_req.url}, status: {main_req.status_code}, payload: {payload}")
    csrf_token = Selector(text=main_req.text).xpath('//meta[@name="csrftoken"]/@content').get()
    logger.info(f"CSRF Token: {csrf_token}")

    results = ParseHtml(main_req.text,row['hsc'])
    hsc_full = results['HSCodeFull']
    hsc_full = hsc_full.strip()
    logger.info("Parsing SBS data")
    sbs_data = ParseSBS(hsc_full,95)
    logger.info("Parsing import policies")
    import_policies = ParseImportExportPolicy(id_,csrf_token,"import")
    logger.info("Parsing GST details")
    gst = ParseGstDetails(hsc_full,csrf_token,"import")


    importGstData = {}
    importGstData['ImportPolicies'] = import_policies
    importGstData['SBSDetails'] = sbs_data
    importGstData['Gst'] = gst
    importGstData['Countries'] = results

    data = {}
    data["ScraperName"] = "indian_trade_portal_scraper"
    data["HsCode"] = row['hsc']
    data['HsCodeSearched'] = row['shsc']
    data["ProductName"] = row['item']
    data["Source"] = "IndianTradePortal"
    data["Mode"] = "Import"
    data["Month"] = datetime.datetime.now().strftime("%b")
    data["Year"] = datetime.datetime.now().strftime("%Y")
    data["Data"] = importGstData
    data["DateCreated"] = str(datetime.datetime.now())
    data["DateUpdated"] = str(datetime.datetime.now())
    logger.info(f"Inserting import data for HSC: {row['hsc']} into database")
    itp_collection.insert_one(data)
    logger.info(f"Completed scraping import data for HSC: {row['hsc']}")



def ScrapeExportData(row):
    logger.info(f"Scraping export data for HSC: {row['hsc']}, item: {row['item']}")
    req = SendGetRequests(f'https://indiantradeportal.in/{row["export"]}',headers,use_proxy=False)
    logger.info(f"Export request: {req.url}, status: {req.status_code}")
    resp = Selector(text=req.text)
    product_id = row['export'].split('&productID=')[-1]
    logger.info(f"Product ID: {product_id}")
    ids_ = resp.xpath('//table[@class="tblhs"]//input[@name="txthscode"]/@value').getall()
    hscs_export = resp.xpath('//table[@class="tblhs"]//tr[contains(@class,"actionLink")]/td[1]/text()').getall()
    hscsd_export = resp.xpath('//table[@class="tblhs"]//tr[contains(@class,"actionLink")]/td[2]/text()').getall()
    hsc_ids = list(zip(ids_,hscs_export,hscsd_export))
    main_data = {}
    for id_,hsx,hsxd in hsc_ids:
        pid = resp.xpath('//form[@id="productSelection"]//input[@name="pid"]/@value').get()
        url = f'https://indiantradeportal.in/vs.jsp?pid={pid}&txthscode={id_}&productID={product_id}'
        req = SendGetRequests(url,headers,use_proxy=False)
        logger.info(f"Product selection request: {req.url}, status: {req.status_code}")
        resp = Selector(text=req.text)
    
        cpid = resp.xpath('//form[@id="frmCountryAgreement"]//input[@name="pid"]/@value').get()
        
        # Debug: Save HTML to file to inspect
        debug_file = f"logs/export_page_debug_{id_}.html"
        with open(debug_file, 'w', encoding='utf-8') as f:
            f.write(req.text)
        logger.info(f"Saved HTML response to {debug_file} for inspection")
        
        # Define all country region classes and their checkbox names
        region_configs = [
            ('top25Countries', 'chkTop25Region'),
            ('saarcregionCountries', 'txtsaarcregion'),
            ('aseanregionCountries', 'txtaseanregion'),
            ('euregionCountries', 'txteuregion'),
            ('gccregionCountries', 'txtgccregion'),
            ('mercosurregionCountries', 'txtmercosurregion'),
            ('eeuregionCountries', 'txteeuregion'),
            ('eacregionCountries', 'txteacregion'),
            ('leastdevelopedcountriesCountries', 'txtleastdevelopedcountries'),
            ('othercountriesCountries', 'txtothercountries')
        ]
        
        # Collect all countries from all regions
        all_countries = []
        logger.info("Collecting countries from all regions")
        
        # Debug: Check ALL country inputs on the page
        all_country_inputs = resp.xpath('//input[@class="getListCountry"]')
        logger.info(f"Total country inputs found on page: {len(all_country_inputs)} for HSC {id_}")
        
        # Check if there are any "Show All" or expand buttons
        show_all_buttons = resp.xpath('//a[contains(text(), "Show All")] | //a[contains(text(), "show all")] | //button[contains(text(), "Show All")]')
        logger.info(f"Found {len(show_all_buttons)} 'Show All' buttons on page for HSC {id_}")
        
        # Debug: Check how many tr elements exist for each region
        for region_class, checkbox_name in region_configs:
            tr_count = len(resp.xpath(f'//tr[contains(@class,"{region_class}")]'))
            logger.info(f"Region {region_class}: Found {tr_count} <tr> elements for HSC {id_}")
        
        for region_class, checkbox_name in region_configs:
            logger.info(f"Processing region: {region_class}")
            region_count = 0
            
            # Get all country labels from this region (including hidden ones)
            # The structure is: tr[contains(@class,"regionClass")]/td/table/tr[contains(@class,"regionClass")]/td/label
            # We need to find the nested table rows that contain the actual country checkboxes
            country_labels = resp.xpath(f'//tr[contains(@class,"{region_class}")]/td/table//tr[contains(@class,"{region_class}")]//label[@class="countryList"]')
            logger.info(f"Found {len(country_labels)} country labels in region {region_class}")
            
            # Also try alternative XPath to catch all countries
            if len(country_labels) == 0:
                logger.warning(f"No countries found with primary XPath for {region_class}, trying alternative XPath")
                country_labels = resp.xpath(f'//tr[contains(@class,"{region_class}")]//label[@class="countryList"]')
                logger.info(f"Alternative XPath found {len(country_labels)} country labels in region {region_class}")
            
            for country_label in country_labels:
                cid = country_label.xpath('./input[@class="getListCountry"]/@value').get()
                # Get country name - it's the text after the input element
                country_text = country_label.xpath('./text()').getall()
                country = ''.join(country_text).strip() if country_text else None
                
                if cid and country:
                    country = country.strip()
                    logger.info(f"Found country: {country} (ID: {cid}) from region: {region_class}")
                    req1 = SendGetRequests(f"https://indiantradeportal.in/apps/ajaxAgreement.jsp?type=3&countryID={cid}",short_headers,use_proxy=False)
                    logger.info(f"Country agreement request: {req1.url}, status: {req1.status_code}")
                    agreement_ids = Selector(text=req1.text).xpath('//input/@value').getall()
                    agreement_ids.extend([cid, country, region_class, checkbox_name])
                    all_countries.append(agreement_ids)
                    region_count += 1
                else:
                    logger.warning(f"Skipping label - cid: {cid}, country: {country}")
            
            logger.info(f"Found {region_count} countries in region: {region_class} for HSC {id_}")
        
        logger.info(f"Total countries collected (with duplicates): {len(all_countries)} for HSC {id_}")
        
        # Deduplicate countries by ID (keep first occurrence)
        unique_countries = {}
        unique_countries_list = []
        for country_data in all_countries:
            cid = country_data[-4]
            if cid not in unique_countries:
                unique_countries[cid] = country_data
                unique_countries_list.append(country_data)
        
        all_countries = unique_countries_list
        logger.info(f"Unique countries after deduplication: {len(all_countries)} for HSC {id_}")
        logger.info(f"Unique country names for HSC {id_}: {sorted([c[-3] for c in all_countries])}")
        
        # Build payload with all regions checked
        base_payload = f'pid=16&hscode={row["hsc"]}&hcode={product_id}&indHscode={id_}'
        
        # Add all region checkboxes
        for _, checkbox_name in region_configs:
            base_payload += f'&{checkbox_name}=on'
        
        # Add all agreements from all countries
        all_agreements = []
        for country_data in all_countries:
            agreements = [x for x in country_data if '-' in x and 'agt' not in x]
            all_agreements.extend(agreements)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_agreements = []
        for agr in all_agreements:
            if agr not in seen:
                seen.add(agr)
                unique_agreements.append(agr)
        
        for agr in unique_agreements:
            base_payload += f'&agreement1={agr}'
        
        logger.info(f"Built payload with {len(unique_agreements)} unique agreements from {len(all_countries)} countries")
        
        # Make single request with all countries
        mp_req = SendGetRequests(f'https://indiantradeportal.in/vs.jsp?{base_payload}',headers=headers,use_proxy=False)
        logger.info(f"Export request with all regions: {mp_req.url}, status: {mp_req.status_code}")
        
        # Now process each country's data
        logger.info(f"Processing {len(all_countries)} countries for export data")
        for o in all_countries:
            country_name = o[-3]
            country_id = o[-4]
            
            try:
                logger.info(f"Starting processing for country: {country_name} (ID: {country_id})")
                
                # Build payload for this specific country
                oo = [x for x in o if '-' in x and 'agt' not in x]
                country_payload = f'pid=16&hscode={row["hsc"]}&hcode={product_id}&indHscode={id_}&{o[-1]}=on&'
                for x in oo:
                    country_payload += f'agreement1={x}&'
                if country_payload[-1] == '&':
                    country_payload = country_payload[:-1]
        
                mp_req = SendGetRequests(f'https://indiantradeportal.in/vs.jsp?{country_payload}',headers=headers,use_proxy=False)
                logger.info(f"Export request for country {country_name}: {mp_req.url}, status: {mp_req.status_code}")
        
                items = []
                for td_id in Selector(text=mp_req.text).xpath('//table[@class="result"]//tr/td/@id').getall():
                    logger.info(f"Processing TD ID: {td_id}")
                    h_req = SendGetRequests(f'https://indiantradeportal.in/apps/ajaxProductList.jsp?cid={td_id}&hcode={row["hsc"]}',short_headers,use_proxy=False)
                    logger.info(f"Product list request: {h_req.url}, status: {h_req.status_code}")
                    for lbl in Selector(text=h_req.text).xpath('//label'):
                        a = lbl.xpath('./@title').get()
                        b = lbl.xpath('./input/@value').get()
                        c = lbl.xpath('./input/@name').get()
                        items.append([a,b,c])
        
                logger.info(f"Found {len(items)} items for country {country_name}")
                
                if not items:
                    logger.warning(f"No items found for country {country_name}, skipping")
                    continue
                
                # Initialize country data only if we have items
                main_data[country_name] = {}
                
            except Exception as e:
                logger.error(f"Error processing country {country_name}: {str(e)}", exc_info=True)
                continue
            
            for itm in items:
                try:
                    logger.info(f"Processing item {itm[1]} for country {country_name}")
                    hf = f'{itm[1]}-{itm[2]}'
                    main_data[country_name][itm[1]] = {}
                    main_data[country_name][itm[1]]['HscodeDescription'] = itm[0]
                    h = itm[1]
                    agreements = ','.join(oo)
                    agreements = agreements.replace(',','%2C')
                    furl = f'https://indiantradeportal.in/vs.jsp?pid=17&agreements={agreements}&indHscode={id_}&hscodes={hf}%2C&{itm[2]}={h}'
                    f_req = SendGetRequests(furl,headers,use_proxy=False)
                    logger.info(f"Final request for item {itm[1]}: {f_req.url}, status: {f_req.status_code}")
                    resp = Selector(text=f_req.text)
                    csrf_token = resp.xpath('//meta[@name="csrftoken"]/@content').get()
                    logger.info(f"Parsing export table for item {itm[1]}")
                    export_data = ParseExportTable(resp,id_,country_name)
                    logger.info("Parsing duty drawback")
                    duty_drawback = ParseDutyDrawback(id_,csrf_token)
                    logger.info("Parsing interest subvention")
                    interest_subvention = ParseInterestSubvention(id_,csrf_token)
                    logger.info("Parsing ROD TEP")
                    rod_tep = ParseRodTep(id_,csrf_token)
                    logger.info(f"Parsing SBS for item {itm[1]}")
                    sbs = ParseSBS(itm[1],country_id)
                    logger.info(f"Parsing GST for item {itm[1]}")
                    gst = ParseGstDetails(hsx,csrf_token,'export')
                    logger.info("Parsing export policies")
                    export_policies = ParseImportExportPolicy(id_,csrf_token,"export")
        
                    main_data[country_name][itm[1]]["Data"] = export_data
                    main_data[country_name][itm[1]]["Hscode"] = hsx
                    main_data[country_name][itm[1]]["HscodeDescription"] = hsxd
                    main_data[country_name][itm[1]]["ExportPolicy"] = export_policies
                    main_data[country_name][itm[1]]["DutyDrawback"] = duty_drawback
                    main_data[country_name][itm[1]]['InterestSubvention'] = interest_subvention
                    main_data[country_name][itm[1]]['RodTep'] = rod_tep
                    main_data[country_name][itm[1]]['Sbs'] = sbs
                    main_data[country_name][itm[1]]['Gst'] = gst
                    logger.info(f"Successfully processed item {itm[1]} for country {country_name}")
                except Exception as e:
                    logger.error(f"Error processing item {itm[1]} for country {country_name}: {str(e)}", exc_info=True)
                    continue
    
    
        # Filter out countries with no data
        main_data = {k: v for k, v in main_data.items() if v}
        
        data = {}
        data["ScraperName"] = "indian_trade_portal_scraper"
        data["HsCode"] = row['hsc']
        data['HsCodeSearched'] = row['shsc']
        data["ProductName"] = row['item']
        data["Source"] = "IndianTradePortal"
        data["Mode"] = "Export"
        data["Month"] = datetime.datetime.now().strftime("%b")
        data["Year"] = datetime.datetime.now().strftime("%Y")
        data["Data"] = main_data
        data["DateCreated"] = str(datetime.datetime.now())
        data["DateUpdated"] = str(datetime.datetime.now())
        logger.info(f"Inserting export data for HSC: {row['hsc']} with {len(main_data)} countries into database")
        logger.info(f"Countries being saved: {sorted(list(main_data.keys()))}")
        itp_collection.insert_one(data)
        logger.info(f"Completed scraping export data for HSC: {row['hsc']}")
    




def ParseExportTable(resp,hsc,current_country):
    logger.info(f"Parsing export table for HSC: {hsc}, country: {current_country}")
    base_url = "https://indiantradeportal.in"
    data = {}
    data['title'] = resp.xpath('//table[@class="result"]//tr[2]/td/text()').get()

    for sr in resp.xpath('//table[@class="result"]//tr[position() > 2]'):
        pdf_link = sr.xpath('./td[3]/a/@href').get()
        a = sr.xpath('./td[2]/text()').get()
        b = sr.xpath('./td[3]/text()').get()
        if pdf_link:
            pdf_name = f'{hsc}_{current_country}_{int(datetime.datetime.now().timestamp())}.pdf'
            logger.info(f"Downloading export table PDF: {pdf_link}")
            # DownloadPdf(pdf_link,pdf_name)
            data[a] = {}
            data[a]['value'] = b
            data[a]['PdfLink'] = pdf_link
            data[a]['Filename'] = pdf_name

        else:
            data[a] = b

    logger.info(f"Completed parsing export table, found {len(data) - 1} entries")
    return data


def ParseDutyDrawback(hid,csrf_token):
    logger.info(f"Parsing duty drawback for HID: {hid}")
    req = SendGetRequests(f'https://indiantradeportal.in/apps/ajaxPolicy.jsp?hscode={hid}&reqtype=drawback&reqfrom=export&country=&csrftoken={csrf_token}',short_headers,use_proxy=False)
    logger.info(f"Duty drawback request: {req.url}, status: {req.status_code}")
    resp = Selector(text=req.text)
    data = []
    
    for _,sr in enumerate(resp.xpath('//table//tr')):
        if _ == 0:continue
        d = {}
        d['ItcHsCode'] = sr.xpath('./td[1]/text()').get()
        d['Description'] = ' '.join(sr.xpath('./td[2]//text()').getall())
        d['DutyDrawbackCode'] = sr.xpath('./td[3]/text()').get()
        d['DrawbackDecision'] = ' '.join(sr.xpath('./td[4]//text()').getall())
        d['Unit'] = sr.xpath('./td[5]/text()').get()
        d['DrawbackRate'] = sr.xpath('./td[6]/text()').get()
        d['DrawbackCapPerUnitInRs.'] = sr.xpath('./td[7]/text()').get()
        data.append(d)
    
    logger.info(f"Completed parsing duty drawback for HID: {hid}, found {len(data)} rows")
    return data


def ParseInterestSubvention(hid,csrf_token):
    logger.info(f"Parsing interest subvention for HID: {hid}")
    req = SendGetRequests(f'https://indiantradeportal.in/apps/ajaxPolicy.jsp?hscode={hid}&reqtype=subvention&reqfrom=export&country=&csrftoken={csrf_token}',short_headers,use_proxy=False)
    logger.info(f"Interest subvention request: {req.url}, status: {req.status_code}")
    resp = Selector(text=req.text)
    data = []
    
    for _,sr in enumerate(resp.xpath('//table[@class="sortable policies"]//tr')):
        if _ == 0:continue
        d = {}
        d['ItcHsCode'] = sr.xpath('./td[1]/text()').get()
        d['ItcHsDescription'] = ' '.join(sr.xpath('./td[2]//text()').getall())
        d['ItcHs4DigitCode'] = sr.xpath('./td[3]/text()').get()
        d['ProductCode'] = sr.xpath('./td[4]/text()').get()
        d['ItcHs4DigitCodeDescription'] = ' '.join(sr.xpath('./td[5]//text()').getall())
        d['MSMESectorManufacturers'] = sr.xpath('./td[6]/text()').get()
        d['MSMESectorManufacturersnotes'] = sr.xpath('./td[6]/div/a/text()').get()
        d['PdfUrl'] = sr.xpath('./td[6]/div/a/@href').get()
        d['MerchantExporter'] = sr.xpath('./td[7]/text()').get()
        
        # Generate filename if PDF URL exists
        link_text = sr.xpath('./td[6]/div/a/text()').get()
        if d['PdfUrl'] and link_text:
            filename = f'{hid}_{link_text}_{int(datetime.datetime.now().timestamp())}'
            filename = f'{CleanFilename(filename)}.pdf'
            d['Filename'] = filename
            logger.info(f"Downloading interest subvention PDF: {d['PdfUrl']}")
            # DownloadPdf(d['PdfUrl'],filename)
        
        data.append(d)
    
    logger.info(f"Completed parsing interest subvention for HID: {hid}, found {len(data)} rows")
    return data


def ParseRodTep(hid,csrf_token):
    logger.info(f"Parsing ROD TEP for HID: {hid}")
    req = SendGetRequests(f'https://indiantradeportal.in/apps/ajaxPolicy.jsp?hscode={hid}&reqtype=meis&reqfrom=export&country=14&csrftoken={csrf_token}',short_headers,use_proxy=False)
    logger.info(f"ROD TEP request: {req.url}, status: {req.status_code}")
    resp = Selector(text=req.text)
    data = {}
    data['ItcHsCode'] = resp.xpath('//table[@class="sortable policies"]//tr[2]/td[1]/text()').get()
    data['ItcHsDescription'] = ' '.join(resp.xpath('//table[@class="sortable policies"]//tr[2]/td[2]//text()').getall())
    data['RoDTEPDescription'] = ' '.join(resp.xpath('//table[@class="sortable policies"]//tr[2]/td[3]//text()').getall())
    data['RODTEPRateDTAExportsAgeOfFOB'] = resp.xpath('//table[@class="sortable policies"]//tr[2]/td[4]/text()').get()
    data['UQC'] = resp.xpath('//table[@class="sortable policies"]//tr[2]/td[5]/text()').get()
    data['Cap(RsPerUQC)'] = resp.xpath('//table[@class="sortable policies"]//tr[2]/td[6]/text()').get()
    data['RoDTEPRatesAA/EOU/SEZExportsAgeOfFOB'] = resp.xpath('//table[@class="sortable policies"]//tr[2]/td[7]/text()').get()
    data['UQC2'] = resp.xpath('//table[@class="sortable policies"]//tr[2]/td[8]/text()').get()
    data['Cap(RsPerUQC)2'] = resp.xpath('//table[@class="sortable policies"]//tr[2]/td[9]/text()').get()
    logger.info(f"Completed parsing ROD TEP for HID: {hid}")
    return data



def IndianTradePortalScrape(hs_code):
    try:
        logger.info(f"Starting Indian Trade Portal scrape for HS code: {hs_code}")
        req = SendGetRequests(f"https://indiantradeportal.in/vs.jsp?pid=1&txthscode={hs_code}&txtproduct=&btnSubmit=Search",
            itp_headers,use_proxy=False
        )
        logger.info(f"Initial request: {req.url}, status: {req.status_code}")
        hscode_list = []
        resp = Selector(text=req.text)
        for _,i in enumerate(resp.xpath('//table[@class="sortable"]/tbody/tr'),start=1):
            tr = {}
            tr['shsc'] = hs_code
            tr['hsc'] = i.xpath('./td[2]/text()').get()
            tr['item'] = i.xpath('./td[3]/text()').get()
            tr['import'] = i.xpath('./td[4]/a[1]/@href').get()
            tr['export'] = i.xpath('./td[4]/a[2]/@href').get()
            hscode_list.append(tr)

        logger.info(f"Found {len(hscode_list)} HS codes to process")
        for idx, o in enumerate(hscode_list, 1):
            logger.info(f"Processing HS code {idx}/{len(hscode_list)}: {o['hsc']}")
            ScrapeImportData(o)
            ScrapeExportData(o)

        logger.info(f"Completed Indian Trade Portal scrape for HS code: {hs_code}")
    except Exception as e:
        logger.error(f"Error in Indian Trade Portal scraper: {str(e)}", exc_info=True)