"""
EGX scraper — indices + top gainers/losers
Sources (in order of reliability):
  1. tradingeconomics.com/egypt/stock-market  — EGX30 confirmed working
  2. english.mubasher.info/markets/EGX/       — all EGX indices
  3. Claude AI on any fetched HTML
  4. Hardcoded fallback
"""

import json, os, re, sys, time
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

OUTPUT_FILE = "egx.json"
TIMEOUT = 20

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
HEADERS    = {"User-Agent": UA, "Accept": "text/html,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"}
HEADERS_AR = {"User-Agent": UA, "Accept": "text/html,*/*;q=0.8", "Accept-Language": "ar,en;q=0.8"}

# Hardcoded fallback — update these manually after each big market move
FALLBACK = {
    "indices": {
        "egx30":  {"value": 52861, "change_pct":  1.48, "date": "2026-05-24"},
        "egx70":  {"value": 14584, "change_pct":  1.29, "date": "2026-05-24"},
        "egx100": {"value": 20388, "change_pct":  1.25, "date": "2026-05-24"},
        "egx35lv":{"value":  5872, "change_pct":  1.24, "date": "2026-05-24"},
        "sharia": {"value":  5847, "change_pct":  0.81, "date": "2026-05-24"},
    },
    "market": {
        "market_cap_egp_bn": 3762, "turnover_egp_bn": 12.9,
        "shares_traded_bn": 1.9,   "transactions": 170000,
        "date": "2026-05-24",
    },
    "gainers": [
        {"name": "Arab Aluminum",   "ticker": "ARAL", "price": None, "change_pct":  9.82},
        {"name": "Prime Holding",   "ticker": "PRMH", "price": None, "change_pct":  9.41},
        {"name": "GlaxoSmithKline", "ticker": "GLSM", "price": None, "change_pct":  8.26},
        {"name": "—", "ticker": "—", "price": None, "change_pct": None},
        {"name": "—", "ticker": "—", "price": None, "change_pct": None},
    ],
    "losers": [
        {"name": "Eg. Const. Dev.",  "ticker": "ECCD", "price": None, "change_pct": -13.51},
        {"name": "Gulf Canadian RE", "ticker": "GCRE", "price": None, "change_pct":  -9.96},
        {"name": "Nasr Civil Works", "ticker": "NSCW", "price": None, "change_pct":  -8.11},
        {"name": "—", "ticker": "—", "price": None, "change_pct": None},
        {"name": "—", "ticker": "—", "price": None, "change_pct": None},
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

def fetch(url, headers=HEADERS):
    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT)
        if r.status_code == 200:
            print(f"  ✅ {url[:65]}")
            return r.text
        print(f"  ❌ HTTP {r.status_code}  {url[:65]}")
    except Exception as e:
        print(f"  ❌ {e}  {url[:65]}")
    return None


# ── SOURCE 1: Trading Economics (most reliable for EGX30) ───────
def from_trading_economics():
    print("\n[1] Trading Economics")
    html = fetch("https://tradingeconomics.com/egypt/stock-market")
    if not html: return {}, []

    soup = BeautifulSoup(html, "lxml")
    indices = {}

    # TE renders a table: symbol | value | day% | weekly% | monthly% | date
    for row in soup.select("table tr"):
        cells = row.find_all(["td","th"])
        if len(cells) < 3: continue
        label = cells[0].get_text(strip=True).lower()
        val   = clean(cells[1].get_text(strip=True))
        chg   = clean(cells[2].get_text(strip=True))

        if "egx" not in label and "egypt" not in label: continue
        if not val or val < 100: continue

        key = None
        if   "30" in label: key = "egx30"
        elif "70" in label: key = "egx70"
        elif "100" in label: key = "egx100"
        elif "35" in label:  key = "egx35lv"
        elif "sharia" in label or "shariah" in label: key = "sharia"

        if key:
            indices[key] = {"value": val, "change_pct": chg, "date": today()}
            print(f"    {key}: {val}  ({chg:+.2f}%)" if chg else f"    {key}: {val}")

    return indices, [html]


# ── SOURCE 2: Mubasher English (all EGX indices + gainers/losers) ─
def from_mubasher():
    print("\n[2] Mubasher English")
    indices, gainers, losers, htmls = {}, [], [], []

    # Indices page
    html = fetch("https://english.mubasher.info/markets/EGX/indices")
    if html:
        htmls.append(html)
        soup = BeautifulSoup(html, "lxml")
        for row in soup.select("table tr, .index-row, [class*='index']"):
            cells = row.find_all(["td","th"])
            if len(cells) < 2: continue
            label = cells[0].get_text(strip=True).lower()
            val   = clean(cells[1].get_text(strip=True)) if len(cells) > 1 else None
            chg   = clean(cells[2].get_text(strip=True)) if len(cells) > 2 else None
            if not val or val < 100: continue

            key = None
            if   "egx 30" in label or "egx30" in label:  key = "egx30"
            elif "egx 70" in label or "egx70" in label:  key = "egx70"
            elif "egx 100" in label or "egx100" in label: key = "egx100"
            elif "35" in label: key = "egx35lv"
            elif "sharia" in label or "shariah" in label: key = "sharia"
            if key:
                indices[key] = {"value": val, "change_pct": chg, "date": today()}
                print(f"    {key}: {val}")

    # Top gainers
    html2 = fetch("https://english.mubasher.info/markets/EGX/top-gainers")
    if html2:
        htmls.append(html2)
        soup2 = BeautifulSoup(html2, "lxml")
        for row in soup2.select("table tr"):
            cells = row.find_all("td")
            if len(cells) < 4: continue
            name   = cells[0].get_text(strip=True)
            ticker = cells[1].get_text(strip=True) if len(cells) > 1 else "—"
            price  = clean(cells[2].get_text(strip=True)) if len(cells) > 2 else None
            chg    = clean(cells[3].get_text(strip=True)) if len(cells) > 3 else None
            if name and name != "Name" and chg is not None:
                gainers.append({"name": name, "ticker": ticker, "price": price, "change_pct": abs(chg)})
        print(f"    Gainers: {len(gainers)}")

    # Top losers
    html3 = fetch("https://english.mubasher.info/markets/EGX/top-losers")
    if html3:
        htmls.append(html3)
        soup3 = BeautifulSoup(html3, "lxml")
        for row in soup3.select("table tr"):
            cells = row.find_all("td")
            if len(cells) < 4: continue
            name   = cells[0].get_text(strip=True)
            ticker = cells[1].get_text(strip=True) if len(cells) > 1 else "—"
            price  = clean(cells[2].get_text(strip=True)) if len(cells) > 2 else None
            chg    = clean(cells[3].get_text(strip=True)) if len(cells) > 3 else None
            if name and name != "Name" and chg is not None:
                losers.append({"name": name, "ticker": ticker, "price": price, "change_pct": -abs(chg)})
        print(f"    Losers: {len(losers)}")

    return indices, gainers, losers, htmls


# ── SOURCE 3: Claude AI ─────────────────────────────────────────
def from_claude(htmls):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("\n[3] Claude — no API key, skipping")
        return {}, [], []

    print("\n[3] Claude AI extraction")
    snippet = "\n---\n".join(h[:5000] for h in htmls if h)[:14000]
    schema = '{"indices":{"egx30":{"value":52861,"change_pct":1.48,"date":"2026-05-24"},"egx70":{"value":14584,"change_pct":1.29,"date":"2026-05-24"},"egx100":{"value":20388,"change_pct":1.25,"date":"2026-05-24"},"egx35lv":{"value":5872,"change_pct":1.24,"date":"2026-05-24"},"sharia":{"value":5847,"change_pct":0.81,"date":"2026-05-24"}},"gainers":[{"name":"Arab Aluminum","ticker":"ARAL","price":null,"change_pct":9.82}],"losers":[{"name":"Eg. Const. Dev.","ticker":"ECCD","price":null,"change_pct":-13.51}]}'
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={
                "model": "claude-sonnet-4-20250514", "max_tokens": 700,
                "system": f"Extract EGX stock data. Return ONLY raw JSON matching schema (no markdown):\n{schema}",
                "messages": [{"role": "user", "content": snippet}],
            }, timeout=35,
        )
        r.raise_for_status()
        raw = re.sub(r"^```[a-z]*\n?|\n?```$", "", r.json()["content"][0]["text"].strip())
        d = json.loads(raw)
        print(f"    indices={len(d.get('indices',{}))}, gainers={len(d.get('gainers',[]))}, losers={len(d.get('losers',[]))}")
        return d.get("indices", {}), d.get("gainers", []), d.get("losers", [])
    except Exception as e:
        print(f"    ❌ {e}")
        return {}, [], []


