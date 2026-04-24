# medium-to-markdown

Scrape any Medium reading list into clean markdown files — no login required, paywall bypassed via [Freedium](https://freedium.cfd/).

Then optionally build a **knowledge graph** from all your scraped articles: an interactive visual explorer with topic communities, keyword search, and clickable links back to every article.

Runs incrementally — only new articles are fetched on each run. Safe to schedule as a cron job.

---

## How it works

```
Medium Reading List
       │
       ▼
  StealthyFetcher          ← headless Chromium (Patchright)
  (infinite scroll)        ← harvests URLs at every step
       │                      (Medium removes off-screen DOM nodes)
       ▼
  Freedium mirror          ← strips paywall, serves full article HTML
       │
       ├── plain HTTP      ← fast path (curl_cffi)
       └── browser fallback← for JS-heavy articles
       │
       ▼
  raw/<article-slug>.md    ← clean markdown with YAML frontmatter
  raw/assets/<hash>.jpg    ← images downloaded locally
  state.json               ← tracks scraped URLs (incremental)
       │
       ▼  (optional)
  graphify update raw/     ← LLM extracts concepts and relationships
       │
       ▼
  build_full_graph.py      ← generates interactive HTML graph
  query_graph.py           ← focused subgraph query + local server
```

---

## Output

### Scraped articles

```
raw/
├── assets/
│   ├── 3a9f1c2e4b12.jpg
│   └── ...
├── how-apache-spark-handles-shuffles.md
├── understanding-kafka-consumer-groups.md
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

### Knowledge graph (optional)

After running graphify and `build_full_graph.py`:

```
graphify-out/
├── graph.json      ← GraphRAG-ready JSON
└── graph.html      ← interactive graph viewer
docs/
└── index.html      ← same file, served via GitHub Pages
```

The graph viewer features:
- **Force-directed layout** with topic communities colored by cluster
- **Node sizes** inversely proportional to degree (specific concepts = bigger)
- **Click any node** → see article title and "Open on Medium" link
- **Keyword search panel** (`/` to open) → find articles by topic, concept, or keyword
- **Auto-layout physics** using ForceAtlas2

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

# 5. Configure your reading list
cp .env.example .env
# Edit .env and set READING_LIST_URL
```

### Finding your reading list URL

1. Go to your Medium profile
2. Click **Lists** in the left sidebar
3. Click any list (e.g., "Reading List")
4. Copy the URL from the browser — it looks like:
   `https://medium.com/@youruser/list/reading-list`

---

## Usage

### Scrape articles

```bash
source venv/bin/activate
export READING_LIST_URL=https://medium.com/@youruser/list/reading-list

python scraper.py
```

**First run** — discovers all articles in the list, fetches each one. Takes a few minutes for large lists.

**Subsequent runs** — only fetches articles added since last run.

---

### Build the knowledge graph

After scraping, install [graphify](https://pypi.org/project/graphifyy/) and run it on your `raw/` folder:

```bash
pip install graphifyy
graphify update raw/
```

This extracts concepts and relationships from every article using an LLM. Results are cached per article — re-running only processes new files.

Then generate the interactive HTML:

```bash
python build_full_graph.py
# → writes graphify-out/graph.html and docs/index.html
```

Open `graphify-out/graph.html` in your browser to explore the graph.

---

### Query the graph

Instead of opening the full graph, query for a focused subgraph around a topic:

```bash
python query_graph.py --query "spark shuffle"
# → http://localhost:8765/<token>/
```

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `--query` | *(required)* | Search query — topics, keywords, article names |
| `--port` | `8765` | Local HTTP port |
| `--ttl` | `1800` | Auto-stop after N seconds |
| `--stop` | — | Stop a running server |

The query finds matched nodes + their 1-hop neighbors, renders a focused subgraph, and serves it locally. Click any node to see the article title and a direct link to Medium.

---

## Docker

```bash
cp .env.example .env
# Edit .env: set READING_LIST_URL

docker compose up
```

Scraped articles are saved to `./output` on your host (configurable via `OUTPUT_VOLUME` in `.env`).

> Note: The knowledge graph features are not included in the Docker image — run graphify locally after scraping.

---

## Publish as GitHub Pages

After running `build_full_graph.py`, the graph viewer lands in `docs/index.html`. Commit it and enable GitHub Pages:

```bash
git add docs/
git commit -m "Publish knowledge graph"
git push

# GitHub repo → Settings → Pages → Source: main branch, /docs folder
```

Your graph is now publicly accessible at `https://<username>.github.io/<repo>/`.

---

## Configuration

All scraper settings can be set via environment variables or a `.env` file:

| Variable | Default | Description |
|---|---|---|
| `READING_LIST_URL` | *(required)* | Your Medium reading list URL |
| `FREEDIUM_BASE` | `https://freedium-mirror.cfd/` | Freedium mirror |
| `OUTPUT_DIR` | `raw` | Where markdown files are saved |
| `STATE_FILE` | `state.json` | Tracks already-scraped URLs |
| `RATE_LIMIT_SECONDS` | `2` | Delay between article requests |

**If the Freedium mirror is down**, find alternatives at [freedium.cfd](https://freedium.cfd/) and update `FREEDIUM_BASE`.

---

## Incremental / Cron

```bash
# Run daily at 8am
0 8 * * * cd /path/to/medium-to-markdown && venv/bin/python scraper.py >> scraper.log 2>&1
```

Delete `state.json` only if you want to re-scrape everything from scratch.

---

## Use cases

| Use case | How |
|----------|-----|
| **Personal knowledge base** | Drop `raw/` into Obsidian as a vault |
| **LLM Wiki** | Compatible with [Andrej Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) as the `raw/` source |
| **RAG pipeline** | Ingest markdown files into a vector store (pgvector, Chroma, Pinecone) for semantic search |
| **Knowledge graph explorer** | Run graphify + `build_full_graph.py` → interactive visual graph of all concepts and articles |
| **Focused research** | `query_graph.py --query "topic"` → subgraph of related articles and concepts served locally |
| **GitHub Pages** | Publish the graph as a static site — share your knowledge graph publicly |
| **Offline reading** | Archive articles before they go behind a harder paywall |

---

## Claude Code skill

A `/medium-to-markdown` skill for [Claude Code](https://claude.ai/code) is included at `.claude/skills/medium-to-markdown/SKILL.md`.

It lets you run the full pipeline — scrape, build graph, query, serve — from a single slash command:

```
/medium-to-markdown "kafka consumer groups"     # query graph
/medium-to-markdown scrape                      # fetch new articles
/medium-to-markdown build-graph                 # run graphify + build HTML
/medium-to-markdown full --port 8080            # serve complete graph
/medium-to-markdown stop                        # kill server
```

**The skill is automatically active** when you open Claude Code from inside the cloned repo — Claude Code picks up `.claude/skills/` automatically.

**To install globally** (available in any project):

```bash
# macOS / Linux
mkdir -p ~/.claude/skills/medium-to-markdown
cp .claude/skills/medium-to-markdown/SKILL.md ~/.claude/skills/medium-to-markdown/SKILL.md
```

---

## Tech stack

| Library | Purpose |
|---|---|
| [Scrapling](https://github.com/D4Vinci/Scrapling) | Anti-bot browser automation (Patchright) + fast HTTP (curl_cffi) |
| [graphifyy](https://pypi.org/project/graphifyy/) | LLM-based knowledge graph extraction from markdown files |
| [vis-network](https://visjs.github.io/vis-network/) | Interactive force-directed graph visualization |
| [python-slugify](https://github.com/un33k/python-slugify) | Article title → safe filename |
| [requests](https://docs.python-requests.org/) | Image downloading |

---

## Limitations

- Only works with **public** reading lists (no login support)
- Infinite-scroll on large lists is slow — 1–3 minutes for 300+ articles
- Freedium quality varies — some articles may return thin content if the mirror has issues
- Knowledge graph quality depends on your graphify LLM configuration and article volume

---

## License

MIT
