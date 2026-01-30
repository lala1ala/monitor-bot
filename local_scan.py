import requests
import time
from datetime import datetime, timedelta

# ==================== Simplified Logic for Local Run ====================

class LocalMonitor:
    def __init__(self):
        self.proxies = []
        self.proxy_index = 0

    def get_public_proxies(self):
        """Fetch public proxies if needed"""
        if self.proxies: return
        try:
            print("正在获取公共代理列表 (Ref: monosans)...")
            url = "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                all_proxies = resp.text.splitlines()[:50]
                self.proxies = [{"http": f"http://{p}", "https": f"http://{p}"} for p in all_proxies]
                print(f"成功获取 {len(self.proxies)} 个代理")
        except Exception as e:
            print(f"获取代理失败: {e}")

    def request_with_retry(self, url):
        # 1. Try Direct
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "restricted" in str(data.get('msg', '')):
                    raise ValueError("IP Restricted")
                return data
        except Exception:
            pass

        # 2. Try Proxies
        self.get_public_proxies()
        if not self.proxies: return None
        
        for _ in range(5):
            if self.proxy_index >= len(self.proxies): self.proxy_index = 0
            proxy = self.proxies[self.proxy_index]
            try:
                resp = requests.get(url, proxies=proxy, timeout=5)
                if resp.status_code == 200:
                    return resp.json()
            except:
                pass
            self.proxy_index += 1
        return None

    def get_real_oi_growth(self, symbol):
        try:
            # OI Now
            oi_resp = self.request_with_retry(f"https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}")
            if not oi_resp or 'openInterest' not in oi_resp: return 0, 0, 1.0
            oi_now = float(oi_resp['openInterest'])
            
            # OI History (30m ago)
            hist_url = f"https://fapi.binance.com/futures/data/openInterestHist?symbol={symbol}&period=5m&limit=7"
            hist_resp = self.request_with_retry(hist_url)
            if not hist_resp or not isinstance(hist_resp, list): return oi_now, 0, 1.0

            oi_30m_ago = float(hist_resp[0]['sumOpenInterest'])
            oi_growth = ((oi_now - oi_30m_ago) / oi_30m_ago) * 100 if oi_30m_ago > 0 else 0

            # LS Ratio
            ls_url = f"https://fapi.binance.com/futures/data/topLongShortPositionRatio?symbol={symbol}&period=30m&limit=1"
            ls_resp = self.request_with_retry(ls_url)
            ls_ratio = float(ls_resp[0]['longShortRatio']) if ls_resp else 1.0

            return oi_now, oi_growth, ls_ratio
        except:
            return 0, 0, 1.0

    def scan(self):
        print("🔍 正在扫描币安市场数据，请稍候...", flush=True)
        t_resp = self.request_with_retry("https://fapi.binance.com/fapi/v1/ticker/24hr")
        p_resp = self.request_with_retry("https://fapi.binance.com/fapi/v1/premiumIndex")

        if not t_resp or not isinstance(t_resp, list):
            print("⚠️ 无法连接币安 API (可能由于网络限制)")
            return

        premiums = {p['symbol']: p for p in p_resp} if isinstance(p_resp, list) else {}
        
        # Filter active USDT pairs
        active_tickers = sorted(
            [t for t in t_resp if t['symbol'].endswith("USDT")],
            key=lambda x: float(x['quoteVolume']),
            reverse=True
        )[:30] # Top 30 for speed

        all_metrics = []
        for i, t in enumerate(active_tickers):
            s = t['symbol']
            # print(f"Processing {s} ({i+1}/{len(active_tickers)})...")
            oi_val, oi_chg, ls = self.get_real_oi_growth(s)
            funding = float(premiums[s]['lastFundingRate']) * 100 if s in premiums else 0
            
            all_metrics.append({
                "symbol": s,
                "price_chg": float(t['priceChangePercent']),
                "oi_chg": oi_chg,
                "ls": ls,
                "funding": funding
            })

        # Generate Report
        accumulation = [d for d in all_metrics if -2 < d['price_chg'] < 5 and d['oi_chg'] > 1.5 and d['ls'] > 1.2]
        top_oi = sorted(all_metrics, key=lambda x: x['oi_chg'], reverse=True)[:5]
        
        print("\n" + "="*40)
        beijing_time = datetime.utcnow() + timedelta(hours=8)
        print(f"🛰️ 【{beijing_time.strftime('%H:%M')} 实时扫描报告】\n")
        
        print("💎 **低位吸筹监控 (盘整+OI增+大户多)**")
        if not accumulation: print("• (无匹配)")
        for d in accumulation:
            print(f"• {d['symbol']}: OI:+{d['oi_chg']:.1f}% | LS:{d['ls']:.2f}")

        print("\n📈 **30分钟 OI 激增榜**")
        for d in top_oi:
            print(f"• {d['symbol']}: +{d['oi_chg']:.1f}% | LS:{d['ls']:.2f} | 费率:{d['funding']:.3f}%")
            
        print("="*40)

if __name__ == "__main__":
    monitor = LocalMonitor()
    monitor.scan()
