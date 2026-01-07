from celery import Celery
from celery.utils.log import get_task_logger
import os
from tools.task_status_checker import check_task_should_pause, TaskPausedException
from scrapers.macmap import (
    ScrapeMacmapTariff,
    ScrapeMacmapTradeRemedies,
    ScrapeMacmapRegulatoryRequirements,
    ScrapeMacmapCompareMarket,
    ScrapeMacmapCompetitors,
    ScrapeMacmapProducts,
    ScrapeTarrifFull,
    ScrapeMacmapTradeAgreements
)
from scrapers.indiantradeportal import IndianTradePortalScrape
from scrapers.trademap.trademap import ScrapeTrademap
from scrapers.eximpedia import ParseDates, ScrapeEximpedia, ScrapeEximpediaBatch
from scrapers.port_scraper import (
    ScrapePortsStartFresh,
    ScrapePortsResumeFrom,
    ScrapePortsUpdateExisting,
    GetPortStatistics
)
from scrapers.indiamart import (
    IndiamartProductScraper,
    IndiamartProductScraperV2,
    ScrapeIndiamartProducts
)
from scrapers.indiamart.indiamart_category_crawler import (
    CrawlIndiamartCategories
)

app = Celery('macmap_scraper')

app.conf.update(
    broker_url=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
    result_backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0'),
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_routes={
        # Scraper-specific queues for dedicated worker assignment
        'celery_app.tasks.scrape_macmap_tariff': {'queue': 'macmap_tariff'},
        'celery_app.tasks.scrape_macmap_trade_remedies': {'queue': 'macmap_trade_remedies'},
        'celery_app.tasks.scrape_macmap_regulatory_requirements': {'queue': 'macmap_regulatory'},
        'celery_app.tasks.scrape_macmap_compare_market': {'queue': 'macmap_compare'},
        'celery_app.tasks.scrape_macmap_competitors': {'queue': 'macmap_competitors'},
        'celery_app.tasks.scrape_macmap_products': {'queue': 'macmap_products'},
        'celery_app.tasks.scrape_tariff_full': {'queue': 'tariff_full'},
        'celery_app.tasks.scrape_trade_agreements': {'queue': 'trade_agreements'},
        'celery_app.tasks.scrape_indian_trade_portal': {'queue': 'indian_trade_portal'},
        'celery_app.tasks.trademap_scraper_task': {'queue': 'trademap'},
        'celery_app.tasks.eximpedia_scraper_task': {'queue': 'eximpedia'},
        'celery_app.tasks.eximpedia_batch_scraper_task': {'queue': 'eximpedia'},
        'celery_app.tasks.port_scraper_start_fresh_task': {'queue': 'port_scraper'},
        'celery_app.tasks.port_scraper_resume_task': {'queue': 'port_scraper'},
        'celery_app.tasks.port_scraper_update_existing_task': {'queue': 'port_scraper'},
        'celery_app.tasks.port_scraper_get_statistics_task': {'queue': 'port_scraper'},
        'celery_app.tasks.indiamart_product_scraper_task': {'queue': 'indiamart_products'},
        'celery_app.tasks.indiamart_product_scraper_legacy_task': {'queue': 'indiamart_products'},
        'celery_app.tasks.indiamart_category_crawler_task': {'queue': 'indiamart_categories'},
        # Batch and comprehensive tasks
        'celery_app.tasks.batch_scrape_tariffs': {'queue': 'batch_operations'},
        'celery_app.tasks.comprehensive_country_analysis': {'queue': 'batch_operations'},
        # Default fallback
        'celery_app.tasks.*': {'queue': 'default'},
    },
    worker_prefetch_multiplier=1,  
    task_acks_late=True,
    worker_max_tasks_per_child=50,  # Increased from 1000 to 50 as requested
)


logger = get_task_logger(__name__)

