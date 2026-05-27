import os
import sys
import time
import logging
import asyncio
import requests
from datetime import datetime, timedelta
import ccxt.async_support as ccxt

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ==================== Configuration ====================
CONFIG = {
    'TG_TOKEN': os.environ.get('TELEGRAM_BOT_TOKEN'),
    'TG_CHAT_ID': os.environ.get('TELEGRAM_CHAT_ID'),
    'PROXY_URL': os.environ.get('PROXY_URL'),
    'BINANCE': {
        'apiKey': os.environ.get('BINANCE_API_KEY'),
        'secret': os.environ.get('BINANCE_SECRET'),
    },
    'GATE': {
        'apiKey': os.environ.get('GATE_API_KEY'),
        'secret': os.environ.get('GATE_SECRET'),
    },
    'HYPERLIQUID_WALLET': os.environ.get('HYPERLIQUID_WALLET')
}

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== Proxy Manager ====================
class ProxyManager:
    def __init__(self):
        self.proxies = []
        self.index = 0
        
    def get_public_proxies(self):
        """Fetch public proxies from github lists"""
        try:
            # Combined list source
            sources = [
                "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
                "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
                "https://raw.githubusercontent.com/prxchk/proxy-list/main/http.txt",
                "https://raw.githubusercontent.com/zloi-user/hideip.me/main/http.txt"
            ]
            
            found = set()
            for url in sources:
                try:
                    resp = requests.get(url, timeout=2) # Reduced timeout
                    if resp.status_code == 200:
                        lines = resp.text.splitlines()
                        for line in lines[:100]: # Increase to top 100
                            if ':' in line: found.add(f"http://{line.strip()}")
                except: continue
                    
            self.proxies = list(found)
            logger.info(f"Fetched {len(self.proxies)} public proxies")
        except Exception as e:
            logger.error(f"Proxy fetch error: {e}")

    def get_next(self):
        if not self.proxies:
            self.get_public_proxies()
        
        if not self.proxies: return None
        
        # Simple rotation
        if self.index >= len(self.proxies):
            self.index = 0
            
        p = self.proxies[self.index]
        self.index += 1
        return p

proxy_mgr = ProxyManager()

# ==================== Data Fetching (Stateless) ====================
def get_beijing_time():
    return datetime.utcnow() + timedelta(hours=8)

async def fetch_ccxt_balance(exchange_id, credentials):
    """Fetch held assets from CCXT exchange (Spot + Futures)"""
    # Skip if no keys
    if not credentials['apiKey']: return {}
    
    holdings = {}
    
    async def get_bal(options={}, use_proxy=None):
        exchange = None
        try:
            exchange_class = getattr(ccxt, exchange_id)
            
            # Prepare config
            ex_config = credentials.copy()
            ex_config['timeout'] = 3000 # 3s timeout (was 10s)
            
            # 1. Private Proxy / Explicit Proxy
            if use_proxy:
                ex_config['aiohttp_proxy'] = use_proxy
            elif CONFIG['PROXY_URL'] and exchange_id == 'binance':
                 ex_config['aiohttp_proxy'] = CONFIG['PROXY_URL']

            # Create new instance for each type to avoid state issues
            exchange = exchange_class(ex_config)
            if options:
                exchange.options.update(options)
            
            # Fetch Balance
            balance = await exchange.fetch_balance()
            
            # Standardize 'total'
            items = balance.get('total', {})
            logger.info(f"{exchange_id} Raw Balance Keys: {list(items.keys())}") # Debugging
            
            for symbol, amount in items.items():
                if amount > 0:
                    holdings[symbol] = holdings.get(symbol, 0) + amount
            
            logger.info(f"{exchange_id} Positive Holdings: {holdings}") # Debugging
            return True
                        
        except Exception as e:
            err_msg = str(e)
            if "futures permission" in err_msg or "FORBIDDEN" in err_msg:
                logger.warning(f"⚠️ {exchange_id} API key does not have futures (swap) permission, skipping futures balance.")
            else:
                logger.error(f"Error fetching {exchange_id} (proxy={use_proxy}): {e}")
            return False
        finally:
            if exchange:
                try:
                    await exchange.close()
                except Exception as e_close:
                    logger.debug(f"Failed to close exchange connection: {e_close}")

    async def attempt_fetch(type_opts):
        # 1. Try Default (Direct or Private Proxy)
        success = await get_bal(type_opts)
        if success: return

        # 2. If binance failed, try Public Proxies rotation
        if exchange_id == 'binance':
            logger.info("Direct/Private connection failed, trying public proxies...")
            for _ in range(1): # Reduced to 1 retry
                pub_proxy = proxy_mgr.get_next()
                if not pub_proxy: break
                
                success = await get_bal(type_opts, use_proxy=pub_proxy)
                if success: 
                    logger.info(f"Success with public proxy")
                    return

    # 1. Fetch Spot
    await attempt_fetch({})
    
    # 2. Fetch Futures
    if exchange_id == 'binance':
        await attempt_fetch({'defaultType': 'future'})
    elif exchange_id == 'gateio':
        await attempt_fetch({'defaultType': 'swap'})
        
    return holdings

