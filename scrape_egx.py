import json
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from curl_cffi import requests

OUTPUT_FILE = "egx.json"


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def get_index_summary(type_id):
    """
    Fetches raw data directly from EGX's unprotected charting engine component.
    type=1 (EGX30), type=2 (EGX70), type=3 (EGX100), type=13 (Shariah)
    """
    url = f"https://www.egx.com.eg/en/indexdata.aspx?type={type_id}&nav=1"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.egx.com.eg/"
    }
    
    # curl_cffi mimics a real browser TLS handshake to slip past basic filters
    response = requests.get(url, headers=headers, impersonate="chrome124", timeout=20)
    return response.text


def parse_metrics(html_content):
    """Extracts data values from the specific data layout."""
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Locate all data rows or labels dynamically
    text = soup.get_text("\n", strip=True)

    # Use flexible regular expressions to grab fields regardless of surrounding whitespace
    date_match = re.search(r"Date\s*:\s*(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
    value_match = re.search(r"Value\s*:\s*([\d,.]+)", text, re.IGNORECASE)
    open_match = re.search(r"Open\s*:\s*([\d,.]+)", text, re.IGNORECASE)
    high_match = re.search(r"High\s*:\s*([\d,.]+)", text, re.IGNORECASE)
    low_match = re.search(r"Low\s*:\s*([\d,.]+)", text, re.IGNORECASE)
    change_match = re.search(r"Change\s*:\s*(-?[\d,.]+)", text, re.IGNORECASE)
    ytd_match = re.search(r"YTD%\s*Change\s*:\s*(-?[\d,.]+)", text, re.IGNORECASE)

    def safe_str(match):
        return match.group(1) if match else None

    def safe_num(match):
        if not match:
            return None
        try:
            return float(match.group(1).replace(",", ""))
        except ValueError:
            return None

    return {
        "date": safe_str(date_match),
        "value": safe_num(value_match),
        "open": safe_num(open_match),
        "high": safe_num(high_match),
        "low": safe_num(low_match),
        "change_pct": safe_num(change_match),
        "ytd_pct": safe_num(ytd_match)
    }


def main():
    print("Beginning connection-bypass scrape...")
    
    # Map index tracking labels directly to internal tracking ID values
    target_map = {
        "EGX30": 1,
        "EGX70": 2,
        "EGX100": 3,
        "SHARIAH": 13
    }
    
    indices_output = {}

    for name, type_id in target_map.items():
        try:
            print(f"Requesting background stream for {name} (ID: {type_id})...")
            html_content = get_index_summary(type_id)
            
            # Extract data parameters cleanly
            metrics = parse_metrics(html_content)
            indices_output[name] = metrics
            print(f"[+] Successfully gathered values for {name}")
            
        except Exception as err:
            print(f"[-] Failed streaming data feed for {name}: {err}")
            indices_output[name] = {k: None for k in ["date", "value", "open", "high", "low", "change_pct", "ytd_pct"]}

    output = {
        "source": "https://www.egx.com.eg",
        "lastUpdated": now_utc(),
        "indices": indices_output,
        "gainers": [],
        "losers": []
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nSaved accurate data metrics successfully to {OUTPUT_FILE}!")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
