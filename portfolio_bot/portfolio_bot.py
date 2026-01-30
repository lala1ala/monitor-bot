import os
import time
import logging
import asyncio
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
import ccxt.async_support as ccxt  # Async CCXT
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Load Config
load_dotenv()

# Configuration
CONFIG = {
    'TG_TOKEN': os.getenv('TELEGRAM_BOT_TOKEN'),
    'TG_CHAT_ID': os.getenv('TELEGRAM_CHAT_ID'),
    'BINANCE': {
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_SECRET'),
        'enableRateLimit': True,
    },
    'GATE': {
        'apiKey': os.getenv('GATE_API_KEY'),
        'secret': os.getenv('GATE_SECRET'),
        'enableRateLimit': True,
    },
    'HYPERLIQUID_WALLET': os.getenv('HYPERLIQUID_WALLET')
}

# Logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# State
PRICE_HISTORY = {}  # { 'SYMBOL': [(timestamp, price), ...] }
LAST_ALERT = {}     # { 'SYMBOL': timestamp }
PORTFOLIO_CACHE = {}

# ==================== Data Fetching ====================

async def fetch_ccxt_balance(exchange_id, credentials):
    """Fetch balance from CCXT exchanges (Binance, Gate)"""
    if not credentials['apiKey'] or not credentials['secret']:
        return {}
    
    try:
        exchange_class = getattr(ccxt, exchange_id)
        async with exchange_class(credentials) as exchange:
            balance = await exchange.fetch_balance()
            # Filter non-zero balances
            holdings = {}
            total_usd = 0.0
            
            # Fetch Tickers for USD conversion
            # Note: This is simplified. In prod, fetch only needed tickers.
            # Using 'USDT' pairs for approx value.
            
            # Simplified: Just return raw amounts first, handle pricing later
            # Or better: CCXT 'total' gives usually amounts
            items = balance.get('total', {})
            
            for symbol, amount in items.items():
                if amount > 0: # Filter dust broadly
                    holdings[symbol] = amount
            
            return holdings
    except Exception as e:
        logger.error(f"Error fetching {exchange_id}: {e}")
        return {}

def fetch_hyperliquid_balance(wallet):
    """Fetch Hyperliquid account value and positions via REST"""
    if not wallet: return {}
    
    try:
        url = 'https://api.hyperliquid.xyz/info'
        headers = {'Content-Type': 'application/json'}
        
        # 1. Get Spot/Margin State
        resp = requests.post(url, json={'type': 'clearinghouseState', 'user': wallet}, timeout=10)
        if resp.status_code != 200: return {}
        
        data = resp.json()
        margin_summary = data.get('marginSummary', {})
        account_value = float(margin_summary.get('accountValue', 0))
        
        positions = data.get('assetPositions', [])
        holdings = {}
        
        # Add Cash (USDC)
        holdings['USDC (Account Value)'] = account_value 
        # Note: Hyperliquid positions are derivatives usually, but let's list net positions
        
        for pos in positions:
            p = pos.get('position', {})
            coin = p.get('coin')
            sze = float(p.get('sze', 0))
            if sze != 0:
                holdings[coin] = sze
                
        return holdings
    except Exception as e:
        logger.error(f"Error fetching Hyperliquid: {e}")
        return {}

async def get_market_prices(symbols):
    """Get current prices for a list of symbols (from Binance primarily)"""
    # Use Binance public API for generic pricing
    try:
        url = "https://api.binance.com/api/v3/ticker/price"
        resp = requests.get(url, timeout=5)
        data = resp.json()
        
        price_map = {}
        for item in data:
            s = item['symbol']
            if s.endswith('USDT'):
                coin = s[:-4]
                price_map[coin] = float(item['price'])
        
        # Add USDC
        price_map['USDC'] = 1.0
        return price_map
    except Exception as e:
        logger.error(f"Error fetching prices: {e}")
        return {}

# ==================== Core Logic ====================

async def update_portfolio():
    """Fetch all balances and prices"""
    # 1. Balances
    binance = await fetch_ccxt_balance('binance', CONFIG['BINANCE'])
    gate = await fetch_ccxt_balance('gateio', CONFIG['GATE'])
    hl = await asyncio.to_thread(fetch_hyperliquid_balance, CONFIG['HYPERLIQUID_WALLET'])
    
    # 2. Identify all unique coins
    all_coins = set()
    all_coins.update(binance.keys())
    all_coins.update(gate.keys())
    # Hyperliquid keys might be distinct, handle separately for pricing
    
    # 3. Prices
    market_prices = await get_market_prices(list(all_coins))
    
    # 4. Calculate Values
    portfolio = {
        'Binance': {'total_usd': 0, 'assets': []},
        'Gate': {'total_usd': 0, 'assets': []},
        'Hyperliquid': {'total_usd': hl.get('USDC (Account Value)', 0), 'assets': []},
        'GrandTotal': 0
    }
    
    # Helper to process exchange
    def process_ex(name, balances, target_dict):
        for coin, amt in balances.items():
            price = market_prices.get(coin, 0)
            val = amt * price
            if val > 1: # Ignore dust < $1
                target_dict['total_usd'] += val
                target_dict['assets'].append((coin, amt, val, price))
                
                # Update Price History for Alerts (only if we hold it)
                track_price(coin, price)
                
        target_dict['assets'].sort(key=lambda x: x[2], reverse=True)

    process_ex('Binance', binance, portfolio['Binance'])
    process_ex('Gate', gate, portfolio['Gate'])
    
    # Hyperliquid specific
    # In this logic, HL returns Account Value directly. Positions are just for info.
    # We will track price of Position coins if possible, but HL prices are best from HL API.
    # For simplicity, we trust Account Value for HL total.
    for coin, size in hl.items():
        if coin == 'USDC (Account Value)': continue
        # Track position prices if found in Binance map
        if coin in market_prices:
             track_price(coin, market_prices[coin])
        portfolio['Hyperliquid']['assets'].append((coin, size, 0, 0)) # Value handled in total

    portfolio['GrandTotal'] = portfolio['Binance']['total_usd'] + \
                              portfolio['Gate']['total_usd'] + \
                              portfolio['Hyperliquid']['total_usd']
                              
    global PORTFOLIO_CACHE
    PORTFOLIO_CACHE = portfolio
    return portfolio

