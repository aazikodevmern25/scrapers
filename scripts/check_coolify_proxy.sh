#!/bin/bash

# Quick script to check if Coolify proxy is running
# Run this if sites are not accessible

echo "🔍 Checking Coolify Proxy Status..."
echo ""

# Check if coolify-proxy container is running
if docker ps | grep -q "coolify-proxy"; then
    echo "✅ Coolify Traefik proxy is RUNNING"
    docker ps | grep coolify-proxy | awk '{print "   Container:", $NF, "| Status:", $(NF-1)}'
else
    echo "❌ Coolify Traefik proxy is NOT RUNNING"
    echo ""
    echo "🔧 Fix: Run this command to restart it:"
    echo "   docker start coolify-proxy"
    echo ""
    
    # Check if nginx is blocking port 80
    if sudo lsof -i :80 2>/dev/null | grep -q "nginx"; then
        echo "⚠️  WARNING: nginx is running on port 80!"
        echo "   This will block Coolify's Traefik proxy"
        echo ""
        echo "🔧 Fix: Stop nginx first:"
        echo "   sudo systemctl stop nginx"
        echo "   docker start coolify-proxy"
    fi
    exit 1
fi

echo ""
echo "🌐 Checking port 80 (HTTP)..."
PORT_80_PROCESS=$(sudo lsof -i :80 -P -n 2>/dev/null | grep LISTEN | head -1 | awk '{print $1}')
if [ "$PORT_80_PROCESS" == "traefik" ]; then
    echo "✅ Port 80 is owned by Traefik (correct)"
elif [ "$PORT_80_PROCESS" == "nginx" ]; then
    echo "❌ Port 80 is owned by nginx (WRONG - conflicts with Coolify!)"
    echo "   Run: sudo systemctl stop nginx"
else
    echo "⚠️  Port 80 is owned by: $PORT_80_PROCESS"
fi

echo ""
echo "🌐 Checking port 443 (HTTPS)..."
PORT_443_PROCESS=$(sudo lsof -i :443 -P -n 2>/dev/null | grep LISTEN | head -1 | awk '{print $1}')
if [ "$PORT_443_PROCESS" == "traefik" ]; then
    echo "✅ Port 443 is owned by Traefik (correct)"
elif [ "$PORT_443_PROCESS" == "nginx" ]; then
    echo "❌ Port 443 is owned by nginx (WRONG - conflicts with Coolify!)"
    echo "   Run: sudo systemctl stop nginx"
else
    echo "⚠️  Port 443 is owned by: $PORT_443_PROCESS"
fi

echo ""
echo "📋 Summary:"
echo "   - Coolify proxy should own ports 80 and 443"
echo "   - nginx should be disabled when using Coolify"
echo "   - All apps (vendor/buyer/admin) are routed by Traefik"
echo ""
