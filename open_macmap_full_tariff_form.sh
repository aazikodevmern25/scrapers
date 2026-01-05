#!/bin/bash

# Open MacMap Full Tariff Form Script
# Opens the full tariff scraping form in the default browser

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                  Opening MacMap Full Tariff Form                            ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""

FORM_PATH="/home/aaziko/scrapers/static/macmap_full_tariff_form.html"

# Check if form exists
if [ ! -f "$FORM_PATH" ]; then
    echo "❌ Error: Form not found at $FORM_PATH"
    exit 1
fi

echo "📋 Opening MacMap Full Tariff Form..."
echo ""
echo "🌍 Form Location: $FORM_PATH"
echo ""
echo "⚠️  IMPORTANT NOTES:"
echo "   • This scraper fetches ALL HS codes and years for each country"
echo "   • Each country may take several hours to complete"
echo "   • Make sure FastAPI server is running on port 8888"
echo ""
echo "🚀 To start services if not running:"
echo "   ./start_ngrok_macmap.sh"
echo ""

# Try to open in default browser
if command -v xdg-open > /dev/null; then
    xdg-open "file://$FORM_PATH" 2>/dev/null &
    echo "✅ Form opened in default browser!"
elif command -v firefox > /dev/null; then
    firefox "file://$FORM_PATH" 2>/dev/null &
    echo "✅ Form opened in Firefox!"
elif command -v google-chrome > /dev/null; then
    google-chrome "file://$FORM_PATH" 2>/dev/null &
    echo "✅ Form opened in Chrome!"
else
    echo "⚠️  Could not auto-open browser. Please manually open:"
    echo "   file://$FORM_PATH"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