# ── MAIN ─────────────────────────────────────────────────────────
def main():
    print(f"\n📈 EGX Scraper — {now_utc()}")

    indices = {k: dict(v) for k, v in FALLBACK["indices"].items()}
    market  = dict(FALLBACK["market"])
    gainers = [dict(g) for g in FALLBACK["gainers"]]
    losers  = [dict(l) for l in FALLBACK["losers"]]
    all_html = []

    # 1 — Trading Economics
    te_idx, te_html = from_trading_economics()
    all_html += te_html
    for k, v in te_idx.items():
        if v.get("value"): indices[k] = v
    time.sleep(1)

    # 2 — Mubasher (indices + gainers/losers)
    mb_idx, mb_gainers, mb_losers, mb_html = from_mubasher()
    all_html += mb_html
    for k, v in mb_idx.items():
        if v.get("value"): indices[k] = v
    if len(mb_gainers) >= 3: gainers = mb_gainers[:5]
    if len(mb_losers)  >= 3: losers  = mb_losers[:5]
    time.sleep(1)

    # 3 — Claude AI if still mostly fallback
    live = sum(1 for v in indices.values() if v.get("date") == today())
    need_gainers = len([g for g in gainers if g["name"] != "—"]) < 3
    if live < 3 or need_gainers:
        print(f"\n    Only {live} live indices / gainers weak — using Claude")
        ai_idx, ai_gain, ai_loss = from_claude(all_html)
        for k, v in ai_idx.items():
            if v.get("value") and indices.get(k, {}).get("date") != today():
                indices[k] = v
        if len(ai_gain) >= 3: gainers = ai_gain[:5]
        if len(ai_loss) >= 3: losers  = ai_loss[:5]

    # Pad to 5
    while len(gainers) < 5: gainers.append({"name":"—","ticker":"—","price":None,"change_pct":None})
    while len(losers)  < 5: losers.append( {"name":"—","ticker":"—","price":None,"change_pct":None})

    out = {
        "source": "https://www.egx.com.eg/",
        "lastUpdated": now_utc(),
        "indices": indices,
        "market": market,
        "gainers": gainers[:5],
        "losers":  losers[:5],
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    live = sum(1 for v in indices.values() if v.get("date") == today())
    print(f"\n✅ {OUTPUT_FILE} — {live}/{len(indices)} live  |  {len([g for g in gainers if g['name']!='—'])} gainers  |  {len([l for l in losers if l['name']!='—'])} losers")

if __name__ == "__main__":
    main()
