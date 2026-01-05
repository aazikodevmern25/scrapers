#!/bin/bash

# Workspace Cleanup Script
# Removes unused folders, temp files, and documentation
# Preserves scraping functionality

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                    Workspace Cleanup Script                                 ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""

cd /home/aaziko/scrapers

# Count before cleanup
echo "📊 Current Status:"
echo "  Total files/folders: $(ls -1 | wc -l)"
echo "  Trademap temp folders: $(find . -maxdepth 1 -type d -name "trademap_*" | wc -l)"
echo "  .md documentation files: $(find . -maxdepth 1 -type f -name "*.md" | wc -l)"
echo "  .txt guide files: $(find . -maxdepth 1 -type f -name "*GUIDE*.txt" -o -name "*COMPLETE*.txt" -o -name "*DIAGRAM*.txt" | wc -l)"
echo ""

# Calculate disk usage before
BEFORE_SIZE=$(du -sh . 2>/dev/null | awk '{print $1}')
echo "  Current disk usage: $BEFORE_SIZE"
echo ""

read -p "⚠️  This will delete temporary files and documentation. Continue? (y/n): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Cleanup cancelled"
    exit 0
fi

echo ""
echo "🧹 Starting cleanup..."
echo ""

# 1. Remove Chrome/Selenium temporary directories
echo "1️⃣  Removing Chrome temporary directories (trademap_*)..."
TRADEMAP_COUNT=$(find . -maxdepth 1 -type d -name "trademap_*" | wc -l)
if [ $TRADEMAP_COUNT -gt 0 ]; then
    find . -maxdepth 1 -type d -name "trademap_*" -exec rm -rf {} + 2>/dev/null
    echo "   ✓ Removed $TRADEMAP_COUNT temporary Chrome directories"
else
    echo "   ✓ No trademap temp directories found"
fi
echo ""

# 2. Remove .md documentation files (keep README.md if exists)
echo "2️⃣  Removing .md documentation files..."
MD_FILES=(
    "ACCESS_METHODS.md"
    "DATA_STORAGE_INFO.md"
    "FIX_NGROK_ERROR.md"
    "MACMAP_FORM_GUIDE.md"
    "MACMAP_SUMMARY.md"
    "MACMAP_WEB_FORM_COMPLETE.md"
    "NGROK_ACCESS_GUIDE.md"
    "NGROK_SETUP_COMPLETE.md"
    "README_MACMAP.md"
    "SERVER_ACCESS_INFO.md"
    "START_MACMAP_GUIDE.md"
)

MD_REMOVED=0
for file in "${MD_FILES[@]}"; do
    if [ -f "$file" ]; then
        rm -f "$file"
        MD_REMOVED=$((MD_REMOVED + 1))
    fi
done
echo "   ✓ Removed $MD_REMOVED .md documentation files"
echo ""

# 3. Remove large text guide/diagram files
echo "3️⃣  Removing text guide/diagram files..."
TXT_FILES=(
    "ACCESS_FROM_ANYWHERE.txt"
    "CHANGES_SUMMARY.txt"
    "COMPASS_GUIDE.txt"
    "CURRENT_NGROK_URL.txt"
    "DHRUVAL_DATABASE_ANSWER.txt"
    "FINAL_SETUP_COMPLETE.txt"
    "FINAL_STATUS.txt"
    "FIXED_SCRAPER_IS_WORKING.txt"
    "HOW_TO_MONITOR.txt"
    "HOW_TO_USE.txt"
    "MACMAP_ARCHITECTURE.txt"
    "MACMAP_FORM_DIAGRAM.txt"
    "MACMAP_NGROK_DIAGRAM.txt"
    "MACMAP_QUICK_START.txt"
    "NGROK_QUICK_START.txt"
    "NGROK_WORKING_NOW.txt"
    "PROBLEM_AND_SOLUTION.txt"
    "SCRAPER_STATUS_REPORT.txt"
    "SIMPLE_ACCESS.txt"
    "SUCCESS.txt"
)

