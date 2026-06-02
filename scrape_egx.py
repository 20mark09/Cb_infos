import json
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

OUTPUT_FILE = "egx.json"


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def get_html(url):
    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )

        page = browser.new_page()

        page.goto(
            url,
            wait_until="networkidle",
            timeout=60000
        )

        html = page.content()

        browser.close()

        return html


def get_match(pattern, text):
    m = re.search(pattern, text, re.IGNORECASE)

    if not m:
        return None

    value = m.group(1).replace(",", "").strip()

    try:
        return float(value)
    except:
        return value


def parse_indices(html):

    text = BeautifulSoup(
        html,
        "html.parser"
    ).get_text("\n", strip=True)

    print("EGX30 found:", "EGX30" in text)
    print("Value found:", "Value" in text)

    date_match = re.search(
        r"Date\s*:\s*(\d{2}/\d{2}/\d{4})",
        text,
        re.IGNORECASE
    )

    indices = {
        "EGX30": {
            "date": date_match.group(1) if date_match else None,
            "value": get_match(
                r"Value\s*:\s*([\d,.]+)",
                text
            ),
            "open": get_match(
                r"Open\s*:\s*([\d,.]+)",
                text
            ),
            "high": get_match(
                r"High\s*:\s*([\d,.]+)",
                text
            ),
            "low": get_match(
                r"Low\s*:\s*([\d,.]+)",
                text
            ),
            "change_pct": get_match(
                r"Change\s*:\s*(-?[\d,.]+)",
                text
            ),
            "ytd_pct": get_match(
                r"YTD%\s*Change\s*:\s*(-?[\d,.]+)",
                text
            )
        }
    }

    return indices


def parse_top_gl(html):

    text = BeautifulSoup(
        html,
        "html.parser"
    ).get_text("\n", strip=True)

    gainers = []
    losers = []

    # We'll implement this after market opens
    # and we can inspect Top_GL.aspx

    return gainers, losers


def main():

    print("Loading indices page...")

    indices_html = get_html(
        "https://www.egx.com.eg/en/Indices.aspx"
    )

    indices = parse_indices(indices_html)

    print(json.dumps(indices, indent=2))

    try:

        print("Loading gainers/losers page...")

        gl_html = get_html(
            "https://www.egx.com.eg/en/Top_GL.aspx"
        )

        gainers, losers = parse_top_gl(gl_html)

    except Exception as e:

        print("Top GL error:", e)

        gainers = []
        losers = []

    output = {
        "source": "https://www.egx.com.eg",
        "lastUpdated": now_utc(),
        "indices": indices,
        "gainers": gainers,
        "losers": losers
    }

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            output,
            f,
            indent=2,
            ensure_ascii=False
        )

    print("\nFinal JSON:")
    print(json.dumps(output, indent=2))

    print(f"\nSaved {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
