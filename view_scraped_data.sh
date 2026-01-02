#!/bin/bash

# View all scraped data from MongoDB

echo "========================================="
echo "  TradeMap Scraped Data Viewer"
echo "========================================="
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}Total documents in database:${NC}"
COUNT=$(mongosh "mongodb://admin:Aaziko%21%40%23123@202.47.115.6:27017/Dhruval?authSource=admin" --quiet --eval "db.trademap.countDocuments()")
echo -e "${GREEN}$COUNT${NC} documents"
echo ""

echo "========================================="
echo -e "${BLUE}Summary of all scraped data:${NC}"
echo "========================================="
mongosh "mongodb://admin:Aaziko%21%40%23123@202.47.115.6:27017/Dhruval?authSource=admin" --quiet --eval "
db.trademap.find({}, {
  HsCode: 1, 
  ProductName: 1,
  'Data.Country1': 1, 
  'Data.Country2': 1, 
  Mode: 1, 
  DateCreated: 1
}).sort({DateCreated: -1}).forEach(doc => {
  print('---');
  print('HS Code: ' + doc.HsCode);
  print('Product: ' + doc.ProductName);
  print('Route: ' + doc.Data.Country1 + ' → ' + doc.Data.Country2);
  print('Mode: ' + doc.Mode);
  print('Date: ' + doc.DateCreated);
});
"

echo ""
echo "========================================="
echo -e "${BLUE}View full data for a specific HS code:${NC}"
echo "========================================="
echo "Run: mongosh Dhruval --eval \"db.trademap.find({HsCode: 'YOUR_CODE'}).pretty()\""
echo ""

echo "========================================="
echo -e "${BLUE}Export data to JSON file:${NC}"
echo "========================================="
echo "Run: mongoexport --db=Dhruval --collection=trademap --out=trademap_export.json"
echo ""
