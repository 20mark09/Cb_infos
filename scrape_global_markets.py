#!/usr/bin/env python3
"""
Fetch global market data using yfinance.
Adds point change (value - prev_close) alongside percent change.
"""
import json, yfinance as yf
from datetime import datetime, timezone

OUT = "global_markets.json"

INDICES = {
    "SP500":  "^GSPC", "NASDAQ": "^NDX",  "DOW":    "^DJI",
    "FTSE":   "^FTSE", "DAX":    "^GDAXI","NIKKEI": "^N225",
    "HSI":    "^HSI",  "SSEC":   "000001.SS","CAC":  "^FCHI",
    "ASX":    "^AXJO",
}
COMMODITIES = {
    "GOLD_USD":   "GC=F",  "SILVER_USD": "SI=F",
    "OIL_BRENT":  "BZ=F",  "OIL_WTI":    "CL=F",
    "NAT_GAS":    "NG=F",  "COPPER":      "HG=F",
    "WHEAT":      "ZW=F",
}
CRYPTO = {
    "BTC":  "BTC-USD", "ETH":  "ETH-USD", "BNB":  "BNB-USD",
    "SOL":  "SOL-USD", "XRP":  "XRP-USD", "ADA":  "ADA-USD",
    "DOGE": "DOGE-USD","USDT": "USDT-USD",
}

def fetch_group(symbols, is_crypto=False):
    result = {}
    for key, ticker in symbols.items():
        try:
            info  = yf.Ticker(ticker).fast_info
            price = float(info.last_price)       if info.last_price       else None
            prev  = float(info.previous_close)   if info.previous_close   else None
            hi    = float(info.day_high)         if info.day_high         else None
            lo    = float(info.day_low)          if info.day_low          else None
            op    = float(info.open)             if info.open             else None

            chg_pct = round((price - prev) / prev * 100, 2) if price and prev else None
            chg_pts = round(price - prev, 4)                 if price and prev else None

            if is_crypto:
                result[key] = {
                    "price_usd":      round(price, 4) if price else None,
                    "change_24h_pct": chg_pct,
                    "change_24h_pts": chg_pts,
                }
            else:
                result[key] = {
                    "value":      round(price, 4) if price else None,
                    "change_pct": chg_pct,
                    "change_pts": chg_pts,
                    "open":       round(op, 4) if op else None,
                    "high":       round(hi, 4) if hi else None,
                    "low":        round(lo, 4) if lo else None,
                }
        except Exception as e:
            result[key] = {"error": str(e)}
    return result

def main():
    error = None
    try:
        indices     = fetch_group(INDICES)
        commodities = fetch_group(COMMODITIES)
        crypto      = fetch_group(CRYPTO, is_crypto=True)
    except Exception as e:
        error = str(e)
        indices = commodities = crypto = {}

    data = {
        "source":       "Yahoo Finance via yfinance",
        "lastUpdated":  datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "scrape_error": error,
        "indices":      indices,
        "commodities":  commodities,
        "crypto":       crypto,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Done — {len(indices)} indices, {len(commodities)} commodities, {len(crypto)} crypto")

if __name__ == "__main__":
    main()