def fetch_hyperliquid_balance(wallet):
    """Fetch Hyperliquid account value via REST"""
    if not wallet: return {}
    try:
        url = 'https://api.hyperliquid.xyz/info'
        # Get Account Value (USDC)
        resp = requests.post(url, json={'type': 'clearinghouseState', 'user': wallet}, timeout=10)
        if resp.status_code != 200: return {}
        data = resp.json()
        margin_summary = data.get('marginSummary', {})
        account_val = float(margin_summary.get('accountValue', 0))
        
        # Get Assets for alert checking
        holdings = {'USDC (HL)': account_val} 
        positions = data.get('assetPositions', [])
        for pos in positions:
            p = pos.get('position', {})
            coin = p.get('coin')
            sze = float(p.get('sze', 0))
            if sze != 0: holdings[coin] = sze
            
        return holdings
    except Exception as e:
        logger.error(f"Error fetching Hyperliquid: {e}")
        return {}

async def get_prices_with_history(symbols):
    """
    Get Current Price AND 30m High for Alerting.
    We use Binance for generic pricing.
    """
    results = {} # { 'BTC': {'current': 50000, 'max_30m': 51000} }
    
    # Clean symbols (remove duplicates and stables)
    targets = [s for s in symbols if s not in ['USDT', 'USDC', 'USD']]
    
    # We'll stick to a simple strategy:
    # Fetch Ticker (24h) is too broad.
    # Fetch kline (15m) -> take last 3 candles -> max(high)
    
    async def fetch_prices_from_exchange(ex_name, symbols_to_fetch, use_proxy=None):
        if not symbols_to_fetch: return
        
        ex_config = {}
        ex_config['timeout'] = 3000 # 3s timeout
        if use_proxy: ex_config['aiohttp_proxy'] = use_proxy
        elif CONFIG['PROXY_URL']: ex_config['aiohttp_proxy'] = CONFIG['PROXY_URL']
        
        exchange = None
        try:
            exchange_class = getattr(ccxt, ex_name)
            exchange = exchange_class(ex_config)
            
            # Use a semaphore to limit concurrency and avoid hitting rate limits
            sem = asyncio.Semaphore(10)
            
            async def fetch_single(symbol):
                if symbol in results: return
                async with sem:
                    pair = f"{symbol}/USDT"
                    # We prefer OHLV for the "Drop Alert" feature
                    try:
                        ohlcv = await exchange.fetch_ohlcv(pair, timeframe='15m', limit=3)
                        if ohlcv:
                            current_price = ohlcv[-1][4]
                            highs = [c[2] for c in ohlcv]
                            results[symbol] = {
                                'current': current_price,
                                'max_30m': max(highs)
                            }
                            return
                    except Exception:
                        pass

                    # Fallback to Ticker if OHLV failed (maybe not supported or restricted)
                    try:
                        ticker = await exchange.fetch_ticker(pair)
                        if ticker and ticker['last']:
                            results[symbol] = {
                                'current': float(ticker['last']),
                                'max_30m': float(ticker['last']) # No history data
                            }
                    except Exception:
                        pass
            
            tasks = [fetch_single(s) for s in symbols_to_fetch]
            await asyncio.gather(*tasks)
            return True
        except Exception as e:
            logger.error(f"Exchange {ex_name} error: {e}")
            return False
        finally:
            if exchange:
                try:
                    await exchange.close()
                except Exception as e_close:
                    logger.debug(f"Failed to close exchange connection: {e_close}")
                    
        # 1. Try Binance
    targets = list(set(targets)) # Unique
    
    # Try with defaults then proxies
    if not await fetch_prices_from_exchange('binance', targets):
        logger.warning("Binance price fetch direct failed, trying proxy rules...")
        # (Retry logic could be complex, for now we assume single shot attempt per exchange 
        # or simplified proxy retry logic if critical)
        pass

    # Retry missing on Binance with public proxy?
    missing = [s for s in targets if s not in results]
    if missing:
        logger.info(f"Retrying {len(missing)} missing coins on Binance with Proxy...")
        for _ in range(1): # Reduced to 1
            pub = proxy_mgr.get_next()
            if not pub: break
            await fetch_prices_from_exchange('binance', missing, use_proxy=pub)
            missing = [s for s in targets if s not in results]
            if not missing: break
            
    # 2. Try Gate for whatever is still missing
    missing = [s for s in targets if s not in results]
    if missing:
        logger.info(f"Checking Gate.io for {len(missing)} missing coins: {missing}")
        await fetch_prices_from_exchange('gateio', missing)
        
    # Add Stables
    results['USDT'] = {'current': 1.0, 'max_30m': 1.0}
    results['USDC'] = {'current': 1.0, 'max_30m': 1.0}
    results['USDC (HL)'] = {'current': 1.0, 'max_30m': 1.0}
    
    logger.info(f"Got prices for {len(results)}/{len(targets)} coins")
    return results

