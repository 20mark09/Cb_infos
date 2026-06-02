import json
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from curl_cffi import requests

OUTPUT_FILE = "egx.json"

def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def get_html(url):
    print(f"Requesting via Spoofed Chrome Client: {url}...")
    
    # impersonate="chrome124" mimics the exact network handshake of Chrome
    response = requests.get(
        url, 
        impersonate="chrome124", 
        timeout=30,
        headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/"
        }
    )
    return response.text

def parse_indices(html):
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    
    if "EGX30" not in text:
        print("--- DEBUG: Text still empty or blocked ---")
        print(text[:500])
        print("---------------------------------------")

    print("Contains EGX30:", "EGX30" in text)

    date_match = re.search(r"Date\s*:\s*(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
    value_match = re.search(r"Value\s*:\s*([\d,.]+)", text, re.IGNORECASE)
    open_match = re.search(r"Open\s*:\s*([\d,.]+)", text, re.IGNORECASE)
    high_match = re.search(r"High\s*:\s*([\d,.]+)", text, re.IGNORECASE)
    low_match = re.search(r"Low\s*:\s*([\d,.]+)", text, re.IGNORECASE)
    change_match = re.search(r"Change\s*:\s*(-?[\d,.]+)", text, re.IGNORECASE)
    ytd_match = re.search(r"YTD%\s*Change\s*:\s*(-?[\d,.]+)", text, re.IGNORECASE)

    def safe_str(match):
        return match.group(1) if match else None

    def num(match):
        if not match:
            return None
        return float(match.group(1).replace(",", ""))

    return {
        "EGX30": {
            "date": safe_str(date_match),
            "value": num(value_match),
            "open": num(open_match),
            "high": num(high_match),
            "low": num(low_match),
            "change_pct": num(change_match),
            "ytd_pct": num(ytd_match)
        }
    }

def main():
    try:
        indices_html = get_html("https://www.egx.com.eg/en/Indices.aspx")
        indices = parse_indices(indices_html)
    except Exception as e:
        print("Indices fetch failed:", e)
        indices = {"EGX30": {k: None for k in ["date", "value", "open", "high", "low", "change_pct", "ytd_pct"]}}

    gainers, losers = [], []
    try:
        gl_html = get_html("https://www.egx.com.eg/en/Top_GL.aspx")
        # Parsing placeholder
    except Exception as e:
        print("Top gainers/losers failed:", e)

    output = {
        "source": "https://www.egx.com.eg",
        "lastUpdated": now_utc(),
        "indices": indices,
        "gainers": gainers,
        "losers": losers
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
        
    print(f"Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
