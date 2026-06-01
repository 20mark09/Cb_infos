"""
EGX (Egyptian Exchange) scraper
Pulls index values + top 5 gainers/losers, commits egx.json to repo.

DATA PULLED:
  Indices: EGX30, EGX70, EGX100, EGX35-LV, Sharia, EGX30-Capped
  Market stats: market cap, turnover, volume, transactions
  Top 5 gainers (name, ticker, price, change%)
  Top 5 losers  (name, ticker, price, change%)

STRATEGY (in order):
  1. Trading Economics — clean structured page, very reliable for EGX30
  2. EgyptToday stock market category — publishes daily article with ALL indices + gainers/losers
  3. Investing.com EGX30 page
  4. Claude AI extraction from any fetched HTML
  5. Hardcoded fallback (last known values — update after each session)
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

OUTPUT_FILE = "egx.json"
TIMEOUT = 20

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
}

HEADERS_AR = {**HEADERS, "Accept-Language": "ar,en;q=0.8"}

# ── HARDCODED FALLBACK (as of May 24, 2026 close) ──────────────
FALLBACK_INDICES = {
    "egx30":        {"value": 52861, "change_pct": 1.48,  "date": "2026-05-24"},
    "egx70":        {"value": 14584, "change_pct": 1.29,  "date": "2026-05-24"},
    "egx100":       {"value": 20388, "change_pct": 1.25,  "date": "2026-05-24"},
    "egx35lv":      {"value": 5872,  "change_pct": 1.24,  "date": "2026-05-24"},
    "sharia":       {"value": 5847,  "change_pct": 0.81,  "date": "2026-05-24"},
    "egx30_capped": {"value": 64869, "change_pct": 1.00,  "date": "2026-05-24"},
}

FALLBACK_MARKET = {
    "market_cap_egp_bn":  3762,
    "turnover_egp_bn":    12.9,
    "shares_traded_bn":   1.9,
    "transactions":       170000,
    "date": "2026-05-24",
}

FALLBACK_GAINERS = [
    {"name": "Arab Aluminum",   "ticker": "ARAL", "price": None, "change_pct": 9.82},
    {"name": "Prime Holding",   "ticker": "PRMH", "price": None, "change_pct": 9.41},
    {"name": "GlaxoSmithKline", "ticker": "GLSM", "price": None, "change_pct": 8.26},
    {"name": "—",               "ticker": "—",    "price": None, "change_pct": None},
    {"name": "—",               "ticker": "—",    "price": None, "change_pct": None},
]

FALLBACK_LOSERS = [
    {"name": "Eg. Co. Const. Dev.", "ticker": "ECCD", "price": None, "change_pct": -13.51},
    {"name": "Gulf Canadian RE",    "ticker": "GCRE", "price": None, "change_pct": -9.96},
    {"name": "Nasr Civil Works",    "ticker": "NSCW", "price": None, "change_pct": -8.11},
    {"name": "—",                   "ticker": "—",    "price": None, "change_pct": None},
    {"name": "—",                   "ticker": "—",    "price": None, "change_pct": None},
]


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def clean_num(text):
    if not text:
        return None
    s = re.sub(r"[٬,\s\xa0%+]", "", str(text).strip())
    s = re.sub(r"[^\d.\-]", "", s)
    try:
        return float(s)
    except ValueError:
        return None


def load_existing():
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def fetch(url, headers=None, session=None):
    try:
        r = (session or requests).get(url, headers=headers or HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            print(f"   ✅ {url[:70]}  ({len(r.text):,} bytes)")
            return r.text
        else:
            print(f"   ❌ {url[:70]}  HTTP {r.status_code}")
    except Exception as e:
        print(f"   ❌ {url[:70]}  {e}")
    return None


# ── SOURCE 1: Trading Economics ─────────────────────────────────
def scrape_trading_economics(session):
    print("\n📊 Trading Economics...")
    indices = {}

    html = fetch("https://tradingeconomics.com/egypt/stock-market", session=session)
    if not html:
        return indices, {}

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ")

    # EGX30 value — look for large number near "EGX" or "Egypt Stock"
    # TE shows a table: | EGX 30 | 52,658.75 | +1.48% | ...
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 3:
            continue
        label = cells[0].get_text(strip=True).lower()
        if "egx" not in label and "egypt" not in label:
            continue
        val = clean_num(cells[1].get_text(strip=True))
        chg_text = cells[2].get_text(strip=True) if len(cells) > 2 else ""
        chg = clean_num(chg_text)

        if "30" in label and val and val > 10000:
            indices["egx30"] = {"value": val, "change_pct": chg, "date": today()}
            print(f"   ✓ EGX30: {val}  {chg}%")
        elif "70" in label and val:
            indices["egx70"] = {"value": val, "change_pct": chg, "date": today()}
            print(f"   ✓ EGX70: {val}  {chg}%")
        elif "100" in label and val:
            indices["egx100"] = {"value": val, "change_pct": chg, "date": today()}
            print(f"   ✓ EGX100: {val}  {chg}%")

    # Also try a simple number extraction for EGX30 if table didn't work
    if "egx30" not in indices:
        m = re.search(r"EGX\s*30[^\d]*(\d[\d,]+\.?\d*)", text, re.IGNORECASE)
        if m:
            val = clean_num(m.group(1))
            if val and val > 10000:
                indices["egx30"] = {"value": val, "change_pct": None, "date": today()}
                print(f"   ✓ EGX30 (regex): {val}")

    return indices, {}


# ── SOURCE 2: EgyptToday stock market page ──────────────────────
def scrape_egypttoday(session):
    """
    EgyptToday publishes a daily article after each session with format:
    "EGX30 rose/fell X.XX percent to XX,XXX points. EGX70 increased/decreased..."
    Also lists top gainers and losers.
    """
    print("\n📰 EgyptToday stock market articles...")
    indices = {}
    gainers = []
    losers = []

    # Search for today's article
    search_url = "https://www.egypttoday.com/Category/3/Stock-Market"
    html = fetch(search_url, session=session)
    if not html:
        # Try direct search
        html = fetch("https://www.egypttoday.com/search?q=EGX30+stock+market+today", session=session)
    if not html:
        return indices, {}, gainers, losers

    soup = BeautifulSoup(html, "lxml")

    # Find most recent article link
    article_link = None
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/Article/" in href and ("EGX" in a.get_text() or "stock" in a.get_text().lower()):
            article_link = href if href.startswith("http") else f"https://www.egypttoday.com{href}"
            break

    if not article_link:
        return indices, {}, gainers, losers

    print(f"   Found article: {article_link[:80]}")
    article_html = fetch(article_link, session=session)
    if not article_html:
        return indices, {}, gainers, losers

    art_soup = BeautifulSoup(article_html, "lxml")
    text = art_soup.get_text(" ")

    # Extract indices from patterns like "EGX30 rose 1.48 percent to 52,861 points"
    index_patterns = [
        (r"EGX\s*30[^%\d]*?(\d+\.?\d*)\s*percent.*?(\d[\d,]+)\s*points?", "egx30"),
        (r"EGX\s*70[^%\d]*?(\d+\.?\d*)\s*percent.*?(\d[\d,]+)\s*points?", "egx70"),
        (r"EGX\s*100[^%\d]*?(\d+\.?\d*)\s*percent.*?(\d[\d,]+)\s*points?", "egx100"),
        (r"EGX\s*35[^%\d]*?(\d+\.?\d*)\s*percent.*?(\d[\d,]+)\s*points?", "egx35lv"),
        (r"[Ss]haria[^%\d]*?(\d+\.?\d*)\s*percent.*?(\d[\d,]+)\s*points?", "sharia"),
        (r"[Cc]apped[^%\d]*?(\d+\.?\d*)\s*percent.*?(\d[\d,]+)\s*points?", "egx30_capped"),
    ]
    for pattern, key in index_patterns:
        m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if m:
            chg = clean_num(m.group(1))
            val = clean_num(m.group(2))
            if val:
                # Determine if rose or fell
                preceding = text[max(0, m.start()-30):m.start()]
                is_negative = any(w in preceding.lower() for w in ["fell", "declined", "dropped", "lost", "decreased"])
                indices[key] = {
                    "value": val,
                    "change_pct": (-chg if is_negative else chg) if chg else None,
                    "date": today(),
                }
                print(f"   ✓ {key}: {val}  {'-' if is_negative else '+'}{chg}%")

    # Extract market cap
    market = {}
    m = re.search(r"market cap[^\d]*LE\s*([\d,.]+)\s*(trillion|billion)", text, re.IGNORECASE)
    if m:
        val = clean_num(m.group(1))
        unit = m.group(2).lower()
        if val:
            market["market_cap_egp_bn"] = round(val * 1000 if "trillion" in unit else val, 1)
            market["date"] = today()

    m = re.search(r"turnover[^\d]*LE\s*([\d,.]+)\s*billion", text, re.IGNORECASE)
    if m:
        market["turnover_egp_bn"] = clean_num(m.group(1))

    m = re.search(r"([\d,.]+)\s*billion shares", text, re.IGNORECASE)
    if m:
        market["shares_traded_bn"] = clean_num(m.group(1))

    m = re.search(r"([\d,]+)\s*transactions", text, re.IGNORECASE)
    if m:
        market["transactions"] = int(clean_num(m.group(1)) or 0)

    # Extract gainers — pattern: "X, Y, and Z were top gainers ... at A%, B%, C%"
    gainer_m = re.search(
        r"top gainers.*?(?:at|by|of)\s*([\d.]+)\s*percent.*?([\d.]+)\s*percent.*?([\d.]+)\s*percent",
        text, re.IGNORECASE | re.DOTALL
    )
    if gainer_m:
        pcts = [clean_num(gainer_m.group(i)) for i in range(1, 4)]
        # Get company names from before "were top gainers"
        names_m = re.search(r"([A-Za-z,\s]+(?:and\s+[A-Za-z\s]+)?)\s+were\s+top\s+gainers", text, re.IGNORECASE)
        names = []
        if names_m:
            raw = names_m.group(1)
            names = [n.strip() for n in re.split(r",|and ", raw) if n.strip() and len(n.strip()) > 2]
        for i, pct in enumerate(pcts):
            if pct:
                gainers.append({
                    "name": names[i] if i < len(names) else f"Gainer {i+1}",
                    "ticker": "—",
                    "price": None,
                    "change_pct": pct,
                })
        print(f"   ✓ Gainers: {[g['change_pct'] for g in gainers]}")

    # Extract losers
    loser_m = re.search(
        r"top losers.*?(?:at|by|of)\s*([\d.]+)\s*percent.*?([\d.]+)\s*percent.*?([\d.]+)\s*percent",
        text, re.IGNORECASE | re.DOTALL
    )
    if loser_m:
        pcts = [clean_num(loser_m.group(i)) for i in range(1, 4)]
        names_m = re.search(r"([A-Za-z,\s]+(?:and\s+[A-Za-z\s]+)?)\s+were\s+top\s+losers", text, re.IGNORECASE)
        names = []
        if names_m:
            raw = names_m.group(1)
            names = [n.strip() for n in re.split(r",|and ", raw) if n.strip() and len(n.strip()) > 2]
        for i, pct in enumerate(pcts):
            if pct:
                losers.append({
                    "name": names[i] if i < len(names) else f"Loser {i+1}",
                    "ticker": "—",
                    "price": None,
                    "change_pct": -abs(pct),
                })
        print(f"   ✓ Losers: {[l['change_pct'] for l in losers]}")

    return indices, market, gainers, losers


# ── SOURCE 3: Investing.com EGX30 ──────────────────────────────
def scrape_investing(session):
    print("\n💹 Investing.com EGX30...")
    html = fetch("https://www.investing.com/indices/egx30", session=session)
    if not html:
        return {}

    soup = BeautifulSoup(html, "lxml")
    indices = {}

    # Investing.com shows the value in a specific span/div
    for tag in soup.find_all(["span", "div"], attrs={"data-test": re.compile(r"instrument-price", re.I)}):
        val = clean_num(tag.get_text())
        if val and val > 10000:
            indices["egx30"] = {"value": val, "change_pct": None, "date": today()}
            print(f"   ✓ EGX30 from Investing.com: {val}")
            break

    # Fallback: scan for large number near EGX
    if "egx30" not in indices:
        text = soup.get_text()
        m = re.search(r"(\d{2,3},\d{3}(?:\.\d+)?)\s*(?:pts?|points?)?", text)
        if m:
            val = clean_num(m.group(1))
            if val and 20000 < val < 100000:
                indices["egx30"] = {"value": val, "change_pct": None, "date": today()}
                print(f"   ✓ EGX30 (regex): {val}")

    return indices


# ── SOURCE 4: Claude AI ─────────────────────────────────────────
def scrape_with_claude(html_list):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("   ⚠️  No ANTHROPIC_API_KEY")
        return {}, {}, [], []

    print("\n🤖 Claude AI extraction...")
    combined = "\n\n---\n\n".join(h[:6000] for h in html_list if h)[:16000]

    schema = json.dumps({
        "indices": {
            "egx30":  {"value": 52861, "change_pct": 1.48, "date": "2026-05-24"},
            "egx70":  {"value": 14584, "change_pct": 1.29, "date": "2026-05-24"},
            "egx100": {"value": 20388, "change_pct": 1.25, "date": "2026-05-24"},
            "egx35lv":{"value": 5872,  "change_pct": 1.24, "date": "2026-05-24"},
            "sharia": {"value": 5847,  "change_pct": 0.81, "date": "2026-05-24"},
        },
        "market": {
            "market_cap_egp_bn": 3762, "turnover_egp_bn": 12.9,
            "shares_traded_bn": 1.9, "transactions": 170000, "date": "2026-05-24"
        },
        "gainers": [{"name": "Arab Aluminum", "ticker": "ARAL", "price": None, "change_pct": 9.82}],
        "losers":  [{"name": "Eg. Co. Const.", "ticker": "ECCD", "price": None, "change_pct": -13.51}]
    }, ensure_ascii=False)

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 900,
        "system": f"Extract EGX stock market data. Return ONLY raw JSON matching this schema (no markdown):\n{schema}",
        "messages": [{"role": "user", "content": combined}],
    }
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json=payload, timeout=40,
        )
        r.raise_for_status()
        raw = r.json()["content"][0]["text"].strip()
        raw = re.sub(r"^```[a-z]*\n?|\n?```$", "", raw)
        data = json.loads(raw)
        print(f"   ✓ Claude returned {len(data.get('indices', {}))} indices, {len(data.get('gainers', []))} gainers")
        return (
            data.get("indices", {}),
            data.get("market", {}),
            data.get("gainers", []),
            data.get("losers", []),
        )
    except Exception as e:
        print(f"   ❌ Claude failed: {e}")
        return {}, {}, [], []


# ── MAIN ─────────────────────────────────────────────────────────
def main():
    print(f"\n📈 EGX Scraper — {now_utc()}\n")

    session = requests.Session()
    try:
        session.get("https://www.egypttoday.com/", headers=HEADERS, timeout=10)
        time.sleep(0.5)
    except Exception:
        pass

    all_indices = dict(FALLBACK_INDICES)
    all_market  = dict(FALLBACK_MARKET)
    all_gainers = list(FALLBACK_GAINERS)
    all_losers  = list(FALLBACK_LOSERS)
    html_for_ai = []

    # Source 1: Trading Economics
    te_indices, _ = scrape_trading_economics(session)
    for k, v in te_indices.items():
        if v.get("value"):
            all_indices[k] = v
    time.sleep(1)

    # Source 2: EgyptToday
    et_indices, et_market, et_gainers, et_losers = scrape_egypttoday(session)
    for k, v in et_indices.items():
        if v.get("value"):
            all_indices[k] = v
    if et_market.get("market_cap_egp_bn"):
        all_market = et_market
    if len(et_gainers) >= 3:
        all_gainers = et_gainers
    if len(et_losers) >= 3:
        all_losers = et_losers
    time.sleep(1)

    # Source 3: Investing.com (only if EGX30 still from fallback)
    if all_indices.get("egx30", {}).get("date") == FALLBACK_INDICES["egx30"]["date"]:
        inv = scrape_investing(session)
        if inv.get("egx30", {}).get("value"):
            all_indices["egx30"] = inv["egx30"]
        time.sleep(1)

    # Source 4: Claude AI if we're still mostly on fallback data
    live_count = sum(1 for v in all_indices.values() if v.get("date") == today())
    if live_count < 3:
        print(f"\n   Only {live_count} live indices — trying Claude AI...")
        ai_indices, ai_market, ai_gainers, ai_losers = scrape_with_claude(html_for_ai)
        for k, v in ai_indices.items():
            if v.get("value"):
                all_indices[k] = v
        if ai_market.get("market_cap_egp_bn"):
            all_market = ai_market
        if len(ai_gainers) >= 3:
            all_gainers = ai_gainers[:5]
        if len(ai_losers) >= 3:
            all_losers = ai_losers[:5]

    # Pad gainers/losers to 5
    while len(all_gainers) < 5:
        all_gainers.append({"name": "—", "ticker": "—", "price": None, "change_pct": None})
    while len(all_losers) < 5:
        all_losers.append({"name": "—", "ticker": "—", "price": None, "change_pct": None})

    output = {
        "source": "https://www.egx.com.eg/",
        "lastUpdated": now_utc(),
        "indices": all_indices,
        "market": all_market,
        "gainers": all_gainers[:5],
        "losers":  all_losers[:5],
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    live_count = sum(1 for v in all_indices.values() if v.get("date") == today())
    print(f"\n✅ Saved to {OUTPUT_FILE}")
    print(f"   Live indices today: {live_count}/{len(all_indices)}")
    for k, v in all_indices.items():
        live = "✓" if v.get("date") == today() else "~"
        print(f"   {live} {k:15s} {v.get('value'):>8}  {v.get('change_pct', '?'):>+6}%  [{v.get('date')}]")


if __name__ == "__main__":
    main()
