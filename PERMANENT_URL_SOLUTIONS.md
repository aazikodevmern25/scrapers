# 🌍 PERMANENT URL SOLUTIONS FOR NGROK

## ❌ THE PROBLEM

When using **FREE ngrok**, the URL changes every time:
- Server restarts
- Ngrok restarts
- After 2 hours (session timeout)

Example:
- Before: `https://c7ee853f5480.ngrok-free.app`
- After restart: `https://a1b2c3d4e5f6.ngrok-free.app` ❌ **DIFFERENT!**

---

## ✅ SOLUTIONS (3 OPTIONS)

### **OPTION 1: Ngrok Paid Plan** ⭐ **RECOMMENDED**

**Cost:** $8-10/month

**Benefits:**
- ✅ Fixed domain (e.g., `aaziko-scraper.ngrok.app`)
- ✅ **NEVER changes**, even after restart
- ✅ No expiration
- ✅ Professional
- ✅ Faster setup (5 minutes)

**How to set up:**

1. **Upgrade to paid:**
   - Go to: https://dashboard.ngrok.com/billing/subscription
   - Choose "Personal" or "Pro" plan

2. **Create fixed domain:**
   - Go to: https://dashboard.ngrok.com/cloud-edge/domains
   - Click "New Domain"
   - Choose name: `aaziko-scraper` (or any name)
   - You get: `aaziko-scraper.ngrok.app`

3. **Update startup command:**
   ```bash
   # OLD (random URL):
   ngrok http 8888
   
   # NEW (fixed URL):
   ngrok http --domain=aaziko-scraper.ngrok.app 8888
   ```

4. **Run setup script:**
   ```bash
   bash setup_ngrok_fixed_domain.sh
   ```

**Result:**
- URL: `https://aaziko-scraper.ngrok.app`
- **This URL NEVER changes!**
- Works forever, even after restart

---

### **OPTION 2: Cloudflare Tunnel** 💰 **FREE!**

**Cost:** FREE (requires domain name ~$10/year)

**Benefits:**
- ✅ 100% FREE (no monthly cost)
- ✅ Permanent URL
- ✅ Your own domain (e.g., `scraper.yourdomain.com`)
- ✅ Better performance than ngrok
- ✅ No bandwidth limits

**Requirements:**
- A domain name (buy from Namecheap, GoDaddy, etc.)
- Cloudflare account (free)

**How to set up:**

1. **Buy domain** (~$10/year):
   - Namecheap.com
   - GoDaddy.com
   - Or use existing domain

2. **Add domain to Cloudflare:**
   - Go to: https://dash.cloudflare.com
   - Add your domain
   - Update nameservers

3. **Install Cloudflare Tunnel:**
   ```bash
   bash setup_cloudflare_tunnel.sh
   ```

4. **Setup tunnel:**
   ```bash
   # Login
   cloudflared tunnel login
   
   # Create tunnel
   cloudflared tunnel create scraper
   
   # Route domain
   cloudflared tunnel route dns scraper scraper.yourdomain.com
   
   # Start tunnel
   cloudflared tunnel --url http://localhost:8888 run scraper
   ```

**Result:**
- URL: `https://scraper.yourdomain.com`
- **Permanent and FREE!**

---

### **OPTION 3: Auto-Update Script** 🔄 **FREE (WORKAROUND)**

**Cost:** FREE

**Benefits:**
- ✅ No cost
- ✅ Works with free ngrok
- ✅ Automatic URL detection

**Drawbacks:**
- ❌ URL still changes after restart
- ❌ Need to share new URL each time
- ❌ Not professional

**How it works:**
- Script detects current ngrok URL
- Saves it to file
- You share the new URL after restart

**Setup:**
```bash
# After each server restart, run:
bash auto_update_ngrok_url.sh
```

This will show you the new URL to share.

---

## 📊 COMPARISON

| Feature | Ngrok Paid | Cloudflare Tunnel | Free Ngrok + Script |
|---------|------------|-------------------|---------------------|
| **Cost** | $8-10/month | FREE (domain $10/year) | FREE |
| **Permanent URL** | ✅ YES | ✅ YES | ❌ NO |
| **Setup Time** | 5 minutes | 30 minutes | 2 minutes |
| **Professional** | ✅ YES | ✅ YES | ❌ NO |
| **Bandwidth** | Unlimited | Unlimited | Limited |
| **Custom Domain** | ❌ NO | ✅ YES | ❌ NO |
| **Best For** | Quick & Easy | Long-term & Free | Testing only |

---

## 🎯 RECOMMENDATION

### **For Production (Real Use):**
→ **Option 1: Ngrok Paid** ($8/month)
- Fastest setup
- Most reliable
- Professional URL
- Worth the cost for business use

### **For Long-term (Budget-conscious):**
→ **Option 2: Cloudflare Tunnel** (FREE)
- One-time domain cost ($10/year)
- Free forever after that
- Your own branded domain
- Better than ngrok free

### **For Testing Only:**
→ **Option 3: Auto-Update Script** (FREE)
- Not suitable for production
- URL changes frequently
- Only for development

---

## 🚀 QUICK START

### **Want permanent URL NOW?**

**Fastest (5 minutes):**
```bash
# 1. Upgrade ngrok (paid)
# 2. Run setup:
bash setup_ngrok_fixed_domain.sh
```

**Free but takes longer (30 minutes):**
```bash
# 1. Buy domain
# 2. Setup Cloudflare:
bash setup_cloudflare_tunnel.sh
```

**Temporary solution (2 minutes):**
```bash
# After each restart:
bash auto_update_ngrok_url.sh
```

---

## 📝 CURRENT STATUS

Your current setup:
- ✅ FastAPI running on port 8888
- ✅ Ngrok running (FREE plan)
- ❌ URL changes after restart

**Current URL:** Check with:
```bash
curl -s http://localhost:4040/api/tunnels | grep public_url
```

---

## 💡 MY RECOMMENDATION FOR YOU

Based on your use case (production scraper with 10 workers):

**→ Use Ngrok Paid Plan ($8/month)**

**Why?**
1. You're running a serious scraper (10 workers, 24/7)
2. $8/month is minimal for business use
3. Setup takes only 5 minutes
4. Professional and reliable
5. No domain management needed

**ROI:** If your scraper saves you 1 hour of manual work per month, it's worth it!

---

## 🔧 SETUP SCRIPTS AVAILABLE

All scripts are in `/home/aaziko/scrapers/`:

1. `setup_ngrok_fixed_domain.sh` - For ngrok paid plan
2. `setup_cloudflare_tunnel.sh` - For Cloudflare tunnel
3. `auto_update_ngrok_url.sh` - For free ngrok workaround

Run any script to get started!

---

## ❓ FAQ

**Q: Can I use free ngrok forever?**
A: Yes, but URL changes after every restart.

**Q: Is Cloudflare Tunnel really free?**
A: Yes! Only cost is domain name (~$10/year).

**Q: Which is better: ngrok paid or Cloudflare?**
A: Ngrok paid is easier. Cloudflare is cheaper long-term.

**Q: Will my scrapers stop working?**
A: No! Only the URL changes. Scrapers keep working.

**Q: Can I switch later?**
A: Yes! You can change solutions anytime.

---

## 📞 NEED HELP?

1. **Ngrok paid plan:** https://dashboard.ngrok.com
2. **Cloudflare tunnel:** https://dash.cloudflare.com
3. **Buy domain:** https://www.namecheap.com

---

**🎊 Choose your solution and get a permanent URL today!**
