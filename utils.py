import json
import os
from curl_cffi import requests
from pymongo import MongoClient
from BunnyCDN.Storage import Storage 
from curl_cffi import requests
import pandas as pd
import random
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

proxies = pd.read_csv('config/proxies.txt',names=['pr'])['pr'].to_list()

def get_proxies():
    # Enable proxies - IndiaMART blocks direct requests
    pr = random.choice(proxies)
    parts = pr.split(':')
    host = parts[0]
    port = parts[1]
    username = parts[2]
    password = parts[3]
    
    # Format: http://username:password@host:port
    proxy_url = f'http://{username}:{password}@{host}:{port}'
    
    return None, {"http": proxy_url, "https": proxy_url}

os.makedirs("pdf_files", exist_ok=True)
cwd = os.getcwd()

# MongoDB connection using environment variable
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/?authSource=admin')
MONGO_DB = os.getenv('MONGO_DB', 'jaimish_data')

client = MongoClient(MONGO_URI)
db = client[MONGO_DB]
obj_storage = Storage("34c2c4ea-2925-444d-8e8590a39d2f-e088-4e18","trade-data-bucket-6969","de")


def SendPostRequests(url,headers,data,use_proxy=False):
    retry = 0
    max_retries = 5
    last_error = None
    
    while retry < max_retries:
        try:
            if use_proxy:
                auth,proxy = get_proxies()
                req = requests.post(url,headers=headers,data=data,impersonate="chrome131",proxy_auth=auth,proxies=proxy,timeout=100)
            else:
                req = requests.post(url,headers=headers,data=data,impersonate="chrome131",timeout=100)
            
            # If we get 403, try with a different proxy
            if req.status_code == 403 and use_proxy and retry < max_retries - 1:
                print(f'Got 403 error, trying with different proxy (attempt {retry + 1}/{max_retries})')
                retry += 1
                continue
                
            return req
        except Exception as e:
            last_error = e
            print(e)
            print(f'request failed, Retry: {retry + 1}/{max_retries}')
            retry +=1
    
    # Raise exception after all retries exhausted
    raise Exception(f"POST request failed after {max_retries} retries: {url}. Last error: {last_error}")

def SendGetRequests(url,headers,use_proxy=True, max_403_retries=1):
    retry = 0
    last_error = None
    max_retries = 3  # Reduced for faster processing
    retries_403 = 0
    
    while retry < max_retries:
        try:    
            if use_proxy:
                auth, proxy = get_proxies()
                req = requests.get(url, headers=headers, impersonate="chrome131",proxy_auth=auth,proxies=proxy,timeout=30)
            else:
                req = requests.get(url, headers=headers, impersonate="chrome131",timeout=30)
            
            # If we get 403, try with a different proxy (limited retries)
            if req.status_code == 403 and use_proxy and retries_403 < max_403_retries:
                print(f'Got 403 error, trying with different proxy (attempt {retries_403 + 1}/{max_403_retries})')
                retries_403 += 1
                retry += 1  # Also increment retry to prevent infinite loop
                continue
            
            # Return response (even if 403) so caller can handle it
            return req
        except Exception as e:
            last_error = e
            print(f'request failed, Retry: {retry + 1}/{max_retries}')
            retry +=1
    
    # Return None after all retries exhausted (don't raise exception)
    print(f"GET request failed after {max_retries} retries: {url}")
    return None


def FetchCountries(filename):
    js = json.load(open(f'payloads/{filename}','r',encoding='utf-8'))
    countries = {}
    for row in js['data']['countries']:
        countries[row['country']] = row
    return countries



def DownloadPdf(uri, fname):
    try:
        auth, proxy = get_proxies()
        # headers = {
        #     "Accept": "application/pdf",  # or */*
        # }
        req = requests.get(uri,impersonate="chrome131",timeout=200,proxy_auth=auth,proxies=proxy)
        print(uri, req.status_code)
        with open(f"pdf_files/{fname}", "wb") as f:
            f.write(req.content)
        f.close()
    except Exception as e:
        print(e)
    # res = obj_storage.PutFile(fname, local_upload_file_path=f"{cwd}/pdf_files")
    # print(res)
    # if res['status'] == 'success':
    #     os.remove(f"pdf_files/{fname}")
    
    # return res
    # 
    # 
# DownloadPdf("https://findrulesoforigin.org/documents/pdf/itc00155_full.pdf","test.pdf")