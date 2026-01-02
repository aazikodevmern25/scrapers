#!/usr/bin/env python3
"""
Compare Market Task Creator - MongoDB Version
"""
import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
data_extractor_dir = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
if data_extractor_dir not in sys.path:
    sys.path.insert(0, data_extractor_dir)

from shared.task_creator_utils.base_task_creator import BaseTaskCreator
from celery_app.tasks import scrape_macmap_compare_market


def payload_extractor(payload):
    """Extract kwargs from payload for Compare Market"""
    return {
        'country': payload.get('country'),
        'hsc': payload.get('hsc')
    }


if __name__ == "__main__":
    creator = BaseTaskCreator(
        scraper_id='comparemarket',
        scraper_name='CompareMarket',
        queue_name='macmap_compare',
        celery_task_func=scrape_macmap_compare_market,
        payload_extractor=payload_extractor
    )
    creator.run()
