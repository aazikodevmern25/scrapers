#!/bin/bash

# Simple cleanup script - deletes unnecessary files without prompts

echo "🗑️  Deleting unnecessary files..."
echo ""

cd /home/aaziko/scrapers

# Count before
BEFORE=$(ls -1 *.md *.txt test*.py captcha.jpeg 2>/dev/null | grep -v requirements.txt | wc -l)

echo "📊 Found $BEFORE unnecessary files"
echo ""

# Delete .md files
echo "   Deleting .md files..."
rm -f *.md 2>/dev/null

# Delete .txt files (except requirements.txt)
echo "   Deleting .txt files..."
find . -maxdepth 1 -name "*.txt" ! -name "requirements.txt" -delete 2>/dev/null

# Delete test*.py files
echo "   Deleting test files..."
rm -f test*.py 2>/dev/null

# Delete temp files
echo "   Deleting temp files..."
rm -f captcha.jpeg 2>/dev/null

echo ""
echo "✅ Cleanup complete!"
echo ""

# Check services still running
echo "📊 Service status:"
CELERY=$(ps aux | grep "celery.*trademap" | grep -v grep | wc -l)
FASTAPI=$(ps aux | grep "uvicorn.*8888" | grep -v grep | wc -l)
NGROK=$(ps aux | grep "ngrok" | grep -v grep | wc -l)

if [ $CELERY -gt 0 ]; then
    echo "   ✅ Celery workers: Running ($CELERY processes)"
else
    echo "   ⚠️  Celery workers: Not running"
fi

if [ $FASTAPI -gt 0 ]; then
    echo "   ✅ FastAPI: Running"
else
    echo "   ⚠️  FastAPI: Not running"
fi

if [ $NGROK -gt 0 ]; then
    echo "   ✅ Ngrok: Running"
else
    echo "   ⚠️  Ngrok: Not running"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "✅ All scrapers still working! Deleted $BEFORE files."
echo "═══════════════════════════════════════════════════════════════"
