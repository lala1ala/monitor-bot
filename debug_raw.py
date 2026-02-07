from btc_monitor import DataFetcher
import json
import requests

def debug_raw():
    f = DataFetcher()
    headers = f.coinalyze_headers
    
    url = "https://api.coinalyze.net/v1/predicted-funding-rate"
    try:
        resp = requests.get(url, headers=headers)
        print(f"Status: {resp.status_code}")
        print(f"Raw Content: {resp.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_raw()
