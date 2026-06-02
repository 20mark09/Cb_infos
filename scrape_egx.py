import json
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from curl_cffi import requests

OUTPUT_FILE = "egx.json"


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def get_html(url):
    print(f"Requesting Main Portal: {url}...")
    response = requests.get(
        url,
        impersonate="chrome124",
        timeout=30,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": "https://www.google.com/"
        }
    )
    return response.text


def parse_all_indices(html):
    soup = BeautifulSoup(html, "html.parser")
    text_content = soup.get_text("\n", strip=True)
    
    # Define cleaner matching targets inside the entire page string
    # We locate sections by their specific index headers
    indices_to_track = {
        "EGX30": r"EGX30\b",
        "EGX70": r"EGX70\s*EWI",
        "EGX100": r"EGX100\s*EWI",
        "SHARIAH": r"SHARIAH|EGX\s*33\s*Shariah"
    }
    
    results = {}
    
    for key, pattern in indices_to_track.items():
        # Find the index context inside the page text blob
        match_anchor = re.search(pattern, text_content, re.IGNORECASE)
        
        if not match_anchor:
            print(f"[-] Could not find text anchor for {key}")
            results[key] = {k: None for k in ["date", "value", "open", "high", "low", "change_pct", "ytd_pct"]}
            continue
            
        # Extract a window of text right after the index name to grab its data values
        start_pos = match_anchor.end()
        snippet = text_content[start_pos:start_pos + 1500]
        
        # Parse numbers cleanly using relative patterns
        date_m = re.search(r"Date\s*:\s*(\d{2}/\d{2}/\d{4})", snippet, re.IGNORECASE)
        val_m = re.search(r"Value\s*:\s*([\d,.]+)", snippet, re.IGNORECASE)
        open_m = re.search(r"Open\s*:\s*([\d,.]+)", snippet, re.IGNORECASE)
        high_m = re.search(r"High\s*:\s*([\d,.]+)", snippet, re.IGNORECASE)
        low_m = re.search(r"Low\s*:\s*([\d,.]+)", snippet, re.IGNORECASE)
        change_m = re.search(r"Change\s*:\s*(-?[\d,.]+)", snippet, re.IGNORECASE)
        ytd_m = re.search(r"YTD%\s*Change\s*:\s*(-?[\d,.]+)", snippet, re.IGNORECASE)
        
        def safe_str(m):
            return m.group(1) if m else None

        def safe_num(m):
            if not m:
                return None
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                return None

        results[key] = {
            "date": safe_str(date_m),
            "value": safe_num(val_m),
            "open": safe_num(open_m),
            "high": safe_num(high_m),
            "low": safe_num(low_m),
            "change_pct": safe_num(change_m),
            "ytd_pct": safe_num(ytd_m)
        }
        print(f"[+] Successfully extracted {key} metrics.")

    return results


def main():
    print("Initializing tracking run...")
    try:
        # Load the main dashboard directly
        html_data = get_html("https://www.egx.com.eg/en/Indices.aspx")
        indices = parse_all_indices(html_data)
    except Exception as e:
        print(f"Critical execution error: {e}")
        indices = {}

    output = {
        "source": "https://www.egx.com.eg",
        "lastUpdated": now_utc(),
        "indices": indices,
        "gainers": [],
        "losers": []
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
        
    print(f"\nSaved combined data to {OUTPUT_FILE}")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