@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 1, 'countdown': 30})
def scrape_macmap_tariff(self, country1, country2, year, hsc):
    try:
        # Check if task should be paused before execution
        if check_task_should_pause(self.request.id):
            logger.info(f"Task {self.request.id} is paused, skipping execution")
            raise TaskPausedException(f"Task {self.request.id} is paused")
        
        logger.info(f"Starting tariff scrape: {country1} -> {country2}, year: {year}, HS: {hsc}")
        ScrapeMacmapTariff(country1, country2, year, hsc)
        logger.info(f"Completed tariff scrape: {country1} -> {country2}, year: {year}, HS: {hsc}")
        return {"status": "success", "country1": country1, "country2": country2, "year": year, "hsc": hsc}
    except TaskPausedException:
        # Don't retry paused tasks
        logger.info(f"Task {self.request.id} is paused, not retrying")
        return {"status": "paused", "message": "Task execution paused"}
    except Exception as exc:
        logger.error(f"Error scraping tariff: {str(exc)}")
        raise self.retry(exc=exc)

@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 1, 'countdown': 30})
def scrape_macmap_trade_remedies(self, country1, country2, year, hsc):
    try:
        # Check if task should be paused before execution
        if check_task_should_pause(self.request.id):
            logger.info(f"Task {self.request.id} is paused, skipping execution")
            raise TaskPausedException(f"Task {self.request.id} is paused")
        
        logger.info(f"Starting trade remedies scrape: {country1} -> {country2}, year: {year}, HS: {hsc}")
        ScrapeMacmapTradeRemedies(country1, country2, year, hsc)
        logger.info(f"Completed trade remedies scrape: {country1} -> {country2}")
        return {"status": "success", "country1": country1, "country2": country2, "year": year, "hsc": hsc}
    except TaskPausedException:
        # Don't retry paused tasks
        logger.info(f"Task {self.request.id} is paused, not retrying")
        return {"status": "paused", "message": "Task execution paused"}
    except Exception as exc:
        logger.error(f"Error scraping trade remedies: {str(exc)}")
        raise self.retry(exc=exc)

@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 1, 'countdown': 30})
def scrape_macmap_regulatory_requirements(self, country1, country2, hsc, regtype):
    try:
        # Check if task should be paused before execution
        if check_task_should_pause(self.request.id):
            logger.info(f"Task {self.request.id} is paused, skipping execution")
            raise TaskPausedException(f"Task {self.request.id} is paused")
        
        logger.info(f"Starting regulatory requirements scrape: {country1} -> {country2}, HS: {hsc}, regtype: {regtype}")
        ScrapeMacmapRegulatoryRequirements(country1, country2, hsc, regtype)
        logger.info(f"Completed regulatory requirements scrape: {country1} -> {country2}")
        return {"status": "success", "country1": country1, "country2": country2, "hsc": hsc, "regtype": regtype}
    except TaskPausedException:
        # Don't retry paused tasks
        logger.info(f"Task {self.request.id} is paused, not retrying")
        return {"status": "paused", "message": "Task execution paused"}
    except Exception as exc:
        logger.error(f"Error scraping regulatory requirements: {str(exc)}")
        raise self.retry(exc=exc)

@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 1, 'countdown': 30})
def scrape_macmap_compare_market(self, country, hsc):
    try:
        # Check if task should be paused before execution
        if check_task_should_pause(self.request.id):
            logger.info(f"Task {self.request.id} is paused, skipping execution")
            raise TaskPausedException(f"Task {self.request.id} is paused")
        
        logger.info(f"Starting compare market scrape: {country}, HS: {hsc}")
        ScrapeMacmapCompareMarket(country, hsc)
        logger.info(f"Completed compare market scrape: {country}")
        return {"status": "success", "country": country, "hsc": hsc}
    except TaskPausedException:
        # Don't retry paused tasks
        logger.info(f"Task {self.request.id} is paused, not retrying")
        return {"status": "paused", "message": "Task execution paused"}
    except Exception as exc:
        logger.error(f"Error scraping compare market: {str(exc)}")
        raise self.retry(exc=exc)

