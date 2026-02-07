from btc_monitor import DataFetcher
import json

def find_robust_symbols():
    f = DataFetcher()
    markets = f.get_future_markets()
    if not markets:
        print("Failed to fetch markets")
        return

    btc_markets = [m for m in markets if m.get('base_asset') == 'BTC']
    eth_markets = [m for m in markets if m.get('base_asset') == 'ETH']
    
    print(f"Total BTC Markets: {len(btc_markets)}")
    print(f"Total ETH Markets: {len(eth_markets)}")
    
    # Look for aggregate symbols
    # Often Coinalyze uses special symbols for the homepage data.
    print("\n--- Potential BTC Aggregates ---")
    for m in btc_markets:
        if m.get('is_perpetual') and ('.A' in m['symbol'] or 'BTCUSD' in m['symbol']):
            print(f"Symbol: {m['symbol']}, Exchange: {m.get('exchange', 'N/A')}, SymbolOnExch: {m.get('symbol_on_exchange', 'N/A')}")

    # Test some common aggregate guesses if not found
    print("\n--- Testing Common Aggregate Symbols ---")
    test_aggs = ["BTCUSD.A", "BTCUSDT.A", "ETHUSD.A", "ETHUSDT.A", "BTCUSD_PERP.6", "BTCUSDT_PERP.6"]
    oi = f.get_coinalyze_oi(test_aggs)
    print(f"OI for Aggregates: {json.dumps(oi, indent=2)}")
    
    # Check for funding on these
    print("\n--- Testing Funding on Aggregates ---")
    for s in test_aggs:
        fund = f.get_coinalyze_funding(s)
        print(f"Funding for {s}: {fund}")

if __name__ == "__main__":
    find_robust_symbols()
