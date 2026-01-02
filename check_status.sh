#!/bin/bash

# Service Status Checker for TradeMap Scraper

echo "========================================="
echo "  TradeMap Scraper - Service Status"
echo "========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check MongoDB
echo -n "MongoDB:       "
if pgrep -x mongod > /dev/null; then
    PID=$(pgrep -x mongod)
    echo -e "${GREEN}✓ Running${NC} (PID: $PID)"
else
    echo -e "${RED}✗ Not Running${NC}"
fi

# Check Redis
echo -n "Redis:         "
if pgrep redis-server > /dev/null; then
    PID=$(pgrep redis-server | head -1)
    echo -e "${GREEN}✓ Running${NC} (PID: $PID)"
else
    echo -e "${RED}✗ Not Running${NC}"
fi

# Check FastAPI
echo -n "FastAPI:       "
if lsof -i :1080 > /dev/null 2>&1; then
    PID=$(lsof -ti :1080)
    echo -e "${GREEN}✓ Running${NC} (PID: $PID, Port: 1080)"
    # Test if API responds
    if curl -s http://localhost:1080/api/v1/health > /dev/null 2>&1; then
        echo "               ${GREEN}✓ API responding${NC}"
    else
        echo "               ${YELLOW}⚠ Port open but API not responding${NC}"
    fi
else
    echo -e "${RED}✗ Not Running${NC}"
    echo "               To start: uvicorn core.main:app --host 0.0.0.0 --port 1080"
fi

# Check Celery Worker
echo -n "Celery Worker: "
if pgrep -f "celery.*trademap" > /dev/null; then
    PID=$(pgrep -f "celery.*trademap")
    echo -e "${GREEN}✓ Running${NC} (PID: $PID)"
else
    echo -e "${RED}✗ Not Running${NC}"
    echo "               To start: celery -A celery_app.tasks worker -Q trademap --loglevel=info"
fi

echo ""
echo "========================================="
echo "  Summary"
echo "========================================="

# Count running services
RUNNING=0
[ $(pgrep -x mongod > /dev/null; echo $?) -eq 0 ] && ((RUNNING++))
[ $(pgrep redis-server > /dev/null; echo $?) -eq 0 ] && ((RUNNING++))
[ $(lsof -i :1080 > /dev/null 2>&1; echo $?) -eq 0 ] && ((RUNNING++))
[ $(pgrep -f "celery.*trademap" > /dev/null; echo $?) -eq 0 ] && ((RUNNING++))

echo "$RUNNING out of 4 services running"
echo ""

if [ $RUNNING -eq 4 ]; then
    echo -e "${GREEN}✅ All services are running!${NC}"
    echo ""
    echo "You can now:"
    echo "  1. Open trademap_form.html in browser"
    echo "  2. Submit scraping tasks"
    echo ""
    echo "To open form: xdg-open trademap_form.html"
elif [ $RUNNING -eq 2 ]; then
    echo -e "${YELLOW}⚠️  MongoDB and Redis running, but FastAPI/Celery need to start${NC}"
    echo ""
    echo "Quick start: ./start_trademap.sh"
else
    echo -e "${RED}❌ Some services are not running${NC}"
    echo ""
    echo "To start all: ./start_trademap.sh"
fi

echo "========================================="
