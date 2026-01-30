import asyncio
import logging
from unittest.mock import MagicMock, patch
from portfolio_bot import update_portfolio, check_alerts, format_report, PRICE_HISTORY, CONFIG

# Mock Logging to console
logging.basicConfig(level=logging.INFO)

async def test_logic():
    print("[TEST] Starting Mock Test...")

    # 1. Mock Data
    mock_binance = {'BTC': 0.5, 'USDT': 100}
    mock_gate = {'GWEI': 5000}
    mock_hl = {'USDC (Account Value)': 2000, 'ETH': 1.0} # Position just for display
    
    mock_prices = {
        'BTC': 50000.0,
        'GWEI': 0.05,
        'ETH': 3000.0,
        'USDT': 1.0,
        'USDC': 1.0
    }

    # 2. Patch External Calls
    with patch('portfolio_bot.fetch_ccxt_balance') as mock_ccxt:
        with patch('portfolio_bot.fetch_hyperliquid_balance') as mock_hl_func:
            with patch('portfolio_bot.get_market_prices') as mock_price_func:
                
                # Setup Returns
                mock_ccxt.side_effect = lambda ex, creds: mock_binance if ex == 'binance' else mock_gate
                mock_hl_func.return_value = mock_hl
                mock_price_func.return_value = mock_prices
                
                # --- Test 1: Full Portfolio Report ---
                print("\n[TEST] Testing Portfolio Update...")
                await update_portfolio()
                report = format_report().encode('gbk', errors='ignore').decode('gbk') # Try to handle or just raw
                print("Generated Report:")
                print("--------------------------------")
                print(report)
                print("--------------------------------")
                
                # --- Test 2: Alert Logic (Simulate Drop) ---
                print("\n[TEST] Testing Alert Logic...")
                # Inject High History for BTC (Now=50k, History=52k -> ~3.8% drop)
                from datetime import datetime
                PRICE_HISTORY['BTC'] = [(datetime.now(), 52000.0)] 
                
                # Mock Context for Bot
                mock_context = MagicMock()
                async def mock_send(chat_id, text, parse_mode):
                    print(f"SENT TO TG: {text.encode('gbk', 'ignore').decode('gbk')}")
                mock_context.bot.send_message = MagicMock(side_effect=mock_send)
                
                # Run Check
                # Note: CONFIG['TG_CHAT_ID'] must be set for it to trigger send
                CONFIG['TG_CHAT_ID'] = "12345" 
                
                await check_alerts(mock_context)
                
                # Verify
                if mock_context.bot.send_message.called:
                    print("[PASS] Alert triggered successfully!")
                else:
                    print("[FAIL] Alert failed to trigger.")

if __name__ == "__main__":
    asyncio.run(test_logic())
