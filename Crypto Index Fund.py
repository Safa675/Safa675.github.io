# crypto_index_real_fixed.py
# Requires: pip install requests python-binance

import requests
import math
from decimal import Decimal
from binance.client import Client
from binance.exceptions import BinanceAPIException

# -------------------- CONFIG --------------------
API_KEY = "Your API Key here"
API_SECRET = "Your API Secret here"
PORTFOLIO_USD_OVERRIDE = None
EXECUTE_REAL = False
REBALANCE_THRESHOLD = 0.02
TOP_N = 15
# ------------------------------------------------

client = Client(API_KEY, API_SECRET)  # mainnet client

# -------------------- Helpers --------------------
def format_quantity(qty, step_size=0.00001):
    """Convert quantity to plain decimal string, no scientific notation."""
    d = Decimal(str(qty)).quantize(Decimal(str(step_size)))
    return format(d, 'f')

def round_qty_for_symbol(sym_usdt, qty):
    """Round quantity DOWN to step size and ensure >= minQty. Return 0 if below minQty."""
    info = client.get_symbol_info(sym_usdt)
    if not info:
        return 0
    lot = next((f for f in info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
    if not lot:
        return round(qty, 8)
    step = float(lot['stepSize'])
    min_qty = float(lot['minQty'])
    if qty < min_qty:
        return 0
    rounded = math.floor(qty / step) * step
    return float(round(rounded, 8))

def meets_min_notional(sym_usdt, qty):
    info = client.get_symbol_info(sym_usdt)
    if not info:
        return False
    mn = next((f for f in info['filters'] if f['filterType'] == 'MIN_NOTIONAL'), None)
    if not mn:
        return True
    min_notional = float(mn['minNotional'])
    price = float(client.get_symbol_ticker(symbol=sym_usdt)['price'])
    return qty * price >= min_notional

def get_usdt_balance():
    acct = client.get_account()
    for bal in acct['balances']:
        if bal['asset'] == 'USDT':
            return float(bal['free']) + float(bal['locked'])
    return 0.0

def get_current_portfolio_for_coins(coins):
    acct = client.get_account()
    balances = {}
    for bal in acct['balances']:
        if bal['asset'] in coins:
            free_qty = float(bal['free'])
            if free_qty > 0:
                balances[bal['asset']] = free_qty
    return balances

def get_top_coins_from_coingecko(n=10):
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {"vs_currency": "usd", "order": "market_cap_desc", "per_page": n+5, "page": 1, "sparkline": False}
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    results = resp.json()
    stablecoins = {"usdt", "usdc", "busd", "dai"}
    top = []
    for c in results:
        sym = c["symbol"].upper()
        if sym.lower() in stablecoins:
            continue
        top.append({"symbol": sym, "price": float(c["current_price"])})
        if len(top) >= n:
            break
    return top

def symbol_exists_on_binance(sym_usdt):
    info = client.get_symbol_info(sym_usdt)
    return info is not None

# -------------------- Main flow --------------------
def main():
    print("Fetching top coins from CoinGecko...")
    top_coins = get_top_coins_from_coingecko(TOP_N)
    print("Top coins (raw):", [c['symbol'] for c in top_coins])

    # Filter coins available on Binance
    available = []
    for c in top_coins:
        pair = c['symbol'] + "USDT"
        if symbol_exists_on_binance(pair):
            price = float(client.get_symbol_ticker(symbol=pair)['price'])
            available.append({"symbol": c['symbol'], "pair": pair, "price": price})
        else:
            print(f"Skipping {c['symbol']}: no {pair} pair on Binance mainnet")

    if not available:
        print("No valid coins on Binance. Exiting.")
        return

    portfolio = PORTFOLIO_USD_OVERRIDE or get_usdt_balance()
    print(f"Using portfolio (USDT): {portfolio}")

    per_coin_usd = portfolio / len(available)
    target_qty = {c['symbol']: per_coin_usd / c['price'] for c in available}
    print("Target quantities (per coin):")
    for c in available:
        print(f"  {c['symbol']} -> {target_qty[c['symbol']]:.8f} ({per_coin_usd} / {c['price']})")

    current_balances = get_current_portfolio_for_coins([c['symbol'] for c in available])
    print("Current balances (nonzero):", current_balances)

    orders = []
    for c in available:
        coin = c['symbol']
        pair = c['pair']
        tgt = target_qty[coin]
        cur = current_balances.get(coin, 0.0)
        deviation = 0 if tgt == 0 else abs(tgt - cur) / tgt
        if deviation <= REBALANCE_THRESHOLD:
            continue

        raw_qty = abs(tgt - cur)
        qty = round_qty_for_symbol(pair, raw_qty)
        if qty <= 0:
            print(f"Qty for {pair} too small -> skip")
            continue
        if not meets_min_notional(pair, qty):
            print(f"Order for {pair} qty {qty} fails MIN_NOTIONAL -> skip")
            continue

        side = "BUY" if tgt > cur else "SELL"
        orders.append({"pair": pair, "side": side, "qty": format_quantity(qty), "coin": coin, "tgt": tgt, "cur": cur})

    if not orders:
        print("No orders to place (within threshold).")
        return

    print("\nOrders prepared:")
    for o in orders:
        print(f"  {o['side']} {o['qty']} {o['pair']} (current {o['cur']:.8f} -> target {o['tgt']:.8f})")

    if not EXECUTE_REAL:
        print("\nEXECUTE_REAL is False — dry run, no orders placed.")
        return

    print("\nEXECUTING ORDERS ON REAL BINANCE")
    for o in orders:
        try:
            print(f"Placing {o['side']} {o['qty']} {o['pair']} ...")
            res = client.create_order(symbol=o['pair'], side=o['side'], type="MARKET", quantity=o['qty'])
            print("Order result:", res)
        except BinanceAPIException as e:
            print(f"Order failed for {o['pair']}: code {e.status_code} - {e.message}")
        except Exception as ex:
            print(f"Unexpected error for {o['pair']}: {ex}")

if __name__ == "__main__":
    main()

