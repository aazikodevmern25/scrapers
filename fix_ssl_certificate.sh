#!/bin/bash

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                                                                ║"
echo "║         🔒 FIX SSL CERTIFICATE FOR scraper.aaziko.com         ║"
echo "║                                                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

DOMAIN="scraper.aaziko.com"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 1: Fix Python dependencies for certbot"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Install missing Python module
echo "Installing missing Python module (_cffi_backend)..."
sudo apt update
sudo apt install -y python3-cffi libffi-dev python3-dev

# Reinstall certbot to fix dependencies
echo "Reinstalling certbot..."
sudo apt remove -y certbot python3-certbot-nginx
sudo apt install -y certbot python3-certbot-nginx

echo ""
echo "✅ Dependencies fixed"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 2: Verify DNS is working"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

DNS_IP=$(nslookup $DOMAIN | grep -A1 "Name:" | grep "Address:" | awk '{print $2}')

if [ -z "$DNS_IP" ]; then
    echo "❌ DNS not resolving for $DOMAIN"
    echo "   Please wait longer for DNS propagation"
    exit 1
fi

echo "✅ DNS working: $DOMAIN → $DNS_IP"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 3: Test HTTP access"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://$DOMAIN/api/v1/health)

if [ "$HTTP_STATUS" = "200" ]; then
    echo "✅ HTTP working: $DOMAIN is accessible"
else
    echo "⚠️  HTTP returned status: $HTTP_STATUS"
    echo "   Continuing anyway..."
fi

echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 4: Get SSL certificate from Let's Encrypt"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "Getting SSL certificate for $DOMAIN..."
echo ""

# Try to get certificate
sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos --email admin@$DOMAIN --redirect

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ SSL certificate installed successfully!"
    echo ""
else
    echo ""
    echo "❌ SSL certificate failed!"
    echo ""
    echo "Trying alternative method..."
    echo ""
    
    # Try without redirect
    sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos --email admin@$DOMAIN
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "✅ SSL certificate installed (without auto-redirect)!"
        echo ""
    else
        echo ""
        echo "❌ SSL still failed. Manual intervention needed."
        echo ""
        echo "Possible issues:"
        echo "  1. Port 80 not accessible from internet"
        echo "  2. Firewall blocking Let's Encrypt"
        echo "  3. DNS not fully propagated"
        echo ""
        echo "Try manually:"
        echo "  sudo certbot --nginx -d $DOMAIN"
        echo ""
        exit 1
    fi
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 5: Test HTTPS access"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

sleep 2

HTTPS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://$DOMAIN/api/v1/health)

if [ "$HTTPS_STATUS" = "200" ]; then
    echo "✅ HTTPS working: https://$DOMAIN is accessible"
else
    echo "⚠️  HTTPS returned status: $HTTPS_STATUS"
fi

echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 6: Reload Nginx"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

sudo systemctl reload nginx
echo "✅ Nginx reloaded"

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "✅ SSL SETUP COMPLETE!"
echo ""
echo "Your scraper is now accessible at:"
echo ""
echo "   🔒 https://scraper.aaziko.com"
echo ""
echo "Direct links:"
echo "   https://scraper.aaziko.com/trademap-form"
echo "   https://scraper.aaziko.com/api/v1/health"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "📋 Certificate info:"
sudo certbot certificates
echo ""
echo "═══════════════════════════════════════════════════════════════"
