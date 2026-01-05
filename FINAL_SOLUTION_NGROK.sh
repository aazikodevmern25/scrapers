#!/bin/bash

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                                                                ║"
echo "║    🌍 FINAL SOLUTION: NGROK WITH YOUR DOMAIN                  ║"
echo "║                                                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

DOMAIN="scraper.aaziko.com"

echo "Your server has Coolify/Traefik which makes direct domain complex."
echo "Ngrok is the EASIEST solution!"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 1: Upgrade Ngrok to Paid Plan"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1. Go to: https://dashboard.ngrok.com/billing/subscription"
echo "2. Choose 'Personal' plan ($8/month)"
echo "3. Complete payment"
echo ""
read -p "Have you upgraded to paid plan? (yes/no): " UPGRADED

if [ "$UPGRADED" != "yes" ]; then
    echo ""
    echo "❌ Please upgrade first, then run this script again."
    exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 2: Add Your Domain in Ngrok"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1. Go to: https://dashboard.ngrok.com/cloud-edge/domains"
echo "2. Click 'New Domain'"
echo "3. Select 'Use your own domain'"
echo "4. Enter: $DOMAIN"
echo "5. Ngrok will show you a CNAME target"
echo ""
echo "Example CNAME: abc123.ngrok-agent.com"
echo ""
read -p "Enter the CNAME target from ngrok: " CNAME_TARGET

if [ -z "$CNAME_TARGET" ]; then
    echo "❌ No CNAME entered. Exiting."
    exit 1
fi

echo ""
echo "✅ CNAME target: $CNAME_TARGET"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 3: Update Your DNS Record"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "⚠️  IMPORTANT: Change from A record to CNAME record!"
echo ""
echo "In your domain dashboard:"
echo ""
echo "1. DELETE the A record:"
echo "   Type: A"
echo "   Name: scraper"
echo "   Value: 202.47.115.6"
echo ""
echo "2. CREATE a CNAME record:"
echo "   Type: CNAME"
echo "   Name: scraper"
echo "   Value: $CNAME_TARGET"
echo "   TTL: 1 Hour"
echo ""
read -p "Have you updated DNS? (yes/no): " DNS_UPDATED

if [ "$DNS_UPDATED" != "yes" ]; then
    echo ""
    echo "⚠️  Please update DNS first, then continue."
    echo ""
    read -p "Press Enter when DNS is updated..."
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 4: Stop Current Ngrok (if running)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

pkill ngrok
echo "✅ Stopped old ngrok"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 5: Start Ngrok with Your Domain"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Create startup script
cat > /home/aaziko/scrapers/start_ngrok_custom_domain.sh << EOF
#!/bin/bash
# Start ngrok with custom domain

echo "🌍 Starting ngrok with domain: $DOMAIN"

# Kill existing ngrok
pkill ngrok

# Start ngrok with your domain
nohup ngrok http --domain=$DOMAIN 8888 > logs/ngrok.log 2>&1 &

sleep 3

echo ""
echo "✅ Ngrok started!"
echo ""
echo "Your permanent URL:"
echo "   https://$DOMAIN"
echo ""
echo "Direct links:"
echo "   https://$DOMAIN/trademap-form"
echo "   https://$DOMAIN/api/v1/health"
echo ""
EOF

chmod +x /home/aaziko/scrapers/start_ngrok_custom_domain.sh

# Start ngrok
bash /home/aaziko/scrapers/start_ngrok_custom_domain.sh

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 6: Wait for DNS Propagation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "DNS changes take 5-30 minutes to propagate."
echo ""
echo "Check DNS:"
echo "  nslookup $DOMAIN"
echo ""
echo "Should show CNAME: $CNAME_TARGET"
echo ""

echo "═══════════════════════════════════════════════════════════════"
echo "✅ SETUP COMPLETE!"
echo ""
echo "Your PERMANENT URL:"
echo ""
echo "   🌍 https://$DOMAIN"
echo ""
echo "Features:"
echo "   ✅ Never changes (even after restart)"
echo "   ✅ Automatic HTTPS/SSL"
echo "   ✅ No server configuration"
echo "   ✅ No Coolify/Traefik conflicts"
echo ""
echo "To restart ngrok after server reboot:"
echo "   bash /home/aaziko/scrapers/start_ngrok_custom_domain.sh"
echo ""
echo "═══════════════════════════════════════════════════════════════"