@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 1, 'countdown': 30})
def scrape_macmap_competitors(self, country, hsc):
    try:
        # Check if task should be paused before execution
        if check_task_should_pause(self.request.id):
            logger.info(f"Task {self.request.id} is paused, skipping execution")
            raise TaskPausedException(f"Task {self.request.id} is paused")
        
        logger.info(f"Starting competitors scrape: {country}, HS: {hsc}")
        ScrapeMacmapCompetitors(country, hsc)
        logger.info(f"Completed competitors scrape: {country}")
        return {"status": "success", "country": country, "hsc": hsc}
    except TaskPausedException:
        # Don't retry paused tasks
        logger.info(f"Task {self.request.id} is paused, not retrying")
        return {"status": "paused", "message": "Task execution paused"}
    except Exception as exc:
        logger.error(f"Error scraping competitors: {str(exc)}")
        raise self.retry(exc=exc)

@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 1, 'countdown': 30})
def scrape_macmap_products(self, country1, country2, hsc_lvl):
    try:
        # Check if task should be paused before execution
        if check_task_should_pause(self.request.id):
            logger.info(f"Task {self.request.id} is paused, skipping execution")
            raise TaskPausedException(f"Task {self.request.id} is paused")
        
        logger.info(f"Starting products scrape: {country1} -> {country2}, HS level: {hsc_lvl}")
        ScrapeMacmapProducts(country1, country2, hsc_lvl)
        logger.info(f"Completed products scrape: {country1} -> {country2}")
        return {"status": "success", "country1": country1, "country2": country2, "hsc_lvl": hsc_lvl}
    except TaskPausedException:
        # Don't retry paused tasks
        logger.info(f"Task {self.request.id} is paused, not retrying")
        return {"status": "paused", "message": "Task execution paused"}
    except Exception as exc:
        logger.error(f"Error scraping products: {str(exc)}")
        raise self.retry(exc=exc)

@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 2, 'countdown': 300})
def scrape_tariff_full(self, country):
    try:
        # Check if task should be paused before execution
        if check_task_should_pause(self.request.id):
            logger.info(f"Task {self.request.id} is paused, skipping execution")
            raise TaskPausedException(f"Task {self.request.id} is paused")
        
        logger.info(f"Starting full tariff scrape for country: {country}")
        ScrapeTarrifFull(country)
        logger.info(f"Completed full tariff scrape for country: {country}")
        return {"status": "success", "country": country}
    except TaskPausedException:
        # Don't retry paused tasks
        logger.info(f"Task {self.request.id} is paused, not retrying")
        return {"status": "paused", "message": "Task execution paused"}
    except Exception as exc:
        logger.error(f"Error scraping full tariff: {str(exc)}")
        raise self.retry(exc=exc)

@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 2, 'countdown': 300})
def scrape_trade_agreements(self, country):
    try:
        # Check if task should be paused before execution
        if check_task_should_pause(self.request.id):
            logger.info(f"Task {self.request.id} is paused, skipping execution")
            raise TaskPausedException(f"Task {self.request.id} is paused")
        
        logger.info(f"Starting Trade Agreements scrape for country: {country}")
        ScrapeMacmapTradeAgreements(country)
        logger.info(f"Completed Trade Agreements scrape for country: {country}")
        return {"status": "success", "country": country}
    except TaskPausedException:
        # Don't retry paused tasks
        logger.info(f"Task {self.request.id} is paused, not retrying")
        return {"status": "paused", "message": "Task execution paused"}
    except Exception as exc:
        logger.error(f"Error scraping trade agreements: {str(exc)}")
        raise self.retry(exc=exc)

# Group task for batch processing
@app.task(bind=True)
def batch_scrape_tariffs(self, country_pairs, year, hsc_codes):
    try:
        task_ids = []
        for country1, country2 in country_pairs:
            for hsc in hsc_codes:
                task = scrape_macmap_tariff.delay(country1, country2, year, hsc)
                task_ids.append(task.id)
                logger.info(f"Queued tariff task: {task.id} for {country1}->{country2}, HS: {hsc}")
        
        return {"status": "batch_queued", "task_count": len(task_ids), "task_ids": task_ids}
    except Exception as exc:
        logger.error(f"Error in batch processing: {str(exc)}")
        raise

