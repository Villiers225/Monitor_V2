# Defence Procurement Monitor (GitHub Pages Starter)

A lightweight, reproducible pipeline and static dashboard that discovers, evaluates, and organises articles about **defence procurement** — including recurring **problems** and proposed **solutions** — and renders them on a clean GitHub Pages site.

## What you get
- **Crawler & ranker** (`scripts/crawler.py`) that pulls from RSS, optional web search, and social (via `snscrape`).
- **Evaluator** that scores relevance, tags themes & solutions, deduplicates and summaries.
- **Dashboard** (in `site/`) with sort-by-column, filtering, search, and charts of recurring themes/solutions.
- **Weekly summaries** generated to `reports/` and rendered at `site/weekly.html`.
- **User steering**: like/ignore articles to bias future search & ranking (`data/user_signals.json`).

## Quick start
1. **Download this repo as ZIP**, then create a new *public* repo on GitHub and upload everything.
2. Enable **GitHub Pages** (Settings → Pages → Deploy from branch → `main` / `/site`).  
   Your site will be served at `https://<you>.github.io/<repo>/`.
3. Add *optional* secrets (Settings → Secrets and variables → Actions → New repository secret):
   - `OPENAI_API_KEY` – for higher‑quality summaries & smarter tagging (optional).
   - `BING_API_KEY` – for supplemental web search (optional).
4. (Optional) Edit `scripts/config.yaml` to fine‑tune sources, keywords, and exclusions.
5. Trigger the workflow: **Actions → Update data → Run workflow**.  
   Or wait for the daily schedule.

## Local run
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r scripts/requirements.txt
python scripts/crawler.py --refresh --summarise --weekly
python scripts/build_site.py
# Open site locally (simple server)
python -m http.server -d site 8080
```

## Add your own articles
- Put URLs in `data/user_seed/urls.txt` (one per line).  
- Or drop full‑text `.txt` files into `data/user_seed/text/` (file name used as title).
- Click the ★ icon next to an article in the dashboard to "like" it — the next run will bias toward its language & themes.

## Data outputs
- `data/articles.json` – all processed items with scores, tags, summaries.
- `data/themes.json` – co-occurrence stats (themes & solutions).
- `reports/weekly_summary.md` – digest of the last 7 days (also rendered to `site/weekly.html`).

## Notes
- News paywalls are respected; only metadata & snippets are stored.
- Social sources use **snscrape** where permitted; APIs are preferred if you have keys.
- This is a starter. Extend sources, models, and UI to your needs.
