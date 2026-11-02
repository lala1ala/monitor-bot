"""Hyperliquid 余额只读探针（诊断用，不推送、不改任何数据）

目的：回答「HL 的其他币种为什么没进报告」。
只调 Hyperliquid 一个域名，不碰币安/Gate，几十秒结束。

查 6 个地方，因为用户看到的「现货余额」在网页上可能来自其中任一：
  1. clearinghouseState   永续账户权益 + 仓位
  2. spotClearinghouseState 现货余额（主战场）
  3. userVaultEquities     vault 里的份额
  4. delegatorSummary      质押
  5. subAccounts           子账户（币可能在子账户里）
  6. evmEscrows            HyperEVM 托管（币转去 HyperEVM 后会在这里，不在 spot）
"""
import os
import json
import requests

WALLET = os.environ.get('HYPERLIQUID_WALLET') or ''
PROXY = os.environ.get('PROXY_URL') or ''

URL = 'https://api.hyperliquid.xyz/info'
PROXIES = {'http': PROXY, 'https': PROXY} if PROXY else None


def mask(a):
    if not a:
        return '(空)'
    return f'{a[:6]}...{a[-4:]}  len={len(a)}'


def call(kind, payload, timeout=15):
    body = {'type': kind}
    body.update(payload)
    try:
        r = requests.post(URL, json=body, proxies=PROXIES, timeout=timeout)
        return r.status_code, r.text
    except Exception as e:
        return None, f'EXCEPTION: {e}'


