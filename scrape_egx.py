import requests
from bs4 import BeautifulSoup
import json
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

def clean_num(text):
    if not text:
        return None

    text = text.replace(",", "").replace("%", "").strip()

    try:
        return float(text)
    except:
        return None


def get_indices():
    url = "https://www.egx.com.eg/en/Indices.aspx"

    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    indices = {}

    tables = soup.find_all("table")

    for table in tables:
        rows = table.find_all("tr")

        for row in rows:
            cols = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]

            if len(cols) < 3:
                continue

            name = cols[0].lower()

            if "egx" not in name:
                continue

            value = clean_num(cols[1])
            change = clean_num(cols[2])

            key = re.sub(r"[^a-z0-9]", "", name)

            indices[key] = {
                "name": cols[0],
                "value": value,
                "change_pct": change
            }

    return indices


def get_gainers_losers():
    url = "https://www.egx.com.eg/en/Top_GL.aspx"

    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    gainers = []
    losers = []

    tables = soup.find_all("table")

    for table in tables:

        caption = table.get_text(" ", strip=True).lower()

        rows = table.find_all("tr")

        parsed = []

        for row in rows[1:]:

            cols = [c.get_text(" ", strip=True) for c in row.find_all("td")]

            if len(cols) < 3:
                continue

            parsed.append({
                "name": cols[0],
                "price": clean_num(cols[1]),
                "change_pct": clean_num(cols[-1])
            })

        if "gainer" in caption:
            gainers = parsed

        elif "loser" in caption:
            losers = parsed

    return gainers, losers


def main():

    data = {
        "indices": get_indices()
    }

    try:
        gainers, losers = get_gainers_losers()

        data["gainers"] = gainers
        data["losers"] = losers

    except Exception as e:
        print("Top gainers/losers unavailable:", e)
        data["gainers"] = []
        data["losers"] = []

    with open("egx.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("Saved to egx.json")


if __name__ == "__main__":
    main()
