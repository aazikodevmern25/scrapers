import glob
import tempfile
import time
import gc
import psutil
import shutil
import os
import uvicorn
from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, WebSocket, WebSocketDisconnect, Body
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request
import asyncio
import json
from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from celery.result import AsyncResult
from celery_app.tasks import (
    app as celery_app,
    scrape_macmap_tariff,
    scrape_macmap_trade_remedies,
    scrape_macmap_regulatory_requirements,
    scrape_macmap_compare_market,
    scrape_macmap_competitors,
    scrape_macmap_products,
    scrape_tariff_full,
    batch_scrape_tariffs,
    comprehensive_country_analysis,
    scrape_indian_trade_portal,
    trademap_scraper_task,
    eximpedia_scraper_task,
    eximpedia_batch_scraper_task,
    port_scraper_start_fresh_task,
    port_scraper_resume_task,
    port_scraper_update_existing_task,
    port_scraper_get_statistics_task,
    indiamart_product_scraper_task,
    indiamart_product_scraper_legacy_task,
    indiamart_category_crawler_task
)
import logging
from datetime import datetime
from services.payload_service import payload_service
# Import state synchronizer for real-time updates
from celery_app.state_synchronizer import state_synchronizer
# Import WebSocket manager and providers
from services.websocket_manager import ws_manager, Channel
from services.websocket_providers import (
    dashboard_provider,
    task_manager_provider,
    logs_provider,
    workers_provider,
    data_sources_provider,
    indiamart_provider,
    system_health_provider
)
# Backup service removed - not needed
try:
    from google_drive_service import google_drive_service
    GOOGLE_DRIVE_AVAILABLE = True
except ImportError:
    google_drive_service = None
    GOOGLE_DRIVE_AVAILABLE = False

# Import task manager
from services.task_manager import task_manager
from tools.celery_status_checker import get_celery_task_details

# Import worker manager
try:
    from services.worker_manager import WorkerManager
    WORKER_MANAGER_AVAILABLE = True
    worker_manager = WorkerManager()
except ImportError:
    WORKER_MANAGER_AVAILABLE = False
    worker_manager = None

# Start task manager monitoring
task_manager.start_monitoring()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")
hscodes_file = 'payloads/hscodes.json'  
with open(hscodes_file, 'r', encoding='utf-8') as f:
    hscodes =  json.load(f)

with open('macmap_countries/countries.json', 'r', encoding='utf-8') as f:
    countries = {item["Name"]: item["Code"] for item in json.load(f)}

with open('payloads/imp_ex_countries.json', 'r', encoding='utf-8') as f:
    imp_data = json.load(f)
    imp_countries = imp_data['data']['countries']

with open('payloads/exp_ex_countries.json', 'r', encoding='utf-8') as f:
    exp_data = json.load(f)
    exp_countries = exp_data['data']['countries']

app = FastAPI(
    title="Macmap Scraper API",
    description="API for managing Macmap trade data scraping tasks",
    version="1.0.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount React static files
# The React app will be served from the root path, while API routes remain at /api/*
react_build_path = Path(__file__).parent.parent / "frontend" / ".next" / "static"
if react_build_path.exists():
    app.mount("/_next/static", StaticFiles(directory=str(react_build_path)), name="react-static")
    logger.info(f"Mounted React static files from {react_build_path}")

# Mount static files for forms (MacMap, TradeMap, etc.)
static_path = Path(__file__).parent.parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
    logger.info(f"Mounted static files from {static_path}")

class TaskResponse(BaseModel):
    task_id: str
    status: str
    message: str

class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    traceback: Optional[str] = None
    date_done: Optional[datetime] = None

class TariffRequest(BaseModel):
    country1: str = Field(..., description="Importing country")
    country2: str = Field(..., description="Exporting country")
    year: int = Field(..., description="Target year")
    hsc: str = Field(..., description="HS code")

class TariffBulkRequest(BaseModel):
    hscodes: List[str] = Field(..., description="List of HS codes")
    importing_countries: List[str] = Field(..., description="List of importing countries (reporters)")
    exporting_countries: List[str] = Field(..., description="List of exporting countries (partners)")
    year: int = Field(..., description="Target year")

class TariffFullBulkRequest(BaseModel):
    countries: List[str] = Field(..., description="List of countries to scrape full tariff data")

class TradeRemediesRequest(BaseModel):
    country1: str = Field(..., description="Importing country")
    country2: str = Field(..., description="Exporting country")
    year: int = Field(..., description="Target year")
    hsc: str = Field(..., description="HS code")

class RegulatoryRequest(BaseModel):
    country1: str = Field(..., description="Importing country")
    country2: str = Field(..., description="Exporting country")
    hsc: str = Field(..., description="HS code")
    regtype: str = Field(..., description="Regulation type: 'i' for import, 'e' for export")

class MarketRequest(BaseModel):
    country: str = Field(..., description="Country name")
    hsc: str = Field(..., description="HS code")

class ProductsRequest(BaseModel):
    country1: str = Field(..., description="Importing country")
    country2: str = Field(..., description="Exporting country")
    hsc_lvl: int = Field(..., description="HS level (2, 4, or 6)")

class FullTariffRequest(BaseModel):
    country: str = Field(..., description="Country name")

class BatchTariffRequest(BaseModel):
    country_pairs: List[List[str]] = Field(..., description="List of [country1, country2] pairs")
    year: int = Field(..., description="Target year")
    hsc_codes: List[str] = Field(..., description="List of HS codes")

class ComprehensiveAnalysisRequest(BaseModel):
    country1: str = Field(..., description="First country")
    country2: str = Field(..., description="Second country")
    year: int = Field(..., description="Target year")
    hsc_codes: List[str] = Field(..., description="List of HS codes")

class IndianTradePortalRequest(BaseModel):
    hscode: str = Field(..., description="HS code to scrape")

class TradeMapRequest(BaseModel):
    hscode: str = Field(..., description="HS code")
    country1: str = Field(..., description="First country")
    country2: str = Field(..., description="Second country")

class TradeMapBulkRequest(BaseModel):
    hscodes: List[str] = Field(..., description="List of HS codes")
    exporting_countries: List[str] = Field(..., description="List of exporting countries")
    importing_countries: List[str] = Field(..., description="List of importing countries")

class EximpediaRequest(BaseModel):
    start_date: str = Field(..., description="Start date in MM/DD/YYYY format")
    end_date: str = Field(..., description="End date in MM/DD/YYYY format")
    hscode: str = Field(..., description="HS code")
    country: str = Field(..., description="Country name")
    mode: str = Field(..., description="Mode: 'import' or 'export'")

class EximpediaBatchItem(BaseModel):
    start_date: str = Field(..., description="Start date in MM/DD/YYYY format")
    end_date: str = Field(..., description="End date in MM/DD/YYYY format")
    hscode: str = Field(..., description="HS code")
    country: str = Field(..., description="Country name")
    mode: str = Field(..., description="Mode: 'import' or 'export'")

class EximpediaBatchRequest(BaseModel):
    batch_data: List[EximpediaBatchItem] = Field(..., description="List of Eximpedia scraping requests")

class PortScraperStartFreshRequest(BaseModel):
    headless: bool = Field(True, description="Run browser in headless mode")
    countries_limit: Optional[int] = Field(None, description="Limit number of countries to scrape (None = all)")

class PortScraperResumeRequest(BaseModel):
    start_country: str = Field(..., description="Country code or name to start from")
    headless: bool = Field(True, description="Run browser in headless mode")
    countries_limit: Optional[int] = Field(None, description="Limit number of countries to scrape (None = all)")

class PortScraperUpdateExistingRequest(BaseModel):
    start_country: Optional[str] = Field(None, description="Country code or name to start from (None = from beginning)")
    headless: bool = Field(True, description="Run browser in headless mode")
    countries_limit: Optional[int] = Field(None, description="Limit number of countries to scrape (None = all)")

class IndiamartProductScraperRequest(BaseModel):
    max_workers: int = Field(10, description="Number of concurrent workers for scraping")
    batch_size: int = Field(100, description="Number of URLs per batch")

class IndiamartCategoryScraperRequest(BaseModel):
    max_workers: int = Field(150, description="Number of concurrent workers for category crawling")
    max_concurrent_requests: int = Field(300, description="Maximum concurrent HTTP requests")
    batch_size: int = Field(1000, description="Number of categories to process per batch")
    auto_start_products: bool = Field(True, description="Automatically start product scraping after category crawling")

class PayloadGenerationRequest(BaseModel):
    payload_type: str = Field(..., description="Type of payload to generate")
    config: Dict[str, Any] = Field(..., description="Configuration for payload generation")

class WorkerStartRequest(BaseModel):
    name: str = Field(..., description="Worker name/hostname")
    queues: str = Field("default", description="Comma-separated list of queues")
    concurrency: int = Field(4, description="Number of concurrent processes")
    loglevel: str = Field("info", description="Log level")

class WorkerAssignmentRequest(BaseModel):
    scraper_id: str = Field(..., description="Scraper ID to assign")
    worker_name: str = Field(..., description="Worker name to assign to")

def get_task_info(task_id: str) -> Dict[str, Any]:
    try:
        details = get_celery_task_details(task_id)
        if details:
            return details
        result = AsyncResult(task_id, app=celery_app)
        return {
            "task_id": task_id,
            "status": result.status,
            "result": result.result,
            "traceback": result.traceback,
            "date_done": result.date_done
        }
    except Exception as e:
        logger.error(f"Error getting task info: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving task info: {str(e)}")

@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api")
async def api_info():
    return {
        "message": "Macmap Scraper API",
        "version": "1.0.0",
        "endpoints": {
            "tariff": "/api/v1/scrape/tariff",
            "trade-remedies": "/api/v1/scrape/trade-remedies",
            "regulatory": "/api/v1/scrape/regulatory",
            "market": "/api/v1/scrape/market",
            "competitors": "/api/v1/scrape/competitors",
            "products": "/api/v1/scrape/products",
            "full-tariff": "/api/v1/scrape/full-tariff",
            "batch": "/api/v1/scrape/batch",
            "comprehensive": "/api/v1/scrape/comprehensive",
            "indian-trade-portal": "/api/v1/scrape/indian-trade-portal",
            "trademap": "/api/v1/scrape/trademap",
            "eximpedia": "/api/v1/scrape/eximpedia",
            "eximpedia-batch": "/api/v1/scrape/eximpedia-batch",
            "status": "/api/v1/task/{task_id}",
            "health": "/health",
            "payload": "/payload"
        }
    }

@app.get("/trademap-form")
async def trademap_form(request: Request):
    return templates.TemplateResponse("trademap_form.html", {"request": request})

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now()}

