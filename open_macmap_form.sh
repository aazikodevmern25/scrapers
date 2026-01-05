#!/bin/bash

# Script to open MacMap Tariff form in default browser

FORM_PATH="$(pwd)/macmap_tariff_form.html"

echo "========================================="
echo "  Opening MacMap Tariff Form"
echo "========================================="
echo ""
echo "Form location: $FORM_PATH"
echo ""

# Check if services are running
if ! curl -s http://localhost:8888/api/v1/health > /dev/null 2>&1; then
    echo "⚠️  WARNING: FastAPI server is not running!"
    echo ""
    echo "The form will open, but you won't be able to submit tasks."
    echo ""
    echo "To start services, run:"
    echo "  ./start_macmap.sh"
    echo ""
    read -p "Press Enter to continue anyway, or Ctrl+C to cancel..."
fi

# Detect OS and open browser
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    if command -v xdg-open > /dev/null; then
        xdg-open "$FORM_PATH"
    elif command -v google-chrome > /dev/null; then
        google-chrome "$FORM_PATH"
    elif command -v firefox > /dev/null; then
        firefox "$FORM_PATH"
    else
        echo "Could not detect browser. Please open manually:"
        echo "  file://$FORM_PATH"
    fi
elif [[ "$OSTYPE" == "darwin"* ]]; then
    open "$FORM_PATH"
elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
    start "$FORM_PATH"
else
    echo "Could not detect OS. Please open manually:"
    echo "  file://$FORM_PATH"
fi

echo ""
echo "✅ MacMap Tariff form opened in browser!"
echo ""
echo "📋 Quick Usage Guide:"
echo "  1. Fill in HS Codes (comma-separated)"
echo "  2. Fill in Importing Countries (comma-separated)"
echo "  3. Fill in Exporting Countries (comma-separated)"
echo "  4. Select Year"
echo "  5. Click 'Generate and Queue Tasks'"
echo ""
echo "Example:"
echo "  HS Codes: 010121, 010129, 29211"
echo "  Importing: United States, China"
echo "  Exporting: India, Germany"
echo "  Year: 2023"
echo "  → Creates 3 × 2 × 2 = 12 tasks"
echo ""
