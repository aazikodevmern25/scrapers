#!/bin/bash

# MacMap Scraper Startup Script
# This script starts all MacMap scraping services

echo "========================================="
echo "  MacMap Scraper Startup Script"
echo "========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check if a service is running
check_service() {
    if pgrep -x "$1" >/dev/null; then
        echo -e "${GREEN}✓${NC} $2 is running"
        return 0
    else
        echo -e "${RED}✗${NC} $2 is not running"
        return 1
    fi
}

# Check Python
echo "Checking prerequisites..."
if ! command_exists python3; then
    echo -e "${RED}Error: Python 3 is not installed${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} Python 3 is installed"

# Check MongoDB
if ! check_service mongod "MongoDB"; then
    echo -e "${YELLOW}⚠${NC}  Starting MongoDB..."
    sudo systemctl start mongod 2>/dev/null || sudo service mongodb start 2>/dev/null
    sleep 2
fi

# Check Redis
if ! check_service redis-server "Redis"; then
    echo -e "${YELLOW}⚠${NC}  Starting Redis..."
    sudo systemctl start redis 2>/dev/null || sudo service redis-server start 2>/dev/null || redis-server --daemonize yes
    sleep 2
fi

echo ""
echo "========================================="
echo "  Preparing Environment"
echo "========================================="

# Create logs directory if it doesn't exist
mkdir -p logs
echo -e "${GREEN}✓${NC} Logs directory created"

echo ""
echo "========================================="
echo "  Starting Services"
echo "========================================="

# Kill any existing processes on port 8888
echo "Checking for existing processes on port 8888..."
lsof -ti:8888 | xargs kill -9 2>/dev/null
sleep 1

# Kill any existing MacMap workers
echo "Stopping any existing MacMap workers..."
pkill -f "celery.*macmap" 2>/dev/null
sleep 1

# Start FastAPI server
echo ""
echo -e "${YELLOW}Starting FastAPI server...${NC}"
uvicorn core.main:app --host 0.0.0.0 --port 8888 > logs/fastapi.log 2>&1 &
FASTAPI_PID=$!
echo -e "${GREEN}✓${NC} FastAPI server started (PID: $FASTAPI_PID)"

# Wait for server to initialize
sleep 3

# Start MacMap Tariff worker
echo ""
echo -e "${YELLOW}Starting MacMap Tariff worker...${NC}"
celery -A celery_app.tasks worker --loglevel=info -Q macmap_tariff --concurrency=1 --hostname=macmap_tariff_worker@%h > logs/celery_macmap_tariff.log 2>&1 &
MACMAP_TARIFF_PID=$!
echo -e "${GREEN}✓${NC} MacMap Tariff worker started (PID: $MACMAP_TARIFF_PID)"

# Wait a bit
sleep 2

# Start MacMap Trade Remedies worker
echo ""
echo -e "${YELLOW}Starting MacMap Trade Remedies worker...${NC}"
celery -A celery_app.tasks worker --loglevel=info -Q macmap_trade_remedies --concurrency=1 --hostname=macmap_trade_remedies_worker@%h > logs/celery_macmap_trade_remedies.log 2>&1 &
MACMAP_REMEDIES_PID=$!
echo -e "${GREEN}✓${NC} MacMap Trade Remedies worker started (PID: $MACMAP_REMEDIES_PID)"

# Wait a bit
sleep 2

# Start MacMap Regulatory worker
echo ""
echo -e "${YELLOW}Starting MacMap Regulatory worker...${NC}"
celery -A celery_app.tasks worker --loglevel=info -Q macmap_regulatory --concurrency=1 --hostname=macmap_regulatory_worker@%h > logs/celery_macmap_regulatory.log 2>&1 &
MACMAP_REGULATORY_PID=$!
echo -e "${GREEN}✓${NC} MacMap Regulatory worker started (PID: $MACMAP_REGULATORY_PID)"

# Wait a bit
sleep 2

# Start MacMap Compare Market worker
echo ""
echo -e "${YELLOW}Starting MacMap Compare Market worker...${NC}"
celery -A celery_app.tasks worker --loglevel=info -Q macmap_compare --concurrency=1 --hostname=macmap_compare_worker@%h > logs/celery_macmap_compare.log 2>&1 &
MACMAP_COMPARE_PID=$!
echo -e "${GREEN}✓${NC} MacMap Compare Market worker started (PID: $MACMAP_COMPARE_PID)"

# Wait a bit
sleep 2

# Start MacMap Competitors worker
echo ""
echo -e "${YELLOW}Starting MacMap Competitors worker...${NC}"
celery -A celery_app.tasks worker --loglevel=info -Q macmap_competitors --concurrency=1 --hostname=macmap_competitors_worker@%h > logs/celery_macmap_competitors.log 2>&1 &
MACMAP_COMPETITORS_PID=$!
echo -e "${GREEN}✓${NC} MacMap Competitors worker started (PID: $MACMAP_COMPETITORS_PID)"

# Wait a bit
sleep 2

