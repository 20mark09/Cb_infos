import json
import re
import time
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from curl_cffi import requests

OUTPUT_FILE = "egx.json"


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def get_index_summary(type_id):
    url = f"https://www.egx.com.eg/en/indexdata.aspx?type={type_id}&nav=1"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.egx.com.eg/"
    }
    
    response = requests.get(url, headers=headers, impersonate="chrome124", timeout=30)
    return response.text


def parse_metrics_from_stream(html_content, name):
    """
    Parses out the metrics structurally by reading table labels directly
    instead of relying on full-page string regex scanning.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    text_lines = [line.strip() for line in soup.get_text("\n").split("\n") if line.strip()]
    
    # --- DEBUGGING COMPONENT ---
    print(f"--- Extracted Lines for {name} ---")
    print(text_lines[:15])
    print("-----------------------------------")

    # Initialize empty data structure
    data = {k: None for k in ["date", "value", "open", "high", "low", "change_pct", "ytd_pct"]}
    
    # Attempt a universal fall-back regex pattern if lines are joined together
    full_text = " ".join(text_lines)
    
    def clean_num(val_str):
        if not val_str:
            return None
        # Strip out symbols, percent signs, and commas
        cleaned = re.sub(r"[^\d\A-Za-z.\-]", "", val_str)
        try:
            return float(cleaned)
        except ValueError:
            return None

    # Loop through structural table rows or label-value pairs dynamically
    for i, line in enumerate(text_lines):
        # Look for standard Egyptian Exchange keywords across structures
        if "Date" in line and i + 1 < len(text_lines):
            # Capture standard dd/mm/yyyy string format
            date_m = re.search(r"\d{2}/\d{2}/\d{4}", text_lines[i] + " " + text_lines[i+1])
            if date_m:
                data["date"] = date_m.group(0)
        elif "Value" in line and i + 1 < len(text_lines):
            data["value"] = clean_num(text_lines[i+1])
        elif "Open" in line and i + 1 < len(text_lines):
            data["open"] = clean_num(text_lines[i+1])
        elif "High" in line and i + 1 < len(text_lines):
            data["high"] = clean_num(text_lines[i+1])
        elif "Low" in line and i + 1 < len(text_lines):
            data["low"] = clean_num(text_lines[i+1])
        elif "Change" in line and "%" not in line and "YTD" not in line and i + 1 < len(text_lines):
            data["change_pct"] = clean_num(text_lines[i+1])
        elif "YTD" in line and i + 1 < len(text_lines):
            data["ytd_pct"] = clean_num(text_lines[i+1])

    # Smart Fallback: If layout lines were packed together horizontally instead of vertically
    if not data["value"]:
        val_m = re.search(r"Value\s*:\s*([\d,.]+)", full_text, re.IGNORECASE)
        if val_m: data["value"] = clean_num(val_m.group(1))
        
        date_m = re.search(r"Date\s*:\s*(\d{2}/\d{2}/\d{4})", full_text, re.IGNORECASE)
        if date_m: data["date"] = date_m.group(1)
        
        open_m = re.search(r"Open\s*:\s*([\d,.]+)", full_text, re.IGNORECASE)
        if open_m: data["open"] = clean_num(open_m.group(1))
        
        high_m = re.search(r"High\s*:\s*([\d,.]+)", full_text, re.IGNORECASE)
        if high_m: data["high"] = clean_num(high_m.group(1))
        
        low_m = re.search(r"Low\s*:\s*([\d,.]+)", full_text, re.IGNORECASE)
        if low_m: data["low"] = clean_num(low_m.group(1))
        
        change_m = re.search(r"Change\s*:\s*(-?[\d,.]+)", full_text, re.IGNORECASE)
        if change_m: data["change_pct"] = clean_num(change_m.group(1))
        
        ytd_m = re.search(r"YTD%\s*Change\s*:\s*(-?[\d,.]+)", full_text, re.IGNORECASE)
        if ytd_m: data["ytd_pct"] = clean_num(ytd_m.group(1))

    return data


def main():
    print("Beginning connection-bypass structural scrape...")
    
    target_map = {
        "EGX30": 1,
        "EGX70": 2,
        "EGX100": 3,
        "SHARIAH": 13
    }
    
    indices_output = {}

    for name, type_id in target_map.items():
        try:
            print(f"Requesting stream feed for {name} (ID: {type_id})...")
            html_content = get_index_summary(type_id)
            
            metrics = parse_metrics_from_stream(html_content, name)
            indices_output[name] = metrics
            print(f"[+] Processed values successfully for {name}")
            
            # CRITICAL: Sleep for 3 seconds between actions to bypass server rate limiting
            # This completely stops the curl (28) timeout error on EGX100
            time.sleep(3)
            
        except Exception as err:
            print(f"[-] Dropped feed collection for {name}: {err}")
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

    print(f"\nSaved updated metrics file directly to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
