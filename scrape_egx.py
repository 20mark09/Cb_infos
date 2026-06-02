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
    """Finds tables on Top_GL.aspx safely by structural order to extract rows."""
    tables = soup.find_all("table", {"class": "table"})
    if not tables:
        tables = soup.find_all("table", id=lambda x: x and ("gvGainer" in x or "gvLoser" in x))
        
    stocks = []
    if not tables or len(tables) <= index_position:
        return stocks

    target_table = tables[index_position]
    rows = target_table.find_all("tr")[1:]  # Drop header row safely
    
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

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )

        # --- PART 1: SCRAPE INDICES ---
        page = context.new_page()
        print("Navigating to Portal Landing View...")
        # Use wait_until="load" to ensure all underlying JavaScript objects are fully ready
        page.goto("https://www.egx.com.eg/en/Indices.aspx", wait_until="load", timeout=60000)
        
        print("Pausing 5 seconds to let page scripts settle...")
        page.wait_for_timeout(5000)

        # Mapping indices to their hardcoded click elements to avoid Javascript evaluation errors
        click_targets = {
            "EGX30": "#ctl00_C_M_lnkEGX30",
            "SHARIAH": "#ctl00_C_M_lnkSHARIAH",
            "EGX70": "#ctl00_C_M_lnkEGX70EWI",
            "EGX100": "#ctl00_C_M_lnkEGX100EWI"
        }

        for tracking_name, selector in click_targets.items():
            print(f"Clicking tab view for {tracking_name}...")
            try:
                # Wait for the selector to be fully actionable, then simulate a clean user click
                page.wait_for_selector(selector, timeout=10000)
                page.click(selector, force=True)
                
                # Wait 4 seconds for the ASP panel update data to apply
                page.wait_for_timeout(4000)

                updated_html = page.content()
                indices_output[tracking_name] = parse_panel_metrics(updated_html)
                print(f"[+] Extracted values completely for {tracking_name}")

            except Exception as loop_error:
                print(f"[-] Error on index loop {tracking_name}: {loop_error}")
                indices_output[tracking_name] = {k: None for k in ["date", "value", "open", "high", "low", "change_pct", "ytd_pct"]}

        page.close()

        # --- PART 2: SCRAPE TOP GAINERS & LOSERS ---
        print("\nNavigating to Top Gainers/Losers Desk...")
        try:
            # Open a completely fresh virtual tab to bypass the connection firewall limit
            gl_page = context.new_page()
            gl_page.goto("https://www.egx.com.eg/en/Top_GL.aspx", wait_until="load", timeout=60000)
            gl_page.wait_for_timeout(6000)

            try:
                gl_page.wait_for_selector("table", timeout=10000)
            except Exception:
                pass

            gl_soup = BeautifulSoup(gl_page.content(), "html.parser")
            gainers = parse_gl_table(gl_soup, 0)
            losers = parse_gl_table(gl_soup, 1)
            
            print(f"[+] Successfully scraped {len(gainers)} gainers and {len(losers)} losers.")
            gl_page.close()
            
        except Exception as gl_error:
            print(f"[-] Failed to fetch Top Gainers/Losers: {gl_error}")

        context.close()
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
