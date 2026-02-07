from btc_monitor import DataFetcher
import json

def debug_coinalyze():
    f = DataFetcher()
    print("--- Testing Future Markets ---")
    markets = f.get_future_markets()
    print(f"Found {len(markets)} markets.")
    
    if markets:
        # Pick a few valid symbols
        btc_syms = [m['symbol'] for m in markets if 'BTC' in m['symbol']][:3]
        eth_syms = [m['symbol'] for m in markets if 'ETH' in m['symbol']][:3]
        test_symbols = btc_syms + eth_syms
        print(f"Using symbols: {test_symbols}")
    else:
        print("Using fallback symbols due to empty markets.")
        test_symbols = ["BTCUSDT.6", "ETHUSDT.6", "BTCUSDT_PERP.A", "ETHUSDT_PERP.A"]
    
    print("\n--- Testing Funding Rate ---")
    for s in test_symbols:
        res = f.get_coinalyze_funding(s)
        print(f"Funding for {s}: {res}")
        
    print("\n--- Testing Open Interest ---")
    # Batch query
    res = f.get_coinalyze_oi(test_symbols)
    # Print only first item to avoid spam, or summary
    print(f"OI Batch Result Count: {len(res)}")
    if res:
        print(f"Sample OI: {res[0]}")
    else:
        print("OI Batch returned empty list.")

if __name__ == "__main__":
    debug_coinalyze()
