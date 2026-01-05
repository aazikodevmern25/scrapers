# 🌐 How to Access Your Scraper - Multiple Methods

## Method 1: Same Machine (Localhost) ✅
If you're on the **same server** where scraper is running:
```
http://localhost:8888/
http://127.0.0.1:8888/
```

## Method 2: Same Network (LAN) 
If your device is on the **same WiFi/network** (192.168.1.x):
```
http://192.168.1.49:8888/
```

**Check your device's IP first:**
- On Windows: `ipconfig` (should show 192.168.1.xxx)
- On Mac/Linux: `ifconfig` (should show 192.168.1.xxx)
- On Phone: Settings → WiFi → IP Address

**If NOT on same network:** Connect to same WiFi/router first!

## Method 3: SSH Tunnel (From Anywhere) 🔐
If you're on a **different network**, use SSH tunnel:

**From your local computer, run:**
```bash
ssh -L 8888:localhost:8888 aaziko@192.168.1.49
```

**Then access:**
```
http://localhost:8888/
```

## Method 4: Reverse Proxy (Public Access) 🌍

### Option A: Using ngrok (Easy, Free)
```bash
# On the server
cd /home/aaziko/scrapers
./ngrok http 8888
```
Will give you a public URL like: `https://xxxx-xx-xx-xx.ngrok.io`

### Option B: Using SSH Reverse Tunnel
```bash
# From server to your local machine
ssh -R 8888:localhost:8888 your-username@your-local-ip
```

## Method 5: Port Forwarding (Router) 🏠

### If you want access from Internet:
1. Login to your router (usually 192.168.1.1)
2. Find "Port Forwarding" settings
3. Forward **External Port 8888** → **Internal IP 192.168.1.49:8888**
4. Access via your public IP: `http://YOUR_PUBLIC_IP:8888`

**Find your public IP:**
```bash
curl ifconfig.me
```

---

## ⚡ Quick Test - Which Method Works?

### Test 1: From the server itself
```bash
curl http://localhost:8888/api/v1/health
```
✅ Should work = Server is running

### Test 2: From another device on same network
```bash
ping 192.168.1.49
curl http://192.168.1.49:8888/api/v1/health
```
✅ Should work = Same network access OK
❌ Doesn't work = Different network OR router blocking

### Test 3: Check your device's network
**Windows:**
```cmd
ipconfig | findstr IPv4
```

**Mac/Linux:**
```bash
ip addr | grep "inet "
```

**Should show:** `192.168.1.xxx` (same as server)
**If shows:** Different subnet = Not on same network!

---

## 🆘 Troubleshooting

### "This site can't be reached"
**Reason 1:** You're not on the same network
- **Fix:** Connect to the same WiFi/router as server

**Reason 2:** Router is blocking inter-device communication
- **Fix:** Enable "AP Isolation" or "Client Isolation" OFF in router settings

**Reason 3:** Your device's firewall
- **Fix:** Temporarily disable firewall on your device

### "Connection Refused"
- **Fix:** Server is down, restart it:
```bash
cd /home/aaziko/scrapers
bash start_trademap.sh
```

### "Connection Timeout"
- **Fix:** Firewall blocking, run:
```bash
sudo ufw allow 8888/tcp
sudo ufw reload
```

---

## 🎯 RECOMMENDED METHOD

**If you're in the same location:**
1. Make sure your laptop/phone is on same WiFi
2. Go to: `http://192.168.1.49:8888/`

**If you're remote (different location):**
1. Use ngrok for quick access
2. Or set up SSH tunnel

---

## 📱 Access from Phone/Tablet

1. Connect phone to **same WiFi** as server
2. Open browser
3. Type: `http://192.168.1.49:8888/`
4. Done!

**If doesn't work:**
- Check WiFi name is exactly the same
- Try turning off mobile data
- Try `http://192.168.1.49:8888` (no trailing slash)

---

**Server IP:** 192.168.1.49  
**Port:** 8888  
**Status:** ✅ RUNNING