# ==================== Core Logic ====================

async def run_scan(force_report=False):
    logger.info("Starting Auto-Scan...")
    
    # 1. Fetch ALL Holdings
    binance = await fetch_ccxt_balance('binance', CONFIG['BINANCE'])
    gate = await fetch_ccxt_balance('gateio', CONFIG['GATE'])
    hl = await asyncio.to_thread(fetch_hyperliquid_balance, CONFIG['HYPERLIQUID_WALLET'])
    
    all_coins = set(binance.keys()) | set(gate.keys()) | set(hl.keys())
    
    # 2. Get Pricing & Drops
    price_data = await get_prices_with_history(list(all_coins))
    
    # 3. Calculate Portfolio Value
    portfolio_total = 0
    exchange_totals = {'Binance': 0, 'Gate': 0, 'Hyperliquid': 0}
    
    def calc_val(holdings, store_key):
        val = 0
        for coin, amt in holdings.items():
            # Handle special HL USDC
            p_key = 'USDC' if coin == 'USDC (HL)' else coin
            
            # Fallback price 0 if missing
            data = price_data.get(p_key)
            price = data['current'] if data else 0
            
            if price > 0:
                val += amt * price
        exchange_totals[store_key] = val
        return val

    portfolio_total += calc_val(binance, 'Binance')
    portfolio_total += calc_val(gate, 'Gate')
    portfolio_total += calc_val(hl, 'Hyperliquid')
    
    # 4. Check Alerts (Drop > 2%)
    alerts = []
    
    for coin, data in price_data.items():
        if coin in ['USDT', 'USDC']: continue
        
        # Check if we actually hold a significant amount of this coin (> $10 value)
        # to avoid spamming alerts for dust
        held_amt = binance.get(coin, 0) + gate.get(coin, 0) + hl.get(coin, 0)
        if held_amt * data['current'] < 10: continue

        # Calc Drop
        high = data['max_30m']
        curr = data['current']
        if high > 0:
            drop = (high - curr) / high
            if drop >= 0.02: # 2% Threshold
                p_fmt = f"{curr:.8f}" if curr < 0.1 else f"{curr:.4f}"
                alerts.append(f"⚠️ **{coin} 急跌警报**\n30分钟内回撤: `-{drop*100:.2f}%`\n现价: ${p_fmt}")

    # 5. Decide to Send Message
    
    # Condition A: Always send Alerts if any
    if alerts:
        alert_msg = "\n\n".join(alerts)
        send_tg(alert_msg)
        
    # Condition B: Send Periodic Report (Every 4 hours)
    now = get_beijing_time()
    # Run hourly, but report only every 4 hours (0, 4, 8, 12, 16, 20)
    is_periodic_time = (now.hour % 4 == 0)
    
    if force_report or is_periodic_time:
        report_msg = f"📊 **持仓监控报告**\n"
        report_msg += f"💰 **总资产: ${portfolio_total:.2f}**\n"
        report_msg += f"---\n"
        report_msg += f"🔶 Binance: ${exchange_totals['Binance']:.2f}\n"
        report_msg += f"🚪 Gate: ${exchange_totals['Gate']:.2f}\n"
        report_msg += f"💧 Hyperliquid: ${exchange_totals['Hyperliquid']:.2f}\n"

        # --- Detailed Breakdown ---
        report_msg += f"\n📜 **持仓详情:**\n"
        
        # Aggregate all holdings for display
        all_holdings_list = []
        
        def collect_details(holdings, source_icon):
            for coin, amt in holdings.items():
                p_key = 'USDC' if coin == 'USDC (HL)' else coin
                data = price_data.get(p_key)
                price = data['current'] if data else 0
                val = amt * price
                if val > 1.0: # Show only > $1
                    all_holdings_list.append({
                        'coin': coin, 
                        'amt': amt, 
                        'val': val, 
                        'icon': source_icon
                    })
                elif amt > 0 and price == 0:
                     logger.warning(f"⚠️ Zero Price for {coin} (Amount: {amt}) - Check if pricing symbol matches")

        collect_details(binance, '🔶')
        collect_details(gate, '🚪')
        collect_details(hl, '💧')

        # Sort by value DESC
        all_holdings_list.sort(key=lambda x: x['val'], reverse=True)

        # Sort by value DESC
        all_holdings_list.sort(key=lambda x: x['val'], reverse=True)

        for item in all_holdings_list:
            # Use comma for thousands, 4 decimals for small amounts, 2 for large
            qty_fmt = "{:,.4f}" if item['amt'] < 1000 else "{:,.2f}"
            report_msg += f"{item['icon']} **{item['coin']}**: {qty_fmt.format(item['amt'])} (${item['val']:,.0f})\n"
            
        report_msg += f"\n_扫描时间: {now.strftime('%H:%M')} (Beijing)_"
        
        # Avoid duplicate report if alert already sent? No, user wants report.
        send_tg(report_msg)

