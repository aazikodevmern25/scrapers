#!/usr/bin/env python3
"""
Indian Trade Portal Task Creator - MongoDB Version
"""
import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
data_extractor_dir = os.path.dirname(os.path.dirname(script_dir))
if data_extractor_dir not in sys.path:
    sys.path.insert(0, data_extractor_dir)

from shared.task_creator_utils.base_task_creator import BaseTaskCreator
from celery_app.tasks import scrape_indian_trade_portal


def payload_extractor(payload):
    """Extract kwargs from payload for Indian Trade Portal"""
    return {'hscode': payload.get('hscode')}


if __name__ == "__main__":
    creator = BaseTaskCreator(
        scraper_id='indiantradeportal',
        scraper_name='IndianTradePortal',
        queue_name='indian_trade_portal',
        celery_task_func=scrape_indian_trade_portal,
        payload_extractor=payload_extractor
    )
    creator.run()
