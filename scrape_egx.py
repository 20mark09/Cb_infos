import json
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import requests

OUTPUT_FILE = "egx.json"


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def parse_panel_metrics(html_content):
    """Parses out numerical metrics from the returned HTML structure."""
    text = BeautifulSoup(html_content, "html.parser").get_text("\n", strip=True)

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
    url = "https://www.egx.com.eg/en/Indices.aspx"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Origin": "https://www.egx.com.eg",
        "Referer": url,
    }

    indices_output = {}
    session = requests.Session()

    print("Fetching base verification tokens...")
    try:
        response = session.get(url, headers=headers, timeout=30)
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Extract necessary form authentication keys required by the ASP backend
        viewstate = soup.find("input", {"id": "__VIEWSTATE"})["value"]
        generator = soup.find("input", {"id": "__VIEWSTATEGENERATOR"})["value"]
        validation = soup.find("input", {"id": "__EVENTVALIDATION"})["value"]
    except Exception as token_err:
        print(f"CRITICAL: Failed to seed foundational form tokens: {token_err}")
        return

    # Map our structural indicators directly to target programmatic event actions
    target_targets = {
        "EGX30": "ctl00$C$M$lnkEGX30",
        "SHARIAH": "ctl00$C$M$lnkSHARIAH",
        "EGX70": "ctl00$C$M$lnkEGX70EWI",
        "EGX100": "ctl00$C$M$lnkEGX100EWI"
    }

    for tracking_name, event_target in target_targets.items():
        print(f"Requesting structural payload updates for: {tracking_name}...")
        
        # Build the exact form schema expected by the server back-end script
        form_payload = {
            "__EVENTTARGET": event_target,
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": viewstate,
            "__VIEWSTATEGENERATOR": generator,
            "__EVENTVALIDATION": validation,
            "ctl00$txtSearch": ""
        }

        try:
            # Replay the structural update post directly to the page form processor
            post_response = session.post(url, headers=headers, data=form_payload, timeout=30)
            
            if post_response.status_code == 200:
                indices_output[tracking_name] = parse_panel_metrics(post_response.text)
                print(f"[+] Successfully structured data metrics for {tracking_name}")
                
                # Update tracking keys sequentially in case states cascade across steps
                post_soup = BeautifulSoup(post_response.text, "html.parser")
                if post_soup.find("input", {"id": "__VIEWSTATE"}):
                    viewstate = post_soup.find("input", {"id": "__VIEWSTATE"})["value"]
                    validation = post_soup.find("input", {"id": "__EVENTVALIDATION"})["value"]
            else:
                print(f"[-] Received unexpected response status {post_response.status_code} for {tracking_name}")
                indices_output[tracking_name] = {k: None for k in ["date", "value", "open", "high", "low", "change_pct", "ytd_pct"]}
                
        except Exception as api_err:
            print(f"[-] Execution pipeline dropped during {tracking_name}: {api_err}")
            indices_output[tracking_name] = {k: None for k in ["date", "value", "open", "high", "low", "change_pct", "ytd_pct"]}

    output = {
        "source": "https://www.egx.com.eg",
        "lastUpdated": now_utc(),
        "indices": indices_output,
        "gainers": [],
        "losers": []
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nSaved metrics completely to {OUTPUT_FILE}")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
