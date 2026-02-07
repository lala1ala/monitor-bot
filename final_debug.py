from btc_monitor import DataFetcher
import json
import requests
import os

def final_debug():
    # Detect the key
    key = os.getenv('COINALYZE_KEY', 'af1e3712-4a26-4293-bba4-579f6b736daa').strip()
    
    symbols = "BTCUSDT_PERP.A,ETHUSDT_PERP.A"
    
    # Try Header 1: api_key
    print(f"--- Header: api_key ---")
    try:
        r1 = requests.get("https://api.coinalyze.net/v1/open-interest", 
                          params={"symbols": symbols}, headers={"api_key": key})
        print(f"Status: {r1.status_code}, Length: {len(r1.json()) if r1.status_code==200 else 'N/A'}")
        if r1.status_code == 200:
            print(f"Data: {r1.json()}")
    except Exception as e:
        print(f"Error 1: {e}")

    # Try Header 2: x-api-key
    print(f"\n--- Header: x-api-key ---")
    try:
        r2 = requests.get("https://api.coinalyze.net/v1/open-interest", 
                          params={"symbols": symbols}, headers={"x-api-key": key})
        print(f"Status: {r2.status_code}, Length: {len(r2.json()) if r2.status_code==200 else 'N/A'}")
    except Exception as e:
        print(f"Error 2: {e}")

if __name__ == "__main__":
    final_debug()