def send_tg(text):
    if not CONFIG['TG_TOKEN'] or not CONFIG['TG_CHAT_ID']:
        enc = sys.stdout.encoding or 'utf-8'
        safe_text = text.encode(enc, errors='replace').decode(enc)
        print("Skipping TG Send (No Config):", safe_text)
        return
    url = f"https://api.telegram.org/bot{CONFIG['TG_TOKEN']}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": CONFIG['TG_CHAT_ID'], "text": text, "parse_mode": "Markdown"}, timeout=10)
        if resp.status_code != 200:
            enc = sys.stdout.encoding or 'utf-8'
            err_msg = f"⚠️ Telegram Send Error: {resp.status_code} - {resp.text}"
            print(err_msg.encode(enc, errors='replace').decode(enc))
        else:
            print("✅ Telegram Message Sent Successfully")
    except Exception as e:
        print(f"Failed to send TG: {e}")

if __name__ == "__main__":
    # Check for manual trigger flag from args
    is_manual = len(sys.argv) > 1 and sys.argv[1] == '--report'
    
    # Run!
    try:
        asyncio.run(run_scan(force_report=is_manual))
    except Exception as e:
        enc = sys.stdout.encoding or 'utf-8'
        err_msg = f"CRITICAL ERROR: {e}"
        print(err_msg.encode(enc, errors='replace').decode(enc))
        # Send error to TG if possible
        send_tg(f"⚠️ Bot Critical Error: {e}")

