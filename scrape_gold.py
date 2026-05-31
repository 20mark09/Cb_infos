"""
Gold price scraper for goldbullioneg.com
Scrapes the dedicated prices page which has a clean server-rendered table.
Runs via GitHub Actions every 2 hours and commits gold.json to the repo.

The table on the prices page embeds prices directly in anchor href attributes:
  details?itemId=125957&buy=7806&sell=7772&item=جرام عيار 24
This is the most reliable extraction method — completely independent of HTML structure.
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

# ── CONFIG ─────────────────────────────────────────────────────
SOURCE_URL = "https://goldbullioneg.com/%d8%a3%d8%b3%d8%b9%d8%a7%d8%b1-%d8%a7%d9%84%d8%b0%d9%87%d8%a8/"
OUTPUT_FILE = "gold.json"
TIMEOUT = 20

# Multiple user-agents to rotate on retry
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

# Arabic label substrings → (output key, display label, unit)
KARAT_MAP = [
    ("عيار 24",  "k24",        "عيار 24",       "EGP/g"),
    ("عيار 22",  "k22",        "عيار 22",       "EGP/g"),
    ("عيار 21",  "k21",        "عيار 21",       "EGP/g"),
    ("عيار 18",  "k18",        "عيار 18",       "EGP/g"),
    ("عيار 14",  "k14",        "عيار 14",       "EGP/g"),
    ("الجنيه",   "gold_pound", "الجنيه الذهب",  "EGP"),
    ("الأونصة",  "ounce_usd",  "الأونصة",       "USD/oz"),
    ("الدولار",  "usd_egp",    "الدولار",       "EGP/USD"),
]


def clean_num(text: str):
    if not text:
        return None
    s = re.sub(r"[٬,\s\xa0]", "", text.strip())
    s = re.sub(r"[^\d.]", "", s)
    try:
        v = float(s)
        return v if v > 0 else None
    except ValueError:
        return None


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def load_existing() -> dict:
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ── FETCH with retry + session ──────────────────────────────────
def fetch_html() -> str | None:
    session = requests.Session()
    # First hit the homepage to get cookies (like a real browser)
    for attempt, ua in enumerate(USER_AGENTS):
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ar-EG,ar;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        try:
            # Warm up session with homepage first
            if attempt == 0:
                session.get("https://goldbullioneg.com/", headers=headers, timeout=TIMEOUT)
                time.sleep(1)

            resp = session.get(SOURCE_URL, headers=headers, timeout=TIMEOUT)
            if resp.status_code == 200:
                print(f"✅ Fetched {len(resp.text):,} bytes (attempt {attempt+1})")
                return resp.text
            else:
                print(f"   Attempt {attempt+1}: HTTP {resp.status_code}")
                time.sleep(2)
        except Exception as e:
            print(f"   Attempt {attempt+1} error: {e}")
            time.sleep(2)

    return None


# ── PARSE: embedded buy/sell in href links (PRIMARY — very reliable) ──
def parse_links(html: str) -> dict:
    """
    The site embeds live prices in anchor hrefs:
      /details?itemId=125957&buy=7806&sell=7772&item= جرام عيار 24
    This works regardless of HTML table structure changes.
    """
    prices = {}
    pattern = re.compile(
        r"buy=(\d+(?:\.\d+)?)&sell=(\d+(?:\.\d+)?)&item=\s*([^\"\n&<]+)",
        re.UNICODE,
    )
    for m in pattern.finditer(html):
        buy_val  = float(m.group(1))
        sell_val = float(m.group(2))
        item_txt = m.group(3).strip()

        for arabic_substr, key, label_ar, unit in KARAT_MAP:
            if arabic_substr in item_txt and key not in prices:
                prices[key] = {"label_ar": label_ar, "buy": buy_val, "sell": sell_val, "unit": unit}
                print(f"   ✓ {key:12s}  buy={buy_val:<8}  sell={sell_val:<8}  [link]")
                break

    return prices


# ── PARSE: HTML table rows (SECONDARY) ──────────────────────────
def parse_table(html: str) -> dict:
    prices = {}
    soup = BeautifulSoup(html, "lxml")
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 3:
            continue
        label    = cells[0].get_text(" ", strip=True)
        buy_raw  = cells[1].get_text(" ", strip=True)
        sell_raw = cells[2].get_text(" ", strip=True)
        for arabic_substr, key, label_ar, unit in KARAT_MAP:
            if arabic_substr in label and key not in prices:
                buy  = clean_num(buy_raw)
                sell = clean_num(sell_raw)
                if buy:
                    prices[key] = {"label_ar": label_ar, "buy": buy, "sell": sell, "unit": unit}
                    print(f"   ✓ {key:12s}  buy={buy:<8}  sell={sell:<8}  [table]")
                break
    return prices


# ── PARSE: Claude AI fallback ────────────────────────────────────
def parse_with_claude(html: str) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("   ⚠️  ANTHROPIC_API_KEY not set — skipping AI fallback")
        return {}

    print("   🤖 Trying Claude AI extraction...")
    snippet = html[:14000]
    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 500,
        "system": (
            "Extract Egyptian gold prices from the HTML. "
            "Return ONLY a raw JSON object, no markdown, no preamble. "
            "Keys: k24 k22 k21 k18 k14 gold_pound ounce_usd usd_egp. "
            "Values: {\"buy\": number, \"sell\": number}. "
            "Use null for missing values."
        ),
        "messages": [{"role": "user", "content": snippet}],
    }
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json=payload, timeout=30,
        )
        r.raise_for_status()
        raw = r.json()["content"][0]["text"].strip()
        raw = re.sub(r"^```[a-z]*\n?|\n?```$", "", raw)
        data = json.loads(raw)
        unit_map = {"k24":"EGP/g","k22":"EGP/g","k21":"EGP/g","k18":"EGP/g","k14":"EGP/g",
                    "gold_pound":"EGP","ounce_usd":"USD/oz","usd_egp":"EGP/USD"}
        label_map = {k: la for (_, k, la, _u) in KARAT_MAP}
        prices = {}
        for key, val in data.items():
            if isinstance(val, dict) and key in unit_map:
                prices[key] = {"label_ar": label_map.get(key, key),
                               "buy": val.get("buy"), "sell": val.get("sell"),
                               "unit": unit_map[key]}
                print(f"   ✓ {key:12s}  buy={val.get('buy')}  sell={val.get('sell')}  [AI]")
        return prices
    except Exception as e:
        print(f"   ❌ Claude failed: {e}")
        return {}


# ── MAIN ─────────────────────────────────────────────────────────
def main():
    print(f"\n🏆 Gold Scraper — {now_utc()}")
    print(f"   Source: {SOURCE_URL}\n")
    existing = load_existing()

    html = fetch_html()

    if not html:
        print("❌ Could not fetch page after all retries")
        existing["scrape_error"] = "HTTP fetch failed after retries"
        existing["last_attempted"] = now_utc()
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        sys.exit(1)

    # Strategy 1 — href links (most reliable)
    print("🔗 Parsing buy/sell from href links...")
    prices = parse_links(html)

    # Strategy 2 — table rows
    if len(prices) < 5:
        print(f"\n📋 Only got {len(prices)} prices from links, trying table parser...")
        prices.update(parse_table(html))

    # Strategy 3 — Claude AI
    if len(prices) < 5:
        print(f"\n🤖 Only got {len(prices)} prices, trying Claude AI...")
        prices.update(parse_with_claude(html))

    if not prices:
        print("\n❌ All strategies failed — keeping existing data")
        existing["scrape_error"] = "No prices extracted by any strategy"
        existing["last_attempted"] = now_utc()
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        sys.exit(1)

    output = {
        "source": SOURCE_URL,
        "lastUpdated": now_utc(),
        "scrape_error": None,
        "prices": prices,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    count = len(prices)
    print(f"\n✅ Done — {count}/8 prices saved to {OUTPUT_FILE}")
    if count < 8:
        print(f"⚠️  Missing {8 - count} prices — check logs above")
        # Don't exit(1) here — partial data is still useful


if __name__ == "__main__":
    main()
