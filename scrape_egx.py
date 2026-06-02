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
            args=["--disable-blink-features=AutomationControlled"]
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


def parse_indices(html):

    text = BeautifulSoup(
        html,
        "html.parser"
    ).get_text("\n", strip=True)

    print("Contains EGX30:", "EGX30" in text)
    print("Contains Value :", "Value" in text)

    date_match = re.search(
        r"Date\s*:\s*(\d{2}/\d{2}/\d{4})",
        text,
        re.IGNORECASE
    )

    value_match = re.search(
        r"Value\s*:\s*([\d,.]+)",
        text,
        re.IGNORECASE
    )

    open_match = re.search(
        r"Open\s*:\s*([\d,.]+)",
        text,
        re.IGNORECASE
    )

    high_match = re.search(
        r"High\s*:\s*([\d,.]+)",
        text,
        re.IGNORECASE
    )

    low_match = re.search(
        r"Low\s*:\s*([\d,.]+)",
        text,
        re.IGNORECASE
    )

    change_match = re.search(
        r"Change\s*:\s*(-?[\d,.]+)",
        text,
        re.IGNORECASE
    )

    ytd_match = re.search(
        r"YTD%\s*Change\s*:\s*(-?[\d,.]+)",
        text,
        re.IGNORECASE
    )

    def num(match):
        if not match:
            return None

        return float(
            match.group(1)
            .replace(",", "")
        )

    return {
        "EGX30": {
            "date": date_match.group(1) if date_match else None,
            "value": num(value_match),
            "open": num(open_match),
            "high": num(high_match),
            "low": num(low_match),
            "change_pct": num(change_match),
            "ytd_pct": num(ytd_match)
        }
    }


def parse_top_gl(html):

    text = BeautifulSoup(
        html,
        "html.parser"
    ).get_text("\n", strip=True)

    gainers = []
    losers = []

    # We'll add parsing later once the market page is populated.

    return gainers, losers


def main():

    print("Loading indices page...")

    indices_html = get_html(
        "https://www.egx.com.eg/en/Indices.aspx"
    )

    indices = parse_indices(indices_html)

    print("Parsed indices:")
    print(json.dumps(indices, indent=2))

    try:

        print("Loading gainers/losers page...")

        gl_html = get_html(
            "https://www.egx.com.eg/en/Top_GL.aspx"
        )

        gainers, losers = parse_top_gl(gl_html)

    except Exception as e:

        print("Top gainers/losers failed:", e)

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

    print("\nGenerated JSON:")
    print(json.dumps(output, indent=2))

    print(f"\nSaved {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
