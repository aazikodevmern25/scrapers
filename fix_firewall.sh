#!/bin/bash

echo "=================================="
echo "Opening Port 8888 for Network Access"
echo "=================================="

# Try iptables
echo "Adding firewall rule for port 8888..."
sudo iptables -I INPUT -p tcp --dport 8888 -j ACCEPT

# Try UFW if available
if command -v ufw &> /dev/null; then
    echo "Configuring UFW..."
    sudo ufw allow 8888/tcp
fi

# Try firewalld if available
if command -v firewall-cmd &> /dev/null; then
    echo "Configuring firewalld..."
    sudo firewall-cmd --permanent --add-port=8888/tcp
    sudo firewall-cmd --reload
fi

echo ""
echo "✅ Port 8888 is now open!"
echo ""
echo "Access your scraper at:"
echo "  http://192.168.1.49:8888/"
echo ""
echo "Test from this server:"
curl -I http://192.168.1.49:8888/ 2>&1 | head -5
