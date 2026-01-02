#!/usr/bin/env python3
"""
Competitors Payload Creator - MongoDB Version
"""
import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
data_extractor_dir = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
if data_extractor_dir not in sys.path:
    sys.path.insert(0, data_extractor_dir)

from shared.task_creator_utils.base_payload_creator import BasePayloadCreator

ENDPOINT = "http://0.0.0.0:1080/api/v1/scrape/macmap-competitors"

FIELD_PROMPTS = {
    'country': 'Countries',
    'hsc': 'HS Codes'
}

if __name__ == "__main__":
    creator = BasePayloadCreator(
        scraper_id='competitors',
        scraper_name='Competitors',
        unique_fields=['country', 'hsc'],
        endpoint=ENDPOINT
    )
    creator.run_interactive(FIELD_PROMPTS)