def main():
    print(f'[probe] 代理: {"已配置" if PROXY else "未配置(直连)"}')
    print(f'[probe] 钱包: {mask(WALLET)}')

    if not WALLET:
        print('[probe] ❌ HYPERLIQUID_WALLET 为空 → 根本没读')
        return

    # ---------- 1. 永续 ----------
    st, txt = call('clearinghouseState', {'user': WALLET})
    acct_val = 0.0
    n_pos = 0
    if st == 200:
        d = json.loads(txt)
        acct_val = float((d.get('marginSummary') or {}).get('accountValue', 0) or 0)
        positions = d.get('assetPositions') or []
        coins = []
        for p in positions:
            pos = p.get('position') or {}
            if float(pos.get('sze', 0) or 0) != 0:
                coins.append(f"{pos.get('coin')}:{pos.get('sze')}")
                n_pos += 1
        print(f'[probe] 1) 永续 accountValue=${acct_val:,.2f}  仓位 {n_pos} 个 {coins}')
    else:
        print(f'[probe] 1) 永续 失败 status={st} body={txt[:200]}')

    # ---------- 2. 现货 ----------
    st, txt = call('spotClearinghouseState', {'user': WALLET})
    spot_bal = []
    evm_escrow = []
    if st == 200:
        d = json.loads(txt)
        spot_bal = d.get('balances') or []
        evm_escrow = d.get('evmEscrows') or []
        print(f'[probe] 2) 现货 status=200  balances={len(spot_bal)} 条')
        if not spot_bal:
            print('[probe]    ⚠️ balances 是空数组 —— 该地址在 HL 现货没有任何余额')
        for b in spot_bal:
            print(f"[probe]      coin={b.get('coin')!r:12s} total={b.get('total')!r:20s} "
                  f"hold={b.get('hold')!r:12s} entryNtl={b.get('entryNtl')!r}")
        print(f'[probe]    evmEscrows={len(evm_escrow)} 条 {evm_escrow if evm_escrow else ""}')
    else:
        print(f'[probe] 2) 现货 失败 status={st} body={txt[:200]}')

    # ---------- 3. vault ----------
    st, txt = call('userVaultEquities', {'user': WALLET})
    if st == 200:
        d = json.loads(txt)
        print(f'[probe] 3) vault 份额 {len(d or [])} 条: '
              f'{[(x.get("vaultAddress", "")[:10], x.get("equity")) for x in (d or [])]}')
    else:
        print(f'[probe] 3) vault 失败 status={st} body={txt[:150]}')

    # ---------- 4. 质押 ----------
    st, txt = call('delegatorSummary', {'user': WALLET})
    if st == 200:
        print(f'[probe] 4) 质押 {txt[:300]}')
    else:
        print(f'[probe] 4) 质押 失败 status={st} body={txt[:150]}')

    # ---------- 5. 子账户 ----------
    st, txt = call('subAccounts', {'user': WALLET})
    if st == 200:
        d = json.loads(txt)
        n = len(d) if isinstance(d, list) else 0
        print(f'[probe] 5) 子账户 {n} 个')
        if n:
            for s in d:
                print(f'[probe]      {s.get("name")} {s.get("subAccountUser")}')
    else:
        print(f'[probe] 5) 子账户 失败 status={st} body={txt[:150]}')

    # ---------- 6. allMids 覆盖 ----------
    st, txt = call('allMids', {})
    if st == 200:
        mids = json.loads(txt)
        print(f'[probe] 6) allMids {len(mids)} 条')
        for b in spot_bal:
            c = b.get('coin')
            print(f'[probe]      现货币 {c} 在 allMids: {mids.get(c, "【无】")}')
    else:
        print(f'[probe] 6) allMids 失败 status={st} body={txt[:150]}')

    # ---------- 小结 ----------
    print('[probe] ---- 小结 ----')
    print(f'[probe] 永续权益 ${acct_val:,.2f} | 永续仓位 {n_pos} | 现货币种 {len(spot_bal)} | '
          f'evmEscrows {len(evm_escrow)}')
    if acct_val > 0 and len(spot_bal) <= 1 and not evm_escrow:
        print('[probe] 判定: 该地址现货确实没有其他币 → 你看到的其他币种在另一个地址/账户')

    # ---------- 7. 定价验证：复刻 cloud_portfolio 的两段式取价 ----------
    # allMids 缺价的币 → spotMeta 映射 pair → l2Book 中间价
    st, txt = call('allMids', {})
    mids = json.loads(txt) if st == 200 else {}
    st2, txt2 = call('spotMeta', {})
    pairmap = {}
    if st2 == 200:
        meta = json.loads(txt2)
        tok = {t['index']: t['name'] for t in meta.get('tokens', [])}
        STABLE = ('USDC', 'USDH', 'USDT0', 'USDE')
        for u in meta.get('universe', []):
            ids = u.get('tokens') or []
            if len(ids) != 2:
                continue
            b, q = tok.get(ids[0]), tok.get(ids[1])
            if not b or q not in STABLE:
                continue
            prev = pairmap.get(b)
            if prev is None or (q == 'USDC' and prev[1] != 'USDC'):
                pairmap[b] = (u.get('name'), q)

    STABLE_COINS = ('USDC', 'USDH', 'USDT', 'USDE', 'USDT0')
    total = 0.0
    print('[probe] ---- 定价（新逻辑）----')
    for b in spot_bal:
        coin = b.get('coin')
        amt = float(b.get('total', 0) or 0)
        px, src = 0.0, '无价'
        if coin in STABLE_COINS:
            px, src = 1.0, '稳定币'
        elif coin in mids:
            try:
                px, src = float(mids[coin]), 'allMids'
            except Exception:
                pass
        elif coin in pairmap:
            st3, txt3 = call('l2Book', {'coin': pairmap[coin][0]})
            if st3 == 200:
                lv = json.loads(txt3).get('levels') or [[], []]
                bb = float(lv[0][0]['px']) if lv[0] else None
                ba = float(lv[1][0]['px']) if lv[1] else None
                if bb and ba:
                    px, src = (bb + ba) / 2, f'l2Book {pairmap[coin][0]}'
                elif bb:
                    px, src = bb, f'l2Book {pairmap[coin][0]}'
        val = amt * px
        total += val
        print(f'[probe]   {coin:8s} {amt:>18.8f} × {px:>14.6f} = ${val:>12,.2f}  [{src}]')
    print(f'[probe] HL 现货总值（新逻辑）= ${total:,.2f}')
    print(f'[probe] 对照：旧逻辑只算到 USDC ≈ '
          f'${sum(float(b.get("total", 0) or 0) for b in spot_bal if b.get("coin") == "USDC"):,.2f}')


if __name__ == '__main__':
    main()
