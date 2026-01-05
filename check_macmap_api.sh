#!/bin/bash

echo "════════════════════════════════════════════════════════════"
echo "  MacMap API Status Checker"
echo "════════════════════════════════════════════════════════════"
echo ""

# Test MacMap API
echo "Testing MacMap API..."
HTTP_CODE=$(curl -s -w "%{http_code}" -o /dev/null --max-time 10 "https://www.macmap.org/api/getyears?datatype=Tariff&reporters=156")

echo "HTTP Status: $HTTP_CODE"
echo ""

if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ SUCCESS! MacMap API is WORKING!"
    echo ""
    echo "API is back online. You can now:"
    echo "  1. Start workers: ./start_macmap_workers.sh"
    echo "  2. Submit tasks via form"
    echo "  3. Data will save successfully"
    echo ""
elif [ "$HTTP_CODE" = "000" ]; then
    echo "❌ FAILED! MacMap API is DOWN"
    echo ""
    echo "API is not responding. This means:"
    echo "  • MacMap server is offline"
    echo "  • No scraping possible right now"
    echo "  • Try again in 2-4 hours"
    echo ""
    echo "Test again later with: ./check_macmap_api.sh"
    echo ""
else
    echo "⚠️  WARNING! Unexpected HTTP code: $HTTP_CODE"
    echo ""
    echo "This might mean:"
    echo "  • API is partially working"
    echo "  • API is rate-limiting"
    echo "  • Network issues"
    echo ""
fi

echo "════════════════════════════════════════════════════════════"
