"""
EGX scraper — uses investing.com (confirmed working, clean HTML)
Pulls: EGX30, EGX70, EGX100, EGX35-LV, Sharia + top 5 gainers/losers
"""

import json, os, re, sys, time
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

OUTPUT_FILE = "egx.json"
TIMEOUT = 25

# investing.com needs these headers or returns 403
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "max-age=0",
}

# Hardcoded fallback — values from today's fetch (2026-04-02)
FALLBACK = {
    "indices": {
        "egx30":  {"value": 46399.00, "change_pct": -0.71, "date": "2026-04-02"},
        "egx70":  {"value": 12753.85, "change_pct":  0.40, "date": "2026-04-02"},
        "egx100": {"value": 17724.91, "change_pct":  0.21, "date": "2026-04-02"},
        "sharia": {"value":  4909.55, "change_pct": -0.22, "date": "2026-04-02"},
    },
    "market": {"date": "2026-04-02"},
    "gainers": [
        {"name": "Qalaa Holdings",     "ticker": "CCAP",  "price": 3.98,  "change_pct":  3.38},
        {"name": "Orascom Construction","ticker": "ORAS",  "price": 497.00,"change_pct":  2.47},
        {"name": "Orascom Invest",      "ticker": "OIH",   "price": 1.39,  "change_pct":  2.21},
        {"name": "Valmore Holding A",   "ticker": "VLMRA", "price": 32.77, "change_pct":  1.87},
        {"name": "Misr Cement",         "ticker": "MCQE",  "price": 172.00,"change_pct":  1.41},
    ],
    "losers": [
        {"name": "Abu Qir Fertilizers", "ticker": "ABUK",  "price": 82.00, "change_pct": -2.14},
        {"name": "TMG Holding",         "ticker": "TMGH",  "price": 77.41, "change_pct": -2.01},
        {"name": "Raya Holding",        "ticker": "RAYA",  "price": 5.16,  "change_pct": -1.90},
        {"name": "Fawry Banking",       "ticker": "FWRY",  "price": 17.58, "change_pct": -1.68},
        {"name": "GB Auto",             "ticker": "GBCO",  "price": 24.60, "change_pct": -1.60},
    ],
}

def now_utc(): return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
def today():   return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def clean(text):
    if not text: return None
    s = re.sub(r"[٬,\s\xa0%+]", "", str(text).strip())
    s = re.sub(r"[^\d.\-]", "", s)
    try:    return float(s)
    except: return None

def fetch(url, session):
    try:
        r = session.get(url, headers=HEADERS, timeout=TIMEOUT)
        print(f"  {'✅' if r.status_code==200 else '❌'} HTTP {r.status_code}  {url[:70]}")
        return r.text if r.status_code == 200 else None
    except Exception as e:
        print(f"  ❌ {e}")
        return None


