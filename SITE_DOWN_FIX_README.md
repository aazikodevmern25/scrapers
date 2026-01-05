# 🔧 Site Down Issue - ROOT CAUSE & FIX

## ❌ PROBLEM
When accessing vendor.aaziko.com, buyer.aaziko.com, or admin.aaziko.com, all sites showed the **Macmap Scraper API** instead of the correct applications.

## 🎯 ROOT CAUSE
**Coolify's Traefik proxy crashed** and nginx hijacked port 80/443, routing ALL domains to the scraper.

### What Happened:
1. **Coolify uses Traefik** as reverse proxy for all your apps (vendor, buyer, admin)
2. **Traefik stopped running** (container exited)
3. **nginx was running on port 80**, catching all HTTP traffic
4. nginx's config at `/etc/nginx/sites-enabled/scraper.aaziko.com` proxied **everything** to `localhost:8888` (scraper)
5. All domains → nginx → scraper ❌

## ✅ SOLUTION APPLIED

### 1. Stopped nginx to free port 80
```bash
sudo systemctl stop nginx
```

### 2. Restarted Coolify's Traefik proxy
```bash
docker start coolify-proxy
```

### 3. Disabled nginx auto-start (prevent future conflicts)
```bash
sudo systemctl disable nginx
```

### 4. Verified sites are working
- vendor.aaziko.com ✅ Redirects to HTTPS
- buyer.aaziko.com ✅ Redirects to HTTPS  
- admin.aaziko.com ✅ Redirects to HTTPS
- Traefik is now handling all traffic properly

## 📋 SCRAPER ACCESS OPTIONS

### Option 1: Add Scraper to Coolify (RECOMMENDED)
Deploy the scraper as a Docker service in Coolify:
1. Go to Coolify dashboard (http://yourserver:8000)
2. Create new resource → Docker Compose
3. Add scraper with domain: scraper.aaziko.com
4. Coolify will automatically configure Traefik routing

### Option 2: Direct Port Access
Access scraper directly via port:
- http://yourserver:8888

### Option 3: Configure nginx on different port (Advanced)
If you need nginx for scraper specifically:
```bash
# Edit nginx config to listen on port 8080 instead
sudo nano /etc/nginx/sites-available/scraper.aaziko.com

# Change:
# listen 80; 
# To:
# listen 8080;

# Then restart nginx
sudo systemctl start nginx
```

## 🚨 IMPORTANT: WHY THIS HAPPENED

**Coolify manages port 80/443 via Traefik.** Never run nginx on these ports while using Coolify!

### Conflict Chain:
```
Port 80 (HTTP)
  ├─ Coolify Traefik (SHOULD own this) ✅
  └─ nginx (WAS competing for this) ❌ CONFLICT!
```

## 🔒 PREVENTION

### ✅ DO:
- Let Coolify/Traefik handle port 80/443
- Deploy apps through Coolify
- If Traefik crashes, restart it: `docker restart coolify-proxy`

### ❌ DON'T:
- Run nginx on port 80/443 alongside Coolify
- Use `systemctl enable nginx` when using Coolify
- Manually configure reverse proxies for Coolify-managed domains

## 📊 MONITORING

### Check if Traefik is running:
```bash
docker ps | grep coolify-proxy
```

### Check what's on port 80:
```bash
sudo lsof -i :80
```

### Restart Coolify proxy if needed:
```bash
docker restart coolify-proxy
```

## 📝 SUMMARY
- **Problem**: Traefik down → nginx hijacked port 80 → all sites showed scraper
- **Fix**: Stopped nginx → Started Traefik → Sites working ✅
- **Prevention**: nginx disabled, Coolify manages all routing

---
**Date Fixed**: January 5, 2026
**Fixed By**: Cascade AI Assistant
