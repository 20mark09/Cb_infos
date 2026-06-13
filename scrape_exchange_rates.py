#!/usr/bin/env python3
"""
Fetch exchange rates relative to EGP using:
- frankfurter.app (free, no key) for USD-based cross rates
- CBE cbe.json for official USD/EGP rate
Saves to exchange_rates.json
"""
import json, requests
from datetime import datetime, timezone

OUT     = "exchange_rates.json"
CBE_URL = "https://raw.githubusercontent.com/20mark09/Cb_infos/main/cbe.json"
FX_URL  = "https://api.frankfurter.app/latest?base=USD"

WANTED = ["EUR","GBP","SAR","AED","KWD","QAR","JPY","CNY","CHF","TRY","CAD","AUD"]

def get_usd_egp():
    """Get official USD/EGP mid rate from CBE JSON."""
    try:
        r = requests.get(CBE_URL, timeout=10)
        data = r.json().get("data", {})
        v = data.get("usd_egp_rate", {}).get("value")
        if v: return float(v)
    except Exception:
        pass
    return 49.85  # fallback

def main():
    error = None
    rates = {}
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(FX_URL, headers=headers, timeout=10)
        r.raise_for_status()
        fx = r.json()  # {"base":"USD","rates":{"EUR":0.92,...}}
        usd_cross = fx.get("rates", {})

        usd_egp = get_usd_egp()

        # USD itself
        rates["USD"] = {
            "buy":  round(usd_egp * 1.001, 4),
            "sell": round(usd_egp * 0.999, 4),
            "mid":  round(usd_egp, 4),
        }

        # All other currencies via cross-rate: EGP = USD_EGP / USD_X
        for code in WANTED:
            x = usd_cross.get(code)
            if x and x > 0:
                mid  = round(usd_egp / x, 4)
                buy  = round(mid * 1.005, 4)
                sell = round(mid * 0.995, 4)
                rates[code] = {"buy": buy, "sell": sell, "mid": mid}

    except Exception as e:
        error = str(e)

    result = {
        "source":       "frankfurter.app (cross-rates via CBE USD/EGP)",
        "lastUpdated":  datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "scrape_error": error,
        "rates":        rates,
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(rates)} rates. Error: {error}")

if __name__ == "__main__":
    main()
