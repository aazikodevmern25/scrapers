#!/usr/bin/env python3
"""
MacMap Regulatory Task Creator - MongoDB Version
"""
import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
data_extractor_dir = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
if data_extractor_dir not in sys.path:
    sys.path.insert(0, data_extractor_dir)

from shared.task_creator_utils.base_task_creator import BaseTaskCreator
from celery_app.tasks import scrape_macmap_regulatory_requirements


def payload_extractor(payload):
    """Extract kwargs from payload for MacMap Regulatory"""
    return {
        'country1': payload.get('country1'),
        'country2': payload.get('country2'),
        'hsc': payload.get('hsc'),
        'regtype': payload.get('regtype')
    }


if __name__ == "__main__":
    creator = BaseTaskCreator(
        scraper_id='macmapregulatory',
        scraper_name='MacMapRegulatory',
        queue_name='macmap_regulatory',
        celery_task_func=scrape_macmap_regulatory_requirements,
        payload_extractor=payload_extractor
    )
    creator.run()