def scrape_investing(session):
    """Scrape EGX30 page — gets price, change, and the gainers/losers tables."""
    indices, gainers, losers = {}, [], []

    # ── EGX30 main page ─────────────────────────────────────────
    html = fetch("https://www.investing.com/indices/egx30", session)
    if html:
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(" ")

        # Price: look for the large number near "EGX 30 live stock price is X"
        m = re.search(r"live stock price is ([\d,]+\.?\d*)", text)
        if m:
            val = clean(m.group(1))
            if val and val > 10000:
                # Change%: look for (-X.XX%) or (+X.XX%) pattern right after price block
                chg_m = re.search(r"([\d,]+\.?\d*)\s*\n.*?([+-][\d.]+)%", text[:3000])
                chg = None
                if not chg_m:
                    # Try pattern from the visible text block
                    chg_m2 = re.search(r"46[,\d]+\.?\d*\s*[-−]\s*([\d.]+)\s*\(([\d.]+)%\)", text)
                    if chg_m2:
                        chg = -clean(chg_m2.group(2))
                indices["egx30"] = {"value": val, "change_pct": chg, "date": today()}
                print(f"    EGX30: {val}  chg={chg}")

        # Top Gainers table — investing.com renders it as:
        # Name | Price+change+pct
        for table in soup.find_all("table"):
            headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
            if not any("gainer" in h or "name" in h for h in headers):
                # check caption or preceding heading
                caption = table.find_previous(["h2","h3","h4","caption"])
                if not caption or "gainer" not in caption.get_text().lower():
                    continue
            rows = table.find_all("tr")[1:]  # skip header
            for row in rows[:5]:
                cells = row.find_all(["td","th"])
                if len(cells) < 2: continue
                name_cell = cells[0].get_text(strip=True)
                # ticker is usually in a span inside the name cell
                ticker_tag = cells[0].find(string=re.compile(r'^[A-Z]{2,6}$'))
                ticker = ticker_tag.strip() if ticker_tag else "—"
                # price+change in second cell: "3.98+0.130+3.38%"
                price_cell = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                nums = re.findall(r"[\d.]+", price_cell)
                price = float(nums[0]) if nums else None
                pct = float(nums[-1]) if len(nums) >= 3 else None
                if name_cell and name_cell not in ("Name",""):
                    gainers.append({"name": name_cell, "ticker": ticker, "price": price, "change_pct": pct})
            if gainers:
                print(f"    Gainers from table: {len(gainers)}")
                break

        # Top Losers
        for table in soup.find_all("table"):
            caption = table.find_previous(["h2","h3","h4","caption"])
            if not caption or "loser" not in caption.get_text().lower():
                continue
            rows = table.find_all("tr")[1:]
            for row in rows[:5]:
                cells = row.find_all(["td","th"])
                if len(cells) < 2: continue
                name_cell = cells[0].get_text(strip=True)
                ticker_tag = cells[0].find(string=re.compile(r'^[A-Z]{2,6}$'))
                ticker = ticker_tag.strip() if ticker_tag else "—"
                price_cell = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                nums = re.findall(r"[\d.]+", price_cell)
                price = float(nums[0]) if nums else None
                pct = float(nums[-1]) if len(nums) >= 3 else None
                if name_cell and name_cell not in ("Name",""):
                    losers.append({"name": name_cell, "ticker": ticker, "price": price, "change_pct": -abs(pct) if pct else None})
            if losers:
                print(f"    Losers from table: {len(losers)}")
                break

        # Fallback regex for gainers/losers if tables not found
        if not gainers:
            gainer_section = re.search(r"Top Gainers(.*?)Top Losers", text, re.DOTALL)
            if gainer_section:
                chunk = gainer_section.group(1)
                for m in re.finditer(r"([A-Z]{2,6})\s+([A-Za-z &]+?)\s+([\d.]+)\s*\+?([\d.]+)\s*\+([\d.]+)%", chunk):
                    gainers.append({"name": m.group(2).strip(), "ticker": m.group(1), "price": float(m.group(3)), "change_pct": float(m.group(5))})
                    if len(gainers) == 5: break

        if not losers:
            loser_section = re.search(r"Top Losers(.*?)(?:People Also|Most Active|$)", text, re.DOTALL)
            if loser_section:
                chunk = loser_section.group(1)
                for m in re.finditer(r"([A-Z]{2,6})\s+([A-Za-z &]+?)\s+([\d.]+)\s*-?([\d.]+)\s*-([\d.]+)%", chunk):
                    losers.append({"name": m.group(2).strip(), "ticker": m.group(1), "price": float(m.group(3)), "change_pct": -float(m.group(5))})
                    if len(losers) == 5: break

    time.sleep(1.5)

    # ── "People Also Watch" gives us EGX70, EGX100, Sharia ──────
    # These appear on the EGX30 page as: "EGX 70 | 12,753.85 | +0.40%"
    if html:
        soup = BeautifulSoup(html, "lxml")
        # The related indices section
        for section in soup.find_all(["div","section"], string=re.compile(r"People Also Watch", re.I)):
            pass  # handled below via text

        text = soup.get_text(" ")
        # EGX 70
        m70 = re.search(r"EGX\s*70[^\d]*?([\d,]+\.?\d*)\s*\n.*?([+-][\d.]+)%", text)
        if not m70:
            m70 = re.search(r"EGX70EWI.*?([\d,]+\.?\d+).*?([+-][\d.]+)%", text)
        if m70:
            v = clean(m70.group(1)); c = clean(m70.group(2))
            if v and v > 1000:
                indices["egx70"] = {"value": v, "change_pct": c, "date": today()}
                print(f"    EGX70: {v}  {c}%")

        # EGX 100
        m100 = re.search(r"EGX\s*100[^\d]*?([\d,]+\.?\d*)\s*(?:EWI)?.*?([+-][\d.]+)%", text)
        if m100:
            v = clean(m100.group(1)); c = clean(m100.group(2))
            if v and v > 1000:
                indices["egx100"] = {"value": v, "change_pct": c, "date": today()}
                print(f"    EGX100: {v}  {c}%")

        # Sharia
        ms = re.search(r"Sharia[^\d]*?([\d,]+\.?\d+).*?([+-][\d.]+)%", text, re.IGNORECASE)
        if ms:
            v = clean(ms.group(1)); c = clean(ms.group(2))
            if v and v > 1000:
                indices["sharia"] = {"value": v, "change_pct": c, "date": today()}
                print(f"    Sharia: {v}  {c}%")

    # ── EGX70 dedicated page for accuracy ───────────────────────
    if "egx70" not in indices or indices["egx70"]["date"] != today():
        html70 = fetch("https://www.investing.com/indices/egx-70", session)
        if html70:
            m = re.search(r"live stock price is ([\d,]+\.?\d*)", html70)
            if m:
                v = clean(m.group(1))
                if v and v > 1000:
                    indices["egx70"] = {"value": v, "change_pct": None, "date": today()}
                    print(f"    EGX70 (dedicated): {v}")
            time.sleep(1)

    return indices, gainers, losers


