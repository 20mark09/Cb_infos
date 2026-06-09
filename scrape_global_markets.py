#!/usr/bin/env python3
"""
Fetch global market data using yfinance (Yahoo Finance).
Saves to global_markets.json in the repo root.

Install: pip install yfinance
Add to GitHub Actions — runs every 30 min on weekdays.
"""
import json, yfinance as yf
from datetime import datetime, timezone

OUT = "global_markets.json"

INDICES = {
    "SP500":   "^GSPC",
    "NASDAQ":  "^NDX",
    "DOW":     "^DJI",
    "FTSE":    "^FTSE",
    "DAX":     "^GDAXI",
    "NIKKEI":  "^N225",
    "HSI":     "^HSI",
    "SSEC":    "000001.SS",
    "CAC":     "^FCHI",
    "ASX":     "^AXJO",
}

COMMODITIES = {
    "GOLD_USD":   "GC=F",
    "SILVER_USD": "SI=F",
    "OIL_BRENT":  "BZ=F",
    "OIL_WTI":    "CL=F",
    "NAT_GAS":    "NG=F",
    "COPPER":     "HG=F",
    "WHEAT":      "ZW=F",
}

CRYPTO = {
    "BTC":  "BTC-USD",
    "ETH":  "ETH-USD",
    "BNB":  "BNB-USD",
    "SOL":  "SOL-USD",
    "XRP":  "XRP-USD",
    "ADA":  "ADA-USD",
    "DOGE": "DOGE-USD",
    "USDT": "USDT-USD",
}

def fetch_group(symbols: dict) -> dict:
    result = {}
    for key, ticker in symbols.items():
        try:
            t = yf.Ticker(ticker)
            info = t.fast_info
            price   = float(info.last_price)          if info.last_price  else None
            prev    = float(info.previous_close)      if info.previous_close else None
            day_hi  = float(info.day_high)            if info.day_high    else None
            day_lo  = float(info.day_low)             if info.day_low     else None
            open_p  = float(info.open)                if info.open        else None
            chg_pct = round((price - prev) / prev * 100, 2) if price and prev else None
            entry = {
                "value":      round(price, 4) if price else None,
                "change_pct": chg_pct,
                "open":       round(open_p, 4) if open_p else None,
                "high":       round(day_hi, 4) if day_hi else None,
                "low":        round(day_lo, 4) if day_lo else None,
            }
            # Crypto uses price_usd key
            if key in CRYPTO:
                entry = {"price_usd": round(price, 4) if price else None, "change_24h_pct": chg_pct}
            result[key] = entry
        except Exception as e:
            result[key] = {"error": str(e)}
    return result

def main():
    error = None
    try:
        indices     = fetch_group(INDICES)
        commodities = fetch_group(COMMODITIES)
        crypto      = fetch_group(CRYPTO)
    except Exception as e:
        error = str(e)
        indices = commodities = crypto = {}

    data = {
        "source":      "Yahoo Finance via yfinance",
        "lastUpdated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "scrape_error": error,
        "indices":     indices,
        "commodities": commodities,
        "crypto":      crypto,
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Saved global markets data — {len(indices)} indices, "
          f"{len(commodities)} commodities, {len(crypto)} crypto")

if __name__ == "__main__":
    main()
