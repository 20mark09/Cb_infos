"""
Gold price scraper for goldbullioneg.com
Runs via GitHub Actions and commits updated gold.json to the repo.

Strategy:
  1. Try direct HTTP fetch + BeautifulSoup (fast, free, no API key needed)
  2. If that fails (JS-rendered page), fall back to Claude AI extraction
     (requires ANTHROPIC_API_KEY secret in GitHub repo settings)
"""

import json
import os
import re
import sys
import traceback
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

# ── CONFIG ─────────────────────────────────────────────────────
SOURCE_URL = "https://goldbullioneg.com/"
OUTPUT_FILE = "gold.json"   # committed to repo root
TIMEOUT = 15

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "ar,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Karats we care about — Arabic label → English key
KARAT_MAP = {
    "عيار 24": "k24",
    "عيار 22": "k22",
    "عيار 21": "k21",
    "عيار 18": "k18",
    "عيار 14": "k14",
    "الجنيه الذهب": "gold_pound",
    "الأونصة": "ounce_usd",
    "الدولار": "usd_egp",
}


# ── HELPERS ────────────────────────────────────────────────────
def clean_number(text: str) -> float | None:
    """Extract a float from messy Arabic/English price text."""
    if not text:
        return None
    # Remove Arabic thousands separator (٬) and any whitespace
    cleaned = re.sub(r"[٬,\s]", "", text.strip())
    try:
        return float(cleaned)
    except ValueError:
        return None


def now_cairo() -> str:
    """Return current UTC time as ISO string (app converts to Cairo)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# ── STRATEGY 1: Direct BeautifulSoup ───────────────────────────
def scrape_direct(html: str) -> dict | None:
    """
    Parse the price table from the raw HTML.
    goldbullioneg renders a <table> server-side with buy/sell columns.
    """
    soup = BeautifulSoup(html, "html.parser")
    prices = {}

    # The main price table has rows with: label | buy | sell | link
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                continue
            label_text = cells[0].get_text(strip=True)
            buy_text   = cells[1].get_text(strip=True)
            sell_text  = cells[2].get_text(strip=True)

            for arabic_key, en_key in KARAT_MAP.items():
                if arabic_key in label_text:
                    buy  = clean_number(buy_text)
                    sell = clean_number(sell_text)
                    if buy or sell:
                        prices[en_key] = {
                            "label_ar": arabic_key,
                            "buy":  buy,
                            "sell": sell,
                            "unit": "EGP/g" if en_key not in ("ounce_usd", "usd_egp", "gold_pound") else (
                                "USD/oz" if en_key == "ounce_usd" else
                                "EGP/USD" if en_key == "usd_egp" else
                                "EGP"
                            ),
                        }
                    break

    if not prices:
        # Fallback: scan page text for "عيار 21 ... 6765" patterns
        text = soup.get_text()
        for arabic_key, en_key in KARAT_MAP.items():
            pattern = re.compile(
                rf"{re.escape(arabic_key)}[^0-9]*(\d[\d,٬.]+)[^0-9]*(\d[\d,٬.]+)?",
                re.UNICODE,
            )
            m = pattern.search(text)
            if m:
                prices[en_key] = {
                    "label_ar": arabic_key,
                    "buy":  clean_number(m.group(1)),
                    "sell": clean_number(m.group(2)) if m.group(2) else None,
                    "unit": "EGP/g",
                }

    return prices if prices else None


# ── STRATEGY 2: Claude AI extraction (fallback) ─────────────────
def scrape_with_claude(html: str) -> dict | None:
    """
    Send a truncated HTML snippet to Claude and ask it to extract prices as JSON.
    Only runs when ANTHROPIC_API_KEY is set.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("⚠️  No ANTHROPIC_API_KEY found — skipping AI fallback.")
        return None

    print("🤖 Falling back to Claude AI extraction...")

    # Truncate HTML to save tokens — keep first 12000 chars which contain the table
    snippet = html[:12000]

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 800,
        "system": (
            "You are a data extraction assistant. "
            "Extract gold prices from the provided HTML snippet and return ONLY valid JSON. "
            "No markdown, no explanation, just the JSON object. "
            "Format: "
            '{"k24":{"buy":7731,"sell":7697},"k22":{"buy":7087,"sell":7056},'
            '"k21":{"buy":6765,"sell":6735},"k18":{"buy":5799,"sell":5773},'
            '"k14":{"buy":4510,"sell":4490},'
            '"gold_pound":{"buy":54120,"sell":53880},'
            '"ounce_usd":{"buy":4540,"sell":4539.5},'
            '"usd_egp":{"buy":52.34,"sell":52.24}} '
            "Use null for any missing values."
        ),
        "messages": [
            {
                "role": "user",
                "content": f"Extract all gold prices from this HTML:\n\n{snippet}",
            }
        ],
    }

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()["content"][0]["text"].strip()

        # Strip any accidental markdown fences
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

        data = json.loads(raw)

        # Normalise to our schema (add label_ar / unit fields)
        unit_map = {
            "k24": "EGP/g", "k22": "EGP/g", "k21": "EGP/g",
            "k18": "EGP/g", "k14": "EGP/g",
            "gold_pound": "EGP", "ounce_usd": "USD/oz", "usd_egp": "EGP/USD",
        }
        label_map = {v: k for k, v in KARAT_MAP.items()}
        prices = {}
        for key, val in data.items():
            if isinstance(val, dict):
                prices[key] = {
                    "label_ar": label_map.get(key, key),
                    "buy":  val.get("buy"),
                    "sell": val.get("sell"),
                    "unit": unit_map.get(key, "EGP/g"),
                }
        return prices if prices else None

    except Exception as e:
        print(f"❌ Claude extraction failed: {e}")
        return None


# ── LOAD EXISTING FILE (for fallback on error) ──────────────────
def load_existing() -> dict:
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ── MAIN ────────────────────────────────────────────────────────
def main():
    print(f"🔍 Fetching {SOURCE_URL} ...")
    existing = load_existing()

    try:
        resp = requests.get(SOURCE_URL, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        html = resp.text
        print(f"✅ Fetched {len(html):,} bytes")
    except Exception as e:
        print(f"❌ HTTP fetch failed: {e}")
        # Keep existing data, just update error field
        existing["scrape_error"] = str(e)
        existing["last_attempted"] = now_cairo()
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        sys.exit(1)

    # Try direct parse first
    prices = scrape_direct(html)

    # AI fallback if direct parse got nothing
    if not prices:
        print("⚠️  Direct parse found no prices — trying AI fallback...")
        prices = scrape_with_claude(html)

    if not prices:
        print("❌ Both strategies failed. Keeping existing data.")
        existing["scrape_error"] = "No prices extracted"
        existing["last_attempted"] = now_cairo()
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        sys.exit(1)

    # Build final JSON
    output = {
        "source": SOURCE_URL,
        "lastUpdated": now_cairo(),
        "scrape_error": None,
        "prices": prices,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Saved {len(prices)} prices to {OUTPUT_FILE}")
    for key, val in prices.items():
        buy  = val.get("buy",  "?")
        sell = val.get("sell", "?")
        unit = val.get("unit", "")
        print(f"   {key:15s} buy={buy}  sell={sell}  {unit}")


if __name__ == "__main__":
    main()
