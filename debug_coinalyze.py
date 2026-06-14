from btc_monitor import DataFetcher
import json

def debug_coinalyze():
    f = DataFetcher()
    print("--- Testing Future Markets ---")
    markets = f.get_future_markets()
    print(f"Found {len(markets)} markets.")
    if markets:
        # print unique exchange codes and one example for each
        codes = set([m.get('exchange') for m in markets])
        print(f"Unique Exchange Codes: {codes}")
        for c in codes:
            example = next((m for m in markets if m['exchange'] == c), None)
            if example:
                print(f"Code {c}: {example['symbol']} ({example.get('symbol_on_exchange')})")
    
    if markets:
        # Strategy: Filter for only Top Exchanges + USDT/USD Pairs
        # Codes: A=Binance(Perp), 6=Binance(Linear?), 4=Bybit, 3=OKX
        top_exchanges = ['A', '6', '4', '3']
        
        # Helper to check if market is relevant
        def is_relevant(m, coin):
            # Must be perpetual
            if not m.get('is_perpetual'): return False
            # Must be the coin base
            if m.get('base_asset') != coin: return False
            # Must be in top exchanges
            return m.get('exchange') in top_exchanges

        btc_markets = [m for m in markets if is_relevant(m, 'BTC')]
        eth_markets = [m for m in markets if is_relevant(m, 'ETH')]
        
        test_symbols = [m['symbol'] for m in btc_markets] + [m['symbol'] for m in eth_markets]
        
        print(f"BTC Markets (Filtered): {len(btc_markets)}")
        print(f"ETH Markets (Filtered): {len(eth_markets)}")
        # Print breakdown by exchange code
        from collections import Counter
        print(f"BTC Breakdown: {Counter([m['exchange'] for m in btc_markets])}")
        
        print(f"Sample Symbols: {test_symbols[:5]}")
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
