#!/bin/bash

##############################################################################
# START ALL SCRAPERS - Eximpedia, TradeMap, MacMap
# Uses port 8001 for FastAPI (port 8000 is used by Cloudflare)
# Automatically generates new ngrok URL on restart
##############################################################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║          ALL SCRAPERS STARTUP SCRIPT                             ║"
echo "║          Eximpedia | TradeMap | MacMap                           ║"
echo "║          Port: 8001 (Avoiding 8000 - Cloudflare)                 ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Change to script directory
cd "$(dirname "$0")"
SCRIPT_DIR="$(pwd)"

# Create logs directory
mkdir -p logs

# Load environment variables
if [ -f .env ]; then
    echo -e "${GREEN}✓ Loading .env file${NC}"
    export $(cat .env | grep -v '^#' | xargs)
else
    echo -e "${RED}✗ .env file not found!${NC}"
    exit 1
fi

# Function to check if port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Function to get ngrok URL
get_ngrok_url() {
    sleep 5
    local url=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | grep -o '"public_url":"https://[^"]*' | head -1 | cut -d'"' -f4)
    echo "$url"
}

##############################################################################
# STEP 1: Check MongoDB and Redis
##############################################################################
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}STEP 1: Checking Dependencies${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"

# Check MongoDB connection
echo -e "${YELLOW}Checking MongoDB connection...${NC}"
if ! timeout 5 bash -c "cat < /dev/null > /dev/tcp/202.47.115.6/27017" 2>/dev/null; then
    echo -e "${RED}✗ Cannot connect to MongoDB at 202.47.115.6:27017${NC}"
    echo -e "${YELLOW}  Please ensure MongoDB is running and accessible${NC}"
else
    echo -e "${GREEN}✓ MongoDB connection successful${NC}"
fi

# Check Redis
echo -e "${YELLOW}Checking Redis...${NC}"
if ! pgrep -x "redis-server" > /dev/null; then
    echo -e "${YELLOW}⚠ Redis not running, starting...${NC}"
    redis-server --daemonize yes
    sleep 2
fi
echo -e "${GREEN}✓ Redis is running${NC}"

##############################################################################
# STEP 2: Stop existing services (cleanup)
##############################################################################
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}STEP 2: Cleaning up old processes${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"

echo -e "${YELLOW}Stopping old FastAPI and ngrok processes...${NC}"
pkill -9 -f "uvicorn.*main:app" 2>/dev/null || true
pkill -9 ngrok 2>/dev/null || true
sleep 3
echo -e "${GREEN}✓ Cleanup complete${NC}"

##############################################################################
# STEP 3: Start FastAPI Backend on Port 8001
##############################################################################
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}STEP 3: Starting FastAPI Backend (Port 8001)${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"

FASTAPI_PORT=8001

echo -e "${YELLOW}Starting FastAPI on port $FASTAPI_PORT...${NC}"
cd core
nohup uvicorn main:app --host 0.0.0.0 --port $FASTAPI_PORT > ../logs/fastapi.log 2>&1 &
FASTAPI_PID=$!
cd ..
echo $FASTAPI_PID > .fastapi_pid

sleep 5

if check_port $FASTAPI_PORT; then
    echo -e "${GREEN}✓ FastAPI started successfully (PID: $FASTAPI_PID)${NC}"
else
    echo -e "${RED}✗ Failed to start FastAPI${NC}"
    echo -e "${YELLOW}  Check logs/fastapi.log for details${NC}"
    exit 1
fi

##############################################################################
# STEP 4: Start Ngrok Tunnel
##############################################################################
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}STEP 4: Starting Ngrok Tunnel${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"

echo -e "${YELLOW}Starting ngrok tunnel to port $FASTAPI_PORT...${NC}"
nohup ~/ngrok http $FASTAPI_PORT --log=stdout > logs/ngrok.log 2>&1 &
NGROK_PID=$!
echo $NGROK_PID > .ngrok_pid

sleep 8

# Get ngrok URL
NGROK_URL=$(get_ngrok_url)

if [ -z "$NGROK_URL" ]; then
    echo -e "${YELLOW}⏳ Waiting for ngrok to fully start...${NC}"
    sleep 10
    NGROK_URL=$(get_ngrok_url)
fi

if [ -z "$NGROK_URL" ]; then
    echo -e "${RED}✗ Failed to get ngrok URL${NC}"
    echo -e "${YELLOW}  Check logs/ngrok.log for details${NC}"
    exit 1
else
    echo -e "${GREEN}✓ Ngrok tunnel established${NC}"
    echo -e "${GREEN}  Public URL: ${NGROK_URL}${NC}"
fi

##############################################################################
# STEP 5: Start Celery Workers
##############################################################################
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}STEP 5: Starting Celery Workers${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"

# Kill existing workers
echo -e "${YELLOW}Cleaning up existing workers...${NC}"
pkill -9 -f 'celery.*eximpedia' 2>/dev/null || true
pkill -9 -f 'celery.*trademap' 2>/dev/null || true
pkill -9 -f 'celery.*macmap' 2>/dev/null || true
sleep 3

# Start Eximpedia Workers
echo -e "${CYAN}Starting Eximpedia workers...${NC}"
celery -A celery_app.tasks worker \
    --loglevel=info \
    -Q eximpedia_task_creator \
    --concurrency=1 \
    --hostname=eximpedia_task_creator@%h \
    --logfile=logs/eximpedia_task_creator.log \
    --pidfile=.eximpedia_task_creator.pid \
    --detach

for i in {1..4}; do
    celery -A celery_app.tasks worker \
        --loglevel=info \
        -Q eximpedia \
        --concurrency=2 \
        --hostname=eximpedia_worker${i}@%h \
        --logfile=logs/eximpedia_worker${i}.log \
        --pidfile=.eximpedia_worker${i}.pid \
        --detach
    sleep 1
done

sleep 2

# Start TradeMap Workers
echo -e "${CYAN}Starting TradeMap workers...${NC}"
for i in {1..10}; do
    celery -A celery_app.tasks worker \
        --loglevel=info \
        -Q trademap \
        --concurrency=3 \
        --hostname=trademap_worker${i}@%h \
        --max-tasks-per-child=100 \
        --logfile=logs/celery_trademap_worker${i}.log \
        --pidfile=.trademap_worker${i}.pid \
        --detach
    sleep 0.5
done

sleep 2

# Start MacMap Workers
echo -e "${CYAN}Starting MacMap workers...${NC}"
for i in {1..4}; do
    celery -A celery_app.tasks worker \
        --loglevel=info \
        -Q macmap_tariff \
        --concurrency=3 \
        --hostname=macmap_tariff_worker_${i}@%h \
        --max-tasks-per-child=50 \
        --logfile=logs/celery_macmap_tariff_worker${i}.log \
        --pidfile=.macmap_worker${i}.pid \
        --detach
    sleep 0.5
done

sleep 3

# Verify workers
EXIMPEDIA_WORKERS=$(ps aux | grep 'celery.*eximpedia' | grep -v grep | wc -l)
TRADEMAP_WORKERS=$(ps aux | grep 'celery.*trademap' | grep -v grep | wc -l)
MACMAP_WORKERS=$(ps aux | grep 'celery.*macmap_tariff' | grep -v grep | wc -l)

echo -e "${GREEN}✓ Workers started:${NC}"
echo -e "${GREEN}  - Eximpedia: $EXIMPEDIA_WORKERS workers${NC}"
echo -e "${GREEN}  - TradeMap: $TRADEMAP_WORKERS workers${NC}"
echo -e "${GREEN}  - MacMap: $MACMAP_WORKERS workers${NC}"

##############################################################################
# STEP 6: Display Access Information
##############################################################################
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                 ALL SCRAPERS READY                               ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}📋 ACCESS URLS:${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${CYAN}🌐 EXIMPEDIA:${NC}"
echo -e "   Form: ${NGROK_URL}/eximpedia-form"
echo -e "   Mirror Data: ${NGROK_URL}/eximpedia-mirror-data-form"
echo ""
echo -e "${CYAN}🌐 TRADEMAP:${NC}"
echo -e "   Form: ${NGROK_URL}/trademap-form"
echo ""
echo -e "${CYAN}🌐 MACMAP:${NC}"
echo -e "   Tariff Form: ${NGROK_URL}/static/macmap_tariff_form.html"
echo -e "   Trade Agreements: ${NGROK_URL}/static/macmap_trade_agreements_form.html"
echo ""
echo -e "${CYAN}📊 API:${NC}"
echo -e "   Documentation: ${NGROK_URL}/docs"
echo -e "   Health Check: ${NGROK_URL}/api/v1/health"
echo ""
echo -e "${BLUE}🗄️  DATABASE:${NC}"
echo -e "   MongoDB: 202.47.115.6:27017"
echo -e "   Database: Dhruval"
echo ""
echo -e "${BLUE}👷 WORKERS:${NC}"
echo -e "   Eximpedia: $EXIMPEDIA_WORKERS workers"
echo -e "   TradeMap: $TRADEMAP_WORKERS workers"
echo -e "   MacMap: $MACMAP_WORKERS workers"
echo ""
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

##############################################################################
# STEP 7: Save URLs to files
##############################################################################

# Save comprehensive URLs file
cat > CURRENT_NGROK_URL.txt << EOF
====================================================================
ALL SCRAPERS - CURRENT NGROK URLS
Updated: $(date)
====================================================================

Base URL: $NGROK_URL
Port: 8001 (FastAPI)

EXIMPEDIA:
  • Form: ${NGROK_URL}/eximpedia-form
  • Mirror Data: ${NGROK_URL}/eximpedia-mirror-data-form

TRADEMAP:
  • Form: ${NGROK_URL}/trademap-form

MACMAP:
  • Tariff Form: ${NGROK_URL}/static/macmap_tariff_form.html
  • Trade Agreements: ${NGROK_URL}/static/macmap_trade_agreements_form.html

API:
  • Docs: ${NGROK_URL}/docs
  • Health: ${NGROK_URL}/api/v1/health

====================================================================
Services Status:
  ✅ FastAPI: Running on localhost:8001
  ✅ Ngrok: Tunneling to public URL
  ✅ Eximpedia Workers: $EXIMPEDIA_WORKERS running
  ✅ TradeMap Workers: $TRADEMAP_WORKERS running
  ✅ MacMap Workers: $MACMAP_WORKERS running
====================================================================
EOF

# Save individual scraper URLs
echo "$NGROK_URL" > EXIMPEDIA_NGROK_URL.txt
echo "$NGROK_URL" > TRADEMAP_NGROK_URL.txt
echo "$NGROK_URL" > MACMAP_NGROK_URL.txt

echo -e "${GREEN}✓ URLs saved to:${NC}"
echo -e "   - CURRENT_NGROK_URL.txt (all scrapers)"
echo -e "   - EXIMPEDIA_NGROK_URL.txt"
echo -e "   - TRADEMAP_NGROK_URL.txt"
echo -e "   - MACMAP_NGROK_URL.txt"
echo ""

echo -e "${GREEN}✨ All scrapers are ready! Use the URLs above to access the forms.${NC}"
echo -e "${GREEN}✨ To stop all services: pkill -9 -f uvicorn; pkill -9 ngrok${NC}"
echo ""
