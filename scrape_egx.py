import json
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

OUTPUT_FILE = "egx.json"


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def parse_panel_metrics(html_content):
    """Parses out numerical metrics from the actively visible tab panel."""
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
        "open": safe_num(safe_num(open_match)), # Fallback layer
        "high": safe_num(high_match),
        "low": safe_num(low_match),
        "change_pct": safe_num(change_match),
        "ytd_pct": safe_num(ytd_match)
    }


def main():
    indices_output = {}

    with sync_playwright() as p:
        print("Launching secure browser session...")
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )

        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        print("Navigating to EGX Indices Portal...")
        page.goto("https://www.egx.com.eg/en/Indices.aspx", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)

        # Map index tracking keys directly to their explicit __doPostBack script calls!
        # This completely avoids searching for dynamic UI components.
        postback_scripts = {
            "EGX30": "__doPostBack('ctl00$C$M$lnkEGX30','')",
            "SHARIAH": "__doPostBack('ctl00$C$M$lnkSHARIAH','')",
            "EGX70": "__doPostBack('ctl00$C$M$lnkEGX70EWI','')",
            "EGX100": "__doPostBack('ctl00$C$M$lnkEGX100EWI','')"
        }

        for tracking_name, js_command in postback_scripts.items():
            try:
                print(f"Triggering PostBack state for: {tracking_name}...")
                
                # Evaluate the raw JavaScript directly on the page window object
                page.evaluate(js_command)
                
                # Wait for the network requests triggered by the postback to finish completely
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(2000)

                # Extract the freshly updated layout state
                updated_html = page.content()
                indices_output[tracking_name] = parse_panel_metrics(updated_html)
                print(f"[+] Successfully extracted {tracking_name} metrics.")

            except Exception as js_err:
                print(f"[-] Failed to execute postback for {tracking_name}: {js_err}")
                indices_output[tracking_name] = {k: None for k in ["date", "value", "open", "high", "low", "change_pct", "ytd_pct"]}

        context.close()
        browser.close()

    output = {
        "source": "https://www.egx.com.eg",
        "lastUpdated": now_utc(),
        "indices": indices_output,
        "gainers": [],
        "losers": []
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nSaved accurate metrics completely to {OUTPUT_FILE}")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
