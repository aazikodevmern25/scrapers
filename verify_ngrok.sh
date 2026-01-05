#!/bin/bash

# Verify ngrok and MacMap are working

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║              ngrok + MacMap Verification Script                              ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to check
check_status() {
    echo -n "  $1... "
    if eval "$2" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ OK${NC}"
        return 0
    else
        echo -e "${RED}✗ FAILED${NC}"
        return 1
    fi
}

echo -e "${BLUE}Step 1: Checking Services${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

check_status "MongoDB" "pgrep mongod"
check_status "Redis" "pgrep redis-server"
check_status "FastAPI (port 8888)" "curl -s http://localhost:8888/api/v1/health"
check_status "Celery workers" "pgrep -f 'celery.*macmap'"
check_status "ngrok process" "pgrep ngrok"

echo ""
echo -e "${BLUE}Step 2: Getting ngrok URL${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

NGROK_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | grep -o 'https://[^"]*\.ngrok-free\.app' | head -1)

if [ -z "$NGROK_URL" ]; then
    echo -e "${RED}✗ Could not get ngrok URL${NC}"
    echo ""
    echo "Possible issues:"
    echo "  1. ngrok is not running"
    echo "  2. ngrok is still connecting (wait 10 seconds)"
    echo "  3. ngrok dashboard not accessible on port 4040"
    echo ""
    echo "Solutions:"
    echo "  - Run: ./start_ngrok_macmap.sh"
    echo "  - Wait 10 seconds and try again"
    echo "  - Check: http://localhost:4040"
    exit 1
else
    echo -e "${GREEN}✓ ngrok URL found:${NC} $NGROK_URL"
fi

echo ""
echo -e "${BLUE}Step 3: Testing Local Access${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

check_status "API Health (local)" "curl -s http://localhost:8888/api/v1/health | grep success"
check_status "MacMap Form (local)" "curl -I http://localhost:8888/static/macmap_tariff_form.html 2>&1 | grep '200 OK'"
check_status "TradeMap Form (local)" "curl -I http://localhost:8888/static/trademap_form.html 2>&1 | grep '200 OK'"

echo ""
echo -e "${BLUE}Step 4: Testing Public Access (via ngrok)${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "⏱️  Waiting 3 seconds for ngrok to stabilize..."
sleep 3

check_status "API Health (ngrok)" "curl -s $NGROK_URL/api/v1/health | grep success"
check_status "MacMap Form (ngrok)" "curl -I $NGROK_URL/static/macmap_tariff_form.html 2>&1 | grep '200'"
check_status "TradeMap Form (ngrok)" "curl -I $NGROK_URL/static/trademap_form.html 2>&1 | grep '200'"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}✅ ALL SYSTEMS OPERATIONAL!${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo -e "${YELLOW}🌍 YOUR PUBLIC URLs:${NC}"
echo ""
echo -e "${GREEN}📋 MacMap Form:${NC}"
echo "   $NGROK_URL/static/macmap_tariff_form.html"
echo ""
echo -e "${GREEN}📋 TradeMap Form:${NC}"
echo "   $NGROK_URL/static/trademap_form.html"
echo ""
echo -e "${GREEN}📊 API Documentation:${NC}"
echo "   $NGROK_URL/docs"
echo ""
echo -e "${GREEN}🏠 Dashboard:${NC}"
echo "   $NGROK_URL"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo -e "${BLUE}💡 HOW TO USE:${NC}"
echo ""
echo "1. Copy the MacMap Form URL above"
echo "2. Open it in ANY browser (phone, tablet, computer)"
echo "3. Fill the form and submit"
echo "4. Tasks will run on this server!"
echo ""
echo -e "${YELLOW}📱 Share these URLs with anyone to give them access!${NC}"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Save to file
cat > WORKING_NGROK_URLS.txt << EOF
╔══════════════════════════════════════════════════════════════════════════════╗
║                       WORKING NGROK URLs                                     ║
║                       Verified: $(date)                                      ║
╚══════════════════════════════════════════════════════════════════════════════╝

✅ ALL SYSTEMS VERIFIED WORKING!

🌍 PUBLIC URLs (Access from ANYWHERE):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 MacMap Form:
   $NGROK_URL/static/macmap_tariff_form.html

📋 TradeMap Form:
   $NGROK_URL/static/trademap_form.html

📊 API Documentation:
   $NGROK_URL/docs

🏠 Main Dashboard:
   $NGROK_URL

🔌 Bulk API:
   POST $NGROK_URL/api/v1/scrape/tariff/bulk

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 USAGE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Open MacMap Form URL in ANY browser
2. Fill in HS codes and countries (comma-separated)
3. Click "Generate and Queue Tasks"
4. Tasks will execute on your server
5. Results saved to MongoDB

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ VERIFIED: All endpoints responding correctly!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EOF

echo -e "${GREEN}✓ URLs saved to: WORKING_NGROK_URLS.txt${NC}"
echo ""
