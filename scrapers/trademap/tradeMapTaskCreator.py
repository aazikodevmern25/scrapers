#!/usr/bin/env python3
"""
Trade Map Task Creator - MongoDB Version
"""
import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
data_extractor_dir = os.path.dirname(os.path.dirname(script_dir))
if data_extractor_dir not in sys.path:
    sys.path.insert(0, data_extractor_dir)

from shared.task_creator_utils.base_task_creator import BaseTaskCreator
from celery_app.tasks import trademap_scraper_task


def payload_extractor(payload):
    """Extract kwargs from payload for Trade Map"""
    return {
        'hscode': payload.get('hscode'),
        'country1': payload.get('country1'),
        'country2': payload.get('country2')
    }


if __name__ == "__main__":
    creator = BaseTaskCreator(
        scraper_id='trademap',
        scraper_name='TradeMap',
        queue_name='trademap',
        celery_task_func=trademap_scraper_task,
        payload_extractor=payload_extractor
    )
    creator.run()