# Workflow task that chains multiple scraping operations
@app.task(bind=True)
def comprehensive_country_analysis(self, country1, country2, year, hsc_codes):
    try:
        results = []
        for hsc in hsc_codes:
            # Chain multiple related tasks
            tariff_task = scrape_macmap_tariff.delay(country1, country2, year, hsc)
            trade_remedies_task = scrape_macmap_trade_remedies.delay(country1, country2, year, hsc)
            regulatory_import_task = scrape_macmap_regulatory_requirements.delay(country1, country2, hsc, 'i')
            regulatory_export_task = scrape_macmap_regulatory_requirements.delay(country1, country2, hsc, 'e')
            
            results.extend([
                tariff_task.id,
                trade_remedies_task.id,
                regulatory_import_task.id,
                regulatory_export_task.id
            ])
        
        # Also scrape market comparison data
        market_task1 = scrape_macmap_compare_market.delay(country1, hsc_codes[0])
        market_task2 = scrape_macmap_compare_market.delay(country2, hsc_codes[0])
        competitors_task1 = scrape_macmap_competitors.delay(country1, hsc_codes[0])
        competitors_task2 = scrape_macmap_competitors.delay(country2, hsc_codes[0])
        
        results.extend([market_task1.id, market_task2.id, competitors_task1.id, competitors_task2.id])
        
        return {"status": "comprehensive_analysis_queued", "task_count": len(results), "task_ids": results}
    except Exception as exc:
        logger.error(f"Error in comprehensive analysis: {str(exc)}")
        raise

@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 1, 'countdown': 30})
def scrape_indian_trade_portal(self, hscode):
    try:
        # Check if task should be paused before execution
        if check_task_should_pause(self.request.id):
            logger.info(f"Task {self.request.id} is paused, skipping execution")
            raise TaskPausedException(f"Task {self.request.id} is paused")
        
        logger.info(f"Starting Indian Trade Portal scrape: HS Code: {hscode}")
        IndianTradePortalScrape(hscode)
        logger.info(f"Completed Indian Trade Portal scrape for HS Code: {hscode}")
        return {"status": "success", "hscode": hscode}
    except TaskPausedException:
        # Don't retry paused tasks
        logger.info(f"Task {self.request.id} is paused, not retrying")
        return {"status": "paused", "message": "Task execution paused"}
    except Exception as exc:
        logger.error(f"Error scraping Indian Trade Portal: {str(exc)}")
        raise self.retry(exc=exc)

@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 2, 'countdown': 300})
def trademap_scraper_task(self, hscode, country1, country2):
    try:
        # Check if task should be paused before execution
        if check_task_should_pause(self.request.id):
            logger.info(f"Task {self.request.id} is paused, skipping execution")
            raise TaskPausedException(f"Task {self.request.id} is paused")
        
        logger.info(f"Starting TradeMap scrape: {hscode}, {country1} -> {country2}")
        ScrapeTrademap(hscode, country1, country2)
        logger.info(f"Completed TradeMap scrape: {hscode}")
        return {"status": "success", "hscode": hscode, "country1": country1, "country2": country2}
    except TaskPausedException:
        # Don't retry paused tasks
        logger.info(f"Task {self.request.id} is paused, not retrying")
        return {"status": "paused", "message": "Task execution paused"}
    except Exception as exc:
        logger.error(f"Error scraping TradeMap: {str(exc)}")
        raise self.retry(exc=exc)

