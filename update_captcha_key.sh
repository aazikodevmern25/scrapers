#!/bin/bash

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                                                                ║"
echo "║         🔑 UPDATE 2CAPTCHA API KEY                            ║"
echo "║                                                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

echo "Current API key: baf9821867a0c0414a15c5b6ac77599c"
echo "Current balance: $0.00014 (empty)"
echo ""

read -p "Enter your NEW 2Captcha API key: " NEW_KEY

if [ -z "$NEW_KEY" ]; then
    echo "❌ No key entered. Exiting."
    exit 1
fi

echo ""
echo "Testing new API key..."

# Test the key
BALANCE=$(curl -s "https://2captcha.com/res.php?key=$NEW_KEY&action=getbalance")

if [[ "$BALANCE" == ERROR* ]]; then
    echo "❌ Invalid API key: $BALANCE"
    exit 1
fi

echo "✅ Valid key! Balance: \$$BALANCE"
echo ""

# Update the code
echo "Updating trademap.py..."

sed -i "s/'apiKey': 'baf9821867a0c0414a15c5b6ac77599c'/'apiKey': '$NEW_KEY'/g" /home/aaziko/scrapers/scrapers/trademap/trademap.py

echo "✅ API key updated!"
echo ""

# Restart workers
echo "Restarting Celery workers..."
pkill -9 -f "celery.*trademap"
sleep 2
cd /home/aaziko/scrapers
nohup celery -A celery_app.tasks worker --loglevel=info -Q trademap --concurrency=10 > logs/celery_trademap.log 2>&1 &

echo "✅ Workers restarted!"
echo ""

echo "═══════════════════════════════════════════════════════════════"
echo "✅ DONE!"
echo ""
echo "New API key: $NEW_KEY"
echo "Balance: \$$BALANCE"
echo ""
echo "You can now start scraping!"
echo "═══════════════════════════════════════════════════════════════"