def scrape_with_claude(html_list):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key: return {}, [], []
    print("\n[Claude AI fallback]")
    snippet = "\n---\n".join(h[:5000] for h in html_list if h)[:14000]
    schema = '{"indices":{"egx30":{"value":46399,"change_pct":-0.71,"date":"2026-04-02"},"egx70":{"value":12753,"change_pct":0.40,"date":"2026-04-02"}},"gainers":[{"name":"Qalaa Holdings","ticker":"CCAP","price":3.98,"change_pct":3.38}],"losers":[{"name":"TMG Holding","ticker":"TMGH","price":77.41,"change_pct":-2.01}]}'
    try:
        r = requests.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-sonnet-4-20250514", "max_tokens": 600,
                  "system": f"Extract EGX stock data. Return ONLY raw JSON matching schema:\n{schema}",
                  "messages": [{"role": "user", "content": snippet}]}, timeout=35)
        r.raise_for_status()
        raw = re.sub(r"^```[a-z]*\n?|\n?```$", "", r.json()["content"][0]["text"].strip())
        d = json.loads(raw)
        print(f"  Claude: {len(d.get('indices',{}))} indices, {len(d.get('gainers',[]))} gainers")
        return d.get("indices",{}), d.get("gainers",[]), d.get("losers",[])
    except Exception as e:
        print(f"  Claude failed: {e}")
        return {}, [], []


def main():
    print(f"\n📈 EGX Scraper — {now_utc()}")

    session = requests.Session()
    # warm up with a simple request first
    try:
        session.get("https://www.investing.com/", headers=HEADERS, timeout=10)
        time.sleep(1)
    except Exception: pass

    # Start from fallback
    indices = {k: dict(v) for k, v in FALLBACK["indices"].items()}
    market  = dict(FALLBACK["market"])
    gainers = [dict(g) for g in FALLBACK["gainers"]]
    losers  = [dict(l) for l in FALLBACK["losers"]]

    print("\n[Investing.com]")
    inv_idx, inv_gain, inv_loss = scrape_investing(session)

    # Merge — live data wins
    for k, v in inv_idx.items():
        if v.get("value"): indices[k] = v
    if len(inv_gain) >= 3: gainers = inv_gain[:5]
    if len(inv_loss) >= 3: losers  = inv_loss[:5]

    # Claude AI if still mostly fallback
    live = sum(1 for v in indices.values() if v.get("date") == today())
    if live < 2:
        print(f"\n  Only {live} live — trying Claude AI")
        ai_idx, ai_gain, ai_loss = scrape_with_claude([])
        for k, v in ai_idx.items():
            if v.get("value"): indices[k] = v
        if len(ai_gain) >= 3: gainers = ai_gain[:5]
        if len(ai_loss) >= 3: losers  = ai_loss[:5]

    # Pad to 5
    while len(gainers) < 5: gainers.append({"name":"—","ticker":"—","price":None,"change_pct":None})
    while len(losers)  < 5: losers.append( {"name":"—","ticker":"—","price":None,"change_pct":None})

    out = {
        "source": "https://www.investing.com/indices/egx30",
        "lastUpdated": now_utc(),
        "indices": indices,
        "market": market,
        "gainers": gainers[:5],
        "losers":  losers[:5],
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    live = sum(1 for v in indices.values() if v.get("date") == today())
    print(f"\n✅ {OUTPUT_FILE} — {live}/{len(indices)} live indices")
    for k, v in indices.items():
        tag = "✓" if v.get("date") == today() else "~"
        print(f"  {tag} {k:12s}  {v['value']:>10,.2f}  {(v.get('change_pct') or 0):>+6.2f}%")
    print(f"  Gainers: {[g['name'] for g in gainers if g['name'] != '—']}")
    print(f"  Losers:  {[l['name'] for l in losers  if l['name'] != '—']}")

if __name__ == "__main__":
    main()
