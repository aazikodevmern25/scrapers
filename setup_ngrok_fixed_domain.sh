#!/bin/bash

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                                                                ║"
echo "║         🌍 SETUP NGROK WITH FIXED DOMAIN                      ║"
echo "║                                                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

echo "📋 STEPS TO GET PERMANENT NGROK URL:"
echo ""
echo "1️⃣  Go to: https://dashboard.ngrok.com/billing/subscription"
echo ""
echo "2️⃣  Upgrade to PAID plan ($8-10/month)"
echo ""
echo "3️⃣  Go to: https://dashboard.ngrok.com/cloud-edge/domains"
echo ""
echo "4️⃣  Click 'New Domain' and choose your domain name"
echo "    Example: aaziko-scraper.ngrok.app"
echo ""
echo "5️⃣  Copy your domain and paste it here:"
read -p "    Enter your fixed domain: " FIXED_DOMAIN
echo ""

if [ -z "$FIXED_DOMAIN" ]; then
    echo "❌ No domain entered. Exiting."
    exit 1
fi

echo "6️⃣  Creating startup script with fixed domain..."
echo ""

cat > /home/aaziko/scrapers/start_ngrok_fixed.sh << EOF
#!/bin/bash

# Start ngrok with fixed domain
echo "🌍 Starting ngrok with fixed domain: $FIXED_DOMAIN"

# Kill existing ngrok
pkill ngrok

# Start ngrok with your fixed domain
nohup ngrok http --domain=$FIXED_DOMAIN 8888 > logs/ngrok.log 2>&1 &

sleep 3

echo "✅ Ngrok started with PERMANENT URL:"
echo ""
echo "   https://$FIXED_DOMAIN"
echo ""
echo "This URL will NEVER change, even after server restart!"
echo ""
EOF

chmod +x /home/aaziko/scrapers/start_ngrok_fixed.sh

echo "✅ Script created: start_ngrok_fixed.sh"
echo ""
echo "7️⃣  To start ngrok with fixed domain, run:"
echo "    bash start_ngrok_fixed.sh"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "✅ Your URL will be: https://$FIXED_DOMAIN"
echo "   This URL is PERMANENT and never changes!"
echo "═══════════════════════════════════════════════════════════════"
