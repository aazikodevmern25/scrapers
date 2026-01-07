#!/bin/bash

##############################################################################
# EXIMPEDIA SETUP VERIFICATION SCRIPT
##############################################################################

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║          EXIMPEDIA SETUP VERIFICATION                            ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# 1. Check MongoDB connectivity
echo -e "${YELLOW}1. Testing MongoDB connection (202.47.115.6:27017)...${NC}"
if timeout 5 bash -c "cat < /dev/null > /dev/tcp/202.47.115.6/27017" 2>/dev/null; then
    echo -e "${GREEN}   ✓ MongoDB is accessible${NC}"
else
    echo -e "${RED}   ✗ Cannot reach MongoDB${NC}"
fi

# 2. Check .env file
echo -e "${YELLOW}2. Checking .env configuration...${NC}"
if [ -f .env ]; then
    if grep -q "MONGO_URI.*202.47.115.6:27017" .env && grep -q "MONGO_DB=Dhruval" .env; then
        echo -e "${GREEN}   ✓ .env configured correctly${NC}"
    else
        echo -e "${RED}   ✗ .env configuration incorrect${NC}"
    fi
else
    echo -e "${RED}   ✗ .env file not found${NC}"
fi

# 3. Check if eximpedia form exists
echo -e "${YELLOW}3. Checking eximpedia form template...${NC}"
if [ -f "templates/eximpedia_form.html" ]; then
    echo -e "${GREEN}   ✓ Form template exists${NC}"
else
    echo -e "${RED}   ✗ Form template missing${NC}"
fi

# 4. Check if FastAPI route was added
echo -e "${YELLOW}4. Checking FastAPI eximpedia route...${NC}"
if grep -q "eximpedia-form" core/main.py; then
    echo -e "${GREEN}   ✓ Eximpedia route added to main.py${NC}"
else
    echo -e "${RED}   ✗ Eximpedia route not found${NC}"
fi

# 5. Check scripts
echo -e "${YELLOW}5. Checking startup scripts...${NC}"
if [ -x "start_eximpedia.sh" ] && [ -x "stop_eximpedia.sh" ]; then
    echo -e "${GREEN}   ✓ Scripts exist and are executable${NC}"
else
    echo -e "${RED}   ✗ Scripts missing or not executable${NC}"
fi

# 6. Check Redis
echo -e "${YELLOW}6. Checking Redis...${NC}"
if redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}   ✓ Redis is running${NC}"
else
    echo -e "${YELLOW}   ⚠ Redis not running (will be started automatically)${NC}"
fi

# 7. Check if FastAPI is running
echo -e "${YELLOW}7. Checking FastAPI backend...${NC}"
if lsof -Pi :1080 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${GREEN}   ✓ FastAPI running on port 1080${NC}"
else
    echo -e "${YELLOW}   ⚠ FastAPI not running (will be started by script)${NC}"
fi

# 8. Check eximpedia workers
echo -e "${YELLOW}8. Checking Eximpedia workers...${NC}"
WORKER_COUNT=$(ps aux | grep 'celery.*eximpedia' | grep -v grep | wc -l)
if [ $WORKER_COUNT -gt 0 ]; then
    echo -e "${GREEN}   ✓ $WORKER_COUNT Eximpedia worker(s) running${NC}"
else
    echo -e "${YELLOW}   ⚠ No workers running (will be started by script)${NC}"
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}SETUP VERIFICATION COMPLETE${NC}"
echo ""
echo -e "${YELLOW}Ready to start? Run:${NC}"
echo -e "   ./start_eximpedia.sh"
echo ""
