from btc_monitor import DataFetcher
import json
import requests
import os

api_key = os.environ.get("COINALYZE_KEY") or "af1e3712-4a26-4293-bba4-579f6b736daa"
print(f"Using API Key: {api_key}")

def test_endpoint(name, url, params=None):
    print(f"\n--- Testing {name} ---")
    try:
        headers = {'api_key': api_key}
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                print(f"Result is list of {len(data)} items.")
                print(f"Sample: {data[0] if data else 'Empty'}")
            else:
                print(f"Result: {data}")
        else:
            print(f"Error: {resp.text}")
    except Exception as e:
        print(f"Exception: {e}")

# 1. Test Funding Rate (Current)
test_endpoint("Current Funding Rate (BTCUSDT.A)", "https://api.coinalyze.net/v1/funding-rate", {'symbols': 'BTCUSDT_PERP.A'})

# 2. Test Open Interest (Aggregated?)
# Try 'BTC' as symbol
test_endpoint("Open Interest (BTC)", "https://api.coinalyze.net/v1/open-interest", {'symbols': 'BTC'})

# 2b. Test Open Interest for Specific Binance Symbol
test_endpoint("Open Interest (BTCUSDT_PERP.A)", "https://api.coinalyze.net/v1/open-interest", {'symbols': 'BTCUSDT_PERP.A'})

# 3. Test Global Open Interest Endpoint? (Guessing)
test_endpoint("Global Open Interest", "https://api.coinalyze.net/v1/global-open-interest", {'symbols': 'BTC'})

# 4. Test list of markets to see if there's a 'global' one
# (Already done in debug_coinalyze.py, skipped)
