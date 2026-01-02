#!/bin/bash

# View ONLY NEW scraped data (last 10 minutes)

echo "========================================="
echo "  TradeMap - View NEW Scraped Data"
echo "========================================="
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Get current time minus 10 minutes (in milliseconds)
TIME_10_MIN_AGO=$(date -d '10 minutes ago' +%s)
TIME_10_MIN_AGO_MS=$((TIME_10_MIN_AGO * 1000))

echo -e "${BLUE}Showing data scraped in last 10 minutes...${NC}"
echo ""

# Count new documents
NEW_COUNT=$(mongosh "mongodb://admin:Aaziko%21%40%23123@202.47.115.6:27017/Dhruval?authSource=admin" --quiet --eval "
  var tenMinAgo = new Date(Date.now() - 10*60*1000);
  db.trademap.countDocuments({DateCreated: {\$gte: tenMinAgo}});
" 2>/dev/null)

if [ "$NEW_COUNT" -eq 0 ]; then
    echo -e "${YELLOW}⚠ No new data in last 10 minutes${NC}"
    echo ""
    echo "Total documents in database:"
    TOTAL=$(mongosh "mongodb://admin:Aaziko%21%40%23123@202.47.115.6:27017/Dhruval?authSource=admin" --quiet --eval "db.trademap.countDocuments()" 2>/dev/null)
    echo -e "${GREEN}$TOTAL${NC} documents"
    echo ""
    echo "Submit a new scraping task via the form!"
    echo "Run: ./open_form.sh"
else
    echo -e "${GREEN}✓ Found $NEW_COUNT new documents!${NC}"
    echo ""
    echo "========================================="
    echo -e "${BLUE}New Scraped Data:${NC}"
    echo "========================================="
    
    mongosh "mongodb://admin:Aaziko%21%40%23123@202.47.115.6:27017/Dhruval?authSource=admin" --quiet --eval "
      var tenMinAgo = new Date(Date.now() - 10*60*1000);
      db.trademap.find({DateCreated: {\$gte: tenMinAgo}}, {
        HsCode: 1, 
        ProductName: 1,
        'Data.Country1': 1, 
        'Data.Country2': 1, 
        Mode: 1, 
        DateCreated: 1
      }).sort({DateCreated: -1}).forEach(doc => {
        print('---');
        print('🆕 NEW - HS Code: ' + doc.HsCode);
        print('   Product: ' + doc.ProductName);
        print('   Route: ' + doc.Data.Country1 + ' → ' + doc.Data.Country2);
        print('   Mode: ' + doc.Mode);
        print('   Scraped: ' + doc.DateCreated);
      });
    " 2>/dev/null
fi

echo ""
echo "========================================="
echo -e "${BLUE}Quick Commands:${NC}"
echo "========================================="
echo "View all data:    ./view_scraped_data.sh"
echo "Monitor scraping: ./monitor_scraping.sh"
echo "View new data:    ./view_new_data.sh"
echo "Open form:        ./open_form.sh"
echo ""
