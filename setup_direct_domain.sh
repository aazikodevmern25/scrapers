#!/bin/bash

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                                                                ║"
echo "║      🌍 SETUP DIRECT DOMAIN ACCESS (NO NGROK)                 ║"
echo "║                                                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Get domain name
read -p "Enter your domain (e.g., scraper.yourdomain.com): " DOMAIN

if [ -z "$DOMAIN" ]; then
    echo "❌ No domain entered. Exiting."
    exit 1
fi

echo ""
echo "📋 Setting up: $DOMAIN"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "⚠️  This script needs sudo access for some steps."
    echo ""
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 1: Installing Nginx"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

sudo apt update
sudo apt install -y nginx

echo ""
echo "✅ Nginx installed"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 2: Configuring Nginx for $DOMAIN"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Create Nginx config
sudo tee /etc/nginx/sites-available/$DOMAIN > /dev/null << EOF
server {
    listen 80;
    server_name $DOMAIN;

    # Redirect all HTTP to HTTPS (after SSL setup)
    # return 301 https://\$server_name\$request_uri;

    # For now, proxy to FastAPI
    location / {
        proxy_pass http://localhost:8888;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # WebSocket support (if needed)
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeouts for long-running requests
        proxy_connect_timeout 600s;
        proxy_send_timeout 600s;
        proxy_read_timeout 600s;
    }
}
EOF

# Enable site
sudo ln -sf /etc/nginx/sites-available/$DOMAIN /etc/nginx/sites-enabled/

# Test Nginx config
echo "Testing Nginx configuration..."
sudo nginx -t

if [ $? -eq 0 ]; then
    echo "✅ Nginx configuration valid"
    sudo systemctl reload nginx
    echo "✅ Nginx reloaded"
else
    echo "❌ Nginx configuration error!"
    exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 3: Opening Firewall Ports"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if ufw is installed
if command -v ufw &> /dev/null; then
    echo "Opening ports 80 and 443..."
    sudo ufw allow 80/tcp
    sudo ufw allow 443/tcp
    echo "✅ Firewall ports opened"
else
    echo "⚠️  UFW not found. You may need to open ports manually."
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 4: Installing SSL Certificate (Let's Encrypt)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Install certbot
sudo apt install -y certbot python3-certbot-nginx

echo ""
echo "⚠️  IMPORTANT: Make sure DNS is propagated before continuing!"
echo "   Check with: nslookup $DOMAIN"
echo ""
read -p "Is DNS working? (yes/no): " DNS_READY

if [ "$DNS_READY" = "yes" ]; then
    echo ""
    echo "Getting SSL certificate..."
    sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos --email admin@$DOMAIN || {
        echo "⚠️  SSL setup failed. You can run it manually later:"
        echo "   sudo certbot --nginx -d $DOMAIN"
    }
else
    echo ""
    echo "⚠️  Skipping SSL for now. Run this later when DNS is ready:"
    echo "   sudo certbot --nginx -d $DOMAIN"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 5: Stopping Ngrok (if running)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

pkill ngrok
echo "✅ Ngrok stopped (if it was running)"

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "✅ SETUP COMPLETE!"
echo ""
echo "Your scraper is now accessible at:"
echo ""
echo "   http://$DOMAIN"
echo ""
if [ "$DNS_READY" = "yes" ]; then
    echo "   https://$DOMAIN (with SSL)"
fi
echo ""
echo "Direct links:"
echo "   http://$DOMAIN/trademap-form"
echo "   http://$DOMAIN/api/v1/health"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "📋 NEXT STEPS:"
echo ""
echo "1. Wait for DNS propagation (5-30 minutes)"
echo "   Check: nslookup $DOMAIN"
echo ""
echo "2. If SSL failed, run manually:"
echo "   sudo certbot --nginx -d $DOMAIN"
echo ""
echo "3. Test your scraper:"
echo "   curl http://$DOMAIN/api/v1/health"
echo ""
echo "═══════════════════════════════════════════════════════════════"
