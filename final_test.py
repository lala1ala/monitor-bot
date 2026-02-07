from btc_monitor import DataFetcher
import json
import requests

def final_api_test():
    f = DataFetcher()
    headers = f.coinalyze_headers
    
    print("--- Testing /v1/predicted-funding-rate (No symbols) ---")
    url_fund = "https://api.coinalyze.net/v1/predicted-funding-rate"
    try:
        resp = requests.get(url_fund, headers=headers, timeout=10)
        data = resp.json()
        print(f"Type: {type(data)}")
        print(f"Data: {json.dumps(data, indent=2)}")
        print(f"Success! Found {len(data)} funding rates.")
        # Find BTC/ETH ones
        btc_funds = [x for x in data if 'BTC' in x['symbol']]
        print(f"Sample BTC Funds: {btc_funds[:3]}")
    except Exception as e:
        print(f"Failed: {e}")

    print("\n--- Testing /v1/open-interest (No symbols) ---")
    url_oi = "https://api.coinalyze.net/v1/open-interest"
    try:
        resp = requests.get(url_oi, headers=headers, timeout=10)
        data = resp.json()
        print(f"Success! Found {len(data)} OI entries.")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    final_api_test()