@app.task(name='celery_app.tasks.eximpedia_scraper_task', bind=True)
def eximpedia_scraper_task(self, start_date: str, end_date: str, hscode: str, country: str, mode: str):
    """
    Celery task wrapper for Eximpedia scraping
    """
    logger.info(f"Starting Eximpedia scrape: {hscode}, {country}, {mode}, {start_date} to {end_date}")
    
    try:
        sd, ed = ParseDates(start_date, end_date)
        result = ScrapeEximpedia(sd, ed, hscode, country, mode)
        logger.info(f"Completed Eximpedia scrape: {result}")
        return {
            "status": "success" if result == "Success" else "failed",
            "result": result,
            "hscode": hscode,
            "country": country,
            "mode": mode,
            "date_range": f"{start_date} to {end_date}"
        }
    except TaskPausedException:
        # Don't retry paused tasks
        logger.info(f"Task {self.request.id} is paused, not retrying")
        return {"status": "paused", "message": "Task execution paused"}
    except Exception as exc:
        logger.error(f"Error scraping Eximpedia: {str(exc)}")
        raise self.retry(exc=exc)

@app.task(bind=True)
def eximpedia_batch_scraper_task(self, batch_data):
    try:
        logger.info(f"Starting Eximpedia batch scrape with {len(batch_data)} items")
        result = ScrapeEximpediaBatch(batch_data)
        logger.info(f"Completed Eximpedia batch scrape: {result}")
        return {
            "status": "success" if result == "Success" else "failed",
            "result": result,
            "batch_size": len(batch_data)
        }
    except Exception as exc:
        logger.error(f"Error scraping Eximpedia batch: {str(exc)}")
        raise self.retry(exc=exc)

@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 1, 'countdown': 60})
def port_scraper_start_fresh_task(self, headless=True, countries_limit=None):
    """
    Start fresh port scraping - scrape all countries from the beginning.
    Skip countries that already exist in the database.
    """
    try:
        # Check if task should be paused before execution
        if check_task_should_pause(self.request.id):
            logger.info(f"Task {self.request.id} is paused, skipping execution")
            raise TaskPausedException(f"Task {self.request.id} is paused")
        
        task_id = self.request.id
        logger.info(f"Starting fresh port scraping (task_id={task_id}, headless={headless}, limit={countries_limit})")
        stats = ScrapePortsStartFresh(headless=headless, countries_limit=countries_limit, task_id=task_id)
        logger.info(f"Completed fresh port scraping: {stats}")
        return {
            "status": "success" if "error" not in stats else "failed",
            "stats": stats
        }
    except TaskPausedException:
        # Don't retry paused tasks
        logger.info(f"Task {self.request.id} is paused, not retrying")
        return {"status": "paused", "message": "Task execution paused"}
    except Exception as exc:
        logger.error(f"Error in fresh port scraping: {str(exc)}")
        raise self.retry(exc=exc)

@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 1, 'countdown': 60})
def port_scraper_resume_task(self, start_country, headless=True, countries_limit=None):
    """
    Resume port scraping from a specific country.
    """
    try:
        # Check if task should be paused before execution
        if check_task_should_pause(self.request.id):
            logger.info(f"Task {self.request.id} is paused, skipping execution")
            raise TaskPausedException(f"Task {self.request.id} is paused")
        
        task_id = self.request.id
        logger.info(f"Resuming port scraping from {start_country} (task_id={task_id}, headless={headless}, limit={countries_limit})")
        stats = ScrapePortsResumeFrom(start_country, headless=headless, countries_limit=countries_limit, task_id=task_id)
        logger.info(f"Completed resume port scraping: {stats}")
        return {
            "status": "success" if "error" not in stats else "failed",
            "stats": stats,
            "start_country": start_country
        }
    except TaskPausedException:
        # Don't retry paused tasks
        logger.info(f"Task {self.request.id} is paused, not retrying")
        return {"status": "paused", "message": "Task execution paused"}
    except Exception as exc:
        logger.error(f"Error in resume port scraping: {str(exc)}")
        raise self.retry(exc=exc)

