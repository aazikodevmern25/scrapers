#!/usr/bin/env python3
"""
MacMap Tariff Payload Creator - MongoDB Version
"""
import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
data_extractor_dir = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
if data_extractor_dir not in sys.path:
    sys.path.insert(0, data_extractor_dir)

from shared.task_creator_utils.base_payload_creator import BasePayloadCreator

ENDPOINT = "http://0.0.0.0:1080/api/v1/scrape/macmap-tariff"

FIELD_PROMPTS = {
    'country1': 'Reporter Country',
    'country2': 'Partner Country',
    'year': 'Year',
    'hsc': 'HS Codes'
}

if __name__ == "__main__":
    creator = BasePayloadCreator(
        scraper_id='macmap_tariff',
        scraper_name='MacMapTariff',
        unique_fields=['country1', 'country2', 'year', 'hsc'],
        endpoint=ENDPOINT
    )
    
    # Check if running in programmatic mode
    if os.environ.get('PROGRAMMATIC_MODE') == 'true' or os.environ.get('PAYLOAD_MODE') == 'programmatic':
        import json
        import itertools
        config = json.loads(os.environ.get('PAYLOAD_CONFIG', '{}'))
        
        # Normalize field names - handle separate country1/country2 from form
        if 'country1' in config:
            if isinstance(config['country1'], str):
                config['country1'] = [c.strip() for c in config['country1'].split(',')]
        if 'country2' in config:
            if isinstance(config['country2'], str):
                config['country2'] = [c.strip() for c in config['country2'].split(',')]
        
        # Fallback: if only 'countries' is provided (legacy), use same list for both
        if 'countries' in config and 'country1' not in config:
            countries = config['countries']
            if isinstance(countries, str):
                countries_list = [c.strip() for c in countries.split(',')]
            else:
                countries_list = countries
            config['country1'] = countries_list
            config['country2'] = countries_list
            del config['countries']
        
        if 'hscodes' in config:
            hsc_val = config['hscodes']
            if isinstance(hsc_val, str):
                config['hsc'] = [c.strip() for c in hsc_val.split(',')]
            else:
                config['hsc'] = hsc_val
            del config['hscodes']
        
        # Ensure year is a list
        if 'year' in config and not isinstance(config['year'], list):
            config['year'] = [config['year']]
        
        # Create cartesian product payloads
        field_values = {field: config.get(field, []) for field in ['country1', 'country2', 'year', 'hsc']}
        combinations = list(itertools.product(*[field_values[f] for f in ['country1', 'country2', 'year', 'hsc']]))
        
        payloads = []
        for combo in combinations:
            payload = {
                'country1': combo[0],
                'country2': combo[1],
                'year': combo[2],
                'hsc': combo[3]
            }
            payloads.append(payload)
        
        # Use create_payloads_programmatic method
        creator.create_payloads_programmatic(payloads)
    else:
        creator.run_interactive(FIELD_PROMPTS)
