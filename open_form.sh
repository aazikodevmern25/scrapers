#!/bin/bash

# Script to open the TradeMap form in default browser

HTML_FILE="$(pwd)/trademap_form.html"

echo "Opening TradeMap form in browser..."
echo "File: $HTML_FILE"

# Try different methods to open browser
if command -v xdg-open > /dev/null; then
    xdg-open "$HTML_FILE"
elif command -v gnome-open > /dev/null; then
    gnome-open "$HTML_FILE"
elif command -v firefox > /dev/null; then
    firefox "$HTML_FILE" &
elif command -v google-chrome > /dev/null; then
    google-chrome "$HTML_FILE" &
elif command -v chromium-browser > /dev/null; then
    chromium-browser "$HTML_FILE" &
else
    echo ""
    echo "Could not detect browser. Please open this file manually:"
    echo "$HTML_FILE"
fi
