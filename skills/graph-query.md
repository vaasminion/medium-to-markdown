---
name: graph-query
description: Full pipeline for the medium-to-markdown knowledge base — scrape new articles, build/update knowledge graph, query it, and serve a focused interactive subgraph on a local port.
trigger: /graph-query
---

# /graph-query

Single entry point for the **medium-to-markdown** knowledge pipeline. It can:

1. **Scrape** new articles from your Medium reading list (paywall bypassed via Freedium)
2. **Build / update** the knowledge graph from scraped articles (via graphify)
3. **Query** the graph and serve a focused interactive subgraph on a local port
4. **Stop** a running server

---

## Project Overview

A complete knowledge management system built on top of any Medium reading list:

- Scrapes articles using Scrapling + Freedium paywall bypass
- Saves each article as a markdown file in `raw/` with YAML frontmatter
- Downloads article images to `raw/assets/`
- Builds a knowledge graph using [graphify](https://pypi.org/project/graphifyy/) (nodes, edges, topic communities)
- Incremental scraping — only new articles are fetched (tracked via `state.json`)
- Incremental graph updates — only new articles are LLM-extracted (cached in `graphify-out/cache/`)

**Key files:**

| File | Purpose |
|------|---------|
| `scraper.py` | Scrapes Medium reading list → `raw/*.md` |
| `build_full_graph.py` | Builds full interactive graph HTML from `graphify-out/graph.json` |
| `query_graph.py` | Queries graph → focused subgraph HTML → local HTTP server |
| `graphify-out/graph.html` | Full interactive graph (all articles) |
| `graphify-out/graph.json` | GraphRAG-ready JSON |
| `raw/*.md` | Scraped articles |
| `state.json` | Scraper state — which URLs are already done |
| `docs/index.html` | GitHub Pages entry point (same as graph.html) |

---

## Usage

```
/graph-query "spark shuffle optimization"          # query + serve
/graph-query "kafka airflow" --port 9090           # custom port
/graph-query "dbt modeling" --ttl 20               # 20 min auto-stop
/graph-query --scrape                              # scrape new articles
/graph-query --build-graph                         # rebuild knowledge graph
/graph-query --stop                                # stop running server
/graph-query --full --port 8080                    # serve full graph
```

---

## What You Must Do When Invoked

### Step 1 — Detect intent

| Intent | Trigger | Action |
|--------|---------|--------|
| Query graph | keywords, search phrase, "find articles about" | Steps 2–5 |
| Scrape new articles | "scrape", "fetch new", "update articles" | Step 6 |
| Rebuild graph | "rebuild graph", "update graph", "re-run graphify" | Step 7 |
| Stop server | "stop", "--stop" | Step 8 |
| Serve full graph | "--full" | Step 9 |

If the user types keywords with no flags → default to **query mode**.

---

### Step 2 — Parse arguments (query mode)

Extract:
- `QUERY`: the search string
- `PORT`: from `--port N`, or default to `8765`
- `TTL`: from `--ttl N` (minutes), default 30 → convert to seconds

---

### Step 3 — Find the project directory

Check in order:
1. Current working directory (look for `query_graph.py`)
2. `~/medium-to-markdown/`

If not found, tell the user:
> "Repo not found. Clone it: `git clone https://github.com/vaasminion/medium-to-markdown.git`"

---

### Step 4 — Run the query

```bash
cd "PROJECT_DIR"
python query_graph.py --query "QUERY" --port PORT --ttl TTL_SECONDS
```

---

### Step 5 — Report to user

```
Graph ready — N articles matched "QUERY"

URL: http://localhost:PORT/<TOKEN>/
Auto-stops in: TTL minutes

Click any node → see article title → "Open on Medium ↗"
```

If 0 results: suggest synonyms or related terms from the scraped corpus.

---

### Step 6 — Scrape new articles

```bash
cd "PROJECT_DIR"
source venv/bin/activate
python scraper.py
```

Reads `state.json` — only fetches articles not yet scraped.
After completion: "Want to rebuild the graph? Run `/graph-query --build-graph`."

---

### Step 7 — Rebuild / update knowledge graph

Tell the user that only new articles will be LLM-extracted (cache handles the rest), then run:

```bash
cd "PROJECT_DIR"
graphify update raw/
python build_full_graph.py
```

Then optionally commit and push:

```bash
git add graphify-out/ docs/
git commit -m "Update knowledge graph"
git push
```

---

### Step 8 — Stop server

```bash
cd "PROJECT_DIR"
python query_graph.py --stop
```

---

### Step 9 — Serve full graph

```bash
cd "PROJECT_DIR"
python -m http.server PORT --directory docs
```

URL: `http://localhost:PORT/`
Serves the complete graph of all articles with the search panel.