@app.get("/api/v1/health")
async def get_system_health():
    """Get comprehensive system health metrics"""
    try:
        import psutil
        
        # CPU metrics
        cpu_percent = psutil.cpu_percent(interval=0.5)
        cpu_count = psutil.cpu_count()
        
        # Memory metrics
        memory = psutil.virtual_memory()
        
        # Disk metrics
        disk = psutil.disk_usage('/')
        
        # Check Redis connection
        redis_healthy = False
        try:
            celery_app.backend.client.ping()
            redis_healthy = True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
        
        # Check Celery workers
        celery_healthy = False
        try:
            inspect = celery_app.control.inspect()
            stats = inspect.stats()
            celery_healthy = stats is not None and len(stats) > 0
        except Exception as e:
            logger.error(f"Celery health check failed: {e}")
        
        # Check database (SQLite)
        database_healthy = False
        try:
            import sqlite3
            from pathlib import Path
            # Check if at least one database exists and is accessible
            db_path = Path("task_creator/scrapped_data/macmap_tariff_tasks.db")
            if db_path.exists():
                conn = sqlite3.connect(db_path)
                conn.execute("SELECT 1")
                conn.close()
                database_healthy = True
            else:
                # If no database exists yet, consider it healthy (not an error)
                database_healthy = True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
        
        return {
            "success": True,
            "health": {
                "cpu": {
                    "percent": round(cpu_percent, 2),
                    "cores": cpu_count
                },
                "memory": {
                    "percent": round(memory.percent, 2),
                    "total": memory.total,
                    "used": memory.used,
                    "available": memory.available
                },
                "disk": {
                    "percent": round((disk.used / disk.total) * 100, 2),
                    "total": disk.total,
                    "used": disk.used,
                    "free": disk.free
                },
                "services": {
                    "redis": "healthy" if redis_healthy else "unhealthy",
                    "celery": "healthy" if celery_healthy else "unhealthy",
                    "database": "healthy" if database_healthy else "unhealthy"
                }
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting system health: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to get system health: {str(e)}",
            "health": None,
            "timestamp": datetime.now().isoformat()
        }

@app.post("/api/v1/scrape/tariff", response_model=TaskResponse)
async def scrape_tariff(request: TariffRequest):
    try:
        task = scrape_macmap_tariff.delay(
            request.country1, 
            request.country2, 
            request.year, 
            request.hsc
        )
        logger.info(f"Queued tariff task: {task.id}")
        return TaskResponse(
            task_id=task.id,
            status="queued",
            message=f"Tariff scraping task queued for {request.country1} -> {request.country2}"
        )
    except Exception as e:
        logger.error(f"Error queueing tariff task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/scrape/tariff/bulk")
async def scrape_tariff_bulk_api(request: TariffBulkRequest):
    """
    Create bulk MacMap Tariff scraping tasks for all combinations of HS codes and countries.
    
    Example:
        - HS codes: ["29211", "081350"]
        - Importing: ["United States", "China"]
        - Exporting: ["India", "Germany"]
        - Year: 2023
        = Creates 2 × 2 × 2 = 8 tasks (all combinations)
    """
    try:
        task_ids = []
        total_tasks = len(request.hscodes) * len(request.importing_countries) * len(request.exporting_countries)
        
        logger.info(f"Creating {total_tasks} MacMap Tariff bulk tasks for year {request.year}")
        
        # Create all combinations of HS codes × importing countries × exporting countries
        for hscode in request.hscodes:
            for importing_country in request.importing_countries:
                for exporting_country in request.exporting_countries:
                    task = scrape_macmap_tariff.delay(
                        importing_country.strip(),  # country1
                        exporting_country.strip(),  # country2
                        request.year,
                        hscode.strip()
                    )
                    task_ids.append(task.id)
                    logger.info(f"Queued MacMap Tariff bulk task {len(task_ids)}/{total_tasks}: {task.id} - HS:{hscode} ({importing_country} <- {exporting_country}, Year:{request.year})")
        
        return {
            "status": "success",
            "total_tasks": total_tasks,
            "task_ids": task_ids,
            "message": f"Successfully queued {total_tasks} MacMap Tariff scraping tasks for year {request.year}"
        }
    except Exception as e:
        logger.error(f"Error queueing MacMap Tariff bulk tasks: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/scrape/tariff/full/bulk")
async def scrape_tariff_full_bulk_api(request: TariffFullBulkRequest):
    """
    Create Full Tariff scraping tasks for multiple countries.
    
    Each country will scrape:
    - All available years
    - All HS codes (8-digit level) for each year
    - Complete tariff data
    
    ⚠️ Warning: This is a FULL scrape and may take several hours per country!
    
    Example:
        - Countries: ["China", "India", "United States"]
        = Creates 3 full tariff scraping tasks
    """
    try:
        task_ids = []
        total_tasks = len(request.countries)
        
        logger.info(f"Creating {total_tasks} Full Tariff scraping tasks")
        
        # Create one full tariff task per country
        for country in request.countries:
            task = scrape_tariff_full.delay(country.strip())
            task_ids.append(task.id)
            logger.info(f"Queued Full Tariff task {len(task_ids)}/{total_tasks}: {task.id} - Country: {country}")
        
        return {
            "status": "success",
            "total_tasks": total_tasks,
            "task_ids": task_ids,
            "message": f"Successfully queued {total_tasks} Full Tariff scraping tasks. Each will scrape all years and HS codes."
        }
    except Exception as e:
        logger.error(f"Error queueing Full Tariff bulk tasks: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/scrape/trade-remedies", response_model=TaskResponse)
async def scrape_trade_remedies(request: TradeRemediesRequest):
    try:
        task = scrape_macmap_trade_remedies.delay(
            request.country1,
            request.country2,
            request.year,
            request.hsc
        )
        logger.info(f"Queued trade remedies task: {task.id}")
        return TaskResponse(
            task_id=task.id,
            status="queued",
            message=f"Trade remedies scraping task queued for {request.country1} -> {request.country2}"
        )
    except Exception as e:
        logger.error(f"Error queueing trade remedies task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/scrape/regulatory", response_model=TaskResponse)
async def scrape_regulatory(request: RegulatoryRequest):
    try:
        task = scrape_macmap_regulatory_requirements.delay(
            request.country1,
            request.country2,
            request.hsc,
            request.regtype
        )
        logger.info(f"Queued regulatory task: {task.id}")
        return TaskResponse(
            task_id=task.id,
            status="queued",
            message=f"Regulatory requirements scraping task queued for {request.country1} -> {request.country2}"
        )
    except Exception as e:
        logger.error(f"Error queueing regulatory task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/scrape/market", response_model=TaskResponse)
async def scrape_market(request: MarketRequest):
    try:
        task = scrape_macmap_compare_market.delay(request.country, request.hsc)
        logger.info(f"Queued market task: {task.id}")
        return TaskResponse(
            task_id=task.id,
            status="queued",
            message=f"Market comparison scraping task queued for {request.country}"
        )
    except Exception as e:
        logger.error(f"Error queueing market task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/scrape/competitors", response_model=TaskResponse)
async def scrape_competitors(request: MarketRequest):
    try:
        task = scrape_macmap_competitors.delay(request.country, request.hsc)
        logger.info(f"Queued competitors task: {task.id}")
        return TaskResponse(
            task_id=task.id,
            status="queued",
            message=f"Competitors scraping task queued for {request.country}"
        )
    except Exception as e:
        logger.error(f"Error queueing competitors task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/scrape/products", response_model=TaskResponse)
async def scrape_products(request: ProductsRequest):
    try:
        task = scrape_macmap_products.delay(
            request.country1,
            request.country2,
            request.hsc_lvl
        )
        logger.info(f"Queued products task: {task.id}")
        return TaskResponse(
            task_id=task.id,
            status="queued",
            message=f"Products scraping task queued for {request.country1} -> {request.country2}"
        )
    except Exception as e:
        logger.error(f"Error queueing products task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/scrape/full-tariff", response_model=TaskResponse)
async def scrape_full_tariff(request: FullTariffRequest):
    try:
        task = scrape_tariff_full.delay(request.country)
        logger.info(f"Queued full tariff task: {task.id}")
        return TaskResponse(
            task_id=task.id,
            status="queued",
            message=f"Full tariff scraping task queued for {request.country} (This may take hours to complete)"
        )
    except Exception as e:
        logger.error(f"Error queueing full tariff task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/scrape/batch", response_model=TaskResponse)
async def scrape_batch_tariffs(request: BatchTariffRequest):
    try:
        task = batch_scrape_tariffs.delay(
            request.country_pairs,
            request.year,
            request.hsc_codes
        )
        logger.info(f"Queued batch task: {task.id}")
        return TaskResponse(
            task_id=task.id,
            status="queued",
            message=f"Batch tariff scraping task queued for {len(request.country_pairs)} country pairs and {len(request.hsc_codes)} HS codes"
        )
    except Exception as e:
        logger.error(f"Error queueing batch task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/scrape/comprehensive", response_model=TaskResponse)
async def scrape_comprehensive_analysis(request: ComprehensiveAnalysisRequest):
    try:
        task = comprehensive_country_analysis.delay(
            request.country1,
            request.country2,
            request.year,
            request.hsc_codes
        )
        logger.info(f"Queued comprehensive analysis task: {task.id}")
        return TaskResponse(
            task_id=task.id,
            status="queued",
            message=f"Comprehensive analysis task queued for {request.country1} <-> {request.country2}"
        )
    except Exception as e:
        logger.error(f"Error queueing comprehensive analysis task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/scrape/indian-trade-portal", response_model=TaskResponse)
async def scrape_indian_trade_portal_api(request: IndianTradePortalRequest):
    try:
        task = scrape_indian_trade_portal.delay(request.hscode)
        logger.info(f"Queued Indian Trade Portal task: {task.id}")
        return TaskResponse(
            task_id=task.id,
            status="queued",
            message=f"Indian Trade Portal scraping task queued for HS code: {request.hscode}"
        )
    except Exception as e:
        logger.error(f"Error queueing Indian Trade Portal task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/scrape/trademap", response_model=TaskResponse)
async def scrape_trademap_api(request: TradeMapRequest):
    try:
        task = trademap_scraper_task.delay(request.hscode, request.country1, request.country2)
        logger.info(f"Queued TradeMap task: {task.id}")
        return TaskResponse(
            task_id=task.id,
            status="queued",
            message=f"TradeMap scraping task queued for HS code: {request.hscode} ({request.country1} -> {request.country2})"
        )
    except Exception as e:
        logger.error(f"Error queueing TradeMap task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/scrape/trademap/bulk")
async def scrape_trademap_bulk_api(request: TradeMapBulkRequest):
    """
    Create bulk TradeMap scraping tasks for all combinations of HS codes and countries.
    
    Example:
        - HS codes: ["29211", "081350"]
        - Exporting: ["United States of America", "India"]
        - Importing: ["China", "Germany"]
        = Creates 2 × 2 × 2 = 8 tasks (all combinations)
    """
    try:
        task_ids = []
        total_tasks = len(request.hscodes) * len(request.exporting_countries) * len(request.importing_countries)
        
        logger.info(f"Creating {total_tasks} TradeMap bulk tasks")
        
        # Create all combinations of HS codes × exporting countries × importing countries
        for hscode in request.hscodes:
            for exporting_country in request.exporting_countries:
                for importing_country in request.importing_countries:
                    task = trademap_scraper_task.delay(
                        hscode.strip(),
                        exporting_country.strip(),
                        importing_country.strip()
                    )
                    task_ids.append(task.id)
                    logger.info(f"Queued TradeMap bulk task {len(task_ids)}/{total_tasks}: {task.id} - HS:{hscode} ({exporting_country} -> {importing_country})")
        
        return {
            "status": "success",
            "total_tasks": total_tasks,
            "task_ids": task_ids,
            "message": f"Successfully queued {total_tasks} TradeMap scraping tasks"
        }
    except Exception as e:
        logger.error(f"Error queueing TradeMap bulk tasks: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/scrape/eximpedia", response_model=TaskResponse)
async def scrape_eximpedia_api(request: EximpediaRequest):
    try:
        task = eximpedia_scraper_task.delay(
            request.start_date,
            request.end_date,
            request.hscode,
            request.country,
            request.mode
        )
        logger.info(f"Queued Eximpedia task: {task.id}")
        return TaskResponse(
            task_id=task.id,
            status="queued",
            message=f"Eximpedia scraping task queued for {request.country} ({request.mode}) - HS code: {request.hscode}"
        )
    except Exception as e:
        logger.error(f"Error queueing Eximpedia task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/scrape/eximpedia-batch", response_model=TaskResponse)
async def scrape_eximpedia_batch_api(request: EximpediaBatchRequest):
    try:
        batch_data = []
        for item in request.batch_data:
            batch_data.append({
                "start_date": item.start_date,
                "end_date": item.end_date,
                "hscode": item.hscode,
                "country": item.country,
                "mode": item.mode
            })
        
        task = eximpedia_batch_scraper_task.delay(batch_data)
        logger.info(f"Queued Eximpedia batch task: {task.id}")
        return TaskResponse(
            task_id=task.id,
            status="queued",
            message=f"Eximpedia batch scraping task queued with {len(batch_data)} items"
        )
    except Exception as e:
        logger.error(f"Error queueing Eximpedia batch task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/scrape/ports/start-fresh", response_model=TaskResponse)
async def scrape_ports_start_fresh_api(request: PortScraperStartFreshRequest):
    """
    Start fresh port scraping - scrape all countries from the beginning.
    Skip countries that already exist in the database.
    """
    try:
        task = port_scraper_start_fresh_task.delay(
            headless=request.headless,
            countries_limit=request.countries_limit
        )
        logger.info(f"Queued Port Scraper (Start Fresh) task: {task.id}")
        limit_msg = f" (limited to {request.countries_limit} countries)" if request.countries_limit else ""
        return TaskResponse(
            task_id=task.id,
            status="queued",
            message=f"Port scraper task queued (start fresh){limit_msg}"
        )
    except Exception as e:
        logger.error(f"Error queueing Port Scraper (Start Fresh) task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/scrape/ports/resume", response_model=TaskResponse)
async def scrape_ports_resume_api(request: PortScraperResumeRequest):
    """
    Resume port scraping from a specific country.
    """
    try:
        task = port_scraper_resume_task.delay(
            start_country=request.start_country,
            headless=request.headless,
            countries_limit=request.countries_limit
        )
        logger.info(f"Queued Port Scraper (Resume) task: {task.id}")
        limit_msg = f" (limited to {request.countries_limit} countries)" if request.countries_limit else ""
        return TaskResponse(
            task_id=task.id,
            status="queued",
            message=f"Port scraper task queued (resume from {request.start_country}){limit_msg}"
        )
    except Exception as e:
        logger.error(f"Error queueing Port Scraper (Resume) task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/scrape/ports/update-existing", response_model=TaskResponse)
async def scrape_ports_update_existing_api(request: PortScraperUpdateExistingRequest):
    """
    Update existing ports - re-scrape countries that already exist in the database.
    """
    try:
        task = port_scraper_update_existing_task.delay(
            start_country=request.start_country,
            headless=request.headless,
            countries_limit=request.countries_limit
        )
        logger.info(f"Queued Port Scraper (Update Existing) task: {task.id}")
        start_msg = f"from {request.start_country}" if request.start_country else "from beginning"
        limit_msg = f" (limited to {request.countries_limit} countries)" if request.countries_limit else ""
        return TaskResponse(
            task_id=task.id,
            status="queued",
            message=f"Port scraper task queued (update existing {start_msg}){limit_msg}"
        )
    except Exception as e:
        logger.error(f"Error queueing Port Scraper (Update Existing) task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/scrape/ports/statistics")
async def get_ports_statistics_api():
    """
    Get current port scraping statistics from the database.
    """
    try:
        task = port_scraper_get_statistics_task.delay()
        logger.info(f"Queued Port Scraper (Get Statistics) task: {task.id}")
        return TaskResponse(
            task_id=task.id,
            status="queued",
            message="Port scraper statistics task queued"
        )
    except Exception as e:
        logger.error(f"Error queueing Port Scraper (Get Statistics) task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# INDIAMART SCRAPER ENDPOINTS
# ============================================================================

@app.post("/api/v1/scrape/indiamart/products", response_model=TaskResponse)
async def scrape_indiamart_products_api(request: IndiamartProductScraperRequest = Body(default=IndiamartProductScraperRequest())):
    """
    Start Indiamart product scraping with dedicated worker (V2 - Default).
    Automatically starts a separate indiamart_products_worker if not already running.
    
    This uses the new V2 scraper that reads URLs from MongoDB and saves data in the perfect format.
    
    Args:
        request: Configuration including:
            - max_workers: Number of concurrent workers (default: 10)
            - batch_size: Number of URLs per batch (default: 100)
    """
    try:
        # Check if IndiaMART products worker is already running
        import subprocess
        result = subprocess.run(
            ['pgrep', '-f', 'celery.*indiamart_products_worker'],
            capture_output=True,
            text=True
        )
        worker_running = bool(result.stdout.strip())
        
        if not worker_running:
            logger.info("Starting IndiaMART Products Celery worker automatically...")
            # Start the worker in the background with dedicated hostname
            worker_cmd = [
                'celery', '-A', 'celery_app.tasks', 'worker',
                '--loglevel', 'info',
                '--concurrency', '1',
                '-Q', 'indiamart_products',
                '--hostname', 'indiamart_products_worker@%h',
                '--max-tasks-per-child', '50',
                '--prefetch-multiplier', '1'
            ]
            
            # Start worker process
            subprocess.Popen(
                worker_cmd,
                stdout=open('logs/indiamart_products_worker.log', 'a'),
                stderr=subprocess.STDOUT,
                cwd=os.getcwd(),
                env={**os.environ, 'PYTHONPATH': os.getcwd()}
            )
            logger.info("IndiaMART Products worker started successfully")
            # Wait for worker to initialize
            await asyncio.sleep(3)
        else:
            logger.info("IndiaMART Products worker already running")
        
        # Queue the task with V2 scraper (now default)
        task = indiamart_product_scraper_task.apply_async(
            kwargs={
                'max_workers': request.max_workers,
                'batch_size': request.batch_size
            },
            queue='indiamart_products'
        )
        logger.info(f"Queued Indiamart Product Scraper V2 task: {task.id} to 'indiamart_products' queue (max_workers={request.max_workers}, batch_size={request.batch_size})")
        
        # Broadcast state update via WebSocket
        await state_synchronizer.websocket_manager.broadcast_to_scraper(
            "indiamart_products",
            {
                "type": "state",
                "state": "queued",
                "task_id": task.id,
                "max_workers": request.max_workers,
                "batch_size": request.batch_size,
                "version": "v2",
                "timestamp": datetime.now().isoformat()
            }
        )
        
        return TaskResponse(
            task_id=task.id,
            status="queued",
            message=f"Indiamart product scraping task queued (V2 - max_workers={request.max_workers}, batch_size={request.batch_size})"
        )
    except Exception as e:
        logger.error(f"Error queueing Indiamart Product Scraper task: {str(e)}")
        
        # Broadcast error state
        await state_synchronizer.websocket_manager.broadcast_to_scraper(
            "indiamart_products",
            {
                "type": "error",
                "message": f"Failed to queue task: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
        )
        
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/scrape/indiamart/products/legacy", response_model=TaskResponse)
async def scrape_indiamart_products_legacy_api(request: IndiamartProductScraperRequest = Body(default=IndiamartProductScraperRequest())):
    """
    LEGACY: Start Indiamart product scraping using old scraper.
    Use /api/v1/scrape/indiamart/products instead (V2 is now default).
    
    This endpoint is kept for backward compatibility only.
    """
    try:
        # Check if IndiaMART products worker is already running
        import subprocess
        result = subprocess.run(
            ['pgrep', '-f', 'celery.*indiamart_products_worker'],
            capture_output=True,
            text=True
        )
        worker_running = bool(result.stdout.strip())
        
        if not worker_running:
            logger.info("Starting IndiaMART Products Celery worker automatically...")
            worker_cmd = [
                'celery', '-A', 'celery_app.tasks', 'worker',
                '--loglevel', 'info',
                '--concurrency', '1',
                '-Q', 'indiamart_products',
                '--hostname', 'indiamart_products_worker@%h',
                '--max-tasks-per-child', '50',
                '--prefetch-multiplier', '1'
            ]
            
            subprocess.Popen(
                worker_cmd,
                stdout=open('logs/indiamart_products_worker.log', 'a'),
                stderr=subprocess.STDOUT,
                cwd=os.getcwd(),
                env={**os.environ, 'PYTHONPATH': os.getcwd()}
            )
            logger.info("IndiaMART Products worker started successfully")
            await asyncio.sleep(3)
        else:
            logger.info("IndiaMART Products worker already running")
        
        # Queue the legacy task
        task = indiamart_product_scraper_legacy_task.apply_async(
            kwargs={'max_workers': request.max_workers},
            queue='indiamart_products'
        )
        logger.info(f"Queued Indiamart Product Scraper LEGACY task: {task.id}")
        
        return TaskResponse(
            task_id=task.id,
            status="queued",
            message=f"Indiamart product scraping task queued (LEGACY - max_workers={request.max_workers})"
        )
    except Exception as e:
        logger.error(f"Error queueing Indiamart Product Scraper LEGACY task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/scrape/indiamart/categories", response_model=TaskResponse)
async def scrape_indiamart_categories_api(request: IndiamartCategoryScraperRequest = Body(default=IndiamartCategoryScraperRequest())):
    """
    Start Indiamart category crawler to generate product URLs.
    Automatically starts the indiamart_worker if not already running.
    
    Args:
        request: Configuration for category crawler including:
            - max_workers: Number of concurrent workers (default: 150)
            - max_concurrent_requests: Maximum concurrent HTTP requests (default: 300)
            - batch_size: Categories per batch (default: 1000)
            - auto_start_products: Auto-start product scraping after completion (default: True)
    """
    try:
        # Check if IndiaMART worker is already running
        import subprocess
        result = subprocess.run(
            ['pgrep', '-f', 'celery.*indiamart'],
            capture_output=True,
            text=True
        )
        worker_running = bool(result.stdout.strip())
        
        if not worker_running:
            logger.info("Starting IndiaMART Celery worker automatically...")
            # Start the worker in the background
            worker_cmd = [
                'celery', '-A', 'celery_app.tasks', 'worker',
                '--loglevel', 'info',
                '--concurrency', '1',
                '-Q', 'indiamart_categories',
                '--hostname', 'indiamart_categories_worker@%h',
                '--max-tasks-per-child', '50',
                '--prefetch-multiplier', '1'
            ]
            
            # Start worker process
            subprocess.Popen(
                worker_cmd,
                stdout=open('logs/indiamart_worker.log', 'a'),
                stderr=subprocess.STDOUT,
                cwd=os.getcwd(),
                env={**os.environ, 'PYTHONPATH': os.getcwd()}
            )
            logger.info("IndiaMART worker started successfully")
            # Wait for worker to initialize
            await asyncio.sleep(3)
        else:
            logger.info("IndiaMART worker already running")
        
        # Queue the task with configuration parameters
        task = indiamart_category_crawler_task.apply_async(
            kwargs={
                'auto_start_product_scraping': request.auto_start_products,
                'max_workers': request.max_workers,
                'max_concurrent_requests': request.max_concurrent_requests,
                'batch_size': request.batch_size
            },
            queue='indiamart_categories'
        )
        logger.info(f"Queued Indiamart Category Crawler task: {task.id} to 'indiamart_categories' queue (max_workers={request.max_workers}, auto_start_products={request.auto_start_products})")
        
        # Broadcast state update via WebSocket
        await state_synchronizer.websocket_manager.broadcast_to_scraper(
            "indiamart",
            {
                "type": "state",
                "state": "queued",
                "task_id": task.id,
                "max_workers": request.max_workers,
                "auto_start_products": request.auto_start_products,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        message = f"Indiamart category crawler task queued (worker started automatically, max_workers={request.max_workers})"
        if request.auto_start_products:
            message += " - Product scraping will start automatically after completion"
        
        return TaskResponse(
            task_id=task.id,
            status="queued",
            message=message
        )
    except Exception as e:
        logger.error(f"Error queueing Indiamart Category Crawler task: {str(e)}")
        
        # Broadcast error state
        await state_synchronizer.websocket_manager.broadcast_to_scraper(
            "indiamart",
            {
                "type": "error",
                "message": f"Failed to queue task: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
        )
        
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/indiamart/stop-crawler/{task_id}")
async def stop_indiamart_crawler(task_id: str):
    """
    Stop a running IndiaMART crawler by task ID with enhanced error handling.
    """
    try:
        logger.info(f"Attempting to stop IndiaMART crawler with task_id: {task_id}")
        
        # Broadcast stopping state immediately
        await state_synchronizer.websocket_manager.broadcast_to_scraper(
            "indiamart",
            {
                "type": "state",
                "state": "stopping",
                "task_id": task_id,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        # Try graceful stop for category crawler
        try:
            from scrapers.indiamart.indiamart_category_crawler import StopIndiamartCategoryCrawlerByTaskId
            # Attempt graceful stop
            graceful_stop = StopIndiamartCategoryCrawlerByTaskId(task_id)
        except Exception as e:
            logger.warning(f"Failed to import or call graceful stop: {e}")
            graceful_stop = False
        
        # Revoke the Celery task
        try:
            from celery import current_app
            current_app.control.revoke(task_id, terminate=True)
            logger.info(f"Celery task {task_id} revoked successfully")
            task_revoked = True
        except Exception as e:
            logger.warning(f"Failed to revoke Celery task {task_id}: {e}")
            task_revoked = False
        
        # Kill any lingering Chrome processes (cleanup)
        try:
            import subprocess
            subprocess.run(['pkill', '-f', 'chrome'], check=False, capture_output=True)
            logger.info("Chrome processes cleanup completed")
        except Exception as e:
            logger.warning(f"Chrome cleanup failed: {e}")
        
        # Kill all IndiaMART Celery workers to ensure complete stop
        try:
            import subprocess
            result = subprocess.run(
                ['pkill', '-9', '-f', 'celery.*indiamart'],
                check=False,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                logger.info("Killed all IndiaMART Celery worker processes")
            else:
                logger.info("No IndiaMART worker processes found to kill")
        except Exception as e:
            logger.warning(f"Failed to kill IndiaMART workers: {e}")
        
        # Stop the indiamart worker if no other tasks are running (legacy support)
        if WORKER_MANAGER_AVAILABLE and worker_manager:
            try:
                logger.info("Attempting to stop indiamart_worker via worker_manager...")
                success, msg = worker_manager.stop_worker("indiamart_worker")
                if success:
                    logger.info(f"IndiaMART worker stopped via manager: {msg}")
                else:
                    logger.warning(f"Worker manager stop result: {msg}")
            except Exception as e:
                logger.warning(f"Worker manager error during stop (continuing anyway): {e}")
        
        # Determine response based on what was successful
        if graceful_stop or task_revoked:
            status = "success"
            message = f"Task {task_id} stopped successfully"
            if graceful_stop:
                message += " (graceful stop)"
            if task_revoked:
                message += " (task revoked)"
            
            # Broadcast stopped state
            await state_synchronizer.websocket_manager.broadcast_to_scraper(
                "indiamart",
                {
                    "type": "state",
                    "state": "stopped",
                    "task_id": task_id,
                    "timestamp": datetime.now().isoformat()
                }
            )
        else:
            status = "warning"
            message = f"Task {task_id} may not have been running or already completed"
            
            # Broadcast warning state
            await state_synchronizer.websocket_manager.broadcast_to_scraper(
                "indiamart",
                {
                    "type": "warning",
                    "message": message,
                    "task_id": task_id,
                    "timestamp": datetime.now().isoformat()
                }
            )
        
        return {
            "status": status,
            "message": message,
            "task_id": task_id,
            "graceful_stop": graceful_stop,
            "task_revoked": task_revoked
        }
            
    except Exception as e:
        logger.error(f"Error stopping IndiaMART crawler {task_id}: {str(e)}")
        
        # Broadcast error state
        await state_synchronizer.websocket_manager.broadcast_to_scraper(
            "indiamart",
            {
                "type": "error",
                "message": f"Failed to stop crawler: {str(e)}",
                "task_id": task_id,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        raise HTTPException(status_code=500, detail=f"Error stopping crawler: {str(e)}")

@app.post("/api/v1/indiamart/stop-all-crawlers")
async def stop_all_indiamart_crawlers():
    """
    Stop all active IndiaMART category crawlers.
    """
    try:
        try:
            from scrapers.indiamart.indiamart_category_crawler import StopAllIndiamartCategoryCrawlers
            stop_function_available = True
        except Exception as e:
            logger.warning(f"Failed to import stop function: {e}")
            stop_function_available = False
        
        logger.info("Received request to stop all IndiaMART category crawlers")
        
        # Broadcast stopping state for all crawlers
        await state_synchronizer.websocket_manager.broadcast_to_scraper(
            "indiamart",
            {
                "type": "state",
                "state": "stopping_all",
                "timestamp": datetime.now().isoformat()
            }
        )
        
        # Stop all active crawlers
        stopped_count = 0
        if stop_function_available:
            result = StopAllIndiamartCategoryCrawlers()
            stopped_count = result.get("stopped_count", 0)
        
        # Also revoke all IndiaMART tasks via Celery
        try:
            from celery import current_app
            inspect = current_app.control.inspect()
            active_tasks = inspect.active() or {}
            
            for worker, tasks in active_tasks.items():
                for task in tasks:
                    if 'indiamart' in task.get('name', '').lower():
                        task_id = task.get('id')
                        current_app.control.revoke(task_id, terminate=True)
                        logger.info(f"Revoked IndiaMART task: {task_id}")
                        stopped_count += 1
        except Exception as e:
            logger.warning(f"Failed to revoke Celery tasks: {e}")
        
        # Kill all IndiaMART Celery workers
        try:
            import subprocess
            result = subprocess.run(
                ['pkill', '-9', '-f', 'celery.*indiamart'],
                check=False,
                capture_output=True,
                text=True
            )
            logger.info("Killed all IndiaMART Celery worker processes")
        except Exception as e:
            logger.warning(f"Failed to kill IndiaMART workers: {e}")
        
        # Kill any lingering Chrome processes
        try:
            import subprocess
            subprocess.run(["pkill", "-f", "chrome"], check=False, capture_output=True)
            logger.info("Killed any lingering Chrome processes")
        except Exception as e:
            logger.warning(f"Failed to kill Chrome processes: {e}")
        
        # Broadcast completion state
        await state_synchronizer.websocket_manager.broadcast_to_scraper(
            "indiamart",
            {
                "type": "state",
                "state": "all_stopped",
                "stopped_count": stopped_count,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        return {
            "status": "success",
            "message": f"Stopped {stopped_count} IndiaMART crawlers",
            "stopped_count": stopped_count
        }
        
    except Exception as e:
        logger.error(f"Error stopping all IndiaMART crawlers: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/indiamart/stop-products/{task_id}")
async def stop_indiamart_products(task_id: str):
    """
    Stop a running IndiaMART products scraper by task ID.
    """
    try:
        logger.info(f"Attempting to stop IndiaMART products scraper with task_id: {task_id}")
        
        # Broadcast stopping state immediately
        await state_synchronizer.websocket_manager.broadcast_to_scraper(
            "indiamart_products",
            {
                "type": "state",
                "state": "stopping",
                "task_id": task_id,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        # Try graceful stop for product scraper
        try:
            from scrapers.indiamart.indiamart_scraper import StopIndiamartProductScraperByTaskId
            graceful_stop = StopIndiamartProductScraperByTaskId(task_id)
        except Exception as e:
            logger.warning(f"Failed to import or call graceful stop: {e}")
            graceful_stop = False
        
        # Revoke the Celery task
        try:
            from celery import current_app
            current_app.control.revoke(task_id, terminate=True)
            logger.info(f"Celery task {task_id} revoked successfully")
            task_revoked = True
        except Exception as e:
            logger.warning(f"Failed to revoke Celery task {task_id}: {e}")
            task_revoked = False
        
        # Kill IndiaMART products worker processes
        try:
            import subprocess
            result = subprocess.run(
                ['pkill', '-9', '-f', 'celery.*indiamart_products_worker'],
                check=False,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                logger.info("Killed IndiaMART products worker processes")
            else:
                logger.info("No IndiaMART products worker processes found to kill")
        except Exception as e:
            logger.warning(f"Failed to kill IndiaMART products workers: {e}")
        
        # Determine response
        if graceful_stop or task_revoked:
            status = "success"
            message = f"Products scraper {task_id} stopped successfully"
            
            # Broadcast stopped state
            await state_synchronizer.websocket_manager.broadcast_to_scraper(
                "indiamart_products",
                {
                    "type": "state",
                    "state": "stopped",
                    "task_id": task_id,
                    "timestamp": datetime.now().isoformat()
                }
            )
        else:
            status = "warning"
            message = f"Task {task_id} may not have been running or already completed"
        
        return {
            "status": status,
            "message": message,
            "task_id": task_id,
            "graceful_stop": graceful_stop,
            "task_revoked": task_revoked
        }
            
    except Exception as e:
        logger.error(f"Error stopping IndiaMART products scraper {task_id}: {str(e)}")
        
        # Broadcast error state
        await state_synchronizer.websocket_manager.broadcast_to_scraper(
            "indiamart_products",
            {
                "type": "error",
                "message": f"Failed to stop scraper: {str(e)}",
                "task_id": task_id,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        raise HTTPException(status_code=500, detail=f"Error stopping scraper: {str(e)}")

@app.post("/api/v1/indiamart/stop-all-products")
async def stop_all_indiamart_products():
    """
    Stop all active IndiaMART products scrapers.
    """
    try:
        logger.info("Received request to stop all IndiaMART products scrapers")
        
        # Broadcast stopping state
        await state_synchronizer.websocket_manager.broadcast_to_scraper(
            "indiamart_products",
            {
                "type": "state",
                "state": "stopping_all",
                "timestamp": datetime.now().isoformat()
            }
        )
        
        # Stop all active scrapers
        stopped_count = 0
        try:
            from scrapers.indiamart.indiamart_scraper import StopAllIndiamartProductScrapers
            result = StopAllIndiamartProductScrapers()
            stopped_count = result.get("stopped_count", 0)
        except Exception as e:
            logger.warning(f"Failed to call stop all function: {e}")
        
        # Revoke all IndiaMART product tasks via Celery
        try:
            from celery import current_app
            inspect = current_app.control.inspect()
            active_tasks = inspect.active() or {}
            
            for worker, tasks in active_tasks.items():
                if 'indiamart_products_worker' in worker:
                    for task in tasks:
                        task_id = task.get('id')
                        current_app.control.revoke(task_id, terminate=True)
                        logger.info(f"Revoked IndiaMART products task: {task_id}")
                        stopped_count += 1
        except Exception as e:
            logger.warning(f"Failed to revoke Celery tasks: {e}")
        
        # Kill all IndiaMART products workers
        try:
            import subprocess
            result = subprocess.run(
                ['pkill', '-9', '-f', 'celery.*indiamart_products_worker'],
                check=False,
                capture_output=True,
                text=True
            )
            logger.info("Killed all IndiaMART products worker processes")
        except Exception as e:
            logger.warning(f"Failed to kill IndiaMART products workers: {e}")
        
        # Broadcast completion state
        await state_synchronizer.websocket_manager.broadcast_to_scraper(
            "indiamart_products",
            {
                "type": "state",
                "state": "all_stopped",
                "stopped_count": stopped_count,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        return {
            "status": "success",
            "message": f"Stopped {stopped_count} IndiaMART products scrapers",
            "stopped_count": stopped_count
        }
        
    except Exception as e:
        logger.error(f"Error stopping all IndiaMART products scrapers: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
        logger.error(f"Error stopping all crawlers: {str(e)}")
        
        # Broadcast error state
        await state_synchronizer.websocket_manager.broadcast_to_scraper(
            "indiamart",
            {
                "type": "error",
                "message": f"Failed to stop all crawlers: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
        )
        
        raise HTTPException(status_code=500, detail=f"Error stopping all crawlers: {str(e)}")

@app.get("/api/v1/indiamart/crawler/health")
async def get_crawler_health():
    """
    Get health status and active crawlers information.
    """
    try:
        # Get active category crawlers (if function exists)
        active_category_crawlers = []
        # Note: GetActiveCategoryCrawlers function doesn't exist in indiamart_category_crawler.py
        
        # Check database connectivity
        db_healthy = True
        try:
            from database import get_database_connection
            conn = get_database_connection()
            if conn:
                conn.close()
        except Exception as e:
            logger.warning(f"Database health check failed: {e}")
            db_healthy = False
        
        # Check Celery worker status
        celery_healthy = True
        active_workers = 0
        try:
            from celery import current_app
            inspect = current_app.control.inspect()
            stats = inspect.stats()
            if stats:
                active_workers = len(stats)
            else:
                celery_healthy = False
        except Exception as e:
            logger.warning(f"Celery health check failed: {e}")
            celery_healthy = False
        
        overall_health = "healthy" if (db_healthy and celery_healthy) else "degraded"
        
        return {
            "status": "success",
            "overall_health": overall_health,
            "timestamp": datetime.now().isoformat(),
            "components": {
                "database": "healthy" if db_healthy else "unhealthy",
                "celery": "healthy" if celery_healthy else "unhealthy",
                "active_workers": active_workers
            },
            "active_crawlers": {
                "category_crawlers": len(active_category_crawlers),
                "total": len(active_category_crawlers)
            },
            "crawler_details": {
                "category": active_category_crawlers
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting crawler health: {str(e)}")
        return {
            "status": "error",
            "overall_health": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }

@app.get("/api/v1/indiamart/crawler/metrics")
async def get_crawler_metrics():
    """
    Get detailed metrics about crawler performance and statistics.
    """
    try:
        import os
        import psutil
        from pathlib import Path
        
        # System metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Check log files and data directories
        log_dir = Path("/data/data-extractor/logs")
        data_dir = Path("/data/data-extractor/url_files")
        
        log_files = list(log_dir.glob("*.log")) if log_dir.exists() else []
        csv_files = list(data_dir.glob("*.csv")) if data_dir.exists() else []
        
        # Get recent log file sizes
        recent_logs = {}
        for log_file in log_files[-5:]:  # Last 5 log files
            try:
                stat = log_file.stat()
                recent_logs[log_file.name] = {
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                }
            except Exception:
                continue
        
        # Get CSV file info
        csv_info = {}
        for csv_file in csv_files:
            try:
                stat = csv_file.stat()
                csv_info[csv_file.name] = {
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                }
            except Exception:
                continue
        
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "system_metrics": {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_gb": round(memory.available / (1024**3), 2),
                "disk_percent": round((disk.used / disk.total) * 100, 2),
                "disk_free_gb": round(disk.free / (1024**3), 2)
            },
            "file_metrics": {
                "log_files_count": len(log_files),
                "csv_files_count": len(csv_files),
                "recent_logs": recent_logs,
                "csv_files": csv_info
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting crawler metrics: {str(e)}")
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }

@app.get("/api/v1/indiamart/statistics")
async def get_indiamart_statistics():
    """
    Get IndiaMART database statistics from MongoDB.
    Returns detailed statistics about categories, URLs, and scraping progress.
    """
    try:
        from scrapers.indiamart.indiamart_mongodb import IndiamartMongoDB
        
        db = IndiamartMongoDB()
        stats = db.get_statistics()
        
        # Calculate additional metrics
        total_urls = stats.get('total_urls', 0)
        pending_urls = stats.get('pending_urls', 0)
        completed_urls = stats.get('completed_urls', 0)
        failed_urls = stats.get('failed_urls', 0)
        
        # Calculate percentages
        completion_rate = (completed_urls / total_urls * 100) if total_urls > 0 else 0
        failure_rate = (failed_urls / total_urls * 100) if total_urls > 0 else 0
        
        # Enhanced response
        response_data = {
            "status": "success",
            "data": {
                # Category statistics
                "categories": {
                    "total": stats.get('total_categories', 0)
                },
                
                # URL statistics
                "urls": {
                    "total": total_urls,
                    "pending": pending_urls,
                    "scraped": completed_urls,
                    "failed": failed_urls,
                    "completion_rate": round(completion_rate, 2),
                    "failure_rate": round(failure_rate, 2)
                },
                
                # Product statistics
                "products": {
                    "total_scraped": stats.get('scraped_products', 0)
                },
                
                # Seller statistics
                "sellers": {
                    "total_scraped": stats.get('scraped_sellers', 0)
                },
                
                # Performance metrics
                "performance": {
                    "cache_hit_rate": round(stats.get('cache_hit_rate', 0), 2),
                    "operation_stats": stats.get('operation_stats', {})
                },
                
                # Database info
                "database": {
                    "type": "MongoDB",
                    "name": "indiamart_data"
                }
            }
        }
        
        db.close()
        return response_data
        
    except Exception as e:
        logger.error(f"Error getting IndiaMART statistics: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting statistics: {str(e)}")

@app.get("/api/v1/indiamart/recent-urls")
async def get_indiamart_recent_urls(limit: int = 100, status: str = None):
    """
    Get recent product URLs from IndiaMART scraper.
    
    Query Parameters:
    - limit: Number of URLs to return (default: 100, max: 1000)
    - status: Filter by status ('pending', 'scraped', 'failed', or None for all)
    """
    try:
        from scrapers.indiamart.indiamart_mongodb import IndiamartMongoDB
        
        # Validate limit
        limit = min(limit, 1000)
        
        db = IndiamartMongoDB()
        
        # Build query filter
        query_filter = {}
        if status and status in ['pending', 'scraped', 'failed']:
            query_filter['status'] = status
        
        # Get recent URLs from MongoDB
        cursor = db.product_urls_collection.find(
            query_filter,
            {
                '_id': 0,
                'product_url': 1,
                'category': 1,
                'subcategory': 1,
                'status': 1,
                'created_at': 1,
                'scraped_at': 1,
                'error_count': 1,
                'last_error': 1
            }
        ).sort('created_at', -1).limit(limit)
        
        urls = list(cursor)
        
        # Convert datetime objects to ISO format strings
        for url in urls:
            if 'created_at' in url and url['created_at']:
                url['created_at'] = url['created_at'].isoformat()
            if 'scraped_at' in url and url['scraped_at']:
                url['scraped_at'] = url['scraped_at'].isoformat()
        
        db.close()
        
        return {
            "status": "success",
            "data": {
                "urls": urls,
                "count": len(urls),
                "filter": status or "all"
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting recent URLs: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting recent URLs: {str(e)}")

@app.get("/api/v1/indiamart/dashboard")
async def get_indiamart_dashboard():
    """
    Get comprehensive IndiaMART dashboard data including statistics and recent activity.
    This endpoint provides all data needed for the homepage dashboard.
    """
    try:
        from scrapers.indiamart.indiamart_mongodb import IndiamartMongoDB
        
        db = IndiamartMongoDB()
        
        # Get statistics
        stats = db.get_statistics()
        
        # Calculate metrics
        total_urls = stats.get('total_urls', 0)
        pending_urls = stats.get('pending_urls', 0)
        completed_urls = stats.get('completed_urls', 0)
        failed_urls = stats.get('failed_urls', 0)
        
        completion_rate = (completed_urls / total_urls * 100) if total_urls > 0 else 0
        failure_rate = (failed_urls / total_urls * 100) if total_urls > 0 else 0
        
        # Get recent URLs (last 50)
        recent_urls_cursor = db.product_urls_collection.find(
            {},
            {
                '_id': 0,
                'product_url': 1,
                'category': 1,
                'status': 1,
                'created_at': 1
            }
        ).sort('created_at', -1).limit(50)
        
        recent_urls = []
        for url in recent_urls_cursor:
            if 'created_at' in url and url['created_at']:
                url['created_at'] = url['created_at'].isoformat()
            recent_urls.append(url)
        
        # Get category breakdown
        category_pipeline = [
            {
                '$group': {
                    '_id': '$category',
                    'total': {'$sum': 1},
                    'pending': {
                        '$sum': {'$cond': [{'$eq': ['$status', 'pending']}, 1, 0]}
                    },
                    'scraped': {
                        '$sum': {'$cond': [{'$eq': ['$status', 'scraped']}, 1, 0]}
                    },
                    'failed': {
                        '$sum': {'$cond': [{'$eq': ['$status', 'failed']}, 1, 0]}
                    }
                }
            },
            {'$sort': {'total': -1}},
            {'$limit': 10}
        ]
        
        category_stats = list(db.product_urls_collection.aggregate(category_pipeline))
        
        # Format category stats
        categories = []
        for cat in category_stats:
            categories.append({
                'name': cat['_id'] or 'Unknown',
                'total': cat['total'],
                'pending': cat['pending'],
                'scraped': cat['scraped'],
                'failed': cat['failed'],
                'completion_rate': round((cat['scraped'] / cat['total'] * 100) if cat['total'] > 0 else 0, 2)
            })
        
        db.close()
        
        return {
            "status": "success",
            "data": {
                "summary": {
                    "total_categories": stats.get('total_categories', 0),
                    "total_urls": total_urls,
                    "pending_urls": pending_urls,
                    "scraped_urls": completed_urls,
                    "failed_urls": failed_urls,
                    "completion_rate": round(completion_rate, 2),
                    "failure_rate": round(failure_rate, 2),
                    "total_products": stats.get('scraped_products', 0),
                    "total_sellers": stats.get('scraped_sellers', 0)
                },
                "recent_urls": recent_urls,
                "top_categories": categories,
                "performance": {
                    "cache_hit_rate": round(stats.get('cache_hit_rate', 0), 2)
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting dashboard data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting dashboard data: {str(e)}")

@app.get("/api/v1/indiamart/logs/{task_id}")
async def get_indiamart_logs(task_id: str, lines: int = 100):
    """
    Get logs for a specific IndiaMART crawler task.
    """
    try:
        import os
        from datetime import datetime
        
        # Look for log files
        log_dir = "logs"
        today = datetime.now().strftime('%Y%m%d')
        log_file = os.path.join(log_dir, f"indiamart_category_crawler_{today}.log")
        
        if not os.path.exists(log_file):
            return {"status": "success", "logs": [], "message": "No log file found"}
        
        # Read the last N lines
        with open(log_file, 'r') as f:
            all_lines = f.readlines()
            recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
        
        # Filter lines related to this task if task_id is provided
        filtered_lines = []
        for line in recent_lines:
            if task_id in line or not task_id:
                filtered_lines.append(line.strip())
        
        return {
            "status": "success",
            "logs": filtered_lines,
            "total_lines": len(filtered_lines)
        }
        
    except Exception as e:
        logger.error(f"Error getting IndiaMART logs: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting logs: {str(e)}")

@app.get("/api/v1/task/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    try:
        task_info = get_task_info(task_id)
        return TaskStatusResponse(**task_info)
    except Exception as e:
        logger.error(f"Error getting task status: {str(e)}")
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

@app.get("/api/v1/task/{task_id}/logs")
async def get_task_logs(task_id: str, lines: int = 100):
    """
    Get logs for a specific task by task ID.
    This endpoint looks for logs across different log files based on the task type.
    """
    try:
        import os
        from datetime import datetime
        
        logs = []
        log_dir = "logs"
        today = datetime.now().strftime('%Y%m%d')
        
        # List of possible log files to check
        log_files = [
            f"indiamart_category_crawler_{today}.log",
            f"port_scraper_{today}.log",
            f"scraper_{today}.log",
            "celery.log",
            "worker.log"
        ]
        
        # Check each log file for the task_id
        for log_filename in log_files:
            log_file_path = os.path.join(log_dir, log_filename)
            if os.path.exists(log_file_path):
                try:
                    with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        all_lines = f.readlines()
                        # Filter lines that contain the task_id
                        task_lines = [line.strip() for line in all_lines if task_id in line]
                        if task_lines:
                            logs.extend(task_lines)
                except Exception as e:
                    logger.warning(f"Error reading log file {log_filename}: {e}")
                    continue
        
        # If no logs found in files, try to get task info from Celery
        if not logs:
            try:
                task_info = get_task_info(task_id)
                if task_info.get('traceback'):
                    logs.append(f"Task Error: {task_info.get('traceback')}")
                if task_info.get('result'):
                    logs.append(f"Task Result: {task_info.get('result')}")
                if task_info.get('status'):
                    logs.append(f"Task Status: {task_info.get('status')}")
            except:
                pass
        
        # Limit the number of lines returned
        if len(logs) > lines:
            logs = logs[-lines:]
        
        return {
            "status": "success",
            "logs": logs,
            "total_lines": len(logs),
            "task_id": task_id
        }
        
    except Exception as e:
        logger.error(f"Error getting task logs for {task_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting logs: {str(e)}")

@app.delete("/api/v1/task/{task_id}")
async def cancel_task(task_id: str):
    """Cancel a specific task"""
    try:
        import asyncio
        stopped = False
        
        # Try to gracefully stop port scrapers first
        try:
            from scrapers.port_scraper import StopPortScraperByTaskId, kill_chrome_processes
            if StopPortScraperByTaskId(task_id):
                logger.info(f"Sent stop signal to port scraper {task_id}")
                stopped = True
                await asyncio.sleep(1)
        except:
            pass
        
        # Try to stop Indiamart scrapers
        try:
            from scrapers.indiamart.indiamart_scraper import StopIndiamartProductScraperByTaskId
            if StopIndiamartProductScraperByTaskId(task_id):
                logger.info(f"Sent stop signal to Indiamart product scraper {task_id}")
                stopped = True
                await asyncio.sleep(1)
        except:
            pass
        
        try:
            from indiamart_category_crawler import StopIndiamartCategoryCrawlerByTaskId
            if StopIndiamartCategoryCrawlerByTaskId(task_id):
                logger.info(f"Sent stop signal to Indiamart category crawler {task_id}")
                stopped = True
                await asyncio.sleep(1)
        except:
            pass
        
        # Now revoke the Celery task
        celery_app.control.revoke(task_id, terminate=True)
        logger.info(f"Cancelled task: {task_id}")
        
        # Force kill any Chrome processes (for port scraper tasks)
        try:
            await asyncio.sleep(0.5)
            killed = kill_chrome_processes()
            if killed > 0:
                logger.info(f"Killed {killed} Chrome processes for task {task_id}")
        except:
            pass
        
        return {"message": f"Task {task_id} has been cancelled", "stopped_gracefully": stopped}
    except Exception as e:
        logger.error(f"Error cancelling task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/tasks/active")
async def get_active_tasks():
    try:
        inspect = celery_app.control.inspect()
        active_tasks = inspect.active()
        
        if not active_tasks:
            return {"active_tasks": {}, "total_active": 0}
        
        total_active = sum(len(tasks) for tasks in active_tasks.values())
        return {
            "active_tasks": active_tasks,
            "total_active": total_active
        }
    except Exception as e:
        logger.error(f"Error getting active tasks: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/tasks/stats")
async def get_task_stats():
    try:
        inspect = celery_app.control.inspect()
        stats = inspect.stats()
        return {"worker_stats": stats} if stats else {"worker_stats": {}}
    except Exception as e:
        logger.error(f"Error getting task stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/tasks/purge")
async def purge_all_tasks():
    try:
        result = celery_app.control.purge()
        logger.warning("Purged all pending tasks")
        return {"message": "All pending tasks have been purged", "purged_count": result}
    except Exception as e:
        logger.error(f"Error purging tasks: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/tasks/all")
async def get_all_tasks(limit: int = 100, offset: int = 0, status: str = None, source: str = None):
    """Get all tasks from SQLite databases with pagination and filtering"""
    logger.info(f"get_all_tasks called with: limit={limit}, offset={offset}, status={status}, source={source}")
    try:
        import sqlite3
        from pathlib import Path
        
        all_tasks = []
        task_creator_path = Path("shared/task_creator_utils/scrapped_data")
        
        # Database files mapping
        db_files = {
            'compare_market': 'compare_market_tasks.db',
            'competitors': 'competitors_tasks.db',
            'eximpedia': 'eximPedia_tasks.db',
            'full_tariff': 'full_tariff_tasks.db',
            'indian_trade_portal': 'indian_trade_portal_tasks.db',
            'macmap_product': 'macmap_product_tasks.db',
            'macmap_regulatory': 'macmap_regulatory_tasks.db',
            'macmap_tariff': 'macmap_tariff_tasks.db',
            'trademap': 'trademap_tasks.db',
            'trade_remedies': 'trade_remedies_tasks.db'
        }
        
        # Filter databases by source if specified
        logger.info(f"Before filtering - db_files keys: {list(db_files.keys())}")
        if source and source != 'all':
            logger.info(f"Filtering by source: '{source}'")
            if source in db_files:
                db_files = {source: db_files[source]}
                logger.info(f"After filtering - db_files: {db_files}")
            else:
                logger.warning(f"Source '{source}' not found in db_files. Available: {list(db_files.keys())}")
                db_files = {}
        else:
            logger.info(f"No source filter applied (source={source})")
        
        # Collect tasks from all databases
        for source_name, db_file in db_files.items():
            logger.info(f"Processing database: {source_name} -> {db_file}")
            db_path = task_creator_path / db_file
            if not db_path.exists():
                continue
                
            try:
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Check if tasks table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
                if not cursor.fetchone():
                    conn.close()
                    continue
                
                # Build query based on status filter
                query = "SELECT * FROM tasks"
                params = []
                
                if status:
                    if status.upper() == 'PENDING':
                        query += " WHERE status IN ('PENDING', 'RUNNING', 'RETRY') OR task_id = '' OR task_id IS NULL"
                    elif status.upper() in ['SUCCESS', 'FAILURE', 'REVOKED']:
                        query += " WHERE status = ?"
                        params.append(status.upper())
                
                query += " ORDER BY id DESC"
                
                cursor.execute(query, params)
                
                for row in cursor.fetchall():
                    task_dict = dict(row)
                    task_dict['source'] = source_name
                    task_dict['source_label'] = source_name.replace('_', ' ').title()
                    all_tasks.append(task_dict)
                
                conn.close()
                
            except Exception as e:
                logger.error(f"Error reading {source_name} database: {str(e)}")
                continue
        
        # Log collected tasks
        unique_sources = set(t.get('source') for t in all_tasks)
        logger.info(f"Collected {len(all_tasks)} tasks from sources: {unique_sources}")
        
        # Sort by created_at timestamp descending (most recent first), fallback to ID
        all_tasks.sort(key=lambda x: (x.get('created_at') or '', x.get('id', 0)), reverse=True)
        
        # Apply pagination
        paginated_tasks = all_tasks[offset:offset + limit]
        
        # Log paginated results
        paginated_sources = set(t.get('source') for t in paginated_tasks)
        logger.info(f"Returning {len(paginated_tasks)} tasks from sources: {paginated_sources}")
        
        # Get counts by status
        status_counts = {
            'pending': sum(1 for t in all_tasks if t.get('status') in ['PENDING', 'RUNNING', 'RETRY'] or not t.get('task_id')),
            'success': sum(1 for t in all_tasks if t.get('status') == 'SUCCESS'),
            'failure': sum(1 for t in all_tasks if t.get('status') == 'FAILURE'),
            'revoked': sum(1 for t in all_tasks if t.get('status') == 'REVOKED'),
            'total': len(all_tasks)
        }
        
        return {
            "success": True,
            "tasks": paginated_tasks,
            "total": len(all_tasks),
            "limit": limit,
            "offset": offset,
            "status_counts": status_counts
        }
        
    except Exception as e:
        logger.error(f"Error getting all tasks: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "timestamp": datetime.now().isoformat()}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "timestamp": datetime.now().isoformat()}
    )

def load_countries_data():
    try:
            
        return countries, imp_countries, exp_countries
    except Exception as e:
        logger.error(f"Error loading countries data: {str(e)}")
        return {}, [], []

# def match_hscodes(hsc):
#     lst = []
#     for h in hscodes:
#         if hsc in h['Code'] or h['Code'].startswith(hsc):
#             lst.append(h['Code'])
#     return lst

@app.get("/api/v1/hscodes")
async def get_hscodes():
    try:
        return hscodes
    except Exception as e:
        logger.error(f"Error serving HS codes: {str(e)}")
        raise HTTPException(status_code=500, detail="Error loading HS codes")

@app.get("/api/v1/hscodes/search")
async def search_hscodes(q: str = Query(..., min_length=2, description="Search query")):
    try:
        query = q.lower()
        filtered_codes = [
            code for code in hscodes 
            if query in code.get('Code', '').lower() or 
               query in code.get('Name', '').lower()
        ]
        
        return filtered_codes[:20]
    except Exception as e:
        logger.error(f"Error searching HS codes: {str(e)}")
        raise HTTPException(status_code=500, detail="Error searching HS codes")

@app.get("/home")
async def get_interface(request: Request):
    """Serve the main interface with countries and HS codes data"""
    try:
        countries_data, imp_countries_data, exp_countries_data = load_countries_data()
        return templates.TemplateResponse("home.html", {
            "request": request,
            "countries": json.dumps(countries_data),
            "imp_countries": json.dumps(imp_countries_data),
            "exp_countries": json.dumps(exp_countries_data),
            "hscodes": json.dumps(hscodes)
        })
    except Exception as e:
        logger.error(f"Error serving home interface: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error serving interface: {str(e)}")

@app.get("/payload")
async def get_payload_dashboard(request: Request):
    """Serve the payload generator dashboard"""
    try:
        return templates.TemplateResponse("payload.html", {
            "request": request,
        })
    except Exception as e:
        logger.error(f"Error serving payload dashboard: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error serving payload dashboard: {str(e)}")

@app.get("/dashboard")
async def get_analytics_dashboard(request: Request):
    """Serve the analytics dashboard"""
    try:
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
        })
    except Exception as e:
        logger.error(f"Error serving analytics dashboard: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error serving analytics dashboard: {str(e)}")

@app.get("/task-manager")
async def get_task_manager(request: Request):
    """Serve the task manager dashboard"""
    try:
        return templates.TemplateResponse("task_manager.html", {
            "request": request,
        })
    except Exception as e:
        logger.error(f"Error serving task manager: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error serving task manager: {str(e)}")

@app.get("/indiamart-scraper")
async def get_indiamart_scraper(request: Request):
    """Serve the IndiaMART scraper dashboard"""
    try:
        return templates.TemplateResponse("indiamart_scraper.html", {
            "request": request,
        })
    except Exception as e:
        logger.error(f"Error serving IndiaMART scraper dashboard: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error serving IndiaMART scraper dashboard: {str(e)}")

@app.get("/task-queue")
async def get_task_queue(request: Request):
    """Serve the task queue page"""
    try:
        return templates.TemplateResponse("task_queue.html", {
            "request": request,
        })
    except Exception as e:
        logger.error(f"Error serving task queue: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error serving task queue: {str(e)}")

@app.get("/health-dashboard")
async def get_system_health_dashboard(request: Request):
    """Serve the system health monitoring dashboard"""
    try:
        return templates.TemplateResponse("health.html", {
            "request": request,
        })
    except Exception as e:
        logger.error(f"Error serving system health dashboard: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error serving system health dashboard: {str(e)}")

@app.get("/workers")
async def get_workers_dashboard(request: Request):
    """Serve the workers management dashboard"""
    try:
        return templates.TemplateResponse("workers.html", {
            "request": request,
        })
    except Exception as e:
        logger.error(f"Error serving workers dashboard: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error serving workers dashboard: {str(e)}")

@app.get("/logs")
async def get_logs_dashboard(request: Request):
    """Serve the real-time logs dashboard"""
    try:
        return templates.TemplateResponse("logs.html", {
            "request": request,
        })
    except Exception as e:
        logger.error(f"Error serving logs dashboard: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error serving logs dashboard: {str(e)}")

@app.get("/data-sources")
async def get_data_sources_dashboard(request: Request):
    """Serve the data sources management dashboard"""
    try:
        return templates.TemplateResponse("data_sources.html", {
            "request": request,
        })
    except Exception as e:
        logger.error(f"Error serving data sources dashboard: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error serving data sources dashboard: {str(e)}")

@app.get("/api/v1/dashboard/stats")
async def get_dashboard_stats():
    """Get comprehensive dashboard statistics"""
    try:
        import sqlite3
        from pathlib import Path
        import json
        from datetime import datetime, timedelta
        
        logger.info("Dashboard stats API called")
        
        # Database paths - matching exactly with payload creators
        db_paths = {
            'comparemarket': Path("shared/task_creator_utils/scrapped_data/compare_market_tasks.db"),
            'competitors': Path("shared/task_creator_utils/scrapped_data/competitors_tasks.db"),
            'fulltariff': Path("shared/task_creator_utils/scrapped_data/full_tariff_tasks.db"),
            'indiantradeportal': Path("shared/task_creator_utils/scrapped_data/indian_trade_portal_tasks.db"),
            'macmapproduct': Path("shared/task_creator_utils/scrapped_data/macmap_product_tasks.db"),
            # Optional databases (may not exist yet)
            'macmapregulatory': Path("shared/task_creator_utils/scrapped_data/macmap_regulatory_tasks.db"),
            'macmaptariff': Path("shared/task_creator_utils/scrapped_data/macmap_tariff_tasks.db"),
            'traderemedies': Path("shared/task_creator_utils/scrapped_data/trade_remedies_tasks.db"),
            'trademap': Path("shared/task_creator_utils/scrapped_data/trademap_tasks.db"),
            'eximpedia': Path("shared/task_creator_utils/scrapped_data/eximPedia_tasks.db")
        }
        
        logger.info(f"Checking databases in: {Path('shared/task_creator_utils/scrapped_data').absolute()}")
        
        scrapers_data = []
        total_tasks = 0
        total_success = 0
        total_failed = 0
        total_pending = 0
        
        for scraper_name, db_path in db_paths.items():
            logger.info(f"Processing {scraper_name}: {db_path} (exists: {db_path.exists()})")
            
            if db_path.exists():
                try:
                    conn = sqlite3.connect(db_path)
                    
                    # Check if tasks table exists
                    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
                    if not cursor.fetchone():
                        logger.warning(f"No 'tasks' table found in {scraper_name} database")
                        conn.close()
                        scrapers_data.append({
                            'name': scraper_name,
                            'total_tasks': 0,
                            'success_tasks': 0,
                            'failed_tasks': 0,
                            'pending_tasks': 0,
                            'success_rate': 0,
                            'status': 'no_table',
                            'last_updated': datetime.now().isoformat()
                        })
                        continue
                    
                    # Get basic stats
                    cursor = conn.execute("SELECT COUNT(*) FROM tasks")
                    scraper_total = cursor.fetchone()[0]
                    logger.info(f"{scraper_name}: {scraper_total} total tasks")
                    
                    cursor = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'SUCCESS'")
                    scraper_success = cursor.fetchone()[0]
                    
                    cursor = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'FAILED'")
                    scraper_failed = cursor.fetchone()[0]
                    
                    cursor = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'PENDING' OR status = '' OR task_id = ''")
                    scraper_pending = cursor.fetchone()[0]
                    
                    # Get last updated time (fallback if column doesn't exist)
                    try:
                        cursor = conn.execute("SELECT MAX(updated_at) FROM tasks")
                        last_updated = cursor.fetchone()[0] or datetime.now().isoformat()
                    except sqlite3.OperationalError:
                        # Fallback if updated_at column doesn't exist
                        try:
                            cursor = conn.execute("SELECT MAX(created_at) FROM tasks")
                            last_updated = cursor.fetchone()[0] or datetime.now().isoformat()
                        except sqlite3.OperationalError:
                            last_updated = datetime.now().isoformat()
                    
                    success_rate = (scraper_success / scraper_total * 100) if scraper_total > 0 else 0
                    
                    scrapers_data.append({
                        'name': scraper_name,
                        'total_tasks': scraper_total,
                        'success_tasks': scraper_success,
                        'failed_tasks': scraper_failed,
                        'pending_tasks': scraper_pending,
                        'success_rate': round(success_rate, 1),
                        'status': 'active' if scraper_pending > 0 else ('idle' if scraper_total > 0 else 'empty'),
                        'last_updated': last_updated
                    })
                    
                    total_tasks += scraper_total
                    total_success += scraper_success
                    total_failed += scraper_failed
                    total_pending += scraper_pending
                    
                    conn.close()
                    
                except Exception as e:
                    logger.error(f"Error reading {scraper_name} database: {e}")
                    scrapers_data.append({
                        'name': scraper_name,
                        'total_tasks': 0,
                        'success_tasks': 0,
                        'failed_tasks': 0,
                        'pending_tasks': 0,
                        'success_rate': 0,
                        'status': 'error',
                        'last_updated': datetime.now().isoformat()
                    })
            else:
                logger.info(f"Database does not exist: {db_path}")
                # Database doesn't exist yet
                scrapers_data.append({
                    'name': scraper_name,
                    'total_tasks': 0,
                    'success_tasks': 0,
                    'failed_tasks': 0,
                    'pending_tasks': 0,
                    'success_rate': 0,
                    'status': 'inactive',
                    'last_updated': datetime.now().isoformat()
                })
        
        # Calculate overall success rate
        overall_success_rate = (total_success / total_tasks * 100) if total_tasks > 0 else 0
        active_scrapers = len([s for s in scrapers_data if s['status'] == 'active'])
        
        # Generate recent tasks (from actual data where possible)
        recent_tasks = []
        task_count = 0
        for scraper_name, db_path in db_paths.items():
            if db_path.exists() and task_count < 10:
                try:
                    conn = sqlite3.connect(db_path)
                    # Check if required columns exist
                    try:
                        cursor = conn.execute("""
                            SELECT payload_json, status, created_at, updated_at 
                            FROM tasks 
                            ORDER BY created_at DESC 
                            LIMIT ?
                        """, (10 - task_count,))
                    except sqlite3.OperationalError:
                        # Fallback query if some columns don't exist
                        try:
                            cursor = conn.execute("""
                                SELECT payload_json, status, created_at, created_at 
                                FROM tasks 
                                ORDER BY created_at DESC 
                                LIMIT ?
                            """, (10 - task_count,))
                        except sqlite3.OperationalError:
                            # Final fallback with minimal columns
                            cursor = conn.execute("""
                                SELECT payload_json, status, '', '' 
                                FROM tasks 
                                ORDER BY id DESC 
                                LIMIT ?
                            """, (10 - task_count,))
                    
                    rows = cursor.fetchall()
                    for row in rows:
                        try:
                            payload = json.loads(row[0]) if row[0] else {}
                            recent_tasks.append({
                                'id': f'task_{len(recent_tasks)}',
                                'scraper': scraper_name,
                                'status': row[1] or 'PENDING',
                                'created_at': row[2] or datetime.now().isoformat(),
                                'country': payload.get('country', payload.get('countries', 'Unknown')),
                                'hscode': payload.get('hsc', payload.get('hscode', 'Unknown'))
                            })
                            task_count += 1
                            if task_count >= 10:
                                break
                        except:
                            continue
                    
                    conn.close()
                except:
                    continue
        
        # Sort recent tasks by creation time
        recent_tasks.sort(key=lambda x: x['created_at'], reverse=True)
        
        return {
            'overview': {
                'total_tasks': total_tasks,
                'success_rate': round(overall_success_rate, 1),
                'active_scrapers': active_scrapers,
                'failed_tasks': total_failed
            },
            'scrapers': scrapers_data,
            'status_distribution': {
                'success': total_success,
                'pending': total_pending,
                'failed': total_failed,
                'retry': max(0, int(total_failed * 0.1))  # Estimate retry tasks
            },
            'recent_tasks': recent_tasks,
            'system_health': get_real_system_health()
        }
        
    except Exception as e:
        logger.error(f"Error getting dashboard stats: {e}")
        return JSONResponse(
            status_code=500,
            content={'error': 'Failed to retrieve dashboard statistics', 'detail': str(e)}
        )

@app.post("/api/v1/payload/generate")
async def generate_payload(request: PayloadGenerationRequest):
    """Generate payloads based on the selected type and configuration"""
    try:
        # Use the payload service to generate payloads
        result = payload_service.generate_payload(request.payload_type, request.config)
        
        if result["success"]:
            return {
                "success": True,
                "message": "Payload generation completed",
                "tasksCreated": result.get("tasksCreated", result.get("count", 0)),
                "payloadType": request.payload_type
            }
        else:
            return {
                "success": False,
                "message": result["message"]
            }
        
    except Exception as e:
        logger.error(f"Error starting payload generation: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to start payload generation: {str(e)}"
        }

@app.get("/api/v1/payload/stats")
async def get_payload_stats():
    """Get payload generation statistics"""
    try:
        # Use the payload service to get stats
        stats = payload_service.get_payload_statistics()
        return stats
        
    except Exception as e:
        logger.error(f"Error getting payload stats: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to get stats: {str(e)}"
        }

@app.get("/api/v1/payload/debug/{scraper_name}")
async def get_payload_debug(scraper_name: str):
    """Debug endpoint to check MongoDB indexes and document counts"""
    try:
        from shared.task_creator_utils.mongodb_base import get_database
        db = get_database()
        collection = db["scraper_tasks"]
        
        # Get indexes
        indexes = collection.index_information()
        
        # Get document count for this scraper
        count = collection.count_documents({"scraper": scraper_name})
        
        # Get sample documents
        samples = list(collection.find({"scraper": scraper_name}).limit(3))
        for s in samples:
            s["_id"] = str(s["_id"])
            if "created_at" in s:
                s["created_at"] = str(s["created_at"])
            if "updated_at" in s:
                s["updated_at"] = str(s["updated_at"])
        
        return {
            "success": True,
            "scraper": scraper_name,
            "document_count": count,
            "indexes": {k: {"key": v.get("key"), "unique": v.get("unique", False)} for k, v in indexes.items()},
            "sample_documents": samples
        }
    except Exception as e:
        logger.error(f"Error in debug endpoint: {str(e)}")
        return {
            "success": False,
            "message": str(e)
        }

@app.post("/api/v1/payload/fix-index/{scraper_name}")
async def fix_payload_index(scraper_name: str):
    """Drop and recreate the unique index for a scraper"""
    try:
        from shared.task_creator_utils.mongodb_base import get_database
        db = get_database()
        collection = db["scraper_tasks"]
        
        index_name = f"idx_unique_{scraper_name.lower().replace(' ', '_')}"
        
        # Try to drop existing index
        dropped = False
        try:
            collection.drop_index(index_name)
            dropped = True
        except Exception as e:
            pass
        
        # Define unique fields based on scraper
        unique_fields_map = {
            "MacMapRegulatory": ["country1", "country2", "hsc", "regtype"],
            "MacMapTariff": ["country", "hsc", "year"],
            "TradeRemedies": ["country", "hsc", "year"],
            "IndianTradePortal": ["hscode"],
            "CompareMarket": ["country", "hsc"],
            "Competitors": ["country", "hsc"],
        }
        
        unique_fields = unique_fields_map.get(scraper_name, [])
        if not unique_fields:
            return {"success": False, "message": f"Unknown scraper: {scraper_name}"}
        
        # Create new index
        from pymongo import ASCENDING
        index_fields = [("scraper", ASCENDING)] + [(f"payload.{field}", ASCENDING) for field in unique_fields]
        
        collection.create_index(
            index_fields,
            unique=True,
            name=index_name,
            partialFilterExpression={"scraper": scraper_name}
        )
        
        return {
            "success": True,
            "message": f"Index {'dropped and ' if dropped else ''}recreated for {scraper_name}",
            "index_name": index_name,
            "fields": [f[0] for f in index_fields]
        }
    except Exception as e:
        logger.error(f"Error fixing index: {str(e)}")
        return {"success": False, "message": str(e)}

@app.get("/api/v1/payload/creators")
async def get_payload_creators():
    """Get available payload creators"""
    try:
        creators = payload_service.get_available_creators()
        return {
            "success": True,
            "creators": creators
        }
    except Exception as e:
        logger.error(f"Error getting payload creators: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to get creators: {str(e)}"
        }

# Task Manager API Endpoints
@app.get("/api/task-manager/status")
async def get_task_manager_status():
    """Get status of all task creators"""
    try:
        return {
            "success": True,
            "data": {
                "creators": task_manager.get_status(),
                "system": task_manager.get_system_stats()
            }
        }
    except Exception as e:
        logger.error(f"Error getting task manager status: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to get status: {str(e)}"
        }

@app.post("/api/task-manager/start/{creator_id}")
async def start_task_creator(creator_id: str):
    """Start a task creator"""
    try:
        success, message = task_manager.start_task_creator(creator_id)
        return {
            "success": success,
            "message": message
        }
    except Exception as e:
        logger.error(f"Error starting task creator {creator_id}: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to start: {str(e)}"
        }

@app.post("/api/task-manager/stop/{creator_id}")
async def stop_task_creator(creator_id: str):
    """Stop a task creator"""
    try:
        # Special handling for port scraper to cancel its Celery tasks
        if creator_id == 'portscraper':
            # Try to load and cancel the active port scraper task
            task_id_file = "shared/task_creator_utils/port_scraper_current_task.json"
            if os.path.exists(task_id_file):
                try:
                    import json
                    from scrapers.port_scraper import StopPortScraperByTaskId, kill_chrome_processes
                    import asyncio
                    
                    with open(task_id_file, 'r') as f:
                        data = json.load(f)
                        task_id = data.get('task_id')
                        if task_id:
                            logger.info(f"Cancelling active port scraper Celery task: {task_id}")
                            # Cancel the Celery task
                            StopPortScraperByTaskId(task_id)
                            await asyncio.sleep(1)
                            celery_app.control.revoke(task_id, terminate=True)
                            logger.info(f"Port scraper task {task_id} cancelled")
                            
                            # Force kill Chrome processes
                            await asyncio.sleep(0.5)
                            killed = kill_chrome_processes()
                            if killed > 0:
                                logger.info(f"Killed {killed} Chrome processes")
                except Exception as e:
                    logger.error(f"Error cancelling port scraper task: {e}")
        
        # Now stop the task creator process
        success, message = task_manager.stop_task_creator(creator_id)
        return {
            "success": success,
            "message": message
        }
    except Exception as e:
        logger.error(f"Error stopping task creator {creator_id}: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to stop: {str(e)}"
        }

class TaskLimitRequest(BaseModel):
    limit: int = Field(..., ge=1, le=1000, description="Task limit between 1 and 1000")

class WorkerStartRequest(BaseModel):
    name: str = Field(..., description="Worker name/hostname")
    concurrency: int = Field(80, ge=1, le=200, description="Number of concurrent processes")
    queues: str = Field("heavy,default", description="Comma-separated list of queues")
    loglevel: str = Field("info", description="Log level (debug, info, warning, error)")

@app.post("/api/task-manager/limit/{creator_id}")
async def set_task_limit(creator_id: str, request: TaskLimitRequest):
    """Set task limit for a creator"""
    try:
        success, message = task_manager.set_task_limit(creator_id, request.limit)
        return {
            "success": success,
            "message": message
        }
    except Exception as e:
        logger.error(f"Error setting task limit for {creator_id}: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to set limit: {str(e)}"
        }

@app.post("/api/task-manager/start-all")
async def start_all_task_creators():
    """Start all task creators"""
    try:
        results = []
        for creator_id in task_manager.task_creators.keys():
            success, message = task_manager.start_task_creator(creator_id)
            results.append({'creator': creator_id, 'success': success, 'message': message})
        
        return {
            "success": True,
            "results": results
        }
    except Exception as e:
        logger.error(f"Error starting all task creators: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to start all: {str(e)}"
        }

@app.post("/api/task-manager/stop-all")
async def stop_all_task_creators():
    """Stop all task creators"""
    try:
        results = []
        for creator_id in task_manager.task_creators.keys():
            success, message = task_manager.stop_task_creator(creator_id)
            results.append({'creator': creator_id, 'success': success, 'message': message})
        
        return {
            "success": True,
            "results": results
        }
    except Exception as e:
        logger.error(f"Error stopping all task creators: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to stop all: {str(e)}"
        }

# Worker Concurrency Management API Endpoints
@app.post("/api/task-manager/concurrency/{creator_id}")
async def set_worker_concurrency(creator_id: str, request: TaskLimitRequest):
    """Set worker concurrency for a specific scraper"""
    try:
        success, message = task_manager.set_worker_concurrency(creator_id, request.limit)
        return {
            "success": success,
            "message": message
        }
    except Exception as e:
        logger.error(f"Error setting worker concurrency for {creator_id}: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to set worker concurrency: {str(e)}"
        }

@app.get("/api/task-manager/worker-status/{creator_id}")
async def get_worker_status(creator_id: str):
    """Get detailed worker status for a specific scraper"""
    try:
        if creator_id not in task_manager.task_creators:
            return {
                "success": False,
                "message": f"Scraper {creator_id} not found"
            }
        
        creator = task_manager.task_creators[creator_id]
        
        # Get worker process stats if running
        worker_stats = {
            "worker_status": creator['worker_status'],
            "worker_concurrency": creator['worker_concurrency'],
            "worker_queue": creator['queue_name'],
            "worker_pid": None,
            "worker_cpu_usage": 0,
            "worker_memory_usage": 0
        }
        
        if creator['worker_status'] == 'running' and creator['worker_process'] and creator['worker_process'].poll() is None:
            try:
                worker_proc = psutil.Process(creator['worker_process'].pid)
                worker_stats['worker_pid'] = creator['worker_process'].pid
                worker_stats['worker_cpu_usage'] = worker_proc.cpu_percent()
                worker_stats['worker_memory_usage'] = worker_proc.memory_info().rss / 1024 / 1024  # MB
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                worker_stats['worker_status'] = 'stopped'
        
        return {
            "success": True,
            "data": worker_stats
        }
    except Exception as e:
        logger.error(f"Error getting worker status for {creator_id}: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to get worker status: {str(e)}"
        }

# Worker Management API Endpoints
@app.get("/api/v1/workers/status")
async def get_workers_status():
    """Get status of all Celery workers"""
    try:
        inspect = celery_app.control.inspect()
        
        # Get basic worker info
        stats = inspect.stats()
        active_tasks = inspect.active()
        
        workers_data = {}
        
        if stats:
            for worker_name, worker_stats in stats.items():
                # Get active tasks count for this worker
                active_count = len(active_tasks.get(worker_name, [])) if active_tasks else 0
                
                # Get total tasks processed (simplified)
                total_tasks = 0
                try:
                    if 'total' in worker_stats and isinstance(worker_stats['total'], dict):
                        for task_name, count in worker_stats['total'].items():
                            if isinstance(count, (int, float)):
                                total_tasks += count
                except Exception:
                    total_tasks = 0
                
                # Get concurrency
                concurrency = 'N/A'
                try:
                    if 'pool' in worker_stats and 'max-concurrency' in worker_stats['pool']:
                        concurrency = worker_stats['pool']['max-concurrency']
                except Exception:
                    pass
                
                # Get load average (simplified)
                load_avg = '0.00'
                try:
                    if 'rusage' in worker_stats and 'utime' in worker_stats['rusage']:
                        load_avg = f"{worker_stats['rusage']['utime']:.2f}"
                except Exception:
                    pass
                
                # Parse queues from worker stats
                queues_list = ['default']
                try:
                    if 'pool' in worker_stats and 'queues' in worker_stats['pool']:
                        queues_list = worker_stats['pool']['queues']
                except Exception:
                    pass
                
                workers_data[worker_name] = {
                    'name': worker_name,
                    'status': 'online',
                    'activeTasks': active_count,
                    'totalTasks': total_tasks,
                    'loadAverage': load_avg,
                    'queues': queues_list,
                    'concurrency': concurrency,
                    'clock': str(worker_stats.get('clock', 'N/A'))
                }
        
        return {
            "success": True,
            "data": workers_data
        }
        
    except Exception as e:
        logger.error(f"Error getting workers status: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to get workers status: {str(e)}",
            "data": {}
        }

@app.post("/api/v1/workers/start")
async def start_worker(request: WorkerStartRequest):
    """Start a new Celery worker"""
    try:
        import subprocess
        import os
        
        # Build the celery command
        cmd = [
            "celery", "-A", "celery_app.tasks", "worker",
            "--loglevel", request.loglevel,
            "--concurrency", str(request.concurrency),
            "-Q", request.queues,
            "--hostname", request.name
        ]
        
        # Start the worker process in the background
        process = subprocess.Popen(
            cmd,
            cwd=os.getcwd(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True
        )
        
        logger.info(f"Started worker {request.name} with PID {process.pid}")
        
        return {
            "success": True,
            "message": f"Worker {request.name} started successfully",
            "pid": process.pid
        }
        
    except Exception as e:
        logger.error(f"Error starting worker: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to start worker: {str(e)}"
        }

@app.post("/api/v1/workers/{worker_name}/shutdown")
async def shutdown_worker(worker_name: str):
    """Shutdown a specific worker"""
    try:
        # Send shutdown command to specific worker
        celery_app.control.broadcast('shutdown', destination=[worker_name])
        
        logger.info(f"Sent shutdown command to worker: {worker_name}")
        
        return {
            "success": True,
            "message": f"Shutdown command sent to worker {worker_name}"
        }
        
    except Exception as e:
        logger.error(f"Error shutting down worker {worker_name}: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to shutdown worker: {str(e)}"
        }

@app.post("/api/v1/workers/{worker_name}/restart")
async def restart_worker(worker_name: str):
    """Restart a specific worker"""
    try:
        # Send pool restart command to specific worker
        celery_app.control.broadcast('pool_restart', destination=[worker_name])
        
        logger.info(f"Sent restart command to worker: {worker_name}")
        
        return {
            "success": True,
            "message": f"Restart command sent to worker {worker_name}"
        }
        
    except Exception as e:
        logger.error(f"Error restarting worker {worker_name}: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to restart worker: {str(e)}"
        }

# Dedicated Worker Management API Endpoints
@app.get("/api/v1/workers/dedicated/status")
async def get_dedicated_workers_status():
    """Get status of all dedicated workers"""
    if not WORKER_MANAGER_AVAILABLE:
        return {
            "success": False,
            "message": "Worker manager not available"
        }
    
    try:
        status = worker_manager.get_worker_status()
        return {
            "success": True,
            "data": status
        }
    except Exception as e:
        logger.error(f"Error getting worker status: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to get worker status: {str(e)}"
        }

@app.post("/api/v1/workers/dedicated/start/{worker_name}")
async def start_dedicated_worker(worker_name: str):
    """Start a specific dedicated worker"""
    if not WORKER_MANAGER_AVAILABLE:
        return {
            "success": False,
            "message": "Worker manager not available"
        }
    
    try:
        success, message = worker_manager.start_worker(worker_name)
        return {
            "success": success,
            "message": message
        }
    except Exception as e:
        logger.error(f"Error starting worker {worker_name}: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to start worker: {str(e)}"
        }

@app.post("/api/v1/workers/dedicated/stop/{worker_name}")
async def stop_dedicated_worker(worker_name: str):
    """Stop a specific dedicated worker"""
    if not WORKER_MANAGER_AVAILABLE:
        return {
            "success": False,
            "message": "Worker manager not available"
        }
    
    try:
        success, message = worker_manager.stop_worker(worker_name)
        return {
            "success": success,
            "message": message
        }
    except Exception as e:
        logger.error(f"Error stopping worker {worker_name}: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to stop worker: {str(e)}"
        }

@app.post("/api/v1/workers/dedicated/restart/{worker_name}")
async def restart_dedicated_worker(worker_name: str):
    """Restart a specific dedicated worker"""
    if not WORKER_MANAGER_AVAILABLE:
        return {
            "success": False,
            "message": "Worker manager not available"
        }
    
    try:
        # Stop then start
        stop_success, stop_msg = worker_manager.stop_worker(worker_name)
        if stop_success:
            await asyncio.sleep(2)  # Wait for graceful shutdown
            start_success, start_msg = worker_manager.start_worker(worker_name)
            return {
                "success": start_success,
                "message": f"Restart completed: {start_msg}"
            }
        else:
            return {
                "success": False,
                "message": f"Failed to stop worker for restart: {stop_msg}"
            }
    except Exception as e:
        logger.error(f"Error restarting worker {worker_name}: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to restart worker: {str(e)}"
        }

@app.post("/api/v1/workers/dedicated/start-all")
async def start_all_dedicated_workers():
    """Start all configured dedicated workers"""
    if not WORKER_MANAGER_AVAILABLE:
        return {
            "success": False,
            "message": "Worker manager not available"
        }
    
    try:
        results = worker_manager.start_all_workers()
        success_count = sum(1 for success, _ in results.values() if success)
        total_count = len(results)
        
        return {
            "success": success_count > 0,
            "message": f"Started {success_count}/{total_count} workers",
            "results": {worker: {"success": success, "message": msg} 
                       for worker, (success, msg) in results.items()}
        }
    except Exception as e:
        logger.error(f"Error starting all workers: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to start workers: {str(e)}"
        }

@app.post("/api/v1/workers/dedicated/stop-all")
async def stop_all_dedicated_workers():
    """Stop all active dedicated workers"""
    if not WORKER_MANAGER_AVAILABLE:
        return {
            "success": False,
            "message": "Worker manager not available"
        }
    
    try:
        results = worker_manager.stop_all_workers()
        success_count = sum(1 for success, _ in results.values() if success)
        total_count = len(results)
        
        return {
            "success": success_count > 0,
            "message": f"Stopped {success_count}/{total_count} workers",
            "results": {worker: {"success": success, "message": msg} 
                       for worker, (success, msg) in results.items()}
        }
    except Exception as e:
        logger.error(f"Error stopping all workers: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to stop workers: {str(e)}"
        }

@app.post("/api/v1/workers/dedicated/assign")
async def assign_scraper_to_worker(request: WorkerAssignmentRequest):
    """Assign a scraper to a specific dedicated worker"""
    if not WORKER_MANAGER_AVAILABLE:
        return {
            "success": False,
            "message": "Worker manager not available"
        }
    
    try:
        success, message = worker_manager.assign_scraper_to_worker(
            request.scraper_id, 
            request.worker_name
        )
        return {
            "success": success,
            "message": message
        }
    except Exception as e:
        logger.error(f"Error assigning scraper to worker: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to assign scraper: {str(e)}"
        }

@app.get("/api/v1/workers/dedicated/scrapers")
async def get_scraper_mappings():
    """Get available scraper-to-queue mappings"""
    if not WORKER_MANAGER_AVAILABLE:
        return {
            "success": False,
            "message": "Worker manager not available"
        }
    
    try:
        from worker_manager import DEFAULT_SCRAPER_QUEUES
        return {
            "success": True,
            "data": {
                "scraper_mappings": DEFAULT_SCRAPER_QUEUES,
                "available_scrapers": list(DEFAULT_SCRAPER_QUEUES.keys())
            }
        }
    except Exception as e:
        logger.error(f"Error getting scraper mappings: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to get scraper mappings: {str(e)}"
        }

# Database Backup API Endpoints - REMOVED (not needed)

# Google Drive Backup API Endpoints
@app.post("/api/v1/backup/gdrive/upload/{backup_filename}")
async def upload_backup_to_gdrive(backup_filename: str, backup_type: str = "manual"):
    """Upload a specific backup file to Google Drive"""
    if not GOOGLE_DRIVE_AVAILABLE:
        return {
            "success": False,
            "message": "Google Drive service not available. Please check configuration."
        }
    
    try:
        backup_path = Path("backups") / backup_filename
        if not backup_path.exists():
            return {
                "success": False,
                "message": f"Backup file not found: {backup_filename}"
            }
        
        # Extract database name from filename
        db_name = backup_filename.split('_')[0] if '_' in backup_filename else None
        
        result = google_drive_service.upload_backup(backup_path, backup_type, db_name)
        return result
        
    except Exception as e:
        logger.error(f"Error uploading backup to Google Drive: {str(e)}")
        return {
            "success": False,
            "message": f"Upload failed: {str(e)}"
        }

@app.get("/api/v1/backup/gdrive/list")
async def list_gdrive_backups(backup_type: str = None):
    """List backups stored in Google Drive"""
    if not GOOGLE_DRIVE_AVAILABLE:
        return {
            "success": False,
            "message": "Google Drive service not available"
        }
    
    try:
        backups = google_drive_service.list_backups(backup_type)
        return {
            "success": True,
            "backups": backups,
            "count": len(backups)
        }
    except Exception as e:
        logger.error(f"Error listing Google Drive backups: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to list backups: {str(e)}"
        }

@app.get("/api/v1/backup/gdrive/storage-info")
async def get_gdrive_storage_info():
    """Get Google Drive storage information"""
    if not GOOGLE_DRIVE_AVAILABLE:
        return {
            "success": False,
            "message": "Google Drive service not available"
        }
    
    try:
        storage_info = google_drive_service.get_storage_info()
        return storage_info
    except Exception as e:
        logger.error(f"Error getting Google Drive storage info: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to get storage info: {str(e)}"
        }

@app.delete("/api/v1/backup/gdrive/{file_id}")
async def delete_gdrive_backup(file_id: str):
    """Delete a backup from Google Drive"""
    if not GOOGLE_DRIVE_AVAILABLE:
        return {
            "success": False,
            "message": "Google Drive service not available"
        }
    
    try:
        result = google_drive_service.delete_backup(file_id)
        return result
    except Exception as e:
        logger.error(f"Error deleting Google Drive backup: {str(e)}")
        return {
            "success": False,
            "message": f"Delete failed: {str(e)}"
        }

@app.post("/api/v1/backup/gdrive/cleanup")
async def cleanup_old_gdrive_backups(keep_days: int = 30):
    """Clean up old backups from Google Drive"""
    if not GOOGLE_DRIVE_AVAILABLE:
        return {
            "success": False,
            "message": "Google Drive service not available"
        }
    
    try:
        result = google_drive_service.cleanup_old_backups(keep_days)
        return result
    except Exception as e:
        logger.error(f"Error cleaning up Google Drive backups: {str(e)}")
        return {
            "success": False,
            "message": f"Cleanup failed: {str(e)}"
        }

@app.get("/api/v1/backup/gdrive/status")
async def get_gdrive_service_status():
    """Get Google Drive service status"""
    try:
        status = {
            "available": GOOGLE_DRIVE_AVAILABLE,
            "enabled": google_drive_service.enabled if GOOGLE_DRIVE_AVAILABLE else False,
            "authenticated": False,
            "message": "Google Drive service not available"
        }
        
        if GOOGLE_DRIVE_AVAILABLE and google_drive_service:
            status.update({
                "enabled": google_drive_service.enabled,
                "authenticated": google_drive_service.service is not None,
                "message": "Google Drive service ready" if google_drive_service.enabled else "Google Drive service disabled or not configured"
            })
        
        return {
            "success": True,
            "status": status
        }
    except Exception as e:
        logger.error(f"Error getting Google Drive status: {str(e)}")
        return {
            "success": False,
            "message": f"Status check failed: {str(e)}"
        }

@app.post("/api/v1/admin/cleanup-selenium")
async def cleanup_selenium_instances():
    """Force cleanup of orphaned Selenium instances and temp files"""
    try:
        cleanup_stats = {
            "killed_processes": 0,
            "cleaned_temp_dirs": 0,
            "memory_freed_mb": 0,
            "errors": []
        }
        
        memory_before = psutil.virtual_memory().used
        
        selenium_processes = ['chrome', 'chromedriver', 'chromium', 'geckodriver', 'firefox']
        
        for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
            try:
                if proc.info['name'] and any(name in proc.info['name'].lower() for name in selenium_processes):
                    if is_orphaned(proc):
                        proc_memory = proc.info['memory_info'].rss / 1024 / 1024  # MB
                        proc.terminate()
                        cleanup_stats["killed_processes"] += 1
                        cleanup_stats["memory_freed_mb"] += proc_memory
                        logger.info(f"Killed orphaned process: {proc.info['name']} (PID: {proc.info['pid']})")
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
                cleanup_stats["errors"].append(f"Process error: {str(e)}")
                continue
        
        # Clean up temporary directories
        temp_dirs_cleaned = cleanup_temp_dirs()
        cleanup_stats["cleaned_temp_dirs"] = temp_dirs_cleaned
        
        # Force garbage collection
        gc.collect()
        
        # Calculate actual memory freed
        memory_after = psutil.virtual_memory().used
        actual_memory_freed = (memory_before - memory_after) / 1024 / 1024  # MB
        cleanup_stats["memory_freed_mb"] = round(actual_memory_freed, 2)
        
        logger.info(f"Selenium cleanup completed: {cleanup_stats}")
        
        return {
            "status": "success", 
            "cleanup_stats": cleanup_stats,
            "message": f"Cleaned {cleanup_stats['killed_processes']} processes, {cleanup_stats['cleaned_temp_dirs']} temp dirs"
        }
        
    except Exception as e:
        logger.error(f"Selenium cleanup failed: {str(e)}")
        return {"status": "error", "message": str(e)}

def is_orphaned(process) -> bool:
    try:
        parent = process.parent()
        if parent is None:
            return True  
            
        if 'python' in parent.name().lower():
            return False  
        legitimate_parents = ['systemd', 'init', 'launchd', 'explorer.exe', 'winlogon.exe']
        if parent.name().lower() in legitimate_parents:
            return True  
            
        if parent.status() == psutil.STATUS_ZOMBIE:
            return True  
        return False  
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return True  

def cleanup_temp_dirs() -> int:
    """Clean up Selenium temporary directories"""
    cleaned_count = 0
    
    temp_patterns = [
        'scoped_dir*',
        'chrome_*',
        'selenium_*',
        '.org.chromium.*',
        'webdriver_*',
        'tmp*chromedriver*',
        'chrome-data_*'
        'downloaded_files',
    ]
    
    try:
        temp_dir = Path(tempfile.gettempdir())
        
        for pattern in temp_patterns:
            for temp_path in temp_dir.glob(pattern):
                try:
                    if temp_path.is_dir():
                        if is_old_temp_dir(temp_path):
                            shutil.rmtree(temp_path)
                            cleaned_count += 1
                            logger.debug(f"Removed temp directory: {temp_path}")
                except (OSError, PermissionError) as e:
                    logger.warning(f"Could not remove {temp_path}: {e}")
        
        user_data_dirs = [
            Path.home() / '.cache' / 'google-chrome',
            Path('/tmp') / 'chrome_*',
            Path('/tmp') / 'selenium_*',
        ]
        
        for pattern in user_data_dirs:
            if isinstance(pattern, Path):
                if '*' in str(pattern):
                    parent_dir = pattern.parent
                    if parent_dir.exists():
                        for match in parent_dir.glob(pattern.name):
                            try:
                                if match.is_dir() and is_selenium_dir(match):
                                    shutil.rmtree(match)
                                    cleaned_count += 1
                                    logger.debug(f"Removed selenium dir: {match}")
                            except (OSError, PermissionError) as e:
                                logger.warning(f"Could not remove {match}: {e}")
                else:
                    if pattern.exists() and pattern.is_dir():
                        try:
                            if is_selenium_dir(pattern):
                                shutil.rmtree(pattern)
                                cleaned_count += 1
                                logger.debug(f"Removed selenium dir: {pattern}")
                        except (OSError, PermissionError) as e:
                            logger.warning(f"Could not remove {pattern}: {e}")
    
        for fi in glob.glob('./downloaded_files/*'):
            try:
                os.remove(fi)
                cleaned_count +=1
                
            except Exception as e:
                print(e)
        base_path = './downloaded_files'
        
        dirs = [d for d in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, d))]
        
        for d in dirs:
            dir_path = os.path.join(base_path, d)
            try:
                shutil.rmtree(dir_path)
                cleaned_count += 1
            except Exception as e:
                logger.error(f"Failed to delete {dir_path}: {e}")
    
    except Exception as e:
        logger.error(f"Error during temp directory cleanup: {e}")
    
    return cleaned_count

def is_old_temp_dir(path: Path) -> bool:
    try:
        dir_age = time.time() - path.stat().st_mtime
        return dir_age > 3600  
    except:
        return False

def is_selenium_dir(path: Path) -> bool:
    selenium_indicators = [
        'selenium',
        'webdriver',
       'downloaded_files', 
        'chrome_',
        'scoped_dir',
        'default',  # Chrome profile dir
        'first run'  # Chrome first run file
    ]
    
    try:
        path_str = str(path).lower()
        
        if any(indicator in path_str for indicator in selenium_indicators):
            return True
            
        if path.is_dir():
            selenium_files = [
                'Preferences',
                'Local State', 
                'chrome_shutdown_ms.txt',
                'SingletonLock',
                'lockfile'
            ]
            
            for selenium_file in selenium_files:
                if (path / selenium_file).exists():
                    return True
                    
        return False
        
    except Exception:
        return False

@app.post("/api/v1/admin/force-kill-all-selenium")
async def force_kill_all_selenium():
    try:
        killed_count = 0
        selenium_processes = ['chrome', 'chromedriver', 'chromium', 'geckodriver', 'firefox']
        
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] and any(name in proc.info['name'].lower() for name in selenium_processes):
                    proc.kill()  
                    killed_count += 1
                    logger.warning(f"Force killed process: {proc.info['name']} (PID: {proc.info['pid']})")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
                
        temp_dirs_cleaned = cleanup_all_temp_dirs()
        
        gc.collect()
        
        return {
            "status": "success",
            "message": f"Force killed {killed_count} processes, cleaned {temp_dirs_cleaned} temp dirs",
            "warning": "This may have interrupted active scraping tasks"
        }
        
    except Exception as e:
        logger.error(f"Force kill failed: {str(e)}")
        return {"status": "error", "message": str(e)}

def cleanup_all_temp_dirs() -> int:
    cleaned_count = 0
    
    temp_patterns = [
        'scoped_dir*',
        'chrome_*',
        'selenium_*',
        '.org.chromium.*',
        'downloaded_files'
        'webdriver_*',
        'tmp*chromedriver*',
        'chrome-data_*'
    ]
    
    try:
        temp_dir = Path(tempfile.gettempdir())
        
        for pattern in temp_patterns:
            for temp_path in temp_dir.glob(pattern):
                try:
                    if temp_path.is_dir():
                        shutil.rmtree(temp_path)
                        cleaned_count += 1
                        logger.debug(f"Force removed temp directory: {temp_path}")
                except (OSError, PermissionError) as e:
                    logger.warning(f"Could not remove {temp_path}: {e}")
                    
    except Exception as e:
        logger.error(f"Error during aggressive temp cleanup: {e}")
    
    return cleaned_count

async def auto_cleanup_if_needed(memory_threshold: float = 80.0):
    try:
        memory_percent = psutil.virtual_memory().percent
        
        if memory_percent > memory_threshold:
            logger.warning(f"Memory usage at {memory_percent}%, triggering auto-cleanup")
            result = await cleanup_selenium_instances()
            return result
        else:
            return {"status": "skipped", "memory_percent": memory_percent, "threshold": memory_threshold}
            
    except Exception as e:
        logger.error(f"Auto-cleanup failed: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/api/v1/admin/auto-cleanup")
async def trigger_auto_cleanup(memory_threshold: float = 80.0):
    try:
        result = await auto_cleanup_if_needed(memory_threshold)
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/v1/admin/selenium-processes")
async def list_selenium_processes():
    try:
        selenium_processes = []
        selenium_process_names = ['chrome', 'chromedriver', 'chromium', 'geckodriver', 'firefox']
        
        for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'status', 'create_time']):
            try:
                if proc.info['name'] and any(name in proc.info['name'].lower() for name in selenium_process_names):
                    proc_memory = proc.info['memory_info'].rss / 1024 / 1024  # MB
                    process_age = time.time() - proc.info['create_time']
                    
                    selenium_processes.append({
                        "pid": proc.info['pid'],
                        "name": proc.info['name'],
                        "memory_mb": round(proc_memory, 2),
                        "status": proc.info['status'],
                        "age_seconds": round(process_age, 2),
                        "age_minutes": round(process_age / 60, 2),
                        "is_orphaned": is_orphaned(proc),
                        "parent_name": get_parent_name(proc)
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
                
        return {
            "status": "success",
            "process_count": len(selenium_processes),
            "processes": selenium_processes,
            "total_memory_mb": round(sum(p["memory_mb"] for p in selenium_processes), 2)
        }
        
    except Exception as e:
        logger.error(f"Failed to list selenium processes: {str(e)}")
        return {"status": "error", "message": str(e)}

# Real-time Log Streaming API

@app.get("/api/v1/data-sources/status")
async def get_data_sources_status():
    """Get status of all data sources"""
    try:
        # Data source configurations
        source_configs = {
            'eximpedia': {
                'name': 'EximPedia',
                'description': 'Export-import trade data and company information',
                'url': 'https://www.eximpedia.app',
                'type': 'web',
                'category': 'Trade Data',
                'icon': 'globe'
            },
            'macmap_tariff': {
                'name': 'MacMap Tariff',
                'description': 'Market access map tariff and trade policy data',
                'url': 'https://www.macmap.org',
                'type': 'web',
                'category': 'Tariff Data',
                'icon': 'map'
            },
            'trademap': {
                'name': 'TradeMap',
                'description': 'International trade statistics and market analysis',
                'url': 'https://www.trademap.org',
                'type': 'web',
                'category': 'Trade Statistics',
                'icon': 'trending-up'
            },
            'indian_trade_portal': {
                'name': 'Indian Trade Portal',
                'description': 'India trade data and export-import statistics',
                'url': 'https://www.indiantradeportal.in',
                'type': 'web',
                'category': 'Regional Trade',
                'icon': 'flag'
            },
            'compare_market': {
                'name': 'Compare Market',
                'description': 'Market comparison and competitive analysis data',
                'url': 'https://comparemarket.com',
                'type': 'web',
                'category': 'Market Analysis',
                'icon': 'bar-chart'
            },
            'competitors': {
                'name': 'Competitors Analysis',
                'description': 'Competitive intelligence and market positioning',
                'url': 'https://competitors.com',
                'type': 'web',
                'category': 'Competitive Intelligence',
                'icon': 'users'
            },
            'full_tariff': {
                'name': 'Full Tariff Database',
                'description': 'Comprehensive tariff schedules and trade regulations',
                'url': 'https://fulltariff.com',
                'type': 'database',
                'category': 'Regulatory Data',
                'icon': 'book'
            },
            'macmap_product': {
                'name': 'MacMap Product',
                'description': 'Product-specific market access and trade data',
                'url': 'https://www.macmap.org/products',
                'type': 'web',
                'category': 'Product Data',
                'icon': 'package'
            },
            'macmap_regulatory': {
                'name': 'MacMap Regulatory',
                'description': 'Trade regulations and compliance requirements',
                'url': 'https://www.macmap.org/regulatory',
                'type': 'web',
                'category': 'Regulatory Data',
                'icon': 'shield'
            },
            'trade_remedies': {
                'name': 'Trade Remedies',
                'description': 'Anti-dumping, countervailing duties and safeguards',
                'url': 'https://traderemedies.com',
                'type': 'web',
                'category': 'Trade Defense',
                'icon': 'shield-check'
            },
            'port_scraper': {
                'name': 'Port Scraper',
                'description': 'Port and shipping data extraction and analysis',
                'url': 'https://ports.com',
                'type': 'web',
                'category': 'Port Data',
                'icon': 'anchor'
            },
            'indiamart_products': {
                'name': 'IndiaMART Products',
                'description': 'IndiaMART product listings and supplier information',
                'url': 'https://www.indiamart.com',
                'type': 'web',
                'category': 'Product Data',
                'icon': 'shopping-bag'
            },
            'indiamart_categories': {
                'name': 'IndiaMART Categories',
                'description': 'IndiaMART category structure and product categorization',
                'url': 'https://www.indiamart.com',
                'type': 'web',
                'category': 'Category Data',
                'icon': 'grid'
            }
        }
        
        sources = []
        
        # Get database stats for each source
        for source_id, config in source_configs.items():
            try:
                # Get database file path
                db_mapping = {
                    'eximpedia': 'shared/task_creator_utils/scrapped_data/eximPedia_tasks.db',
                    'macmap_tariff': 'shared/task_creator_utils/scrapped_data/macmap_tariff_tasks.db',
                    'trademap': 'shared/task_creator_utils/scrapped_data/trademap_tasks.db',
                    'indian_trade_portal': 'shared/task_creator_utils/scrapped_data/indian_trade_portal_tasks.db',
                    'compare_market': 'shared/task_creator_utils/scrapped_data/compare_market_tasks.db',
                    'competitors': 'shared/task_creator_utils/scrapped_data/competitors_tasks.db',
                    'full_tariff': 'shared/task_creator_utils/scrapped_data/full_tariff_tasks.db',
                    'macmap_product': 'shared/task_creator_utils/scrapped_data/macmap_product_tasks.db',
                    'macmap_regulatory': 'shared/task_creator_utils/scrapped_data/macmap_regulatory_tasks.db',
                    'trade_remedies': 'shared/task_creator_utils/scrapped_data/trade_remedies_tasks.db'
                }
                
                db_path = db_mapping.get(source_id)
                records = 0
                errors = 0
                status = 'inactive'
                last_update = datetime.now().isoformat()
                today_count = 0
                
                # Get MongoDB collection name for scraped data (based on actual collections)
                mongo_collection_mapping = {
                    'eximpedia': 'eximpedia',  # May not exist yet
                    'macmap_tariff': 'macmap_tariff',  # May not exist yet
                    'trademap': 'trademap',  # May not exist yet
                    'indian_trade_portal': 'indiantradeportal',  # Exists with 166 documents
                    'compare_market': 'macmap_compare_market',  # Exists - fixed collection name
                    'competitors': 'macmap_competitors',  # Exists with 40 documents
                    'full_tariff': 'full_tariff',  # May not exist yet
                    'macmap_product': 'macmap_products',  # Exists with 1 document
                    'macmap_regulatory': 'macmap_regulatory',  # Exists with 1 document
                    'trade_remedies': 'macmap_trade_remedies',  # Exists with 11 documents
                    'indiamart_products': 'indiamart_products',  # IndiaMART product data
                    'indiamart_categories': 'indiamart_categories'  # IndiaMART category data
                }
                
                mongo_collection = mongo_collection_mapping.get(source_id)
                
                if mongo_collection:
                    try:
                        from pymongo import MongoClient
                        
                        # MongoDB connection
                        MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
                        MONGO_DB = os.getenv('MONGO_DB', 'jaimish_data')
                        
                        client = MongoClient(MONGO_URI)
                        db = client[MONGO_DB]
                        collection = db[mongo_collection]
                        
                        # Get total records from MongoDB
                        records = collection.count_documents({})
                        
                        # Get today's count (from 12 AM today)
                        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                        today_count = 0
                        
                        try:
                            # Try different date field formats for today's count
                            date_fields = ["DateCreated", "DateUpdated", "created_at", "updated_at", "timestamp"]
                            
                            for date_field in date_fields:
                                try:
                                    # Check if field exists in collection
                                    sample_doc = collection.find_one({date_field: {"$exists": True}})
                                    if sample_doc:
                                        # Count documents created today
                                        today_count = collection.count_documents({
                                            date_field: {"$gte": today_start.isoformat()}
                                        })
                                        break
                                except:
                                    continue
                            
                            # If no date field found, try ObjectId-based approach
                            if today_count == 0:
                                from bson import ObjectId
                                today_start_objectid = ObjectId.from_datetime(today_start)
                                today_count = collection.count_documents({
                                    "_id": {"$gte": today_start_objectid}
                                })
                        except Exception as e:
                            today_count = 0
                        
                        # Get last update (assuming documents have a timestamp field)
                        last_update = datetime.now().isoformat()
                        try:
                            latest_doc = collection.find_one(sort=[("_id", -1)])
                            if latest_doc and '_id' in latest_doc:
                                # Extract timestamp from ObjectId
                                last_update = latest_doc['_id'].generation_time.isoformat()
                        except:
                            pass
                        
                        status = 'active' if records > 0 else 'inactive'
                        errors = 0  # MongoDB doesn't track errors in the same way
                        
                        # Calculate real throughput based on today's data
                        try:
                            if today_count > 0:
                                # Calculate hours since midnight
                                now = datetime.now()
                                midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
                                hours_since_midnight = max(1, (now - midnight).total_seconds() / 3600)
                                throughput = int(today_count / hours_since_midnight)
                            else:
                                throughput = 0
                        except:
                            throughput = 0
                        
                        client.close()
                        
                    except ImportError:
                        logger.debug(f"PyMongo not available for source {source_id}")
                        status = 'inactive'
                        records = 0
                        errors = 0
                        throughput = 0
                    except Exception as mongo_error:
                        logger.debug(f"Error reading MongoDB for {source_id}: {mongo_error}")
                        status = 'error'
                        records = 0
                        errors = 1
                        throughput = 0
                else:
                    # Fallback to SQLite for task count if no MongoDB collection
                    if db_path and os.path.exists(db_path):
                        try:
                            import sqlite3
                            conn = sqlite3.connect(db_path)
                            cursor = conn.cursor()
                            
                            # Get table info first
                            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                            tables = cursor.fetchall()
                            
                            if tables:
                                table_name = tables[0][0]  # Use first table
                                
                                # Get total records (tasks, not scraped data)
                                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                                records = cursor.fetchone()[0]
                                
                                status = 'active' if records > 0 else 'inactive'
                            else:
                                records = 0
                                status = 'inactive'
                            
                            conn.close()
                            
                        except Exception as db_error:
                            logger.debug(f"Error reading database {db_path}: {db_error}")
                            status = 'error'
                            errors = 1
                
                # Initialize throughput for non-MongoDB sources
                if 'throughput' not in locals():
                    throughput = 0
                
                source_data = {
                    'id': source_id,
                    'name': config['name'],
                    'description': config['description'],
                    'url': config['url'],
                    'type': config['type'],
                    'category': config['category'],
                    'icon': config['icon'],
                    'status': status,
                    'records': records,
                    'errors': errors,
                    'lastUpdate': last_update,
                    'throughput': throughput,
                    'todayCount': today_count
                }
                
                sources.append(source_data)
                
            except Exception as e:
                logger.error(f"Error processing source {source_id}: {e}")
                # Add source with error status
                source_data = {
                    'id': source_id,
                    'name': config['name'],
                    'description': config['description'],
                    'url': config['url'],
                    'type': config['type'],
                    'category': config['category'],
                    'icon': config['icon'],
                    'status': 'error',
                    'records': 0,
                    'errors': 1,
                    'lastUpdate': datetime.now().isoformat(),
                    'throughput': 0
                }
                sources.append(source_data)
        
        return {
            "success": True,
            "sources": sources,
            "total": len(sources),
            "active": len([s for s in sources if s['status'] == 'active']),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting data sources status: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to get data sources status: {str(e)}"
        }

@app.post("/api/v1/data-sources/test/{source_id}")
async def test_data_source_connection(source_id: str):
    """Test connection to a specific data source"""
    try:
        # This would implement actual connection testing
        # For now, return mock results
        import random
        import asyncio
        
        # Simulate test delay
        await asyncio.sleep(1)
        
        success = random.choice([True, True, True, False])  # 75% success rate
        
        if success:
            return {
                "success": True,
                "source_id": source_id,
                "status": "connected",
                "response_time": f"{random.randint(100, 500)}ms",
                "message": "Connection successful"
            }
        else:
            return {
                "success": False,
                "source_id": source_id,
                "status": "failed",
                "message": "Connection timeout or unreachable"
            }
            
    except Exception as e:
        logger.error(f"Error testing data source {source_id}: {str(e)}")
        return {
            "success": False,
            "source_id": source_id,
            "status": "error",
            "message": f"Test failed: {str(e)}"
        }

@app.get("/api/v1/data-sources/{source_id}/data")
async def get_data_source_data(source_id: str, limit: int = 100, offset: int = 0):
    """Get scraped data for a specific data source from MongoDB"""
    try:
        # MongoDB collection mapping for scraped data (based on actual collections)
        collection_mapping = {
            'eximpedia': 'eximpedia',  # May not exist yet
            'macmap_tariff': 'macmap_tariff',  # May not exist yet
            'trademap': 'trademap',  # May not exist yet
            'indian_trade_portal': 'indiantradeportal',  # Exists with 166 documents
            'compare_market': 'macmap_compare_market',  # Exists - fixed collection name
            'competitors': 'macmap_competitors',  # Exists with 40 documents
            'full_tariff': 'full_tariff',  # May not exist yet
            'macmap_product': 'macmap_products',  # Exists with 1 document
            'macmap_regulatory': 'macmap_regulatory',  # Exists with 1 document
            'trade_remedies': 'macmap_trade_remedies',  # Exists with 11 documents
            'port_scraper': 'port_scraper'  # Port scraper data
        }
        
        collection_name = collection_mapping.get(source_id)
        if not collection_name:
            return {
                "success": False,
                "message": f"Unknown data source: {source_id}",
                "data": [],
                "total": 0,
                "columns": []
            }
        
        try:
            from pymongo import MongoClient
            
            # MongoDB connection - adjust these settings according to your setup
            MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
            MONGO_DB = os.getenv('MONGO_DB', 'jaimish_data')
            
            client = MongoClient(MONGO_URI)
            db = client[MONGO_DB]
            collection = db[collection_name]
            
            # Get total count
            total = collection.count_documents({})
            
            if total == 0:
                return {
                    "success": True,
                    "source_id": source_id,
                    "data": [],
                    "total": 0,
                    "columns": [],
                    "limit": limit,
                    "offset": offset,
                    "has_more": False
                }
            
            # Get data with pagination
            cursor = collection.find({}).skip(offset).limit(limit)
            documents = list(cursor)
            
            # Convert MongoDB documents to regular dicts and get column names
            data = []
            all_columns = set()
            
            for doc in documents:
                # Convert ObjectId to string
                if '_id' in doc:
                    doc['_id'] = str(doc['_id'])
                
                # Flatten nested objects for display (optional)
                flattened_doc = {}
                for key, value in doc.items():
                    if isinstance(value, dict):
                        # Flatten nested dictionaries
                        for nested_key, nested_value in value.items():
                            flattened_key = f"{key}.{nested_key}"
                            flattened_doc[flattened_key] = nested_value
                            all_columns.add(flattened_key)
                    elif isinstance(value, list):
                        # Convert lists to strings for display
                        flattened_doc[key] = str(value) if value else ""
                        all_columns.add(key)
                    else:
                        flattened_doc[key] = value
                        all_columns.add(key)
                
                data.append(flattened_doc)
            
            # Convert set to sorted list for consistent column ordering
            columns = sorted(list(all_columns))
            
            # Ensure all documents have all columns (fill missing with None)
            for doc in data:
                for col in columns:
                    if col not in doc:
                        doc[col] = None
            
            client.close()
            
            return {
                "success": True,
                "source_id": source_id,
                "data": data,
                "total": total,
                "columns": columns,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total
            }
            
        except ImportError:
            return {
                "success": False,
                "message": "PyMongo not installed. Please install with: pip install pymongo",
                "data": [],
                "total": 0,
                "columns": []
            }
        except Exception as mongo_error:
            logger.error(f"MongoDB error for source {source_id}: {str(mongo_error)}")
            return {
                "success": False,
                "message": f"Database connection error: {str(mongo_error)}",
                "data": [],
                "total": 0,
                "columns": []
            }
        
    except Exception as e:
        logger.error(f"Error getting data for source {source_id}: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to get data: {str(e)}",
            "data": [],
            "total": 0,
            "columns": []
        }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Main WebSocket endpoint with channel-based subscriptions
    Supports multiple channels: dashboard, tasks, logs, workers, scrapers, data_sources, indiamart
    """
    await ws_manager.connect(websocket, [Channel.GENERAL])
    
    # Background task for sending periodic updates
    async def send_updates():
        # Wait a bit before starting updates to ensure connection is stable
        await asyncio.sleep(0.5)
        while True:
            try:
                channels = ws_manager.get_connection_channels(websocket)
                
                # Skip GENERAL channel for data updates
                data_channels = [ch for ch in channels if ch != Channel.GENERAL]
                
                # Send updates for each subscribed channel
                for channel in data_channels:
                    try:
                        data = None
                        if channel == Channel.DASHBOARD:
                            data = await dashboard_provider.get_data()
                        elif channel == Channel.TASKS:
                            data = await task_manager_provider.get_data()
                        elif channel == Channel.LOGS:
                            data = await logs_provider.get_data()
                        elif channel == Channel.WORKERS:
                            data = await workers_provider.get_data()
                        elif channel == Channel.SCRAPERS:
                            data = await dashboard_provider.get_data()
                        elif channel == Channel.DATA_SOURCES:
                            data = await data_sources_provider.get_data()
                        elif channel == Channel.INDIAMART:
                            data = await indiamart_provider.get_data()
                        elif channel == Channel.HEALTH:
                            data = await system_health_provider.get_data()
                        
                        if data:
                            await ws_manager.send_to_connection(websocket, data)
                    except Exception as channel_error:
                        logger.error(f"Error getting data for channel {channel}: {channel_error}", exc_info=True)
                        # Send error message to client
                        await ws_manager.send_to_connection(websocket, {
                            "type": "error",
                            "channel": channel,
                            "message": str(channel_error)
                        })
                
                # Different update intervals for different channels
                if Channel.WORKERS in data_channels or Channel.HEALTH in data_channels:
                    await asyncio.sleep(2)  # Faster updates for workers and health (2 seconds)
                elif Channel.INDIAMART in data_channels:
                    await asyncio.sleep(3)  # Fast updates for IndiaMART (3 seconds)
                elif Channel.DASHBOARD in data_channels:
                    await asyncio.sleep(3)  # Fast updates for dashboard to show IndiaMART stats (3 seconds)
                else:
                    await asyncio.sleep(5)  # Standard updates for other channels (5 seconds)
                
            except asyncio.CancelledError:
                logger.info("Update task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in update loop: {e}", exc_info=True)
                # Don't break, keep trying
                await asyncio.sleep(5)
    
    # Start update task
    update_task = asyncio.create_task(send_updates())
    
    try:
        while True:
            # Handle incoming messages
            data = await websocket.receive_text()
            response = await ws_manager.handle_message(websocket, data)
            
            # Send response if needed
            if response:
                await ws_manager.send_to_connection(websocket, response)
                
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        update_task.cancel()
        await ws_manager.disconnect(websocket)

@app.websocket("/ws/indiamart")
async def websocket_indiamart(websocket: WebSocket):
    """WebSocket endpoint for IndiaMART scraper real-time updates (legacy support)"""
    await ws_manager.connect(websocket, [Channel.INDIAMART])
    
    # Background task for sending updates
    async def send_updates():
        while True:
            try:
                data = await indiamart_provider.get_data()
                await ws_manager.send_to_connection(websocket, data)
                await asyncio.sleep(1)  # Update every second for IndiaMART
            except asyncio.CancelledError:
                logger.info("IndiaMART update task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in IndiaMART update loop: {e}", exc_info=True)
                # Don't break, keep trying
                await asyncio.sleep(5)
    
    update_task = asyncio.create_task(send_updates())
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle different message types
            if message.get("type") == "ping":
                await ws_manager.send_to_connection(websocket, {"type": "pong"})
            
            elif message.get("type") == "start_crawler":
                try:
                    task = indiamart_category_crawler_task.delay()
                    await ws_manager.broadcast_to_channel(
                        Channel.INDIAMART,
                        {
                            "type": "state",
                            "state": "starting",
                            "task_id": task.id
                        }
                    )
                except Exception as e:
                    logger.error(f"Error starting crawler via WebSocket: {e}")
                    await ws_manager.send_to_connection(websocket, {
                        "type": "error",
                        "message": f"Failed to start crawler: {str(e)}"
                    })
            
            elif message.get("type") == "stop_crawler":
                task_id = message.get("task_id")
                if task_id:
                    try:
                        celery_app.control.revoke(task_id, terminate=True)
                        await ws_manager.broadcast_to_channel(
                            Channel.INDIAMART,
                            {
                                "type": "state",
                                "state": "stopping",
                                "task_id": task_id
                            }
                        )
                    except Exception as e:
                        logger.error(f"Error stopping crawler via WebSocket: {e}")
                        await ws_manager.send_to_connection(websocket, {
                            "type": "error",
                            "message": f"Failed to stop crawler: {str(e)}"
                        })
                        
    except WebSocketDisconnect:
        logger.info("IndiaMART WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        update_task.cancel()
        await ws_manager.disconnect(websocket)

@app.on_event("startup")
async def startup_event():
    """Startup event handler - automatically start category crawler"""
    logger.info("Application startup - checking if category crawler should be auto-started")
    
    # Check if auto-start is enabled via environment variable
    auto_start_crawler = os.getenv("AUTO_START_INDIAMART_CRAWLER", "true").lower() == "true"
    
    if auto_start_crawler:
        try:
            logger.info("Auto-starting IndiaMART category crawler...")
            task = indiamart_category_crawler_task.delay()
            logger.info(f"IndiaMART category crawler auto-started with task_id: {task.id}")
            
            # Broadcast state update via WebSocket
            await state_synchronizer.websocket_manager.broadcast_to_scraper(
                "indiamart",
                {
                    "type": "state",
                    "state": "auto_started",
                    "task_id": task.id,
                    "timestamp": datetime.now().isoformat()
                }
            )
        except Exception as e:
            logger.error(f"Failed to auto-start category crawler: {e}")
    else:
        logger.info("Auto-start disabled for IndiaMART category crawler")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
        
        

