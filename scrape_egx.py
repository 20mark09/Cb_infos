import json
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from curl_cffi import requests

OUTPUT_FILE = "egx.json"


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def get_html(url):
    print(f"Requesting Feed: {url}...")
    response = requests.get(
        url,
        impersonate="chrome124",
        timeout=30,
        headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.egx.com.eg/"
        }
    )
    return response.text


def parse_single_index(html, index_name):
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)

    # Regular expressions matching the metrics
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
        "date": safe_str(date_match),
        "value": num(value_match),
        "open": num(open_match),
        "high": num(high_match),
        "low": num(low_match),
        "change_pct": num(change_match),
        "ytd_pct": num(ytd_match)
    }


def main():
    # Map index tracking keys to their internal platform ID numbers
    # type=1: EGX30, type=2: EGX70 EWI, type=3: EGX100 EWI, type=13: SHARIAH
    target_indices = {
        "EGX30": "https://www.egx.com.eg/en/indexdata.aspx?type=1&nav=1",
        "EGX70": "https://www.egx.com.eg/en/indexdata.aspx?type=2&nav=1",
        "EGX100": "https://www.egx.com.eg/en/indexdata.aspx?type=3&nav=1",
        "SHARIAH": "https://www.egx.com.eg/en/indexdata.aspx?type=13&nav=1"
    }

    indices_output = {}

    print("Loading all market indices...")
    for name, url in target_indices.items():
        try:
            html_content = get_html(url)
            indices_output[name] = parse_single_index(html_content, name)
            print(f"Successfully compiled data for {name}")
        except Exception as e:
            print(f"Failed to fetch or parse {name}: {e}")
            indices_output[name] = {k: None for k in ["date", "value", "open", "high", "low", "change_pct", "ytd_pct"]}

    gainers, losers = [], []
    try:
        print("Loading gainers/losers data...")
        gl_html = get_html("https://www.egx.com.eg/en/Top_GL.aspx")
        # Parsing adjustments can go here if needed later
    except Exception as e:
        print("Top gainers/losers feed failed:", e)

    output = {
        "source": "https://www.egx.com.eg",
        "lastUpdated": now_utc(),
        "indices": indices_output,
        "gainers": gainers,
        "losers": losers
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
        
    print(f"\nSaved tracking updates successfully to {OUTPUT_FILE}!")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