def track_price(symbol, price):
    """Update rolling window price history"""
    if price <= 0: return
    now = datetime.now()
    
    if symbol not in PRICE_HISTORY:
        PRICE_HISTORY[symbol] = []
        
    history = PRICE_HISTORY[symbol]
    history.append((now, price))
    
    # Prune > 30 mins
    threshold = now - timedelta(minutes=30)
    PRICE_HISTORY[symbol] = [x for x in history if x[0] > threshold]

async def check_alerts(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled Job: Check for 2% drop"""
    await update_portfolio() # Refresh Data
    
    alerts = []
    now = datetime.now()
    
    for symbol, history in PRICE_HISTORY.items():
        if not history: continue
        
        current_price = history[-1][1]
        
        # Find max price in last 30m
        max_price = 0
        for _, p in history:
            if p > max_price: max_price = p
            
        if max_price == 0: continue
        
        drop_pct = (max_price - current_price) / max_price
        
        if drop_pct >= 0.02: # 2% Drop
            # Check Cooldown (1 hour)
            last_t = LAST_ALERT.get(symbol)
            if last_t and (now - last_t < timedelta(hours=1)):
                continue
                
            LAST_ALERT[symbol] = now
            alerts.append(f"⚠️ **{symbol} 警报**\n30分钟内下跌 `{drop_pct*100:.1f}%`\n现价: ${current_price:.4f}")

    if alerts and CONFIG['TG_CHAT_ID']:
        msg = "\n\n".join(alerts)
        await context.bot.send_message(chat_id=CONFIG['TG_CHAT_ID'], text=msg, parse_mode='Markdown')

async def send_periodic_report(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled Job: 4h Report"""
    if not CONFIG['TG_CHAT_ID']: return
    report = format_report()
    await context.bot.send_message(chat_id=CONFIG['TG_CHAT_ID'], text=report, parse_mode='Markdown')

def format_report():
    p = PORTFOLIO_CACHE
    if not p: return "⏳ 数据正在同步中..."
    
    msg = f"📊 **持仓监控报告**\n"
    msg += f"💰 **总资产: ${p['GrandTotal']:.2f}**\n"
    msg += f"----------------\n"
    
    # Binance
    if p['Binance']['total_usd'] > 0:
        msg += f"🔶 **Binance: ${p['Binance']['total_usd']:.2f}**\n"
        for coin, amt, val, price in p['Binance']['assets'][:5]: # Top 5
            msg += f"- {coin}: {amt:.3f} (${val:.1f})\n"
    
    # Gate
    if p['Gate']['total_usd'] > 0:
        msg += f"\n🚪 **Gate: ${p['Gate']['total_usd']:.2f}**\n"
        for coin, amt, val, price in p['Gate']['assets'][:5]:
            msg += f"- {coin}: {amt:.3f} (${val:.1f})\n"
            
    # Hyperliquid
    if p['Hyperliquid']['total_usd'] > 0:
        msg += f"\n💧 **Hyperliquid: ${p['Hyperliquid']['total_usd']:.2f}**\n"
        for coin, amt, val, price in p['Hyperliquid']['assets']:
             if coin == 'USDC (Account Value)': continue
             msg += f"- {coin}: {amt:.3f}\n"

    msg += f"\n_更新于: {datetime.now().strftime('%H:%M:%S')}_"
    return msg

# ==================== Bot Handlers ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 监控机器人已启动！\n使用 /report 查看当前持仓。")

async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = await update.message.reply_text("⏳ 正在扫描各交易所...")
    await update_portfolio() # Force refresh
    msg = format_report()
    await status.edit_text(msg, parse_mode='Markdown')

# ==================== Main ====================

def main():
    if not CONFIG['TG_TOKEN']:
        print("❌ 请先配置 .env 文件中的 TELEGRAM_BOT_TOKEN")
        return

    # App Setup
    app = Application.builder().token(CONFIG['TG_TOKEN']).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", report_cmd))
    
    # Scheduler
    scheduler = AsyncIOScheduler()
    
    # Alert Job: Every 1 minute
    scheduler.add_job(check_alerts, "interval", minutes=1, args=[app])
    
    # Report Job: Every 4 hours
    scheduler.add_job(send_periodic_report, "interval", hours=4, args=[app])
    
    scheduler.start()
    
    print("✅ 机器人已启动！按 Ctrl+C 停止。")
    app.run_polling()

if __name__ == "__main__":
    main()
