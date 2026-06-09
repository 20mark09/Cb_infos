#!/usr/bin/env python3
"""
Scrape CBE official exchange rates from:
https://www.cbe.org.eg/en/economic-research/statistics/exchange-rates

Save result to exchange_rates.json in the repo root.
Add this to your GitHub Actions workflow to run daily.
"""
import json, re, requests
from datetime import datetime, timezone
from bs4 import BeautifulSoup

URL = "https://www.cbe.org.eg/en/economic-research/statistics/exchange-rates"
OUT = "exchange_rates.json"

CURRENCY_MAP = {
    "US Dollar": "USD", "Euro": "EUR", "British Pound": "GBP",
    "Saudi Riyal": "SAR", "UAE Dirham": "AED", "Kuwaiti Dinar": "KWD",
    "Qatari Riyal": "QAR", "Japanese Yen": "JPY", "Chinese Yuan": "CNY",
    "Swiss Franc": "CHF", "Turkish Lira": "TRY", "Canadian Dollar": "CAD",
    "Australian Dollar": "AUD", "Swedish Krona": "SEK",
}

def scrape():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        r = requests.get(URL, headers=headers, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        rates = {}
        # CBE page has a table with Currency | Buying | Selling columns
        for table in soup.find_all("table"):
            headers_row = [th.get_text(strip=True) for th in table.find_all("th")]
            if not any("buy" in h.lower() or "selling" in h.lower() for h in headers_row):
                continue
            for row in table.find_all("tr")[1:]:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) < 3:
                    continue
                name = cells[0]
                code = CURRENCY_MAP.get(name)
                if not code:
                    # Try to extract 3-letter code from the cell text
                    m = re.search(r'\b([A-Z]{3})\b', name)
                    if m:
                        code = m.group(1)
                if not code:
                    continue
                try:
                    buy  = float(cells[1].replace(",", ""))
                    sell = float(cells[2].replace(",", ""))
                    rates[code] = {"buy": buy, "sell": sell, "mid": round((buy + sell) / 2, 4)}
                except (ValueError, IndexError):
                    pass

        result = {
            "source": URL,
            "lastUpdated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "scrape_error": None if rates else "No rates found",
            "rates": rates,
        }
    except Exception as e:
        # Load existing file to preserve last good data
        try:
            with open(OUT) as f:
                result = json.load(f)
            result["scrape_error"] = str(e)
        except Exception:
            result = {"source": URL, "lastUpdated": "", "scrape_error": str(e), "rates": {}}

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(result.get('rates', {}))} rates to {OUT}")
    if result.get("scrape_error"):
        print(f"  Warning: {result['scrape_error']}")

if __name__ == "__main__":
    scrape()
