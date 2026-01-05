#!/bin/bash

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                                                                ║"
echo "║         ☁️  CLOUDFLARE TUNNEL SETUP (FREE ALTERNATIVE)        ║"
echo "║                                                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

echo "📋 CLOUDFLARE TUNNEL - FREE PERMANENT URL"
echo ""
echo "Benefits:"
echo "  ✅ 100% FREE"
echo "  ✅ Permanent URL (never changes)"
echo "  ✅ Your own domain (e.g., scraper.yourdomain.com)"
echo "  ✅ Better than ngrok free"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "REQUIREMENTS:"
echo "  1. A domain name (e.g., yourdomain.com)"
echo "  2. Cloudflare account (free)"
echo ""

read -p "Do you have a domain name? (yes/no): " HAS_DOMAIN

if [ "$HAS_DOMAIN" != "yes" ]; then
    echo ""
    echo "❌ You need a domain name first."
    echo ""
    echo "💡 OPTIONS:"
    echo "   1. Buy domain from: Namecheap, GoDaddy (~$10/year)"
    echo "   2. Free domain from: Freenom.com"
    echo "   3. Use ngrok paid plan instead ($8/month)"
    echo ""
    exit 1
fi

echo ""
echo "📥 Installing Cloudflare Tunnel..."
echo ""

# Download cloudflared
if ! command -v cloudflared &> /dev/null; then
    wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
    sudo dpkg -i cloudflared-linux-amd64.deb
    rm cloudflared-linux-amd64.deb
    echo "✅ Cloudflared installed"
else
    echo "✅ Cloudflared already installed"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 SETUP STEPS:"
echo ""
echo "1️⃣  Login to Cloudflare:"
echo "    cloudflared tunnel login"
echo ""
echo "2️⃣  Create tunnel:"
echo "    cloudflared tunnel create scraper"
echo ""
echo "3️⃣  Route your domain:"
echo "    cloudflared tunnel route dns scraper scraper.yourdomain.com"
echo ""
echo "4️⃣  Run tunnel:"
echo "    cloudflared tunnel --url http://localhost:8888 run scraper"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "After setup, your URL will be:"
echo "  https://scraper.yourdomain.com"
echo ""
echo "This URL is PERMANENT and FREE!"
echo ""
