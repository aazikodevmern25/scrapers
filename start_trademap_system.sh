#!/bin/bash
##############################################################################
# Start TradeMap Complete System
# - Starts trademap workers
# - Starts auto-processor to monitor and push tasks
##############################################################################

set -e

cd "$(dirname "$0")"

echo "=========================================="
echo "🚀 Starting TradeMap System"
echo "=========================================="

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

# Kill any existing trademap processes
echo -e "${YELLOW}Cleaning up old processes...${NC}"
pkill -9 -f 'celery.*trademap' 2>/dev/null || true
pkill -9 -f 'trademap_auto_processor' 2>/dev/null || true
pkill -9 -f 'tradeMapTaskCreator' 2>/dev/null || true
sleep 2

# Check Redis
echo -e "${YELLOW}Checking Redis...${NC}"
if ! pgrep -x "redis-server" > /dev/null; then
    echo -e "${YELLOW}Starting Redis...${NC}"
    redis-server --daemonize yes
    sleep 2
fi
echo -e "${GREEN}✓ Redis running${NC}"

# Start TradeMap Workers
echo ""
echo -e "${BLUE}Starting TradeMap Workers...${NC}"
WORKER_COUNT=5  # Reduced from 10 to prevent Chrome driver overload

for i in $(seq 1 $WORKER_COUNT); do
    celery -A celery_app.tasks worker \
        --loglevel=info \
        -Q trademap \
        --concurrency=2 \
        --hostname=trademap_worker${i}@%h \
        --max-tasks-per-child=50 \
        --logfile=logs/celery_trademap_worker${i}.log \
        --pidfile=.trademap_worker${i}.pid \
        --detach
    sleep 1  # Increased delay to stagger Chrome startup
done

# Wait for workers to start
sleep 3

# Count workers
TRADEMAP_WORKERS=$(ps aux | grep 'celery.*trademap' | grep -v grep | wc -l)
echo -e "${GREEN}✓ Started $TRADEMAP_WORKERS trademap worker processes${NC}"

# Start Auto Processor
echo ""
echo -e "${BLUE}Starting TradeMap Auto Processor...${NC}"
nohup python3 trademap_auto_processor.py > logs/trademap_auto_processor.log 2>&1 &
PROCESSOR_PID=$!
echo $PROCESSOR_PID > .trademap_auto_processor.pid
sleep 2

if ps -p $PROCESSOR_PID > /dev/null; then
    echo -e "${GREEN}✓ Auto Processor started (PID: $PROCESSOR_PID)${NC}"
else
    echo -e "${RED}✗ Failed to start Auto Processor${NC}"
    exit 1
fi

# Start Status Updater
echo ""
echo -e "${BLUE}Starting TradeMap Status Updater...${NC}"
nohup python3 trademap_status_updater.py > logs/trademap_status_updater.log 2>&1 &
UPDATER_PID=$!
echo $UPDATER_PID > .trademap_status_updater.pid
sleep 2

if ps -p $UPDATER_PID > /dev/null; then
    echo -e "${GREEN}✓ Status Updater started (PID: $UPDATER_PID)${NC}"
else
    echo -e "${RED}✗ Failed to start Status Updater${NC}"
    exit 1
fi

# Display status
echo ""
echo "=========================================="
echo -e "${GREEN}✅ TradeMap System Ready${NC}"
echo "=========================================="
echo ""
echo -e "${BLUE}📊 System Status:${NC}"
echo -e "   Workers: $TRADEMAP_WORKERS processes"
echo -e "   Auto Processor: Running (PID: $PROCESSOR_PID)"
echo ""
echo -e "${BLUE}📝 Logs:${NC}"
echo -e "   Workers: logs/celery_trademap_worker*.log"
echo -e "   Auto Processor: logs/trademap_auto_processor.log"
echo ""
echo -e "${BLUE}💡 How it works:${NC}"
echo -e "   ✅ When you create tasks, they go to MongoDB with status='pending'"
echo -e "   ✅ Auto Processor monitors every 10s for new pending tasks"
echo -e "   ✅ New tasks are automatically pushed to Celery queue"
echo -e "   ✅ Workers process tasks and save results"
echo -e "   ✅ No manual intervention needed!"
echo ""
echo -e "${YELLOW}To stop: ./stop_trademap_system.sh${NC}"
echo ""
