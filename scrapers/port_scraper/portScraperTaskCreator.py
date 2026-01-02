#!/usr/bin/env python3
"""
Port Scraper Task Creator - MongoDB Version
"""
import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
data_extractor_dir = os.path.dirname(os.path.dirname(script_dir))
if data_extractor_dir not in sys.path:
    sys.path.insert(0, data_extractor_dir)

from shared.task_creator_utils.base_task_creator import BaseTaskCreator
from celery_app.tasks import port_scraper_start_fresh_task


def payload_extractor(payload):
    """Extract kwargs from payload for Port Scraper"""
    return {
        'headless': payload.get('headless', True),
        'countries_limit': payload.get('countries_limit')
    }


if __name__ == "__main__":
    creator = BaseTaskCreator(
        scraper_id='portscraper',
        scraper_name='PortScraper',
        queue_name='port_scraper',
        celery_task_func=port_scraper_start_fresh_task,
        payload_extractor=payload_extractor
    )
    creator.run()
