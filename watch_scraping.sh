#!/bin/bash

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         🔴 LIVE SCRAPING MONITOR - Press Ctrl+C to Exit      ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Watch the log file in real-time with color
tail -f logs/celery_trademap.log | grep --line-buffered -E "Starting|received|SUCCESS|FAILURE|Scraping|Saved|Error" | while read line; do
    # Color code the output
    if echo "$line" | grep -q "SUCCESS"; then
        echo -e "\033[0;32m✅ $line\033[0m"  # Green for success
    elif echo "$line" | grep -q "FAILURE\|Error"; then
        echo -e "\033[0;31m❌ $line\033[0m"  # Red for failure
    elif echo "$line" | grep -q "Starting"; then
        echo -e "\033[0;33m🚀 $line\033[0m"  # Yellow for starting
    elif echo "$line" | grep -q "Saved"; then
        echo -e "\033[0;36m💾 $line\033[0m"  # Cyan for saved
    else
        echo -e "\033[0;37m📋 $line\033[0m"  # White for others
    fi
done
