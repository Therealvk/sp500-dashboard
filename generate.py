"""
Build a static S&P 500 daily-movers dashboard.

- Pulls the current constituent list from Wikipedia
- Pulls daily closes from Yahoo Finance via yfinance (no API key)
- Computes each stock's daily % change (last close vs. previous close)
- Renders docs/index.html (served by GitHub Pages)

Run locally:  python generate.py
"""

import io
import html
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import pandas as pd
import yfinance as yf

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; sp500-dashboard/1.0)"}
OUT_DIR = "docs"


# ----------------------------------------------------------------------------- data
def get_constituents():
    """Return DataFrame with Symbol, Name, Sector for the current S&P 500."""
    resp = requests.get(WIKI_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    tables = pd.read_html(io.StringIO(resp.text))
    df = tables[0][["Symbol", "Security", "GICS Sector"]].copy()
    df.columns = ["symbol", "name", "sector"]
    # Yahoo uses '-' where Wikipedia uses '.'  (e.g. BRK.B -> BRK-B)
    df["symbol"] = df["symbol"].str.replace(".", "-", regex=False).str.strip()
    df = df.drop_duplicates(subset="symbol").reset_index(drop=True)
    return df


def download_chunk(symbols, tries=3):
    """Download ~5 days of daily closes for a batch of symbols, with retries."""
    for attempt in range(tries):
        try:
            data = yf.download(
                symbols, period="5d", interval="1d",
                group_by="ticker", auto_adjust=False,
                threads=True, progress=False,
            )
            if data is not None and not data.empty:
                return data
        except Exception as e:  # noqa: BLE001
            print(f"  chunk attempt {attempt+1} failed: {e}")
        time.sleep(3)
    return None


def get_quotes(symbols):
    """Return list of dicts with symbol, price, change, pct — plus the as-of date."""
    quotes, as_of = {}, None
    for i in range(0, len(symbols), 100):
        batch = symbols[i:i + 100]
        print(f"Downloading {i+1}-{i+len(batch)} of {len(symbols)}...")
        data = download_chunk(batch)
        if data is None:
            continue
        for sym in batch:
            try:
                closes = data[sym]["Close"].dropna()
                if len(closes) < 2:
                    continue
                prev, last = float(closes.iloc[-2]), float(closes.iloc[-1])
                if prev == 0:
                    continue
                quotes[sym] = {
                    "price": last,
                    "change": last - prev,
                    "pct": (last - prev) / prev * 100.0,
                }
                as_of = closes.index[-1]
            except Exception:  # noqa: BLE001
                continue
    return quotes, as_of


# ----------------------------------------------------------------------------- render
PALETTE = dict(
    bg="#0E131F", panel="#161D2C", panelHi="#1B2436", line="#27314A",
    text="#E9EDF5", muted="#8B98B2", faint="#5B6784",
    gain="#3DBE8B", gainDim="#1F3B33", loss="#E56A62", lossDim="#3B2320", gold="#E0B15E",
)


def fmt(n, d=2):
    if n is None:
        return "—"
    return f"{n:,.{d}f}"


def pct_str(n):
    return ("+" if n >= 0 else "") + f"{n:,.2f}%"


def leaderboard_html(title, rows, color, dim):
    mx = max([abs(r["pct"]) for r in rows] + [0.01])
    items = []
    for r in rows:
        w = abs(r["pct"]) / mx * 100
        items.append(f"""
        <div class="lb-row">
          <div class="lb-bar" style="width:{w:.1f}%;background:{dim}"></div>
          <div class="lb-content">
            <div class="lb-left">
              <span class="mono lb-sym">{html.escape(r['symbol'])}</span>
              <span class="lb-name">{html.escape(r['name'])}</span>
            </div>
            <div class="lb-right">
              <span class="mono lb-price">{fmt(r['price'])}</span>
              <span class="mono lb-pct" style="color:{color}">{pct_str(r['pct'])}</span>
            </div>
          </div>
        </div>""")
    return f"""
    <section class="card">
      <div class="card-head"><span class="dot" style="background:{color}"></span><h2>{title}</h2></div>
      <div>{''.join(items)}</div>
    </section>"""


def render(rows, as_of):
    gainers = sorted(rows, key=lambda r: r["pct"], reverse=True)[:10]
    losers = sorted(rows, key=lambda r: r["pct"])[:10]
    up = sum(1 for r in rows if r["pct"] > 0)
    down = sum(1 for r in rows if r["pct"] < 0)
    avg = sum(r["pct"] for r in rows) / len(rows) if rows else 0
    p = PALETTE

    tape = gainers[:6] + losers[:6]
    tape_html = "".join(
        f'<span class="mono tape-item"><b>{html.escape(t["symbol"])}</b> {fmt(t["price"])} '
        f'<span style="color:{p["gain"] if t["pct"]>=0 else p["loss"]}">{pct_str(t["pct"])}</span></span>'
        for t in (tape + tape)
    )

    table_rows = "".join(
        f'<tr data-sym="{html.escape(r["symbol"])}" data-name="{html.escape(r["name"]).upper()}" '
        f'data-price="{r["price"]}" data-change="{r["change"]}" data-pct="{r["pct"]}">'
        f'<td class="mono b">{html.escape(r["symbol"])}</td>'
        f'<td class="muted ellip">{html.escape(r["name"])}</td>'
        f'<td class="mono r">{fmt(r["price"])}</td>'
        f'<td class="mono r" style="color:{p["gain"] if r["change"]>=0 else p["loss"]}">'
        f'{"+" if r["change"]>=0 else ""}{fmt(r["change"])}</td>'
        f'<td class="mono r b" style="color:{p["gain"] if r["pct"]>=0 else p["loss"]}">{pct_str(r["pct"])}</td>'
        f'</tr>'
        for r in sorted(rows, key=lambda r: r["pct"], reverse=True)
    )

    stamp = ""
    if as_of is not None:
        try:
            d = pd.Timestamp(as_of).to_pydatetime()
            stamp = d.strftime("%b %-d, %Y")
        except Exception:  # noqa: BLE001
            stamp = str(as_of)[:10]
    built = datetime.now(ZoneInfo("America/New_York")).strftime("%b %-d, %Y · %-I:%M %p ET")

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>S&amp;P 500 Daily Movers</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  *{{box-sizing:border-box}}
  body{{margin:0;background:{p['bg']};color:{p['text']};font-family:'Space Grotesk',system-ui,sans-serif}}
  .mono{{font-family:'JetBrains Mono',ui-monospace,monospace;font-variant-numeric:tabular-nums}}
  .b{{font-weight:600}} .muted{{color:{p['muted']}}} .r{{text-align:right}}
  header{{border-bottom:1px solid {p['line']};padding:20px 24px}}
  .head-row{{display:flex;flex-wrap:wrap;align-items:baseline;gap:16px;justify-content:space-between;max-width:1240px;margin:0 auto}}
  .eyebrow{{font-size:11px;letter-spacing:.22em;color:{p['gold']};text-transform:uppercase;margin-bottom:4px}}
  h1{{margin:0;font-size:26px;font-weight:700;letter-spacing:-.01em}}
  .meta{{display:flex;align-items:center;gap:14px;flex-wrap:wrap;font-size:12.5px;color:{p['muted']}}}
  .tape{{border-bottom:1px solid {p['line']};overflow:hidden;background:{p['panel']};padding:9px 0;white-space:nowrap}}
  .tape-track{{display:inline-flex;animation:scroll 40s linear infinite}}
  .tape-item{{padding:0 22px;font-size:13px;color:{p['muted']}}} .tape-item b{{color:{p['text']}}}
  @keyframes scroll{{from{{transform:translateX(0)}}to{{transform:translateX(-50%)}}}}
  main{{padding:24px;max-width:1240px;margin:0 auto}}
  .statgrid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}}
  .stat{{background:{p['panel']};border:1px solid {p['line']};border-radius:12px;padding:14px 16px}}
  .stat .lbl{{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:{p['muted']};margin-bottom:6px}}
  .stat .val{{font-size:24px;font-weight:700}}
  .split{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:28px}}
  .card{{background:{p['panel']};border:1px solid {p['line']};border-radius:12px;overflow:hidden}}
  .card-head{{padding:14px 16px;border-bottom:1px solid {p['line']};display:flex;align-items:center;gap:8px}}
  .card-head h2{{margin:0;font-size:15px;font-weight:600}}
  .dot{{width:9px;height:9px;border-radius:2px}}
  .lb-row{{position:relative;padding:9px 16px;border-top:1px solid {p['line']}}}
  .lb-row:first-child{{border-top:none}}
  .lb-bar{{position:absolute;left:0;top:0;bottom:0;z-index:0}}
  .lb-content{{position:relative;z-index:1;display:flex;align-items:center;justify-content:space-between;gap:10px}}
  .lb-left{{display:flex;align-items:baseline;gap:10px;min-width:0}}
  .lb-sym{{font-weight:600;width:58px;flex-shrink:0}}
  .lb-name{{color:{p['muted']};font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
  .lb-right{{display:flex;align-items:baseline;gap:12px;flex-shrink:0}}
  .lb-price{{font-size:12.5px;color:{p['muted']}}} .lb-pct{{font-weight:600}}
  .tbl-head{{display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid {p['line']};flex-wrap:wrap;gap:10px}}
  .tbl-head h2{{margin:0;font-size:15px;font-weight:600}}
  input#q{{background:{p['bg']};border:1px solid {p['line']};color:{p['text']};border-radius:8px;padding:8px 12px;font-size:13px;font-family:'JetBrains Mono',monospace;outline:none;width:200px}}
  input#q:focus{{border-color:{p['gold']}}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th{{padding:11px 16px;font-weight:600;color:{p['muted']};border-bottom:1px solid {p['line']};text-transform:uppercase;font-size:11px;letter-spacing:.06em;cursor:pointer;user-select:none}}
  th.r,td.r{{text-align:right}} th:first-child,td:first-child{{text-align:left}}
  td{{padding:10px 16px;border-top:1px solid {p['line']}}}
  tbody tr:hover{{background:{p['panelHi']}}}
  .ellip{{max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
  footer{{color:{p['faint']};font-size:11.5px;margin-top:20px;line-height:1.6}}
  @media (prefers-reduced-motion: reduce){{.tape-track{{animation:none}}}}
  @media (max-width:760px){{.split{{grid-template-columns:1fr}}.statgrid{{grid-template-columns:repeat(2,1fr)}}}}
</style></head>
<body>
<header><div class="head-row">
  <div><div class="eyebrow">S&amp;P 500 · Daily Movers</div><h1>Market Board</h1></div>
  <div class="meta"><span>As of close {stamp}</span><span class="mono" style="color:{p['faint']}">Built {built}</span></div>
</div></header>

<div class="tape"><div class="tape-track">{tape_html}</div></div>

<main>
  <div class="statgrid">
    <div class="stat"><div class="lbl">Advancing</div><div class="val" style="color:{p['gain']}">{up}</div></div>
    <div class="stat"><div class="lbl">Declining</div><div class="val" style="color:{p['loss']}">{down}</div></div>
    <div class="stat"><div class="lbl">Index avg</div><div class="val mono" style="color:{p['gain'] if avg>=0 else p['loss']}">{pct_str(avg)}</div></div>
    <div class="stat"><div class="lbl">Tracked</div><div class="val" style="color:{p['gold']}">{len(rows)}</div></div>
  </div>

  <div class="split">
    {leaderboard_html("Top 10 Gainers", gainers, p['gain'], p['gainDim'])}
    {leaderboard_html("Top 10 Losers", losers, p['loss'], p['lossDim'])}
  </div>

  <section class="card">
    <div class="tbl-head"><h2>All constituents</h2><input id="q" placeholder="Search ticker or name"></div>
    <div style="overflow-x:auto">
      <table id="tbl"><thead><tr>
        <th data-k="sym">Symbol</th><th data-k="name">Name</th>
        <th class="r" data-k="price">Price</th><th class="r" data-k="change">Change</th>
        <th class="r" data-k="pct">% Change</th>
      </tr></thead><tbody>{table_rows}</tbody></table>
    </div>
  </section>

  <footer>Data via Yahoo Finance (yfinance). Rebuilt automatically each weekday after the US close by GitHub Actions. Not investment advice.</footer>
</main>

<script>
  const tbody = document.querySelector('#tbl tbody');
  const rows = () => Array.from(tbody.querySelectorAll('tr'));
  document.getElementById('q').addEventListener('input', e => {{
    const q = e.target.value.trim().toUpperCase();
    rows().forEach(r => {{
      const show = !q || r.dataset.sym.includes(q) || r.dataset.name.includes(q);
      r.style.display = show ? '' : 'none';
    }});
  }});
  let dir = {{}};
  document.querySelectorAll('#tbl th').forEach(th => th.addEventListener('click', () => {{
    const k = th.dataset.k, num = ['price','change','pct'].includes(k);
    dir[k] = dir[k] === 'asc' ? 'desc' : 'asc';
    const s = dir[k] === 'asc' ? 1 : -1;
    rows().sort((a,b) => {{
      let av = a.dataset[k==='sym'?'sym':k], bv = b.dataset[k==='sym'?'sym':k];
      if (num) {{ av = parseFloat(av); bv = parseFloat(bv); return (av-bv)*s; }}
      return av.localeCompare(bv)*s;
    }}).forEach(r => tbody.appendChild(r));
  }}));
</script>
</body></html>"""


# ----------------------------------------------------------------------------- main
def main():
    import os
    print("Fetching constituent list...")
    const = get_constituents()
    print(f"  {len(const)} symbols")

    quotes, as_of = get_quotes(const["symbol"].tolist())
    print(f"Got quotes for {len(quotes)} symbols")

    rows = []
    for _, c in const.iterrows():
        q = quotes.get(c["symbol"])
        if not q:
            continue
        rows.append({"symbol": c["symbol"], "name": c["name"], "sector": c["sector"], **q})

    if not rows:
        raise SystemExit("No quote data retrieved — aborting so the page isn't blanked.")

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(render(rows, as_of))
    open(os.path.join(OUT_DIR, ".nojekyll"), "w").close()
    print(f"Wrote {OUT_DIR}/index.html with {len(rows)} rows")


if __name__ == "__main__":
    main()
