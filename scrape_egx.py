"""
EGX scraper — uses Claude AI with web_search tool
Since most financial sites block GitHub Actions IPs, we ask Claude to
search for and extract the latest EGX data. This approach is reliable
because Claude can reach any site, not just ones that allow server IPs.

Costs ~$0.003 per run (web search + extraction).
At 2 runs/day = ~$0.18/month.
"""

import json, os, re, sys, time
from datetime import datetime, timezone
import requests

OUTPUT_FILE = "egx.json"

FALLBACK = {
    "indices": {
        "egx30":  {"value": 46399.00, "change_pct": -0.71, "date": "2026-04-02"},
        "egx70":  {"value": 12753.85, "change_pct":  0.40, "date": "2026-04-02"},
        "egx100": {"value": 17724.91, "change_pct":  0.21, "date": "2026-04-02"},
        "sharia": {"value":  4909.55, "change_pct": -0.22, "date": "2026-04-02"},
    },
    "market": {"date": "2026-04-02"},
    "gainers": [
        {"name": "Qalaa Holdings",       "ticker": "CCAP",  "price": 3.98,   "change_pct":  3.38},
        {"name": "Orascom Construction", "ticker": "ORAS",  "price": 497.00, "change_pct":  2.47},
        {"name": "Orascom Invest",       "ticker": "OIH",   "price": 1.39,   "change_pct":  2.21},
        {"name": "Valmore Holding A",    "ticker": "VLMRA", "price": 32.77,  "change_pct":  1.87},
        {"name": "Misr Cement",          "ticker": "MCQE",  "price": 172.00, "change_pct":  1.41},
    ],
    "losers": [
        {"name": "Abu Qir Fertilizers",  "ticker": "ABUK",  "price": 82.00,  "change_pct": -2.14},
        {"name": "TMG Holding",          "ticker": "TMGH",  "price": 77.41,  "change_pct": -2.01},
        {"name": "Raya Holding",         "ticker": "RAYA",  "price": 5.16,   "change_pct": -1.90},
        {"name": "Fawry Banking",        "ticker": "FWRY",  "price": 17.58,  "change_pct": -1.68},
        {"name": "GB Auto",              "ticker": "GBCO",  "price": 24.60,  "change_pct": -1.60},
    ],
}

def now_utc(): return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
def today():   return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def load_existing():
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def scrape_with_claude_search(api_key: str) -> dict | None:
    """
    Ask Claude to search the web for today's EGX data and return structured JSON.
    Uses the web_search tool so Claude can fetch live data from any site.
    """
    print("🤖 Asking Claude to search for EGX data...")

    today_str = today()
    prompt = f"""Search for the latest Egyptian Stock Exchange (EGX) market data for today ({today_str}).

Find:
1. EGX30 index value and % change
2. EGX70 index value and % change  
3. EGX100 index value and % change
4. EGX Sharia/Shariah index value and % change
5. Top 5 gainers: company name, ticker, price, % change
6. Top 5 losers: company name, ticker, price, % change

Search investing.com, tradingeconomics.com, or any financial site that has this data.

Return ONLY a raw JSON object, no markdown, no explanation:
{{
  "indices": {{
    "egx30":  {{"value": 46399, "change_pct": -0.71, "date": "{today_str}"}},
    "egx70":  {{"value": 12753, "change_pct":  0.40, "date": "{today_str}"}},
    "egx100": {{"value": 17724, "change_pct":  0.21, "date": "{today_str}"}},
    "sharia": {{"value":  4909, "change_pct": -0.22, "date": "{today_str}"}}
  }},
  "gainers": [
    {{"name": "Company Name", "ticker": "TICK", "price": 1.23, "change_pct": 4.56}}
  ],
  "losers": [
    {{"name": "Company Name", "ticker": "TICK", "price": 1.23, "change_pct": -2.34}}
  ]
}}

Use null for any value you cannot find. Include exactly 5 gainers and 5 losers if available."""

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1500,
        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
            timeout=90,  # web search needs more time
        )
        r.raise_for_status()
        response = r.json()

        # Extract the final text response (after web search tool calls)
        text_blocks = [
            block["text"]
            for block in response.get("content", [])
            if block.get("type") == "text"
        ]
        raw = "\n".join(text_blocks).strip()

        print(f"   Claude responded ({len(raw)} chars)")

        # Strip markdown fences if present
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        raw = raw.strip()

        # Find JSON object in the response
        json_match = re.search(r"\{[\s\S]+\}", raw)
        if not json_match:
            print("   ❌ No JSON found in response")
            print(f"   Response preview: {raw[:300]}")
            return None

        data = json.loads(json_match.group(0))
        return data

    except requests.exceptions.Timeout:
        print("   ❌ Request timed out (90s)")
        return None
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None


