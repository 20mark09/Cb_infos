import json
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


OUTPUT_FILE = "egx.json"


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def extract_number(text):
    if not text:
        return None

    text = text.replace(",", "")
    m = re.search(r"-?\d+\.?\d*", text)

    return float(m.group()) if m else None


def get_html(url):
    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled"
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


def parse_indices(html):

    soup = BeautifulSoup(html, "html.parser")

    text = soup.get_text("\n", strip=True)

    result = {}

    blocks = [
        "EGX30",
        "SHARIAH",
        "EGX35-LV",
        "EGX70 EWI",
        "EGX100 EWI",
        "TAMAYUZ",
        "EGX30 Capped",
        "EGX30 TR",
        "EGX T BONDS"
    ]

    for idx in blocks:

        if idx not in text:
            continue

        start = text.find(idx)

        chunk = text[start:start + 1500]

        value_match = re.search(
            r"Value\s*:\s*([\d,.]+)",
            chunk,
            re.IGNORECASE
        )

        change_match = re.search(
            r"Change\s*:\s*([-\d,.]+)",
            chunk,
            re.IGNORECASE
        )

        ytd_match = re.search(
            r"YTD% Change\s*:\s*([-\d,.]+)",
            chunk,
            re.IGNORECASE
        )

        result[idx] = {
            "value": extract_number(
                value_match.group(1)
            ) if value_match else None,
            "change_pct": extract_number(
                change_match.group(1)
            ) if change_match else None,
            "ytd_pct": extract_number(
                ytd_match.group(1)
            ) if ytd_match else None
        }

    return result


def parse_top_gl(html):

    text = BeautifulSoup(
        html,
        "html.parser"
    ).get_text("\n", strip=True)

    gainers = []
    losers = []

    return gainers, losers


def main():

    indices_html = get_html(
        "https://www.egx.com.eg/en/Indices.aspx"
    )

    indices = parse_indices(indices_html)

    try:

        gl_html = get_html(
            "https://www.egx.com.eg/en/Top_GL.aspx"
        )

        gainers, losers = parse_top_gl(gl_html)

    except Exception:

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

    print(
        f"Saved {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
