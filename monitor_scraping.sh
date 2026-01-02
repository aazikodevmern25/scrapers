#!/bin/bash

# Monitor TradeMap Scraping Progress

echo "========================================="
echo "  TradeMap Scraping Monitor"
echo "========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}1. Checking Celery Worker Status...${NC}"
if pgrep -f "celery.*trademap" > /dev/null; then
    echo -e "${GREEN}✓ Celery worker is running${NC}"
else
    echo -e "${RED}✗ Celery worker is NOT running${NC}"
    exit 1
fi

echo ""
echo -e "${BLUE}2. Last 20 lines of scraper log:${NC}"
echo "----------------------------------------"
if [ -f logs/trademap_scraper.log ]; then
    tail -20 logs/trademap_scraper.log
else
    echo -e "${YELLOW}⚠ No scraper log found yet${NC}"
fi

echo ""
echo "========================================="
echo -e "${BLUE}3. Checking MongoDB for scraped data...${NC}"
echo "========================================="

# Count documents in trademap collection
COUNT=$(mongosh "mongodb://admin:Aaziko%21%40%23123@202.47.115.6:27017/Dhruval?authSource=admin" --quiet --eval "db.trademap.countDocuments()" 2>/dev/null)

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ MongoDB connected${NC}"
    echo "Total documents in trademap collection: ${GREEN}$COUNT${NC}"
    
    if [ "$COUNT" -gt 0 ]; then
        echo ""
        echo "Latest document:"
        mongosh "mongodb://admin:Aaziko%21%40%23123@202.47.115.6:27017/Dhruval?authSource=admin" --quiet --eval "db.trademap.find().sort({DateCreated: -1}).limit(1).pretty()" 2>/dev/null
    else
        echo -e "${YELLOW}⚠ No data scraped yet (collection is empty)${NC}"
    fi
else
    echo -e "${RED}✗ Could not connect to MongoDB${NC}"
fi

echo ""
echo "========================================="
echo -e "${BLUE}4. Current Celery Tasks:${NC}"
echo "========================================="
celery -A celery_app.tasks inspect active -q 2>/dev/null || echo "No active tasks"

echo ""
echo "========================================="
echo -e "${BLUE}5. Watch logs in real-time:${NC}"
echo "========================================="
echo "Run: tail -f logs/trademap_scraper.log"
echo ""
