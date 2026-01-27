# Ngrok Auto-Start Guide for All Scrapers

## Overview
This guide explains how to automatically start all 3 scrapers (Eximpedia, TradeMap, MacMap) with automatic ngrok URL generation when your server restarts.

**Important:** Port 8001 is used for FastAPI (Port 8000 is avoided as it's used by Cloudflare)

---

## Quick Start

### 1. Manual Start (Recommended for first use)
```bash
cd /home/aaziko/scrapers
bash start_all_scrapers.sh
```

This script will:
- ✅ Start FastAPI on port 8001
- ✅ Generate a new ngrok URL
- ✅ Start all workers (Eximpedia, TradeMap, MacMap)
- ✅ Save URLs to files

After running, check `CURRENT_NGROK_URL.txt` for all URLs.

---

### 2. Restart Services (When ngrok URL expires)
```bash
cd /home/aaziko/scrapers
bash restart_all_services.sh
```

This will:
- Stop old FastAPI and ngrok
- Start new instances with fresh ngrok URL
- Keep workers running (no interruption)
- Update all URL files

---

### 3. Auto-Start on Server Reboot

#### Setup Crontab (One-time setup)
```bash
crontab -e
```

Add this line:
```
@reboot /home/aaziko/scrapers/auto_start_on_reboot.sh
```

Save and exit. Now all scrapers will auto-start after server reboot.

---

## Port Configuration

**Port 8001** is used for FastAPI backend
- Eximpedia, TradeMap, and MacMap all use the same backend
- Port 8000 is **avoided** (reserved for Cloudflare)
- Ngrok tunnels port 8001 to public URL

---

## Access URLs After Start

After starting, you'll have access to:

### Eximpedia
- Form: `{NGROK_URL}/eximpedia-form`
- Mirror Data: `{NGROK_URL}/eximpedia-mirror-data-form`

### TradeMap
- Form: `{NGROK_URL}/trademap-form`

### MacMap
- Tariff Form: `{NGROK_URL}/static/macmap_tariff_form.html`
- Trade Agreements: `{NGROK_URL}/static/macmap_trade_agreements_form.html`

### API
- Documentation: `{NGROK_URL}/docs`
- Health Check: `{NGROK_URL}/api/v1/health`

---

## URL Files

URLs are saved to these files:
- `CURRENT_NGROK_URL.txt` - All scrapers (main file)
- `EXIMPEDIA_NGROK_URL.txt` - Eximpedia only
- `TRADEMAP_NGROK_URL.txt` - TradeMap only
- `MACMAP_NGROK_URL.txt` - MacMap only

---

## Workers Information

### Eximpedia Workers
- 1 Task Creator Worker
- 4 Scraper Workers (2 concurrent tasks each)
- Queue: `eximpedia_task_creator`, `eximpedia`

### TradeMap Workers
- 10 Workers (3 concurrent tasks each)
- Queue: `trademap`

### MacMap Workers
- 4 Workers (3 concurrent tasks each)
- Queue: `macmap_tariff`

---

## Troubleshooting

### Check if services are running
```bash
# Check FastAPI
curl http://localhost:8001/api/v1/health

# Check ngrok
curl http://localhost:4040/api/tunnels

# Check workers
ps aux | grep celery
```

### View logs
```bash
# FastAPI logs
tail -f logs/fastapi.log

# Ngrok logs
tail -f logs/ngrok.log

# Worker logs
tail -f logs/eximpedia_worker1.log
tail -f logs/celery_trademap_worker1.log
tail -f logs/celery_macmap_tariff_worker1.log
```

### Restart everything
```bash
# Kill all services
pkill -9 -f uvicorn
pkill -9 ngrok
pkill -9 -f celery

# Start fresh
bash start_all_scrapers.sh
```

---

## Important Notes

1. **Ngrok URL expires** when server restarts - always use `restart_all_services.sh` to get new URL
2. **Port 8000 is reserved** - all scrapers use port 8001
3. **Workers keep running** when you restart FastAPI/ngrok
4. **All 3 scrapers** share the same FastAPI backend and ngrok URL
5. **Auto-start on reboot** requires crontab setup (see section 3)

---

## Summary of Scripts

| Script | Purpose | When to Use |
|--------|---------|-------------|
| `start_all_scrapers.sh` | Start everything from scratch | First time or after complete shutdown |
| `restart_all_services.sh` | Restart FastAPI + ngrok only | When ngrok URL expires |
| `auto_start_on_reboot.sh` | Auto-start on server boot | Runs automatically via crontab |

---

## Example Workflow

1. **Server restarts**
   - Auto-start script runs via crontab
   - New ngrok URL generated
   - Check `CURRENT_NGROK_URL.txt` for URLs

2. **Ngrok URL expires (but server still running)**
   ```bash
   bash restart_all_services.sh
   ```
   - New URL generated
   - Workers keep running

3. **Need to restart workers**
   ```bash
   bash start_all_scrapers.sh
   ```
   - Everything restarts fresh

---

Last Updated: $(date)
