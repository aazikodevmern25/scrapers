from scrapy import Selector
import json
import re

def parse_trademap_table_flexible(html_content):
    import logging
    logger = logging.getLogger(__name__)
    
    # Handle None or empty content
    if not html_content:
        logger.warning("parse_trademap_table_flexible: Received None or empty html_content")
        return {
            "format": "no_data",
            "trade_descriptions": [],
            "years": [],
            "products": []
        }
    
    selector = Selector(text=html_content)
    
    has_hs8_column = bool(selector.xpath('//th[contains(text(), "HS8")]'))
    
    header_spans = selector.xpath('//td[@align="center"]/span/text()').getall()
    trade_descriptions = [header.strip() for header in header_spans if header.strip()]
    
    years = []
    # Match various header formats: "Value in 2024", "Quantity in 2024", "Growth in 2024", etc.
    year_links = selector.xpath('//th//a/text()').getall()
    for link_text in year_links:
        match = re.search(r'(\d{4}(?:-(?:Q\d|M\d{1,2}))?)', link_text)
        if match:
            years.append(match.group(1))
    
    years = sorted(list(set(years)))
    
    # If trade_descriptions contain year patterns (e.g. '2006', '2024-Q1'), they are actually years
    # This happens when indicator changes (Quantities, Growth, etc.) and headers shift format
    if trade_descriptions and not years:
        year_like = [td for td in trade_descriptions if re.match(r'^\d{4}(-(?:Q\d|M\d{1,2}))?$', td)]
        if len(year_like) == len(trade_descriptions):
            years = sorted(year_like)
            trade_descriptions = []
    
    products = []
    data_rows = selector.xpath('//tr[@align="right"]')
    
    logger.info(f"parse_trademap_table_flexible: Found {len(data_rows)} data rows, {len(years)} years, {len(trade_descriptions)} trade_descriptions")
    
    for row in data_rows:
        product = parse_product_row_flexible(row, years, has_hs8_column, trade_descriptions)
        if product:
            products.append(product)
    
    if len(data_rows) == 0:
        logger.warning("parse_trademap_table_flexible: No data rows found in table - table may be empty or have different format")
    
    if has_hs8_column:
        fmt = "multi_product"
    elif trade_descriptions:
        fmt = "single_product"
    else:
        fmt = "country_timeseries"
    
    return {
        "format": fmt,
        "trade_descriptions": trade_descriptions,
        "years": years,
        "products": products
    }

def parse_product_row_flexible(row, years, has_hs8_column, trade_descriptions):
    try:
        if has_hs8_column:
            product_code_cell = row.xpath('./td[2]')
            product_label_cell = row.xpath('./td[3]')
            data_start_index = 2
        else:
            product_code_cell = row.xpath('./td[1]')
            product_label_cell = row.xpath('./td[2]')
            data_start_index = 1
        
        product_code = extract_product_code(product_code_cell)
        
        product_label = extract_product_label(product_label_cell)
        
        all_cells = row.xpath('./td')
        data_values = []
        
        for i in range(data_start_index + 1, len(all_cells)):
            cell = all_cells[i]
            
            if cell.xpath('.//input[@type="image"]'):
                continue
            
            cell_text = cell.xpath('./text()').get()
            if cell_text:
                try:
                    cell_text = cell_text.strip()
                    value = int(cell_text.replace(',', ''))
                    data_values.append(value)
                except ValueError:
                    data_values.append(0)
            else:
                data_values.append(0)
        
        num_years = len(years)
        num_trades = len(trade_descriptions)
        
        trades_data = []
        if num_trades > 0:
            for trade_idx in range(num_trades):
                start_idx = trade_idx * num_years
                end_idx = start_idx + num_years
                trade_values = data_values[start_idx:end_idx]
                
                # Create year-value mapping
                trade_data = {}
                for year_idx, year in enumerate(years):
                    if year_idx < len(trade_values):
                        trade_data[year] = trade_values[year_idx]
                    else:
                        trade_data[year] = 0
                
                trades_data.append({
                    "description": trade_descriptions[trade_idx] if trade_idx < len(trade_descriptions) else f"Trade {trade_idx + 1}",
                    "data": trade_data
                })
        elif num_years > 0 and data_values:
            # No trade descriptions (Country_SelProduct_TS format) - map values directly to years
            trade_data = {}
            for year_idx, year in enumerate(years):
                if year_idx < len(data_values):
                    trade_data[year] = data_values[year_idx]
                else:
                    trade_data[year] = 0
            trades_data.append({
                "description": "Value",
                "data": trade_data
            })
        
        return {
            "product_code": product_code,
            "product_label": product_label,
            "trades": trades_data
        }
    
    except Exception as e:
        print(f"Error parsing product row: {e}")
        return None

def extract_product_code(product_code_cell):
    if not product_code_cell:
        return None
    
    span_code = product_code_cell.xpath('.//span/text()').get()
    if span_code:
        return span_code.strip()
    
    link_code = product_code_cell.xpath('.//a/text()').get()
    if link_code:
        return link_code.strip()
    
    # Try direct text
    direct_text = product_code_cell.xpath('./text()').get()
    if direct_text:
        return direct_text.strip()
    
    return None

def extract_product_label(product_label_cell):
    if not product_label_cell:
        return None
    
    label_texts = product_label_cell.xpath('.//text()').getall()
    if label_texts:
        return ' '.join([t.strip() for t in label_texts if t.strip()])
    
    return None
