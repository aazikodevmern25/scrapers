# TradeMap Automated Processing System

## ✅ System Overview

The TradeMap automated system solves the problem where tasks get stuck in "pending" status and never process automatically. Now when you create trademap tasks, they are **automatically detected and processed** without any manual intervention.

## 🎯 What Problem Does This Solve?

**BEFORE (Old System):**
- ❌ Create tasks → They sit in MongoDB with status="pending" 
- ❌ Have to manually run task creator script
- ❌ Task creator waits for batches to complete before continuing
- ❌ Tasks get stuck, never complete
- ❌ Manual intervention required constantly

**AFTER (New Automated System):**
- ✅ Create tasks → Auto Processor detects them every 10 seconds
- ✅ Tasks automatically pushed to Celery workers
- ✅ Workers process continuously
- ✅ All tasks complete without intervention
- ✅ Just create and forget!

## 🚀 How to Use

### Start the System
```bash
cd /home/aaziko/scrapers
./start_trademap_system.sh
```

**What this does:**
1. Starts 10 TradeMap Celery workers (30 concurrent processes)
2. Starts Auto Processor that monitors for new tasks
3. System runs continuously in background

### Stop the System
```bash
./stop_trademap_system.sh
```

### Check System Status
```bash
# Check if auto processor is running
ps aux | grep trademap_auto_processor | grep -v grep

# Check workers
ps aux | grep 'celery.*trademap' | grep -v grep | wc -l

# View auto processor logs
tail -f logs/trademap_auto_processor.log

# View worker logs
tail -f logs/celery_trademap_worker1.log
```

### Check Task Status (MongoDB)
```bash
python3 -c "
from utils import db
success = db['scraper_tasks'].count_documents({'scraper': 'TradeMap', 'status': 'SUCCESS'})
pending = db['scraper_tasks'].count_documents({'scraper': 'TradeMap', 'status': 'PENDING'})
waiting = db['scraper_tasks'].count_documents({'scraper': 'TradeMap', 'status': 'pending'})
failed = db['scraper_tasks'].count_documents({'scraper': 'TradeMap', 'status': 'FAILED'})
total = success + pending + waiting + failed
print(f'TradeMap Tasks:')
print(f'  ✅ SUCCESS: {success}/{total}')
print(f'  ⏳ PENDING: {pending}')
print(f'  📋 Waiting: {waiting}')
print(f'  ❌ FAILED: {failed}')
"
```

## 📋 How It Works

```
┌─────────────────────────────────────────────────────────────┐
│ YOU CREATE TASK                                             │
│ (via API, form, or script)                                  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ MongoDB: Task saved with status="pending", task_id=""       │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ AUTO PROCESSOR (runs every 10 seconds)                      │
│ - Scans MongoDB for pending tasks                           │
│ - Finds your task                                            │
│ - Pushes to Celery queue                                     │
│ - Updates: status="PENDING", task_id="abc123..."            │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ CELERY WORKERS (10 workers, 30 concurrent processes)        │
│ - Pick up task from queue                                    │
│ - Run TradeMap scraper                                       │
│ - Save data to MongoDB trademap collection                   │
│ - Update task: status="SUCCESS"                             │
└─────────────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ DONE! Data saved in MongoDB                                  │
│ Collection: trademap                                         │
└─────────────────────────────────────────────────────────────┘
```

## 🔧 Configuration

Edit `trademap_auto_processor.py` to change:

```python
CHECK_INTERVAL = 10  # Seconds between checks for new tasks
BATCH_SIZE = 50      # Max tasks to process per batch
RATE_LIMIT = 0.1     # Delay between task submissions
```

## 📊 Monitoring

### Real-time Monitoring
```bash
# Watch auto processor activity
watch -n 5 'tail -20 logs/trademap_auto_processor.log'

# Watch task counts
watch -n 5 'python3 -c "from utils import db; print(db[\"scraper_tasks\"].count_documents({\"scraper\": \"TradeMap\", \"status\": \"SUCCESS\"}), \"completed\")"'
```

### Log Files
- **Auto Processor:** `logs/trademap_auto_processor.log`
- **Workers:** `logs/celery_trademap_worker1.log` to `worker10.log`
- **PID Files:** `.trademap_auto_processor.pid`, `.trademap_worker*.pid`

## 🔄 Auto-Start on Reboot

To make the system start automatically when server reboots, add to crontab:

```bash
crontab -e
```

Add this line:
```
@reboot cd /home/aaziko/scrapers && ./start_trademap_system.sh
```

## 🐛 Troubleshooting

### Problem: Tasks stuck in "pending" (lowercase)
**Solution:**
```bash
# Check if auto processor is running
ps aux | grep trademap_auto_processor

# If not running, start it
./start_trademap_system.sh
```

### Problem: Tasks stuck in "PENDING" (uppercase)
**Meaning:** Workers are processing, just slow
**Solution:** Wait, or add more workers by editing `start_trademap_system.sh` and increasing `WORKER_COUNT`

### Problem: No workers running
**Solution:**
```bash
./stop_trademap_system.sh
./start_trademap_system.sh
```

### Problem: Redis not running
**Solution:**
```bash
redis-server --daemonize yes
./start_trademap_system.sh
```

## 📝 Task Status Meanings

| Status | Meaning |
|--------|---------|
| `pending` (lowercase) | Task created, waiting for auto processor to pick up |
| `PENDING` (uppercase) | Task pushed to Celery, being processed by workers |
| `SUCCESS` | Task completed successfully, data saved |
| `FAILED` | Task failed after retries |

## ✨ Key Features

1. **Automatic Detection:** Finds new tasks every 10 seconds
2. **Continuous Processing:** Never stops monitoring
3. **No Manual Intervention:** Create and forget
4. **Robust:** Handles errors gracefully
5. **Scalable:** Easy to add more workers
6. **Observable:** Clear logs and status

## 🎯 Current Status

System is **OPERATIONAL** and processing tasks:
- ✅ Auto Processor: Running
- ✅ Workers: 10 workers, 30+ processes
- ✅ Currently Processing: Check with status command above

## 📞 Quick Commands

```bash
# Start system
./start_trademap_system.sh

# Stop system
./stop_trademap_system.sh

# Check status
ps aux | grep trademap

# View logs
tail -f logs/trademap_auto_processor.log

# Task counts
python3 -c "from utils import db; print('Success:', db['scraper_tasks'].count_documents({'scraper': 'TradeMap', 'status': 'SUCCESS'}))"
```

---

**Created:** January 27, 2026  
**System Status:** ✅ Fully Operational