# Start MacMap Products worker
echo ""
echo -e "${YELLOW}Starting MacMap Products worker...${NC}"
celery -A celery_app.tasks worker --loglevel=info -Q macmap_products --concurrency=1 --hostname=macmap_products_worker@%h > logs/celery_macmap_products.log 2>&1 &
MACMAP_PRODUCTS_PID=$!
echo -e "${GREEN}✓${NC} MacMap Products worker started (PID: $MACMAP_PRODUCTS_PID)"

# Wait for all services to start
echo ""
echo "Waiting for services to initialize..."
sleep 3

# Check if server is running
if curl -s http://localhost:8888/api/v1/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Server is running successfully!"
else
    echo -e "${YELLOW}⚠${NC}  Server might still be starting..."
fi

echo ""
echo "========================================="
echo "  MacMap Services Started Successfully!"
echo "========================================="
echo ""
echo "📋 Service Information:"
echo "  • FastAPI Server:     http://localhost:8888"
echo "  • API Documentation:  http://localhost:8888/docs"
echo "  • Main Dashboard:     file://$(pwd)/templates/index.html"
echo ""
echo "🔧 MacMap Workers Running:"
echo "  • Tariff Worker       (PID: $MACMAP_TARIFF_PID)"
echo "  • Trade Remedies      (PID: $MACMAP_REMEDIES_PID)"
echo "  • Regulatory          (PID: $MACMAP_REGULATORY_PID)"
echo "  • Compare Market      (PID: $MACMAP_COMPARE_PID)"
echo "  • Competitors         (PID: $MACMAP_COMPETITORS_PID)"
echo "  • Products            (PID: $MACMAP_PRODUCTS_PID)"
echo ""
echo "📊 Logs:"
echo "  • FastAPI:            logs/fastapi.log"
echo "  • Tariff Worker:      logs/celery_macmap_tariff.log"
echo "  • Trade Remedies:     logs/celery_macmap_trade_remedies.log"
echo "  • Regulatory:         logs/celery_macmap_regulatory.log"
echo "  • Compare Market:     logs/celery_macmap_compare.log"
echo "  • Competitors:        logs/celery_macmap_competitors.log"
echo "  • Products:           logs/celery_macmap_products.log"
echo "  • Scraper Logs:       logs/macmap_tariff_*.log"
echo ""
echo "🚀 How to Use MacMap Scrapers:"
echo ""
echo "  Method 1: Web Form (EASIEST! Like TradeMap)"
echo "  ============================================="
echo "  ./open_macmap_form.sh"
echo "  OR open: file://$(pwd)/macmap_tariff_form.html"
echo ""
echo "  Method 2: Task Creator (Bulk Operations)"
echo "  =========================================="
echo "  1. Create payloads:"
echo "     python3 scrapers/macmap/tariff/macmapTariffPayloadCreator.py"
echo ""
echo "  2. Run task creator:"
echo "     python3 scrapers/macmap/tariff/macmapTariffTaskCreator.py"
echo ""
echo "  Method 3: API Calls"
echo "  ==================="
echo "  curl -X POST http://localhost:8888/api/v1/scrape/tariff \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"country1\": \"United States\", \"country2\": \"China\", \"year\": 2023, \"hsc\": \"29211\"}'"
echo ""
echo "  Method 4: Browser (API Docs)"
echo "  ============================="
echo "  Open: http://localhost:8888/docs"
echo ""
echo "📖 For detailed guide, see: START_MACMAP_GUIDE.md"
echo ""
echo "📌 PIDs saved to .macmap_pids"
echo ""
echo "To stop services, run:"
echo "  kill $FASTAPI_PID $MACMAP_TARIFF_PID $MACMAP_REMEDIES_PID $MACMAP_REGULATORY_PID $MACMAP_COMPARE_PID $MACMAP_COMPETITORS_PID $MACMAP_PRODUCTS_PID"
echo ""

# Save PIDs to file for easy stopping
cat > .macmap_pids << EOF
FASTAPI_PID=$FASTAPI_PID
MACMAP_TARIFF_PID=$MACMAP_TARIFF_PID
MACMAP_REMEDIES_PID=$MACMAP_REMEDIES_PID
MACMAP_REGULATORY_PID=$MACMAP_REGULATORY_PID
MACMAP_COMPARE_PID=$MACMAP_COMPARE_PID
MACMAP_COMPETITORS_PID=$MACMAP_COMPETITORS_PID
MACMAP_PRODUCTS_PID=$MACMAP_PRODUCTS_PID
EOF

echo "========================================="
echo "  Press Ctrl+C to stop all services"
echo "========================================="

# Wait for user interrupt
trap "echo ''; echo 'Stopping services...'; kill $FASTAPI_PID $MACMAP_TARIFF_PID $MACMAP_REMEDIES_PID $MACMAP_REGULATORY_PID $MACMAP_COMPARE_PID $MACMAP_COMPETITORS_PID $MACMAP_PRODUCTS_PID 2>/dev/null; echo 'Services stopped.'; exit 0" INT

# Keep script running
tail -f /dev/null
