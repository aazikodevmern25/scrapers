#!/usr/bin/env python3
"""
EximPedia Task Creator - MongoDB Version
"""
import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
data_extractor_dir = os.path.dirname(os.path.dirname(script_dir))
if data_extractor_dir not in sys.path:
    sys.path.insert(0, data_extractor_dir)

from shared.task_creator_utils.base_task_creator import BaseTaskCreator
from celery_app.tasks import eximpedia_scraper_task


def payload_extractor(payload):
    """Extract kwargs from payload for EximPedia"""
    return {
        'start_date': payload.get('start_date'),
        'end_date': payload.get('end_date'),
        'hscode': payload.get('hscode'),
        'country': payload.get('country'),
        'mode': payload.get('mode')
    }


if __name__ == "__main__":
    creator = BaseTaskCreator(
        scraper_id='eximpedia',
        scraper_name='EximPedia',
        queue_name='eximpedia',
        celery_task_func=eximpedia_scraper_task,
        payload_extractor=payload_extractor
    )
    creator.run()
