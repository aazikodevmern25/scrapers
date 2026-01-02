#!/usr/bin/env python3
"""
MacMap Regulatory Payload Creator - MongoDB Version
"""
import sys
import os
import json

script_dir = os.path.dirname(os.path.abspath(__file__))
data_extractor_dir = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
if data_extractor_dir not in sys.path:
    sys.path.insert(0, data_extractor_dir)

from shared.task_creator_utils.base_payload_creator import BasePayloadCreator

ENDPOINT = "http://0.0.0.0:1080/api/v1/scrape/macmap-regulatory"

FIELD_PROMPTS = {
    'country1': 'Reporter Country',
    'country2': 'Partner Country',
    'hsc': 'HS Codes',
    'regtype': 'Regulation Type'
}

if __name__ == "__main__":
    creator = BasePayloadCreator(
        scraper_id='macmapregulatory',
        scraper_name='MacMapRegulatory',
        unique_fields=['country1', 'country2', 'hsc', 'regtype'],
        endpoint=ENDPOINT
    )
    
    # Check if running programmatically (via API) with environment variables
    if os.environ.get('PROGRAMMATIC_MODE') == 'true':
        # Get config from environment variable
        config_json = os.environ.get('PAYLOAD_CONFIG', '{}')
        config = json.loads(config_json)
        
        # Extract and prepare parameters - handle both string and list inputs
        def parse_field(value):
            if isinstance(value, list):
                return value
            elif isinstance(value, str):
                return [v.strip() for v in value.split(',') if v.strip()]
            else:
                return []
        
        country1_list = parse_field(config.get('country1', ''))
        country2_list = parse_field(config.get('country2', ''))
        hsc_list = parse_field(config.get('hsc', ''))
        regtype_list = parse_field(config.get('regtype', ''))
        
        # Debug logging
        print(f"DEBUG: country1_list = {country1_list}")
        print(f"DEBUG: country2_list = {country2_list}")
        print(f"DEBUG: hsc_list = {hsc_list}")
        print(f"DEBUG: regtype_list = {regtype_list}")
        print(f"DEBUG: Total combinations = {len(country1_list)} × {len(country2_list)} × {len(hsc_list)} × {len(regtype_list)} = {len(country1_list) * len(country2_list) * len(hsc_list) * len(regtype_list)}")
        
        # Create payloads programmatically
        creator.create_payloads_from_params(
            country1=country1_list,
            country2=country2_list,
            hsc=hsc_list,
            regtype=regtype_list
        )
    else:
        # Run in interactive mode
        creator.run_interactive(FIELD_PROMPTS)
