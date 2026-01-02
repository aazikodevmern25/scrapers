import json
import os
from curl_cffi import requests
from pymongo import MongoClient
from BunnyCDN.Storage import Storage 
from curl_cffi import requests
import pandas as pd
import random
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file
load_dotenv()

# Get the data-extractor root directory
root_dir = Path(__file__).parent.parent
proxies_path = root_dir / 'config' / 'proxies.txt'
proxies = pd.read_csv(proxies_path, names=['pr'])['pr'].to_list()

def get_proxies():
    pr = random.choice(proxies)
    pr = pr.split(':')
    pr1 = ':'.join(pr[:-2])
    auth = (pr[-2],pr[-1])
    proxy_url = f'http://{pr1}'
    return auth,{"http": proxy_url, "https": proxy_url}

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
    while retry < 5:
        try:
            if use_proxy:
                auth,proxy = get_proxies()
                req = requests.post(url,headers=headers,data=data,impersonate="chrome131",proxy_auth=auth,proxies=proxy,timeout=100)
            else:
                req = requests.post(url,headers=headers,data=data,impersonate="chrome131",timeout=100)
            return req
        except Exception as e:
            print(e)
            print(f'request failed, Retry: {retry}/5')
            retry +=1
    # Raise exception after all retries exhausted
    raise Exception(f"POST request failed after 5 retries: {url}")

def SendGetRequests(url,headers,use_proxy=True):
    retry = 0
    last_error = None
    while retry < 5:
        try:    
            if use_proxy:
                auth, proxy = get_proxies()
                req = requests.get(url, headers=headers, impersonate="chrome131",proxy_auth=auth,proxies=proxy,timeout=100)
            else:
                req = requests.get(url, headers=headers, impersonate="chrome131",timeout=100)
                
            return req
        except Exception as e:
            last_error = e
            print(e)
            print(f'request failed, Retry: {retry}/5')
            retry +=1
    # Raise exception after all retries exhausted
    raise Exception(f"GET request failed after 5 retries: {url}. Last error: {last_error}")


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