@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 1, 'countdown': 60})
def port_scraper_update_existing_task(self, start_country=None, headless=True, countries_limit=None):
    """
    Update existing ports - re-scrape countries that already exist.
    """
    try:
        # Check if task should be paused before execution
        if check_task_should_pause(self.request.id):
            logger.info(f"Task {self.request.id} is paused, skipping execution")
            raise TaskPausedException(f"Task {self.request.id} is paused")
        
        task_id = self.request.id
        logger.info(f"Updating existing ports from {start_country or 'beginning'} (task_id={task_id}, headless={headless}, limit={countries_limit})")
        stats = ScrapePortsUpdateExisting(start_country=start_country, headless=headless, countries_limit=countries_limit, task_id=task_id)
        logger.info(f"Completed update existing ports: {stats}")
        return {
            "status": "success" if "error" not in stats else "failed",
            "stats": stats
        }
    except TaskPausedException:
        # Don't retry paused tasks
        logger.info(f"Task {self.request.id} is paused, not retrying")
        return {"status": "paused", "message": "Task execution paused"}
    except Exception as exc:
        logger.error(f"Error in update existing ports: {str(exc)}")
        raise self.retry(exc=exc)

@app.task(bind=True)
def port_scraper_get_statistics_task(self):
    """
    Get current port scraping statistics.
    """
    try:
        logger.info("Getting port scraping statistics")
        stats = GetPortStatistics()
        logger.info(f"Retrieved port statistics: {stats}")
        return {
            "status": "success" if stats else "failed",
            "stats": stats
        }
    except Exception as exc:
        logger.error(f"Error getting port statistics: {str(exc)}")
        raise

@app.task(bind=True, queue='indiamart_products', autoretry_for=(Exception,), retry_kwargs={'max_retries': 1, 'countdown': 60})
def indiamart_product_scraper_task(self, max_workers=10, batch_size=100):
    """
    Scrape products from Indiamart using V2 scraper (default).
    Reads URLs from MongoDB and saves scraped data back.
    
    Args:
        max_workers: Number of concurrent workers (default: 10)
        batch_size: Number of URLs per batch (default: 100)
    """
    try:
        # Check if task should be paused before execution
        if check_task_should_pause(self.request.id):
            logger.info(f"Task {self.request.id} is paused, skipping execution")
            raise TaskPausedException(f"Task {self.request.id} is paused")
        
        task_id = self.request.id
        logger.info(f"Starting Indiamart product scraper V2 (task_id={task_id}, max_workers={max_workers}, batch_size={batch_size})")
        
        # Use the V2 scraper (new default)
        from scrapers.indiamart.indiamart_product_scraper import IndiamartProductScraperV2, ProductScraperConfig
        
        config = ProductScraperConfig()
        config.max_workers = max_workers
        config.batch_size = batch_size
        
        scraper = IndiamartProductScraperV2(task_id=task_id, config=config)
        scraper.celery_task = self  # Set celery task reference for revocation checking
        result = scraper.run()
        
        logger.info(f"Completed Indiamart product scraping V2: {result}")
        return {
            "status": result.get('status', 'success'),
            "message": "Indiamart product scraping completed",
            "stats": result.get('stats', {})
        }
    except TaskPausedException:
        # Don't retry paused tasks
        logger.info(f"Task {self.request.id} is paused, not retrying")
        return {"status": "paused", "message": "Task execution paused"}
    except Exception as exc:
        logger.error(f"Error in Indiamart product scraping: {str(exc)}")
        raise self.retry(exc=exc)