TXT_REMOVED=0
for file in "${TXT_FILES[@]}"; do
    if [ -f "$file" ]; then
        rm -f "$file"
        TXT_REMOVED=$((TXT_REMOVED + 1))
    fi
done
echo "   ✓ Removed $TXT_REMOVED text guide files"
echo ""

# 4. Remove duplicate/unused HTML forms (keep only in static/)
echo "4️⃣  Removing duplicate HTML forms..."
HTML_REMOVED=0
if [ -f "macmap_tariff_form.html" ] && [ -f "static/macmap_tariff_form.html" ]; then
    rm -f "macmap_tariff_form.html"
    HTML_REMOVED=$((HTML_REMOVED + 1))
    echo "   ✓ Removed duplicate macmap_tariff_form.html (kept in static/)"
fi
if [ -f "trademap_form.html" ] && [ -f "static/trademap_form.html" ]; then
    rm -f "trademap_form.html"
    HTML_REMOVED=$((HTML_REMOVED + 1))
    echo "   ✓ Removed duplicate trademap_form.html (kept in static/)"
fi
if [ $HTML_REMOVED -eq 0 ]; then
    echo "   ✓ No duplicate HTML forms found"
fi
echo ""

# 5. Remove unused test files
echo "5️⃣  Removing test files..."
TEST_REMOVED=0
for file in test_chrome.py test_simple_selenium.py; do
    if [ -f "$file" ]; then
        rm -f "$file"
        TEST_REMOVED=$((TEST_REMOVED + 1))
    fi
done
echo "   ✓ Removed $TEST_REMOVED test files"
echo ""

# 6. Remove old PID files
echo "6️⃣  Cleaning old PID files..."
rm -f .macmap_pids .ngrok_pid 2>/dev/null
echo "   ✓ Removed old PID files"
echo ""

# 7. Remove unused directories
echo "7️⃣  Removing unused directories..."
UNUSED_DIRS=(
    "data-extractor-frontend"
    "downloaded_files"
)

DIR_REMOVED=0
for dir in "${UNUSED_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        rm -rf "$dir"
        DIR_REMOVED=$((DIR_REMOVED + 1))
    fi
done
echo "   ✓ Removed $DIR_REMOVED unused directories"
echo ""

# 8. Clean __pycache__ directories
echo "8️⃣  Cleaning Python cache files..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete 2>/dev/null
echo "   ✓ Removed Python cache files"
echo ""

# 9. Clean old log files (keep recent ones)
echo "9️⃣  Cleaning old log files (keeping last 3 days)..."
if [ -d "logs" ]; then
    find logs/ -name "*.log" -type f -mtime +3 -delete 2>/dev/null
    echo "   ✓ Removed old log files"
fi
echo ""

# Calculate disk usage after
AFTER_SIZE=$(du -sh . 2>/dev/null | awk '{print $1}')

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Cleanup Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📊 Summary:"
echo "  Before: $BEFORE_SIZE"
echo "  After:  $AFTER_SIZE"
echo ""
echo "🗑️  Removed:"
echo "  • $TRADEMAP_COUNT Chrome temp directories"
echo "  • $MD_REMOVED .md documentation files"
echo "  • $TXT_REMOVED .txt guide files"
echo "  • $HTML_REMOVED duplicate HTML forms"
echo "  • $TEST_REMOVED test files"
echo "  • $DIR_REMOVED unused directories"
echo "  • Python cache files"
echo "  • Old log files (>3 days)"
echo ""
echo "✅ Preserved:"
echo "  • All scrapers/ code"
echo "  • All celery_app/ code"
echo "  • All core/ code"
echo "  • Configuration files"
echo "  • Recent logs"
echo "  • Static files"
echo "  • PDF files"
echo "  • Payloads"
echo ""
echo "🔍 Verify scraping still works:"
echo "  python3 view_macmap_data.py"
echo "  tail -f logs/celery_macmap_tariff.log"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
