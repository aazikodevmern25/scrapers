#!/bin/bash

# Start ngrok tunnel for MacMap Form
# This exposes the FastAPI server (port 8888) to the internet

echo "========================================="
echo "  Starting ngrok for MacMap Access"
echo "========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if FastAPI is running
if ! curl -s http://localhost:8888/api/v1/health > /dev/null 2>&1; then
    echo -e "${RED}✗${NC} FastAPI server is not running on port 8888!"
    echo ""
    echo "Please start MacMap services first:"
    echo -e "  ${YELLOW}./start_macmap.sh${NC}"
    echo ""
    read -p "Do you want to start services now? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Starting MacMap services..."
        ./start_macmap.sh &
        echo "Waiting 10 seconds for services to start..."
        sleep 10
    else
        echo "Exiting..."
        exit 1
    fi
fi

echo -e "${GREEN}✓${NC} FastAPI server is running"
echo ""

# Kill any existing ngrok processes on port 8888
echo "Checking for existing ngrok tunnels..."
pkill -f "ngrok.*8888" 2>/dev/null
sleep 2

# Start ngrok
echo -e "${YELLOW}Starting ngrok tunnel...${NC}"
echo ""

# Start ngrok in background and save PID
ngrok http 8888 --log=stdout > logs/ngrok.log 2>&1 &
NGROK_PID=$!

echo "ngrok PID: $NGROK_PID"
echo "Waiting for ngrok to initialize..."
sleep 5

# Get the public URL
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✓ ngrok tunnel is running!${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Try to get URL from ngrok API
NGROK_URL=""
for i in {1..10}; do
    NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | grep -o 'https://[^"]*\.ngrok-free\.app' | head -1)
    if [ ! -z "$NGROK_URL" ]; then
        break
    fi
    sleep 1
done

if [ -z "$NGROK_URL" ]; then
    echo -e "${YELLOW}⚠${NC}  Could not auto-detect ngrok URL"
    echo ""
    echo "Please check the ngrok dashboard:"
    echo -e "  ${BLUE}http://localhost:4040${NC}"
    echo ""
    echo "Or check logs:"
    echo "  tail -f logs/ngrok.log"
else
    echo -e "${GREEN}🌍 Your MacMap is now accessible from ANYWHERE!${NC}"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo -e "${YELLOW}📋 MacMap Form (Web Interface):${NC}"
    echo -e "   ${GREEN}$NGROK_URL/static/macmap_tariff_form.html${NC}"
    echo ""
    echo -e "${YELLOW}📋 Alternative - Direct Form Upload:${NC}"
    echo "   You need to upload macmap_tariff_form.html to:"
    echo -e "   ${GREEN}$NGROK_URL${NC}"
    echo ""
    echo -e "${YELLOW}🔌 API Endpoints:${NC}"
    echo -e "   ${BLUE}$NGROK_URL/api/v1/scrape/tariff/bulk${NC}"
    echo -e "   ${BLUE}$NGROK_URL/api/v1/scrape/tariff${NC}"
    echo -e "   ${BLUE}$NGROK_URL/docs${NC} (API Documentation)"
    echo ""
    echo -e "${YELLOW}📊 Dashboard:${NC}"
    echo -e "   ${BLUE}$NGROK_URL${NC} (Main Dashboard)"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo -e "${YELLOW}📱 Share these URLs with anyone!${NC}"
    echo ""
    echo -e "${GREEN}✓${NC} Works on any device (phone, tablet, computer)"
    echo -e "${GREEN}✓${NC} Works from anywhere in the world"
    echo -e "${GREEN}✓${NC} No VPN or port forwarding needed"
    echo ""
    
    # Save URLs to file
    cat > ngrok_urls.txt << EOF
MacMap ngrok Access URLs
Generated: $(date)

🌍 PUBLIC ACCESS (Share these URLs):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 MacMap Form:
   $NGROK_URL/static/macmap_tariff_form.html
   
📋 API Documentation:
   $NGROK_URL/docs
   
📊 Dashboard:
   $NGROK_URL
   
🔌 Bulk API:
   POST $NGROK_URL/api/v1/scrape/tariff/bulk

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 How to Use:
1. Open the MacMap Form URL in any browser
2. Fill in HS codes and countries
3. Click "Generate and Queue Tasks"
4. Tasks will run on this server

⏱️  Valid until: ngrok tunnel is stopped
🔒 Security: Add authentication if needed

EOF
    
    echo -e "${GREEN}✓${NC} URLs saved to: ${BLUE}ngrok_urls.txt${NC}"
    echo ""
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo -e "${YELLOW}📊 ngrok Dashboard (Local):${NC}"
echo -e "   ${BLUE}http://localhost:4040${NC}"
echo ""
echo -e "${YELLOW}📝 Logs:${NC}"
echo "   logs/ngrok.log"
echo ""
echo -e "${YELLOW}🛑 To Stop:${NC}"
echo "   Press Ctrl+C or run: kill $NGROK_PID"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Save PID
echo $NGROK_PID > .ngrok_pid

echo -e "${GREEN}ngrok is running in the background...${NC}"
echo ""
echo "Press Ctrl+C to stop ngrok"
echo ""

# Keep script running
trap "echo ''; echo 'Stopping ngrok...'; kill $NGROK_PID 2>/dev/null; echo 'ngrok stopped.'; exit 0" INT

# Monitor ngrok
tail -f logs/ngrok.log
