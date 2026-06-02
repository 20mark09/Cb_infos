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
        "open": safe_num(open_match),
        "high": safe_num(high_match),
        "low": safe_num(low_match),
        "change_pct": safe_num(change_match),
        "ytd_pct": safe_num(ytd_match)
    }


def parse_gl_table(soup, index_position):
    """
    Finds tables on Top_GL.aspx by order of appearance to avoid mangled ASP server IDs.
    index_position=0 parses the first table data (Gainers), index_position=1 parses the second (Losers).
    """
    # The grid tables on EGX always share the same styling classes
    tables = soup.find_all("table", {"class": "table"})
    if not tables or len(tables) <= index_position:
        # Fallback to look for alternative GridView table markers if class matches are hidden
        tables = soup.find_all("table", id=lambda x: x and ("gvGainer" in x or "gvLoser" in x))
        
    stocks = []
    if not tables or len(tables) <= index_position:
        return stocks

    target_table = tables[index_position]
    rows = target_table.find_all("tr")[1:] # Drop header columns safely
    
    for row in rows:
        cols = row.find_all("td")
        if len(cols) >= 4:
            try:
                name_text = cols[0].get_text(strip=True)
                if not name_text or "No data available" in name_text:
                    continue
                    
                stocks.append({
                    "name": name_text,
                    "price": float(cols[1].get_text(strip=True).replace(",", "")),
                    "change_pct": float(cols[2].get_text(strip=True).replace(",", "").replace("%", "")),
                    "volume": int(cols[3].get_text(strip=True).replace(",", ""))
                })
            except Exception:
                continue
    return stocks


def main():
    indices_output = {}
    gainers = []
    losers = []

    with sync_playwright() as p:
        print("Launching secure browser context...")
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )

        # --- PART 1: SCRAPE INDICES ---
        postback_actions = {
            "EGX30": "ctl00$C$M$lnkEGX30",
            "SHARIAH": "ctl00$C$M$lnkSHARIAH",
            "EGX70": "ctl00$C$M$lnkEGX70EWI",
            "EGX100": "ctl00$C$M$lnkEGX100EWI"
        }

        for tracking_name, event_target in postback_actions.items():
            print(f"Opening clean tab view for {tracking_name}...")
            try:
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 720}
                )
                page = context.new_page()
                
                page.goto("https://www.egx.com.eg/en/Indices.aspx", wait_until="commit", timeout=60000)
                page.wait_for_timeout(6000)

                page.evaluate(f"""
                    if (typeof __doPostBack !== 'undefined') {{
                        __doPostBack('{event_target}', '');
                    }} else {{
                        document.getElementById('aspnetForm').submit();
                    }}
                """)
                
                page.wait_for_timeout(4000)

                updated_html = page.content()
                indices_output[tracking_name] = parse_panel_metrics(updated_html)
                print(f"[+] Successfully extracted true metrics for {tracking_name}")
                context.close()

            except Exception as loop_error:
                print(f"[-] Failed tracking loop on {tracking_name}: {loop_error}")
                indices_output[tracking_name] = {k: None for k in ["date", "value", "open", "high", "low", "change_pct", "ytd_pct"]}

        # --- PART 2: SCRAPE TOP GAINERS & LOSERS ---
        print("\nNavigating to Top Gainers/Losers Desk...")
        try:
            gl_context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720}
            )
            gl_page = gl_context.new_page()
            gl_page.goto("https://www.egx.com.eg/en/Top_GL.aspx", wait_until="commit", timeout=60000)
            gl_page.wait_for_timeout(8000)  # Wait for JavaScript shield room

            # CRITICAL: Explicitly check if the stock layout tables exist on page before gathering HTML
            try:
                gl_page.wait_for_selector("table", timeout=10000)
            except Exception:
                print("[-] Note: Grid tables didn't render inside target frame timeout.")

            gl_soup = BeautifulSoup(gl_page.content(), "html.parser")
            
            # Position 0 is always the first data grid (Gainers) 
            # Position 1 is always the second data grid (Losers)
            gainers = parse_gl_table(gl_soup, 0)
            losers = parse_gl_table(gl_soup, 1)
            
            print(f"[+] Successfully scraped {len(gainers)} gainers and {len(losers)} losers.")
            gl_context.close()
            
        except Exception as gl_error:
            print(f"[-] Failed to fetch Top Gainers/Losers: {gl_error}")

        browser.close()

    # --- SAVE STRUCTURED RESULTS ---
    output = {
        "source": "https://www.egx.com.eg",
        "lastUpdated": now_utc(),
        "indices": indices_output,
        "gainers": gainers,
        "losers": losers
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nFinal run complete! Tracking metrics saved perfectly to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
