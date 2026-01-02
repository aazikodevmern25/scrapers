#!/usr/bin/env python3
"""
Competitors Task Creator - MongoDB Version
"""
import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
data_extractor_dir = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
if data_extractor_dir not in sys.path:
    sys.path.insert(0, data_extractor_dir)

from shared.task_creator_utils.base_task_creator import BaseTaskCreator
from celery_app.tasks import scrape_macmap_competitors


def payload_extractor(payload):
    """Extract kwargs from payload for Competitors"""
    return {
        'country': payload.get('country'),
        'hsc': payload.get('hsc')
    }


if __name__ == "__main__":
    creator = BaseTaskCreator(
        scraper_id='competitors',
        scraper_name='Competitors',
        queue_name='macmap_competitors',
        celery_task_func=scrape_macmap_competitors,
        payload_extractor=payload_extractor
    )
    creator.run()
