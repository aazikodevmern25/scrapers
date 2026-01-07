"""
Test Webshare residential proxies with MacMap API
"""
import random
import pandas as pd
from curl_cffi import requests

# Load Webshare proxies
webshare_proxies = pd.read_csv('config/webshare_proxies.txt', names=['pr'])['pr'].to_list()

def get_webshare_proxy():
    """Get a random Webshare residential proxy"""
    pr = random.choice(webshare_proxies)
    parts = pr.split(':')
    host = parts[0]
    port = parts[1]
    username = parts[2]
    password = parts[3]
    
    # Format: http://username:password@host:port
    proxy_url = f'http://{username}:{password}@{host}:{port}'
    
    return {"http": proxy_url, "https": proxy_url}

# Test MacMap API with Webshare proxy
print("Testing MacMap API with Webshare residential proxy...")
print()

url = 'https://www.macmap.org/api/results/custom-duties-by-year?reporter=682&partner=702&product=381210&year=2025'
headers = {
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.macmap.org/en/query/customs-duties',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

for attempt in range(3):
    print(f"Attempt {attempt + 1}/3...")
    try:
        proxies = get_webshare_proxy()
        print(f"Using proxy: {list(proxies.values())[0].split('@')[1]}")
        
        response = requests.get(
            url, 
            headers=headers, 
            proxies=proxies,
            impersonate='chrome131', 
            timeout=30
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ SUCCESS! Got {len(data.get('CustomDuty', []))} custom duty items")
            print(f"\nSample data keys: {list(data.keys())}")
            if data.get('CustomDuty'):
                print(f"First item keys: {list(data['CustomDuty'][0].keys())}")
            break
        else:
            print(f"❌ Failed with status {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        
    print()

print("\n" + "="*60)
print("Test complete!")
