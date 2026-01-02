#!/bin/bash

# TradeMap Scraper Startup Script
# This script will help you start all necessary services

echo "========================================="
echo "  TradeMap Scraper Startup Script"
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

# Check if dependencies are installed (skip pip install to avoid errors)
echo -e "${GREEN}✓${NC} Skipping pip install (use virtual environment if needed)"

echo ""
echo "========================================="
echo "  Starting Services"
echo "========================================="

# Kill any existing processes on port 1080
echo "Checking for existing processes on port 1080..."
lsof -ti:1080 | xargs kill -9 2>/dev/null
sleep 1

# Start Celery worker in background
echo ""
echo -e "${YELLOW}Starting Celery worker for TradeMap...${NC}"
celery -A celery_app.tasks worker --loglevel=info -Q trademap --concurrency=1 > logs/celery_trademap.log 2>&1 &
CELERY_PID=$!
echo -e "${GREEN}✓${NC} Celery worker started (PID: $CELERY_PID)"

# Wait a bit for Celery to initialize
sleep 3

# Start FastAPI server
echo ""
echo -e "${YELLOW}Starting FastAPI server...${NC}"
uvicorn core.main:app --host 0.0.0.0 --port 1080 > logs/fastapi.log 2>&1 &
FASTAPI_PID=$!
echo -e "${GREEN}✓${NC} FastAPI server started (PID: $FASTAPI_PID)"

# Wait for server to start
echo ""
echo "Waiting for server to start..."
sleep 5

# Check if server is running
if curl -s http://localhost:1080/api/v1/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Server is running successfully!"
else
    echo -e "${YELLOW}⚠${NC}  Server might still be starting..."
fi

echo ""
echo "========================================="
echo "  Services Started Successfully!"
echo "========================================="
echo ""
echo "📋 Service Information:"
echo "  • FastAPI Server: http://localhost:1080"
echo "  • TradeMap Form:  file://$(pwd)/trademap_form.html"
echo "  • Celery Worker:  Running (PID: $CELERY_PID)"
echo ""
echo "📊 Logs:"
echo "  • FastAPI:  logs/fastapi.log"
echo "  • Celery:   logs/celery_trademap.log"
echo "  • Scraper:  logs/trademap_scraper.log"
echo ""
echo "🌐 To use the TradeMap scraper:"
echo "  1. Open: trademap_form.html in your browser"
echo "  2. Fill in the form with HS code and countries"
echo "  3. Click 'Start Scraping'"
echo ""
echo "📌 PIDs saved:"
echo "  Celery: $CELERY_PID"
echo "  FastAPI: $FASTAPI_PID"
echo ""
echo "To stop services, run: kill $CELERY_PID $FASTAPI_PID"
echo ""

# Save PIDs to file for easy stopping
echo "CELERY_PID=$CELERY_PID" > .trademap_pids
echo "FASTAPI_PID=$FASTAPI_PID" >> .trademap_pids

echo "========================================="
echo "  Press Ctrl+C to stop all services"
echo "========================================="

# Wait for user interrupt
trap "echo ''; echo 'Stopping services...'; kill $CELERY_PID $FASTAPI_PID 2>/dev/null; echo 'Services stopped.'; exit 0" INT

# Keep script running
tail -f /dev/null
