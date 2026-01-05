#!/bin/bash

echo "Opening port 1080 for external access..."

# Try UFW first
if command -v ufw &> /dev/null; then
    echo "Using UFW..."
    sudo ufw allow 1080/tcp
    sudo ufw status
fi

# Try iptables
if command -v iptables &> /dev/null; then
    echo "Using iptables..."
    sudo iptables -I INPUT -p tcp --dport 1080 -j ACCEPT
    sudo iptables -L -n | grep 1080
fi

# Try firewalld
if command -v firewall-cmd &> /dev/null; then
    echo "Using firewalld..."
    sudo firewall-cmd --permanent --add-port=1080/tcp
    sudo firewall-cmd --reload
    sudo firewall-cmd --list-ports
fi

echo ""
echo "Port 1080 should now be open!"
echo "Test with: curl http://192.168.1.49:1080/"
