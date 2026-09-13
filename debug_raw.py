from btc_monitor import DataFetcher
import json
import requests
import os

# 调试脚本同样不硬编码凭据，也绝不把密钥打印出来
# （公开仓库的 Actions 日志是任何人都能看到的）
api_key = (os.environ.get("COINALYZE_KEY") or "").strip()
if not api_key:
    raise SystemExit("请先设置环境变量 COINALYZE_KEY（不要在源码里写死凭据）。")
print("Using COINALYZE_KEY from environment (value hidden).")

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
