#!/usr/bin/env python3
"""
MacMap Tariff Task Creator - MongoDB Version
"""
import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
data_extractor_dir = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
if data_extractor_dir not in sys.path:
    sys.path.insert(0, data_extractor_dir)

from shared.task_creator_utils.base_task_creator import BaseTaskCreator
from celery_app.tasks import scrape_macmap_tariff


def payload_extractor(payload):
    """Extract kwargs from payload for MacMap Tariff"""
    return {
        'country1': payload.get('country1'),
        'country2': payload.get('country2'),
        'year': payload.get('year'),
        'hsc': payload.get('hsc')
    }


if __name__ == "__main__":
    creator = BaseTaskCreator(
        scraper_id='macmaptariff',
        scraper_name='MacMapTariff',
        queue_name='macmap_tariff',
        celery_task_func=scrape_macmap_tariff,
        payload_extractor=payload_extractor
    )
    creator.run()
