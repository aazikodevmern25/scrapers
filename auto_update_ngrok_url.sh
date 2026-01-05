#!/bin/bash

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                                                                ║"
echo "║         🔄 AUTO-UPDATE NGROK URL (FREE SOLUTION)              ║"
echo "║                                                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

cd /home/aaziko/scrapers

# Get current ngrok URL
echo "🔍 Getting current ngrok URL..."
NGROK_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | grep -o '"public_url":"https://[^"]*"' | cut -d'"' -f4 | head -1)

if [ -z "$NGROK_URL" ]; then
    echo "❌ Ngrok not running! Start it first:"
    echo "   ngrok http 8888"
    exit 1
fi

echo "✅ Current ngrok URL: $NGROK_URL"
echo ""

# Save to file
echo "$NGROK_URL" > current_ngrok_url.txt
echo "📝 Saved to: current_ngrok_url.txt"
echo ""

# Create a simple redirect page
cat > static/index.html << EOF
<!DOCTYPE html>
<html>
<head>
    <title>Scraper Dashboard - Auto Redirect</title>
    <meta http-equiv="refresh" content="0;url=$NGROK_URL/trademap-form">
    <style>
        body {
            font-family: Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .container {
            text-align: center;
            padding: 40px;
            background: rgba(255,255,255,0.1);
            border-radius: 20px;
            backdrop-filter: blur(10px);
        }
        h1 { margin: 0 0 20px 0; }
        .url { 
            background: rgba(255,255,255,0.2);
            padding: 15px;
            border-radius: 10px;
            margin: 20px 0;
            word-break: break-all;
        }
        a {
            color: #fff;
            text-decoration: none;
            background: rgba(255,255,255,0.3);
            padding: 10px 20px;
            border-radius: 5px;
            display: inline-block;
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 Redirecting to Scraper...</h1>
        <p>Current URL:</p>
        <div class="url">$NGROK_URL</div>
        <p>If not redirected, <a href="$NGROK_URL/trademap-form">click here</a></p>
    </div>
</body>
</html>
EOF

echo "✅ Created redirect page"
echo ""

# Display the URL prominently
cat << EOF

═══════════════════════════════════════════════════════════════

🌍 YOUR CURRENT NGROK URL:

   $NGROK_URL

📋 DIRECT LINKS:

   Dashboard:     $NGROK_URL/
   TradeMap Form: $NGROK_URL/trademap-form
   Health Check:  $NGROK_URL/api/v1/health

⚠️  IMPORTANT: This URL changes when server restarts!

💡 SOLUTIONS:
   1. Upgrade to ngrok paid plan for permanent URL
   2. Run this script after each restart
   3. Bookmark the URL and update after restart

═══════════════════════════════════════════════════════════════

EOF

# Copy URL to clipboard if xclip is available
if command -v xclip &> /dev/null; then
    echo "$NGROK_URL/trademap-form" | xclip -selection clipboard
    echo "📋 URL copied to clipboard!"
    echo ""
fi
