import os
import sys
import time
import logging
import asyncio
import requests
from datetime import datetime
import ccxt.async_support as ccxt

# ==================== Configuration ====================
CONFIG = {
    'TG_TOKEN': os.environ.get('TELEGRAM_BOT_TOKEN'),
    'TG_CHAT_ID': os.environ.get('TELEGRAM_CHAT_ID'),
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

# ==================== Data Fetching (Stateless) ====================

async def fetch_ccxt_balance(exchange_id, credentials):
    """Fetch held assets from CCXT exchange"""
    # Skip if no keys, but allow running if just one is missing
    if not credentials['apiKey']: return {}
    
    try:
        exchange_class = getattr(ccxt, exchange_id)
        async with exchange_class(credentials) as exchange:
            # Load markets for pricing if possible, but we use unified pricing later
            balance = await exchange.fetch_balance()
            holdings = {}
            items = balance.get('total', {})
            for symbol, amount in items.items():
                if amount > 0: holdings[symbol] = amount
            return holdings
    except Exception as e:
        logger.error(f"Error fetching {exchange_id}: {e}")
        return {}

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
    
    async with ccxt.binance() as exchange:
        for symbol in targets:
            try:
                # Try USDT Pair
                pair = f"{symbol}/USDT"
                
                # Fetch recent candles (15m timeframe, last 3 candles = 45 mins coverage)
                # This covers the "30 min" window safely
                ohlcv = await exchange.fetch_ohlcv(pair, timeframe='15m', limit=3)
                if not ohlcv: continue
                
                current_price = ohlcv[-1][4] # Close of latest
                
                # Calculate Max High in the last 3 candles
                highs = [candle[2] for candle in ohlcv]
                max_30m = max(highs)
                
                results[symbol] = {
                    'current': current_price,
                    'max_30m': max_30m
                }
            except Exception:
                # If symbol not on Binance, ignore for price alert but maybe assume stable
                pass
                
    # Add Stables
    results['USDT'] = {'current': 1.0, 'max_30m': 1.0}
    results['USDC'] = {'current': 1.0, 'max_30m': 1.0}
    results['USDC (HL)'] = {'current': 1.0, 'max_30m': 1.0}
    
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
                alerts.append(f"⚠️ **{coin} 急跌警报**\n30分钟内回撤: `-{drop*100:.2f}%`\n现价: ${curr:.4f}")

    # 5. Decide to Send Message
    
    # Condition A: Always send Alerts if any
    if alerts:
        alert_msg = "\n\n".join(alerts)
        send_tg(alert_msg)
        
    # Condition B: Send Periodic Report (Every 4 hours)
    # Since this runs every 20 mins, we check if hour % 4 == 0 and minute < 20
    # OR if manually triggered (github workflow input)
    now = datetime.now()
    is_periodic_time = (now.hour % 4 == 0) and (now.minute < 25)
    
    if force_report or is_periodic_time:
        report_msg = f"📊 **持仓监控报告**\n"
        report_msg += f"💰 **总资产: ${portfolio_total:.2f}**\n"
        report_msg += f"---\n"
        report_msg += f"🔶 Binance: ${exchange_totals['Binance']:.2f}\n"
        report_msg += f"🚪 Gate: ${exchange_totals['Gate']:.2f}\n"
        report_msg += f"💧 Hyperliquid: ${exchange_totals['Hyperliquid']:.2f}\n"
        report_msg += f"\n_扫描时间: {now.strftime('%H:%M')}_"
        
        # Avoid duplicate report if alert already sent? No, user wants report.
        send_tg(report_msg)

def send_tg(text):
    if not CONFIG['TG_TOKEN'] or not CONFIG['TG_CHAT_ID']:
        print("Skipping TG Send (No Config):", text)
        return
    url = f"https://api.telegram.org/bot{CONFIG['TG_TOKEN']}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CONFIG['TG_CHAT_ID'], "text": text, "parse_mode": "Markdown"})
    except Exception as e:
        print(f"Failed to send TG: {e}")

if __name__ == "__main__":
    # Check for manual trigger flag from args
    is_manual = len(sys.argv) > 1 and sys.argv[1] == '--report'
    asyncio.run(run_scan(force_report=is_manual))
