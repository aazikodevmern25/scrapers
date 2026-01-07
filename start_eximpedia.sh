#!/bin/bash

##############################################################################
# EXIMPEDIA SCRAPER STARTUP SCRIPT
# This script starts the complete Eximpedia scraping system with ngrok access
##############################################################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║          EXIMPEDIA SCRAPER STARTUP SCRIPT                        ║"
echo "║          MongoDB: 202.47.115.6:27017 (Dhruval DB)               ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Change to script directory
cd "$(dirname "$0")"
SCRIPT_DIR="$(pwd)"

# Load environment variables
if [ -f .env ]; then
    echo -e "${GREEN}✓ Loading .env file${NC}"
    export $(cat .env | grep -v '^#' | xargs)
else
    echo -e "${RED}✗ .env file not found!${NC}"
    exit 1
fi

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
    sleep 3
    local url=$(curl -s http://localhost:4040/api/tunnels | grep -o '"public_url":"https://[^"]*' | head -1 | cut -d'"' -f4)
    echo "$url"
}

# 1. Check FastAPI Backend (uses same port as trademap: 8001)
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}1. CHECKING FASTAPI BACKEND${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"

FASTAPI_PORT=8001

if check_port $FASTAPI_PORT; then
    echo -e "${GREEN}✓ FastAPI already running on port $FASTAPI_PORT${NC}"
    echo -e "${GREEN}  (Shared with trademap - both forms use same backend)${NC}"
else
    echo -e "${YELLOW}FastAPI not running. Starting on port $FASTAPI_PORT...${NC}"
    cd core
    nohup uvicorn main:app --host 0.0.0.0 --port $FASTAPI_PORT > ../logs/fastapi.log 2>&1 &
    FASTAPI_PID=$!
    cd ..
    echo $FASTAPI_PID > .fastapi_pid
    sleep 3
    
    if check_port $FASTAPI_PORT; then
        echo -e "${GREEN}✓ FastAPI started successfully (PID: $FASTAPI_PID)${NC}"
    else
        echo -e "${RED}✗ Failed to start FastAPI${NC}"
        exit 1
    fi
fi

# 2. Start Ngrok (if not running)
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}2. STARTING NGROK TUNNEL${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"

# Kill any existing ngrok processes
pkill -9 ngrok 2>/dev/null || true
sleep 2

echo -e "${YELLOW}Starting ngrok tunnel to port $FASTAPI_PORT...${NC}"
nohup ~/ngrok http $FASTAPI_PORT --log=stdout > logs/eximpedia_ngrok.log 2>&1 &
NGROK_PID=$!
echo $NGROK_PID > .eximpedia_ngrok_pid

# Wait for ngrok to start
sleep 5

# Get ngrok URL
NGROK_URL=$(get_ngrok_url)

if [ -z "$NGROK_URL" ]; then
    echo -e "${RED}✗ Failed to get ngrok URL${NC}"
    echo -e "${YELLOW}  Check logs/eximpedia_ngrok.log for details${NC}"
else
    echo -e "${GREEN}✓ Ngrok tunnel established${NC}"
    echo -e "${GREEN}  Public URL: ${NGROK_URL}${NC}"
    
    # Save URL to file
    echo "$NGROK_URL" > EXIMPEDIA_NGROK_URL.txt
fi

# 3. Start Eximpedia Celery Workers
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}3. STARTING EXIMPEDIA CELERY WORKERS${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"

# Check if workers already running
WORKER_COUNT=$(ps aux | grep 'celery.*eximpedia' | grep -v grep | wc -l)

if [ $WORKER_COUNT -gt 0 ]; then
    echo -e "${YELLOW}⚠ $WORKER_COUNT Eximpedia worker(s) already running${NC}"
    read -p "Kill existing workers and restart? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Killing existing workers...${NC}"
        pkill -9 -f 'celery.*eximpedia' 2>/dev/null || true
        sleep 2
    else
        echo -e "${YELLOW}Keeping existing workers${NC}"
    fi
fi

# Start task creator worker
echo -e "${GREEN}Starting Eximpedia task creator worker...${NC}"
celery -A celery_app.tasks worker \
    --loglevel=info \
    -Q eximpedia_task_creator \
    --concurrency=1 \
    --hostname=eximpedia_task_creator@%h \
    --logfile=logs/eximpedia_task_creator.log \
    --pidfile=.eximpedia_task_creator.pid \
    --detach

sleep 2

# Start main scraper workers (4 workers for parallel processing)
echo -e "${GREEN}Starting Eximpedia scraper workers (4 workers)...${NC}"
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

sleep 3

# Verify workers are running
WORKER_COUNT=$(ps aux | grep 'celery.*eximpedia' | grep -v grep | wc -l)
echo -e "${GREEN}✓ $WORKER_COUNT Eximpedia worker(s) running${NC}"

# 4. Display Access Information
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                 EXIMPEDIA SYSTEM READY                           ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}📋 ACCESS INFORMATION:${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if [ ! -z "$NGROK_URL" ]; then
    echo -e "${GREEN}🌐 Eximpedia Form:${NC}"
    echo -e "   ${NGROK_URL}/eximpedia-form"
    echo ""
    echo -e "${GREEN}📊 API Documentation:${NC}"
    echo -e "   ${NGROK_URL}/docs"
    echo ""
    echo -e "${GREEN}💚 Health Check:${NC}"
    echo -e "   ${NGROK_URL}/api/v1/health"
else
    echo -e "${YELLOW}⚠ Ngrok URL not available. Use local access:${NC}"
    echo -e "   http://localhost:1080/eximpedia-form"
fi

echo ""
echo -e "${BLUE}🗄️  DATABASE:${NC}"
echo -e "   MongoDB: 202.47.115.6:27017"
echo -e "   Database: Dhruval"
echo -e "   Collection: eximpedia"

echo ""
echo -e "${BLUE}👷 WORKERS:${NC}"
echo -e "   Task Creator: 1 worker"
echo -e "   Scrapers: 4 workers (2 concurrent tasks each)"

echo ""
echo -e "${BLUE}📁 LOG FILES:${NC}"
echo -e "   FastAPI: logs/fastapi.log"
echo -e "   Ngrok: logs/eximpedia_ngrok.log"
echo -e "   Task Creator: logs/eximpedia_task_creator.log"
echo -e "   Workers: logs/eximpedia_worker[1-4].log"
echo -e "   Scraper: logs/eximpedia_scraper_$(date +%Y%m%d).log"

echo ""
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${GREEN}✨ To monitor tasks:${NC}"
echo -e "   tail -f logs/eximpedia_scraper_*.log"
echo ""
echo -e "${GREEN}✨ To stop all services:${NC}"
echo -e "   ./stop_eximpedia.sh"
echo ""

# Save access info to file
cat > EXIMPEDIA_ACCESS.txt << EOF
====================================================================
EXIMPEDIA SCRAPER ACCESS INFORMATION
Updated: $(date)
====================================================================

🌐 EXIMPEDIA FORM:
   ${NGROK_URL}/eximpedia-form

📊 API DOCUMENTATION:
   ${NGROK_URL}/docs

💚 HEALTH CHECK:
   ${NGROK_URL}/api/v1/health

🗄️  DATABASE:
   MongoDB: 202.47.115.6:27017
   Database: Dhruval
   Collection: eximpedia

📝 FORM FIELDS:
   - HS Codes (comma-separated, e.g., 010121, 010129)
   - Country (dropdown)
   - Trade Type (Import/Export)
   - Start Date (MM/DD/YYYY or YYYY)
   - End Date (MM/DD/YYYY or YYYY)

====================================================================
EOF

echo -e "${GREEN}Access information saved to: EXIMPEDIA_ACCESS.txt${NC}"
echo ""
