# medium-to-markdown

Scrape any Medium reading list into clean markdown files — no login required, paywall bypassed via [Freedium](https://freedium.cfd/).

Runs incrementally: only new articles are fetched on each run. Safe to re-run daily as a cron job.

---

## How it works

```
Medium Reading List
       │
       ▼
  StealthyFetcher          ← headless Chromium (Patchright)
  (infinite scroll)        ← harvests URLs at every scroll step
       │                      (Medium removes off-screen DOM nodes)
       ▼
  Freedium mirror          ← strips paywall, serves full article HTML
       │
       ├── plain HTTP      ← fast path (curl_cffi)
       └── browser fallback← for JS-heavy articles
       │
       ▼
  Markdown file            ← raw/<article-slug>.md
  + images downloaded      ← raw/assets/<hash>.<ext>
  + state.json updated     ← tracks scraped URLs, safe to re-run
```

---

## Output

```
raw/
├── assets/
│   ├── 3a9f1c2e4b12.jpg
│   └── ...
├── how-apache-spark-handles-shuffles.md
├── pyspark-window-functions-explained.md
└── ...
```

Each markdown file:

```markdown
---
source: https://medium.com/towards-data-science/how-apache-spark-handles-shuffles-abc123def456
date_scraped: 2024-11-15
---

# How Apache Spark Handles Shuffles

![diagram](assets/3a9f1c2e4b12.jpg)

Article content paragraphs...
```

---

## Setup

**Requirements:** Python 3.9+

```bash
# 1. Clone the repo
git clone https://github.com/vaasminion/medium-to-markdown.git
cd medium-to-markdown

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate        # Linux / macOS
# venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install browser binaries (Playwright / Patchright)
scrapling install

# 5. Set your reading list URL
cp .env.example .env
# Edit .env and set READING_LIST_URL to your Medium reading list
```

### Finding your reading list URL

1. Go to your Medium profile
2. Click **Lists** in the left sidebar
3. Click any list (e.g., "Reading List")
4. Copy the URL from the browser — it looks like:
   `https://medium.com/@youruser/list/reading-list`

---

## Usage

```bash
# Activate venv first
source venv/bin/activate

# Set your reading list URL (or configure in .env)
export READING_LIST_URL=https://medium.com/@youruser/list/reading-list

# Run
python scraper.py
```

**First run** — discovers all articles in the list, then fetches each one. Takes a few minutes for large lists (scrolling + rate limiting).

**Subsequent runs** — only fetches articles added since last run. Fast.

---

## Docker

```bash
# Copy and configure
cp .env.example .env
# Edit .env: set READING_LIST_URL and OUTPUT_VOLUME

# Build and run
docker compose up
```

Output is saved to the `OUTPUT_VOLUME` folder on your host (default: `./output`).

---

## Configuration

All settings can be set via environment variables or a `.env` file:

| Variable | Default | Description |
|---|---|---|
| `READING_LIST_URL` | *(required)* | Your Medium reading list URL |
| `FREEDIUM_BASE` | `https://freedium-mirror.cfd/` | Freedium mirror to use |
| `OUTPUT_DIR` | `raw` | Where markdown files are saved |
| `STATE_FILE` | `state.json` | Tracks already-scraped URLs |
| `RATE_LIMIT_SECONDS` | `2` | Delay between article requests |

**If the Freedium mirror is down**, find alternatives at [freedium.cfd](https://freedium.cfd/) and update `FREEDIUM_BASE`.

---

## Incremental / Cron

The scraper is safe to schedule. Delete `state.json` only if you want to re-scrape everything from scratch.

```bash
# Example: run daily at 8am
0 8 * * * cd /path/to/medium-to-markdown && venv/bin/python scraper.py >> scraper.log 2>&1
```

---

## Use cases

- **Personal knowledge base** — drop `raw/` into Obsidian as a vault
- **LLM Wiki** — compatible with [Andrej Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) as the `raw/` source
- **Offline reading** — archive articles before they go behind a harder paywall
- **RAG pipeline** — ingest markdown files into a vector store for semantic search

---

## Tech stack

| Library | Purpose |
|---|---|
| [Scrapling](https://github.com/D4Vinci/Scrapling) | Anti-bot browser automation (Patchright) + fast HTTP fetching (curl_cffi) |
| [python-slugify](https://github.com/un33k/python-slugify) | Article title → safe filename |
| [requests](https://docs.python-requests.org/) | Image downloading |

---

## Limitations

- Only works with **public** reading lists (no login support)
- Medium's infinite-scroll virtualization means scrolling is slow for large lists (1–3 minutes for 300+ articles)
- Freedium quality varies by article — some articles may have thin content if the mirror has issues

---

## License

MIT
