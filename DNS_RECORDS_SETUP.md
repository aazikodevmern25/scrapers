# 🌍 DNS RECORDS FOR SUBDOMAIN SETUP

## 📋 WHAT YOU NEED TO CREATE

You want to point your subdomain to your server so you can access the scraper.

---

## ✅ OPTION 1: Direct Server Access (A Record)

**Use this if:** Your server has a public IP address

### **DNS Record to Create:**

| Type | Name | Value | TTL |
|------|------|-------|-----|
| **A** | `scraper` | `YOUR_SERVER_PUBLIC_IP` | 1 Hour |

**Example:**
- Type: `A`
- Name: `scraper` (or `scraper.yourdomain.com`)
- Value: `202.47.115.6` (your server IP)
- TTL: `1 Hour` (or Auto)

**Result:**
- Your subdomain: `scraper.yourdomain.com`
- Points to: Your server at port 8888

**Then you need:**
- Reverse proxy (Nginx) on your server
- SSL certificate (Let's Encrypt)

---

## ✅ OPTION 2: Ngrok Tunnel (CNAME Record)

**Use this if:** You want to use ngrok with your domain

### **Step 1: Upgrade Ngrok to Paid**
- Go to: https://dashboard.ngrok.com/billing/subscription
- Upgrade to paid plan ($8/month)

### **Step 2: Get Ngrok Edge Domain**
- Go to: https://dashboard.ngrok.com/cloud-edge/domains
- Click "New Domain"
- Choose: "Use your own domain"
- You'll get a CNAME target like: `xxx.ngrok-agent.com`

### **Step 3: Create DNS Record:**

| Type | Name | Value | TTL |
|------|------|-------|-----|
| **CNAME** | `scraper` | `xxx.ngrok-agent.com` | 1 Hour |

**Example:**
- Type: `CNAME`
- Name: `scraper`
- Value: `abc123.ngrok-agent.com` (from ngrok dashboard)
- TTL: `1 Hour`

**Result:**
- Your subdomain: `scraper.yourdomain.com`
- Points to: Ngrok tunnel
- Permanent URL!

---

## ✅ OPTION 3: Cloudflare Tunnel (CNAME Record)

**Use this if:** You want FREE permanent solution

### **Step 1: Setup Cloudflare Tunnel**
```bash
# Install cloudflared
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb

# Login
cloudflared tunnel login

# Create tunnel
cloudflared tunnel create scraper

# This will give you a tunnel ID
```

### **Step 2: Create DNS Record:**

Cloudflare will automatically create the CNAME record when you run:
```bash
cloudflared tunnel route dns scraper scraper.yourdomain.com
```

**Or manually create:**

| Type | Name | Value | TTL |
|------|------|-------|-----|
| **CNAME** | `scraper` | `TUNNEL-ID.cfargotunnel.com` | Auto |

**Result:**
- Your subdomain: `scraper.yourdomain.com`
- Points to: Cloudflare tunnel
- 100% FREE and permanent!

---

## 🎯 RECOMMENDED FOR YOU

Based on your screenshot (looks like GoDaddy or similar):

### **EASIEST: Ngrok with Custom Domain**

**Step-by-step:**

1. **Upgrade ngrok to paid:**
   - https://dashboard.ngrok.com/billing/subscription
   - Cost: $8/month

2. **Add your domain to ngrok:**
   - Go to: https://dashboard.ngrok.com/cloud-edge/domains
   - Click "New Domain"
   - Select "Use your own domain"
   - Enter: `scraper.yourdomain.com`
   - Ngrok will show you a CNAME target

3. **In your domain dashboard (screenshot):**
   - Type: Select `CNAME`
   - Name: Enter `scraper`
   - Value: Paste the ngrok CNAME (e.g., `abc123.ngrok-agent.com`)
   - TTL: Select `1/2 Hour` or `1 Hour`
   - Click "Save"

4. **Start ngrok with your domain:**
   ```bash
   ngrok http --domain=scraper.yourdomain.com 8888
   ```

5. **Done!** Access at: `https://scraper.yourdomain.com`

---

## 📊 COMPARISON

| Method | Cost | Difficulty | Permanent? |
|--------|------|------------|------------|
| **A Record + Nginx** | FREE | Hard | ✅ YES |
| **Ngrok CNAME** | $8/month | Easy | ✅ YES |
| **Cloudflare Tunnel** | FREE | Medium | ✅ YES |

---

## 🚀 QUICK SETUP (RECOMMENDED)

### **For Ngrok (Easiest):**

1. Upgrade ngrok to paid
2. In ngrok dashboard, add your domain
3. Copy the CNAME target
4. In your domain DNS:
   - Type: `CNAME`
   - Name: `scraper`
   - Value: `[paste ngrok CNAME]`
   - Save

5. Start ngrok:
   ```bash
   ngrok http --domain=scraper.yourdomain.com 8888
   ```

**Result:** `https://scraper.yourdomain.com` - PERMANENT!

---

## 📝 WHAT TO ENTER IN YOUR SCREENSHOT

Based on your screenshot, here's exactly what to fill:

### **If using Ngrok (after upgrading):**

```
Type: CNAME
Name: scraper
Value: [get from ngrok dashboard - looks like: abc123.ngrok-agent.com]
TTL: 1 Hour
```

### **If using direct server IP:**

```
Type: A
Name: scraper
Value: 202.47.115.6 (your server IP)
TTL: 1 Hour
```

Then click "Add More Records" and "Save"

---

## ⚠️ IMPORTANT NOTES

1. **DNS Propagation:** Takes 5-60 minutes to work worldwide

2. **SSL Certificate:** 
   - Ngrok: Automatic (included)
   - Direct IP: Need to setup Let's Encrypt

3. **Port 8888:**
   - Ngrok: Handles automatically
   - Direct IP: Need reverse proxy (Nginx)

---

## 🔧 AFTER DNS SETUP

### **For Ngrok:**
```bash
# Stop current ngrok
pkill ngrok

# Start with your domain
ngrok http --domain=scraper.yourdomain.com 8888
```

### **For Cloudflare Tunnel:**
```bash
# Start tunnel
cloudflared tunnel --url http://localhost:8888 run scraper
```

---

## ✅ VERIFICATION

After DNS setup, check if it works:

```bash
# Check DNS resolution
nslookup scraper.yourdomain.com

# Test access
curl https://scraper.yourdomain.com/api/v1/health
```

---

## 💡 MY RECOMMENDATION

**→ Use Ngrok with Custom Domain**

**Why?**
1. Easiest setup (5 minutes)
2. Automatic SSL
3. No server configuration needed
4. Professional and reliable
5. Worth $8/month for permanent URL

**Steps:**
1. Upgrade ngrok ($8/month)
2. Add domain in ngrok dashboard
3. Create CNAME record (as shown above)
4. Start ngrok with your domain
5. Done!

---

**🎊 Your permanent URL: `https://scraper.yourdomain.com`**
