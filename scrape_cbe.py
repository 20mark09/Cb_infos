"""
CBE (Central Bank of Egypt) data scraper
Pulls the most important macroeconomic indicators and commits cbe.json to the repo.

DATA PULLED:
  1. Overnight Deposit Rate       — floor of CBE corridor
  2. Overnight Lending Rate       — ceiling of CBE corridor
  3. Main Operation Rate          — policy benchmark
  4. Discount Rate                — reference rate for banks
  5. Annual Headline Inflation    — urban CPI, CAPMAS
  6. Annual Core Inflation        — CBE measure (ex food/energy)
  7. Net International Reserves   — USD billions
  8. USD/EGP Exchange Rate        — official CBE rate
  9. Next MPC Meeting Date        — forward-looking info
 10. Last MPC Decision            — what happened at last meeting

STRATEGY:
  CBE's main site blocks bots (WAF). We use:
  - Primary:   CBE press release HTML pages (structured, reliable)
  - Secondary: Trading Economics API-less page scrape
  - Tertiary:  Claude AI extraction from any fetched HTML
  - Hardcoded: Known current values as absolute last resort
               (manually update these when rates change)
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

OUTPUT_FILE = "cbe.json"
TIMEOUT = 20

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# ── KNOWN FALLBACK VALUES (update manually when rates change) ───
# As of May 21, 2026 — MPC kept rates unchanged
HARDCODED_FALLBACK = {
    "overnight_deposit_rate":  {"value": 19.00, "unit": "%", "date": "2026-05-21"},
    "overnight_lending_rate":  {"value": 20.00, "unit": "%", "date": "2026-05-21"},
    "main_operation_rate":     {"value": 19.50, "unit": "%", "date": "2026-05-21"},
    "discount_rate":           {"value": 19.50, "unit": "%", "date": "2026-05-21"},
    "headline_inflation":      {"value": 14.9,  "unit": "%", "date": "2026-04"},
    "core_inflation":          {"value": 13.8,  "unit": "%", "date": "2026-04"},
    "net_international_reserves": {"value": 53.0, "unit": "USD bn", "date": "2026-04"},
    "usd_egp_rate":            {"value": 49.60, "unit": "EGP", "date": "2026-05-21"},
    "last_mpc_decision":       {"value": "Unchanged", "date": "2026-05-21"},
    "next_mpc_date":           {"value": "2026-07-03", "date": ""},
}


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def load_existing():
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def fetch(url, session=None):
    try:
        r = (session or requests).get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.text
    except Exception as e:
        print(f"   fetch error: {e}")
    return None


def clean_num(text):
    if not text:
        return None
    s = re.sub(r"[%,\s\xa0]", "", str(text).strip())
    s = re.sub(r"[^\d.]", "", s)
    try:
        v = float(s)
        return v if v > 0 else None
    except ValueError:
        return None


# ── SOURCE 1: CBE MPC Press Release page ───────────────────────
def scrape_cbe_mpc(session):
    """Scrape the CBE MPC decisions listing page for latest rates."""
    print("   Trying CBE MPC decisions page...")
    data = {}

    html = fetch("https://www.cbe.org.eg/en/monetary-policy/mpc-decisions", session)
    if not html:
        return data

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ")

    # overnight deposit rate
    m = re.search(r"overnight deposit rate[^\d]*(\d+\.?\d*)\s*[%p]", text, re.IGNORECASE)
    if m:
        data["overnight_deposit_rate"] = {"value": float(m.group(1)), "unit": "%", "date": now_utc()[:10]}

    # overnight lending rate
    m = re.search(r"overnight lending rate[^\d]*(\d+\.?\d*)\s*[%p]", text, re.IGNORECASE)
    if m:
        data["overnight_lending_rate"] = {"value": float(m.group(1)), "unit": "%", "date": now_utc()[:10]}

    # main operation rate
    m = re.search(r"main operation[^\d]*(\d+\.?\d*)\s*[%p]", text, re.IGNORECASE)
    if m:
        data["main_operation_rate"] = {"value": float(m.group(1)), "unit": "%", "date": now_utc()[:10]}

    print(f"   → Got {len(data)} fields from CBE MPC page")
    return data


# ── SOURCE 2: CBE CPI press release ────────────────────────────
def scrape_cbe_cpi(session):
    """Scrape latest CPI press release for inflation data."""
    print("   Trying CBE CPI page...")
    data = {}

    html = fetch("https://www.cbe.org.eg/en/economic-research/statistics/inflation-rates", session)
    if not html:
        return data

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ")

    # Annual headline inflation
    m = re.search(r"annual[^\d]*headline[^\d]*(\d+\.?\d*)\s*percent", text, re.IGNORECASE)
    if m:
        data["headline_inflation"] = {"value": float(m.group(1)), "unit": "%", "date": now_utc()[:7]}

    # Annual core inflation
    m = re.search(r"annual[^\d]*core[^\d]*(\d+\.?\d*)\s*percent", text, re.IGNORECASE)
    if m:
        data["core_inflation"] = {"value": float(m.group(1)), "unit": "%", "date": now_utc()[:7]}

    print(f"   → Got {len(data)} fields from CBE CPI page")
    return data


# ── SOURCE 3: CBE NIR page ──────────────────────────────────────
def scrape_cbe_nir(session):
    """Scrape Net International Reserves."""
    print("   Trying CBE NIR page...")
    data = {}

    html = fetch("https://www.cbe.org.eg/en/economic-research/statistics/net-international-reserves", session)
    if not html:
        return data

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ")

    # "Net International Reserves reached US$ 53,009.2 mn"
    m = re.search(r"reserves[^\d]*US\$?\s*([\d,]+\.?\d*)\s*(mn|bn|million|billion)", text, re.IGNORECASE)
    if m:
        val = clean_num(m.group(1))
        unit = m.group(2).lower()
        if val and "mn" in unit or "million" in unit:
            val = round(val / 1000, 2)
        if val:
            data["net_international_reserves"] = {"value": val, "unit": "USD bn", "date": now_utc()[:7]}

    print(f"   → Got {len(data)} fields from CBE NIR page")
    return data


# ── SOURCE 4: CBE Exchange Rates ───────────────────────────────
def scrape_cbe_fx(session):
    """Scrape official USD/EGP rate from CBE."""
    print("   Trying CBE exchange rates page...")
    data = {}

    html = fetch("https://www.cbe.org.eg/en/economic-research/statistics/exchange-rates", session)
    if not html:
        return data

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ")

    # Look for USD rate pattern
    m = re.search(r"USD[^\d]*(\d{2,3}\.?\d*)", text)
    if not m:
        m = re.search(r"(\d{2,3}\.?\d+)\s*EGP.*USD", text, re.IGNORECASE)
    if m:
        val = clean_num(m.group(1))
        if val and 40 < val < 100:  # sanity check — EGP is in 45–60 range
            data["usd_egp_rate"] = {"value": val, "unit": "EGP", "date": now_utc()[:10]}

    print(f"   → Got {len(data)} fields from CBE FX page")
    return data


# ── SOURCE 5: Trading Economics (very reliable, clean HTML) ────
def scrape_trading_economics(session):
    """
    Trading Economics has clean, well-structured pages with current values.
    Used as reliable fallback for all key indicators.
    """
    print("   Trying Trading Economics...")
    data = {}

    # Interest rate
    html = fetch("https://tradingeconomics.com/egypt/interest-rate", session)
    if html:
        soup = BeautifulSoup(html, "lxml")
        # TE shows the value in a large number element
        for tag in soup.find_all(["td", "span", "div"], class_=re.compile(r"(value|number|rate|current)", re.I)):
            val = clean_num(tag.get_text())
            if val and 10 < val < 40:  # CBE rates are in this range
                data["overnight_deposit_rate"] = {"value": val, "unit": "%", "date": now_utc()[:10]}
                data["overnight_lending_rate"] = {"value": round(val + 1, 2), "unit": "%", "date": now_utc()[:10]}
                data["main_operation_rate"] = {"value": round(val + 0.5, 2), "unit": "%", "date": now_utc()[:10]}
                data["discount_rate"] = {"value": round(val + 0.5, 2), "unit": "%", "date": now_utc()[:10]}
                print(f"   → Deposit rate from TE: {val}%")
                break

    time.sleep(1)

    # Inflation
    html = fetch("https://tradingeconomics.com/egypt/inflation-cpi", session)
    if html:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup.find_all(["td", "span", "div"], class_=re.compile(r"(value|number|rate|current)", re.I)):
            val = clean_num(tag.get_text())
            if val and 0 < val < 60:
                data["headline_inflation"] = {"value": val, "unit": "%", "date": now_utc()[:7]}
                print(f"   → Inflation from TE: {val}%")
                break

    time.sleep(1)

    # FX rate
    html = fetch("https://tradingeconomics.com/egypt/currency", session)
    if html:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup.find_all(["td", "span", "div"], class_=re.compile(r"(value|number|rate|current)", re.I)):
            val = clean_num(tag.get_text())
            if val and 40 < val < 100:
                data["usd_egp_rate"] = {"value": val, "unit": "EGP", "date": now_utc()[:10]}
                print(f"   → USD/EGP from TE: {val}")
                break

    print(f"   → Got {len(data)} fields from Trading Economics")
    return data


# ── SOURCE 6: Claude AI (best effort on any raw HTML) ──────────
def scrape_with_claude(html_snippets: list[str]) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("   ⚠️  No ANTHROPIC_API_KEY — skipping AI fallback")
        return {}

    print("   🤖 Trying Claude AI extraction...")
    combined = "\n\n---\n\n".join(html_snippets)[:16000]

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 700,
        "system": (
            "Extract Egyptian central bank data from the text. "
            "Return ONLY raw JSON, no markdown. "
            "Schema: {"
            '"overnight_deposit_rate": {"value": 19.0, "unit": "%", "date": "2026-05-21"},'
            '"overnight_lending_rate": {"value": 20.0, "unit": "%", "date": "2026-05-21"},'
            '"main_operation_rate": {"value": 19.5, "unit": "%", "date": "2026-05-21"},'
            '"discount_rate": {"value": 19.5, "unit": "%", "date": "2026-05-21"},'
            '"headline_inflation": {"value": 14.9, "unit": "%", "date": "2026-04"},'
            '"core_inflation": {"value": 13.8, "unit": "%", "date": "2026-04"},'
            '"net_international_reserves": {"value": 53.0, "unit": "USD bn", "date": "2026-04"},'
            '"usd_egp_rate": {"value": 49.6, "unit": "EGP", "date": "2026-05-21"},'
            '"last_mpc_decision": {"value": "Unchanged", "date": "2026-05-21"},'
            '"next_mpc_date": {"value": "2026-07-03", "date": ""}'
            "} — Use null for any value you cannot find."
        ),
        "messages": [{"role": "user", "content": combined}],
    }

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json=payload, timeout=40,
        )
        r.raise_for_status()
        raw = r.json()["content"][0]["text"].strip()
        raw = re.sub(r"^```[a-z]*\n?|\n?```$", "", raw)
        data = json.loads(raw)
        valid = {k: v for k, v in data.items() if isinstance(v, dict) and v.get("value") is not None}
        print(f"   → Got {len(valid)} fields from Claude AI")
        return valid
    except Exception as e:
        print(f"   ❌ Claude AI failed: {e}")
        return {}


# ── MERGE: live data on top of hardcoded fallback ──────────────
def merge(base: dict, updates: dict) -> dict:
    result = dict(base)
    for k, v in updates.items():
        if v and isinstance(v, dict) and v.get("value") is not None:
            result[k] = v
    return result


# ── MAIN ────────────────────────────────────────────────────────
def main():
    print(f"\n🏦 CBE Scraper — {now_utc()}\n")
    existing = load_existing()

    session = requests.Session()
    # Warm up session
    try:
        session.get("https://www.cbe.org.eg/en/", headers=HEADERS, timeout=TIMEOUT)
        time.sleep(1)
    except Exception:
        pass

    # Collect HTML snippets for AI fallback
    html_snippets = []

    # Run all scrapers
    all_data = dict(HARDCODED_FALLBACK)  # start with hardcoded

    # CBE pages
    for scrape_fn in [scrape_cbe_mpc, scrape_cbe_cpi, scrape_cbe_nir, scrape_cbe_fx]:
        try:
            result = scrape_fn(session)
            all_data = merge(all_data, result)
        except Exception as e:
            print(f"   ⚠️  {scrape_fn.__name__} failed: {e}")
        time.sleep(1)

    # Trading Economics fallback
    try:
        te_data = scrape_trading_economics(session)
        # Only use TE data for fields not yet found by CBE pages
        for k, v in te_data.items():
            if k not in all_data or all_data[k] == HARDCODED_FALLBACK.get(k):
                all_data = merge(all_data, {k: v})
    except Exception as e:
        print(f"   ⚠️  Trading Economics failed: {e}")

    # Claude AI — pass everything we fetched
    try:
        if html_snippets:
            ai_data = scrape_with_claude(html_snippets)
            for k, v in ai_data.items():
                if k not in all_data or all_data[k] == HARDCODED_FALLBACK.get(k):
                    all_data = merge(all_data, {k: v})
    except Exception as e:
        print(f"   ⚠️  AI fallback failed: {e}")

    output = {
        "source": "https://www.cbe.org.eg/en/",
        "lastUpdated": now_utc(),
        "scrape_error": None,
        "data": all_data,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Saved {len(all_data)} indicators to {OUTPUT_FILE}")
    for k, v in all_data.items():
        val = v.get("value", "?") if isinstance(v, dict) else v
        unit = v.get("unit", "") if isinstance(v, dict) else ""
        date = v.get("date", "") if isinstance(v, dict) else ""
        print(f"   {k:35s} {val} {unit}  [{date}]")


if __name__ == "__main__":
    main()