def validate_and_merge(fresh: dict, fallback_indices: dict, fallback_gainers: list, fallback_losers: list):
    """Validate fresh data and merge with fallback for missing fields."""
    indices = dict(fallback_indices)
    gainers = list(fallback_gainers)
    losers  = list(fallback_losers)

    fresh_indices = fresh.get("indices", {})
    for key in ["egx30", "egx70", "egx100", "sharia"]:
        d = fresh_indices.get(key, {})
        if isinstance(d, dict) and d.get("value") and isinstance(d["value"], (int, float)):
            val = float(d["value"])
            # Sanity check — EGX30 should be between 5000 and 200000
            if 5000 < val < 200000:
                indices[key] = {
                    "value": val,
                    "change_pct": d.get("change_pct"),
                    "date": today(),
                }
                print(f"   ✓ {key}: {val}  {d.get('change_pct')}%")

    fresh_gainers = fresh.get("gainers", [])
    if len(fresh_gainers) >= 3:
        gainers = []
        for g in fresh_gainers[:5]:
            if isinstance(g, dict) and g.get("name") and g["name"] not in ("—", "", None):
                gainers.append({
                    "name": str(g.get("name", "—")),
                    "ticker": str(g.get("ticker", "—")),
                    "price": g.get("price"),
                    "change_pct": abs(float(g["change_pct"])) if g.get("change_pct") is not None else None,
                })
        print(f"   ✓ Gainers: {len(gainers)}")

    fresh_losers = fresh.get("losers", [])
    if len(fresh_losers) >= 3:
        losers = []
        for l in fresh_losers[:5]:
            if isinstance(l, dict) and l.get("name") and l["name"] not in ("—", "", None):
                losers.append({
                    "name": str(l.get("name", "—")),
                    "ticker": str(l.get("ticker", "—")),
                    "price": l.get("price"),
                    "change_pct": -abs(float(l["change_pct"])) if l.get("change_pct") is not None else None,
                })
        print(f"   ✓ Losers: {len(losers)}")

    # Pad to 5
    while len(gainers) < 5: gainers.append({"name":"—","ticker":"—","price":None,"change_pct":None})
    while len(losers)  < 5: losers.append( {"name":"—","ticker":"—","price":None,"change_pct":None})

    return indices, gainers[:5], losers[:5]


def main():
    print(f"\n📈 EGX Scraper — {now_utc()}")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY not set — cannot scrape, writing fallback data")
        out = {
            "source": "https://www.egx.com.eg/",
            "lastUpdated": now_utc(),
            "scrape_error": "No API key",
            "indices": FALLBACK["indices"],
            "market": FALLBACK["market"],
            "gainers": FALLBACK["gainers"],
            "losers": FALLBACK["losers"],
        }
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        sys.exit(1)

    fresh = scrape_with_claude_search(api_key)

    if fresh is None:
        print("\n⚠️  Claude search failed — keeping existing/fallback data")
        existing = load_existing()
        if not existing:
            existing = {"source": "https://www.egx.com.eg/", "lastUpdated": now_utc(),
                        "scrape_error": "Claude search failed",
                        "indices": FALLBACK["indices"], "market": FALLBACK["market"],
                        "gainers": FALLBACK["gainers"], "losers": FALLBACK["losers"]}
        existing["scrape_error"] = "Claude search failed"
        existing["last_attempted"] = now_utc()
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        sys.exit(1)

    print("\n✅ Validating data...")
    indices, gainers, losers = validate_and_merge(
        fresh,
        FALLBACK["indices"],
        FALLBACK["gainers"],
        FALLBACK["losers"],
    )

    live = sum(1 for v in indices.values() if v.get("date") == today())

    out = {
        "source": "https://www.egx.com.eg/",
        "lastUpdated": now_utc(),
        "scrape_error": None,
        "indices": indices,
        "market": FALLBACK["market"],
        "gainers": gainers,
        "losers": losers,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Done — {live}/{len(indices)} live indices today")
    for k, v in indices.items():
        tag = "✓" if v.get("date") == today() else "~"
        chg = v.get("change_pct") or 0
        print(f"  {tag} {k:10s}  {v['value']:>10,.2f}  {chg:>+6.2f}%")


if __name__ == "__main__":
    main()
