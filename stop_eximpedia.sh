#!/bin/bash

##############################################################################
# EXIMPEDIA SCRAPER STOP SCRIPT
# Stops all Eximpedia-related services
##############################################################################

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║          STOPPING EXIMPEDIA SCRAPER SYSTEM                       ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Change to script directory
cd "$(dirname "$0")"

# 1. Stop Eximpedia Workers
echo -e "${YELLOW}Stopping Eximpedia workers...${NC}"
WORKER_COUNT=$(ps aux | grep 'celery.*eximpedia' | grep -v grep | wc -l)

if [ $WORKER_COUNT -eq 0 ]; then
    echo -e "${GREEN}✓ No Eximpedia workers running${NC}"
else
    pkill -9 -f 'celery.*eximpedia' 2>/dev/null || true
    sleep 2
    echo -e "${GREEN}✓ Stopped $WORKER_COUNT Eximpedia worker(s)${NC}"
fi

# Remove PID files
rm -f .eximpedia_task_creator.pid
rm -f .eximpedia_worker*.pid

# 2. Stop Ngrok (optional - ask user)
echo ""
read -p "Stop ngrok tunnel? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Stopping ngrok...${NC}"
    if [ -f .eximpedia_ngrok_pid ]; then
        NGROK_PID=$(cat .eximpedia_ngrok_pid)
        kill -9 $NGROK_PID 2>/dev/null || true
        rm -f .eximpedia_ngrok_pid
    fi
    pkill -9 ngrok 2>/dev/null || true
    echo -e "${GREEN}✓ Ngrok stopped${NC}"
else
    echo -e "${YELLOW}⚠ Ngrok still running${NC}"
fi

# 3. Stop FastAPI (optional - ask user)
echo ""
read -p "Stop FastAPI backend? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Stopping FastAPI...${NC}"
    if [ -f .fastapi_pid ]; then
        FASTAPI_PID=$(cat .fastapi_pid)
        kill -9 $FASTAPI_PID 2>/dev/null || true
        rm -f .fastapi_pid
    fi
    pkill -9 -f 'uvicorn.*main:app' 2>/dev/null || true
    pkill -9 -f 'gunicorn.*main:app' 2>/dev/null || true
    echo -e "${GREEN}✓ FastAPI stopped${NC}"
else
    echo -e "${YELLOW}⚠ FastAPI still running (other scrapers may be using it)${NC}"
fi

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║          EXIMPEDIA SYSTEM STOPPED                                ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════╝${NC}"
echo ""
