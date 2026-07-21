# S&P 500 Daily Movers Dashboard

A self-updating dashboard that tracks the daily price and % change of every S&P 500
stock and highlights the top 10 gainers and losers. It rebuilds itself every weekday
after the US market close using GitHub Actions — no server, no API key, no cost.

Your live dashboard will be at: `https://YOUR-USERNAME.github.io/YOUR-REPO/`

---

## One-time setup (about 10 minutes)

### 1. Create the repository
- On GitHub, click **New repository**.
- Name it something like `sp500-dashboard`. Make it **Public** (GitHub Pages is free
  for public repos; private repos need a paid plan for Pages).
- Create it.

### 2. Add these files
Upload all of these, keeping the folder structure exactly as-is:

```
generate.py
requirements.txt
README.md
.github/workflows/update-dashboard.yml
```

The easiest way: on the repo page, choose **Add file → Upload files**, drag everything
in, and commit. Make sure the workflow file lands at
`.github/workflows/update-dashboard.yml` (GitHub needs that exact path).

### 3. Run it once by hand to generate the first page
- Go to the **Actions** tab.
- If prompted, click the green button to enable workflows.
- Select **Update S&P 500 Dashboard** on the left, then **Run workflow** → **Run workflow**.
- Wait ~2 minutes. When it finishes green, a new `docs/` folder with `index.html` will
  be in your repo.

### 4. Turn on GitHub Pages
- Go to **Settings → Pages**.
- Under **Source**, choose **Deploy from a branch**.
- Set **Branch** to `main` and the folder to **/docs**, then **Save**.
- Give it a minute, then visit `https://YOUR-USERNAME.github.io/YOUR-REPO/`.

Bookmark that URL on your phone. Done.

---

## How the automation works
- The workflow runs **weekdays at 22:00 UTC** (after the 4:00 PM ET close in both
  winter and summer). GitHub may delay scheduled runs by a few minutes during busy
  periods — that's normal.
- Each run pulls the current constituent list from Wikipedia, downloads the latest two
  daily closes per stock from Yahoo Finance, computes the daily change, rebuilds
  `docs/index.html`, and commits it. Pages serves the updated file automatically.
- Because it commits every run, the repo stays "active," so GitHub won't auto-disable
  the schedule. You also get a dated commit history of past dashboards.

## Want it to run at a different time?
Edit the `cron` line in `.github/workflows/update-dashboard.yml`. The format is
`minute hour day month weekday`, in UTC. For example, `30 21 * * 1-5` is 21:30 UTC on
weekdays.

## Troubleshooting
- **Blank or failed run:** Yahoo Finance occasionally rate-limits. The script retries,
  and if it gets no data at all it stops rather than publishing an empty page, so your
  last good dashboard stays up. Just re-run the workflow.
- **A stock is missing:** if Yahoo has no recent data for a ticker that day, it's
  skipped; it returns the next run.
- **If yfinance breaks after an update:** pin a known-good version in
  `requirements.txt`, e.g. `yfinance==0.2.65`.

Not investment advice — for personal tracking only.
