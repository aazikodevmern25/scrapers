#!/usr/bin/env python3
"""
Trade Agreements Task Creator - MongoDB Version
"""
import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
data_extractor_dir = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
if data_extractor_dir not in sys.path:
    sys.path.insert(0, data_extractor_dir)

from shared.task_creator_utils.base_task_creator import BaseTaskCreator
from celery_app.tasks import scrape_trade_agreements


def payload_extractor(payload):
    """Extract kwargs from payload for Trade Agreements"""
    return {
        'country': payload.get('country')
    }


if __name__ == "__main__":
    creator = BaseTaskCreator(
        scraper_id='tradeagreements',
        scraper_name='TradeAgreements',
        queue_name='trade_agreements',
        celery_task_func=scrape_trade_agreements,
        payload_extractor=payload_extractor
    )
    creator.run()
