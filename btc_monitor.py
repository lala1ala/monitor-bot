import os
import requests
import json
import time
from datetime import datetime

# ==================== CONFIGURATION ====================
# API Keys
# Use 'or' to fallback if the env var is set but empty (e.g. GHA empty secret)
COINGLASS_API_KEY = os.environ.get("COINGLASS_SECRET") or "438d3e0c3aaa4fdd9caa5d7853e41cb3"
COINALYZE_API_KEY = os.environ.get("COINALYZE_KEY") or "af1e3712-4a26-4293-bba4-579f6b736daa"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL") or "https://discord.com/api/webhooks/1469265206646542348/cBUvNdqBZgji_AY7huzVjVbQ-XEkDAL3A0Z1snmdc2IEaFFN5yAxenAgrEuqaIVPllme"

# Thresholds
ALTS_OI_REL_THRESHOLD = 0.55  # Warning if Alts OI > 55% of Total
VOLUME_SPIKE_THRESHOLD = 0.9  # Warning if Alt Volume > 90% of BTC Volume

# ==================== DATA FETCHER ====================
class DataFetcher:
    def __init__(self):
        # V4 Auth uses header 'CG-API-KEY'
        self.coinglass_headers = {
            "CG-API-KEY": COINGLASS_API_KEY,
            "accept": "application/json"
        }
        # Coinalyze headers
        self.coinalyze_headers = {
            "api_key": COINALYZE_API_KEY.strip(),
            "accept": "application/json"
        }
    
    # ... (binance 24hr ticker remains same or similar)
    def get_binance_ticker_24hr(self):
        """Fetch 24hr ticker data from Binance"""
        try:
            url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return [x for x in data if x['symbol'].endswith('USDT')]
        except Exception as e:
            print(f"Error fetching Binance tickers: {e}")
            return []

    def get_binance_daily_candles(self, symbol="BTCUSDT", limit=250):
        """Fetch daily candles for MA calculation"""
        # Endpoint: https://fapi.binance.com/fapi/v1/klines
        try:
            url = "https://fapi.binance.com/fapi/v1/klines"
            params = {
                "symbol": symbol,
                "interval": "1d",
                "limit": limit
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            # Returns list of lists: [ [open_time, open, high, low, close, ...], ... ]
            return resp.json()
        except Exception as e:
            print(f"Error fetching Binance candles: {e}")
            return []

    def get_fear_and_greed(self):
        """Fetch Fear & Greed Index from Alternative.me"""
        try:
            url = "https://api.alternative.me/fng/"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # { "data": [ { "value": "70", "value_classification": "Greed", ... } ] }
                if 'data' in data and len(data['data']) > 0:
                    return data['data'][0]
            return None
        except Exception as e:
            print(f"Error fetching F&G: {e}")
            return None

    def get_coinalyze_funding(self, symbols=None):
        """Fetch Predicted Funding Rate(s) from Coinalyze"""
        url = f"https://api.coinalyze.net/v1/predicted-funding-rate"
        try:
            if symbols:
                # Batch request
                params = {"symbols": symbols}
                resp = requests.get(url, params=params, headers=self.coinalyze_headers, timeout=10)
                if resp.status_code == 200:
                    return resp.json()
            else:
                # Default candidates loop
                candidates = ["BTCUSDT.A", "BTCUSDT_PERP.A", "BTC-PERP.A", "BTCUSDT.6"]
                for sym in candidates:
                    resp = requests.get(url, params={"symbols": sym}, headers=self.coinalyze_headers, timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data: return data
                return None
        except Exception as e:
            print(f"Error fetching Funding Rate: {e}")
            return None

    def get_future_markets(self):
        """Fetch list of supported future markets"""
        url = f"https://api.coinalyze.net/v1/future-markets"
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = requests.get(url, headers=self.coinalyze_headers, timeout=15)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 429:
                    wait_time = float(resp.headers.get('Retry-After', 5)) + 1
                    print(f"Markets fetch rate limited. Waiting {wait_time:.1f}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    try:
                        print(f"Coinalyze Markets Error: {resp.status_code} {resp.text}")
                    except: pass
                    return []
            except Exception as e:
                print(f"Error fetching Coinalyze Markets: {e}")
                return []
        return []

    def get_coinalyze_oi(self, symbols_list=None):
        """Fetch Open Interest from Coinalyze"""
        if not symbols_list:
            return []
            
        try:
            url = f"https://api.coinalyze.net/v1/open-interest"
            symbols_str = ",".join(symbols_list)
            params = {"symbols": symbols_str}
            
            # Simple retry logic
            max_retries = 3
            for attempt in range(max_retries):
                resp = requests.get(url, params=params, headers=self.coinalyze_headers, timeout=15)
                
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 429:
                    # Rate limited
                    wait_time = float(resp.headers.get('Retry-After', 5)) + 1
                    print(f"Rate limited. Waiting {wait_time:.1f}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"Coinalyze OI Error: {resp.status_code} {resp.text}")
                    return []
            return []
        except Exception as e:
            print(f"Error fetching Coinalyze OI: {e}")
            return []

    def get_coinglass_sth_price(self):
        """Fetch STH Realized Price"""
        # Endpoint: https://open-api-v4.coinglass.com/api/index/bitcoin-sth-realized-price (guess based on slug)
        # Actually standard charts are usually under /index/
        try:
            url = "https://open-api-v4.coinglass.com/api/index/bitcoin-sth-realized-price"
            resp = requests.get(url, headers=self.coinglass_headers, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') == '0' and data.get('data'):
                    # Data format might be list of [time, value]
                    # Or 'data': [{'t':..., 'v':...}]
                    series = data.get('data', [])
                    if series:
                         # Assume list of time-value pairs if simpler api, or list of dicts. 
                         # Let's handle both safely.
                         last = series[-1]
                         val = 0
                         if isinstance(last, dict): val = last.get('v', 0)
                         elif isinstance(last, list): val = last[1]
                         else: val = last # If single value
                         return float(val)
            # Try V3 fallback or different slug if first failed? No, just keep simple.
            return 0
        except Exception as e:
            print(f"Coinglass STH Error: {e}")
            return 0

    def get_coinglass_mvrv(self):
        """Fetch MVRV Z-Score"""
        try:
            # Trying slug 'bitcoin-mvrv-z-score' based on naming convention
            url = "https://open-api-v4.coinglass.com/api/index/bitcoin-mvrv-z-score"
            resp = requests.get(url, headers=self.coinglass_headers, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') == '0' and data.get('data'):
                    series = data.get('data', [])
                    if series:
                         last = series[-1]
                         val = 0
                         if isinstance(last, dict): val = last.get('v', 0)
                         elif isinstance(last, list): val = last[1]
                         else: val = last
                         return float(val)
            return 0
        except Exception as e:
            print(f"Coinglass MVRV Error: {e}")
            return 0

# ==================== ANALYZER_SENDER ====================
class BtcMonitor:
    def __init__(self):
        self.fetcher = DataFetcher()

    def run(self):

        print("Gathering Data...")
        
        # 1. Market Heat (Binance Volume) & Price
        binance_data = self.fetcher.get_binance_ticker_24hr()
        current_btc_price = 0
        hot_alts = []
        binance_price_map = {}
        binance_vol_map = {}
        
        if binance_data:
            sorted_vol = sorted(binance_data, key=lambda x: float(x['quoteVolume']), reverse=True)
            btc_item = next((x for x in sorted_vol if x['symbol'] == 'BTCUSDT'), None)
            btc_vol = float(btc_item['quoteVolume']) if btc_item else 0
            current_btc_price = float(btc_item['lastPrice']) if btc_item else 0
            
            for x in sorted_vol[:10]:
                sym = x['symbol']
                if sym in ['BTCUSDT', 'ETHUSDT', 'USDCUSDT', 'FDUSDUSDT']: continue
                vol = float(x['quoteVolume'])
                ratio_btc = vol / btc_vol if btc_vol > 0 else 0
                if ratio_btc > VOLUME_SPIKE_THRESHOLD:
                    hot_alts.append(f"**{sym}** Vol: ${vol/1e9:.2f}B ({ratio_btc*100:.0f}% of BTC)")
        
        # 2. Speculation Heat (Coinalyze Aggregation)
        print("Fetching OI and Funding from Coinalyze...")
        all_markets = self.fetcher.get_future_markets()
        
        # Track units and values
        btc_units = 0
        eth_units = 0
        alts_usd = 0
        
        btc_funding_list = []
        
        if all_markets:
            print(f"Total Coinalyze markets: {len(all_markets)}")
            perpetuals = [m for m in all_markets if m.get('is_perpetual')]
            
            # Group symbols
            btc_perps = [m['symbol'] for m in perpetuals if m.get('base_asset') == 'BTC']
            eth_perps = [m['symbol'] for m in perpetuals if m.get('base_asset') == 'ETH']
            
            # For Alts, we take the top 100 by Binance volume to estimate "All Alts"
            binance_vol_map = {item['symbol']: float(item['quoteVolume']) for item in binance_data} if binance_data else {}
            binance_price_map = {item['symbol']: float(item['lastPrice']) for item in binance_data} if binance_data else {}
            
            other_perps = []
            for m in perpetuals:
                base = m.get('base_asset')
                if base in ['BTC', 'ETH']: continue
                
                exch_sym = m.get('symbol_on_exchange', '')
                vol = binance_vol_map.get(exch_sym, 0)
                if vol > 0:
                    other_perps.append({"symbol": m['symbol'], "vol": vol, "exch_sym": exch_sym})
            
            # Sort and take top 100 alts
            other_perps.sort(key=lambda x: x['vol'], reverse=True)
            top_alts = other_perps[:100]
            alt_symbols = [x['symbol'] for x in top_alts]

            # Fetch Data in Batches
            # 1. BTC Totals
            print(f"Fetching {len(btc_perps)} BTC perpetuals...")
            for i in range(0, len(btc_perps), 100):
                batch = btc_perps[i:i+100]
                resp = self.fetcher.get_coinalyze_oi(batch)
                if resp:
                    for item in resp: btc_units += float(item.get('value', 0))
                time.sleep(1.0)
            
            # 2. ETH Totals
            print(f"Fetching {len(eth_perps)} ETH perpetuals...")
            for i in range(0, len(eth_perps), 100):
                batch = eth_perps[i:i+100]
                resp = self.fetcher.get_coinalyze_oi(batch)
                if resp:
                    for item in resp: eth_units += float(item.get('value', 0))
                time.sleep(1.0)
            
            # 3. Alts Totals (Estimated via top 100)
            # Fetch for Alts and calculate USD immediately using Binance prices
            print(f"Fetching {len(alt_symbols)} Top Alt perpetuals...")
            for i in range(0, len(alt_symbols), 100):
                batch = alt_symbols[i:i+100]
                resp = self.fetcher.get_coinalyze_oi(batch)
                if resp:
                    for item in resp:
                        sym = item.get('symbol', '')
                        units = float(item.get('value', 0))
                        # Match back to binance price
                        match = next((x for x in top_alts if x['symbol'] == sym), None)
                        if match:
                            price = binance_price_map.get(match['exch_sym'], 0)
                            alts_usd += (units * price)
                time.sleep(1.0)

            # 4. BTC Funding Average (Predicted)
            # Use top 10 BTC perps to get a good average
            top_btc_for_fund = btc_perps[:10]
            fund_resp = self.fetcher.get_coinalyze_funding(",".join(top_btc_for_fund))
            if fund_resp:
                for f_item in fund_resp:
                    pf = float(f_item.get('pf', 0))
                    btc_funding_list.append(pf)

        # Final Aggregation
        btc_oi_usd = btc_units * current_btc_price
        # Need ETH price
        eth_price = binance_price_map.get('ETHUSDT', 2000) # Fallback to 2k if missing
        eth_oi_usd = eth_units * eth_price
        
        total_market_oi_usd = btc_oi_usd + eth_oi_usd + alts_usd
        alts_oi_share = (alts_usd / total_market_oi_usd * 100) if total_market_oi_usd > 0 else 0
        
        # Funding Average
        funding_annual_str = "N/A"
        funding_annual = 0
        if btc_funding_list:
            avg_pf = sum(btc_funding_list) / len(btc_funding_list)
            funding_annual = avg_pf * 3 * 365 * 100
            funding_annual_str = f"{funding_annual:+.2f}%"

        oi_status = "Healthy"
        if alts_oi_share > (ALTS_OI_REL_THRESHOLD * 100):
            oi_status = "⚠️ Overheated (Alts domination)"

        # 3. Fear & Greed
        fg_data = self.fetcher.get_fear_and_greed()
        fg_str = f"{fg_data.get('value')} ({fg_data.get('value_classification')})" if fg_data else "N/A"
        
        # 4. Technical Models
        ma_msg = ""
        candles = self.fetcher.get_binance_daily_candles("BTCUSDT", limit=250)
        if candles and len(candles) >= 200:
            closes = [float(x[4]) for x in candles]
            ma_200 = sum(closes[-200:]) / 200
            ma_111 = sum(closes[-111:]) / 111 if len(closes) >= 111 else 0
            diff_ma200 = ((current_btc_price - ma_200) / ma_200) * 100
            ma_msg = f"**MA200 (Bull/Bear Line)**: ${ma_200:,.0f} (Diff: {diff_ma200:+.1f}%)\n**MA111 (Pi Cycle Use)**: ${ma_111:,.0f}"

        # 5. Construct Report
        report = {
            "title": "🛡️ BTC Decision System Daily",
            "color": 16711680 if (hot_alts or alts_oi_share > 55 or funding_annual > 50) else 65280, 
            "fields": [
                {
                    "name": "1. 投机热度 & 情绪",
                    "value": (
                        f"**Fear & Greed**: {fg_str}\n"
                        f"**Funding Rate (Annual)**: {funding_annual_str}\n"
                        f"**Open Interest (OI)**:\n"
                        f" • BTC: ${btc_oi_usd/1e9:.1f}B\n"
                        f" • ETH: ${eth_oi_usd/1e9:.1f}B\n"
                        f" • Alts: ${alts_usd/1e9:.1f}B ({oi_status})"
                    ),
                    "inline": False
                },
                {
                    "name": "2. 市场过热 (Volume Spike)",
                    "value":  "\n".join(hot_alts) if hot_alts else "✅ 无异常 (无山寨币成交量 > 90% BTC)",
                    "inline": False
                },
                {
                    "name": "3. 趋势估值 (Technical Models)",
                    "value": f"**BTC Price**: ${current_btc_price:,.0f}\n{ma_msg}",
                    "inline": False
                }
            ],
            "footer": {"text": f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}\nSources: Coinalyze (OI/Fund), Alt.me (F&G), Binance (Vol/MA)."}
        }
        
        self.send_discord_embed(report)
        print("Report sent!")

    def send_discord_embed(self, embed_data):
        payload = {
            "username": "Antigravity BTC Monitor",
            "embeds": [embed_data]
        }
        try:
            resp = requests.post(DISCORD_WEBHOOK_URL, json=payload)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as err:
             print(f"Discord Send Error: {err.response.text}")

if __name__ == "__main__":
    BtcMonitor().run()