@app.task(bind=True, queue='indiamart_products', autoretry_for=(Exception,), retry_kwargs={'max_retries': 1, 'countdown': 60})
def indiamart_product_scraper_legacy_task(self, max_workers=20):
    """
    LEGACY: Old Indiamart product scraper (kept for backward compatibility).
    Use indiamart_product_scraper_task instead (V2 is now default).
    """
    try:
        # Check if task should be paused before execution
        if check_task_should_pause(self.request.id):
            logger.info(f"Task {self.request.id} is paused, skipping execution")
            raise TaskPausedException(f"Task {self.request.id} is paused")
        
        task_id = self.request.id
        logger.info(f"Starting Indiamart product scraper LEGACY (task_id={task_id}, max_workers={max_workers})")
        
        # Initialize the old scraper
        from scrapers.indiamart.indiamart_mongodb import IndiamartMongoDB
        from scrapers.indiamart.indiamart_scraper import IndiamartProductScraper, ScrapingConfig
        
        db_manager = IndiamartMongoDB()
        config = ScrapingConfig()
        config.max_workers = max_workers
        
        scraper = IndiamartProductScraper(db_manager=db_manager, config=config)
        scraper.run()
        
        logger.info("Completed Indiamart product scraping (legacy)")
        return {
            "status": "success",
            "message": "Indiamart product scraping completed (legacy)"
        }
    except TaskPausedException:
        # Don't retry paused tasks
        logger.info(f"Task {self.request.id} is paused, not retrying")
        return {"status": "paused", "message": "Task execution paused"}
    except Exception as exc:
        logger.error(f"Error in Indiamart product scraping (legacy): {str(exc)}")
        raise self.retry(exc=exc)


@app.task(bind=True, queue='indiamart_categories')
def indiamart_category_crawler_task(self, auto_start_product_scraping=True, max_workers=150, max_concurrent_requests=300, batch_size=1000):
    """
    Celery task for IndiaMART category crawler with unlimited page crawling
    
    Args:
        auto_start_product_scraping: If True, automatically starts product scraping after category crawling
        max_workers: Number of concurrent workers for category crawling (default: 150)
        max_concurrent_requests: Maximum concurrent HTTP requests (default: 300)
        batch_size: Number of categories to process per batch (default: 1000)
    """
    logger.info(f"Starting IndiaMART category crawler task: {self.request.id}")
    logger.info(f"Configuration: max_workers={max_workers}, max_concurrent_requests={max_concurrent_requests}, batch_size={batch_size}")
    logger.info(f"Auto-start product scraping: {auto_start_product_scraping}")
    
    try:
        # Import here to avoid circular imports
        from scrapers.indiamart.indiamart_category_crawler import IndiamartCategoryCrawler
        from scrapers.indiamart.indiamart_mongodb import IndiamartMongoDB
        
        # Save crawler settings to MongoDB for dashboard display
        db = IndiamartMongoDB()
        db.save_crawler_settings(max_workers, max_concurrent_requests, batch_size)
        
        # Create crawler with custom configuration
        crawler = IndiamartCategoryCrawler(task_id=self.request.id)
        
        # Update configuration with provided parameters
        crawler.config.max_workers = max_workers
        crawler.config.max_concurrent_requests = max_concurrent_requests
        crawler.config.batch_size = batch_size
        
        # Set celery task reference for revocation checking
        crawler.celery_task = self
        
        # Run the crawler
        crawler.run()
        
        logger.info(f"IndiaMART category crawler task completed: {self.request.id}")
        
        # Automatically start product scraping if enabled
        if auto_start_product_scraping:
            logger.info("Category crawling completed - Auto-starting product URL scraping (V2)...")
            try:
                # Queue product scraping task with V2 scraper (new default)
                product_task = indiamart_product_scraper_task.apply_async(
                    kwargs={
                        'max_workers': 10,  # Optimized for V2 scraper
                        'batch_size': 100   # V2 batch size
                    },
                    queue='indiamart_products',
                    countdown=5  # Start after 5 seconds
                )
                logger.info(f"✓ Product scraping task (V2) queued: {product_task.id}")
                return {
                    "status": "success",
                    "category_task_id": self.request.id,
                    "product_task_id": product_task.id,
                    "message": "Category crawling completed and product scraping (V2) started automatically"
                }
            except Exception as e:
                logger.error(f"Failed to auto-start product scraping: {e}")
                return {
                    "status": "partial_success",
                    "category_task_id": self.request.id,
                    "message": f"Category crawling completed but failed to start product scraping: {e}"
                }
        
        return {
            "status": "success",
            "category_task_id": self.request.id,
            "message": "Category crawling completed"
        }
        
    except Exception as e:
        logger.error(f"IndiaMART category crawler task failed: {e}")
        raise


if __name__ == '__main__':
    app.start()