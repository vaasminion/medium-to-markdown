---
name: medium-to-markdown
description: Full pipeline for the medium-to-markdown knowledge base — scrape new articles, build/update knowledge graph, query it, and serve a focused interactive subgraph on a local port.
version: 1.0.0
---

# /medium-to-markdown

Manages your Medium reading list knowledge base end-to-end from a single slash command.

**What it does:**
- **Scrape** new articles from your reading list via Freedium paywall bypass
- **Build / update** a knowledge graph from scraped articles using graphify
- **Query** the graph with keywords → focused interactive subgraph served locally
- **Serve** the full graph on a local port
- **Stop** any running server

---

## Inputs needed

- Repo cloned and set up (see README)
- Python venv activated with `pip install -r requirements.txt` done
- `scrapling install` done (for scraping)
- `READING_LIST_URL` set in `.env` (for scraping)

---

## Detect intent from user message

| What user says | Mode |
|----------------|------|
| keywords / "show me X" / "find articles about X" / any search phrase | **query** |
| "scrape", "fetch new", "update articles" | **scrape** |
| "rebuild graph", "update graph", "re-run graphify" | **build-graph** |
| "stop", "kill server" | **stop** |
| "full graph", "all articles", "open graph", "--full" | **full** |

If intent is unclear, default to **query** mode and ask for a search term.

---

## Workflow

### Mode: query

1. Extract:
   - `QUERY` — keywords from user message
   - `PORT` — from `--port N`, or ask if missing
   - `TTL` — from `--ttl N` (minutes), default 30 → convert to seconds

2. Find project dir — check in order:
   - Current working directory (look for `query_graph.py`)
   - `~/medium-to-markdown/`
   - If not found: tell user to clone `https://github.com/vaasminion/medium-to-markdown.git`

3. Run:
   ```bash
   cd <PROJECT_DIR>
   source venv/bin/activate
   python query_graph.py --query "<QUERY>" --port <PORT> --ttl <TTL_SECONDS>
   ```

4. Parse output for: matched article count, URL, auto-stop time.

5. Report:
   ```
   Graph ready — N articles matched "QUERY"

   URL: http://localhost:PORT/TOKEN/
   Auto-stops in: TTL minutes

   Click any node → see article title → Open on Medium ↗
   ```

   If 0 results: suggest synonyms. Remind user of topics in their scraped corpus (check `raw/` filenames for themes).

---

### Mode: scrape

1. Find project dir.
2. Run:
   ```bash
   cd <PROJECT_DIR>
   source venv/bin/activate
   python scraper.py
   ```
3. Report: how many new articles were scraped.
4. Ask: "Graph is now out of date — run `/medium-to-markdown build-graph` to update it?"

---

### Mode: build-graph

1. Find project dir.
2. Tell user: "Only new articles will be LLM-extracted — existing ones use the graphify cache."
3. Run graphify on the raw folder:
   ```bash
   cd <PROJECT_DIR>
   graphify update raw/
   ```
4. After graphify completes, generate the HTML:
   ```bash
   python build_full_graph.py
   ```
5. Optionally commit and push:
   ```bash
   git add graphify-out/ docs/
   git commit -m "Update knowledge graph"
   git push
   ```
6. Report: updated node/edge/article counts from `build_full_graph.py` output.

---

### Mode: stop

1. Find project dir.
2. Run:
   ```bash
   cd <PROJECT_DIR>
   python query_graph.py --stop
   ```
3. Confirm server stopped.

---

### Mode: full

1. Find project dir.
2. Get `PORT` from user (or use `8080` as default).
3. Run:
   ```bash
   cd <PROJECT_DIR>
   python -m http.server <PORT> --directory docs
   ```
4. Report: `http://localhost:<PORT>/`
5. Note: serves the complete graph of all articles with the keyword search panel.

---

## Guardrails

- Never delete `state.json` or `raw/` — they are the source of truth
- Never force-push to main
- If `--stop` finds no running server, just report "No server running"
- Do not re-scrape articles already in `state.json`

## Failure handling

| Failure | Response |
|---------|----------|
| Repo not found | Tell user to clone and set up the repo |
| Port in use | Ask user to pick a different port |
| 0 query results | Suggest broader keywords; check `raw/` for covered topics |
| scraper.py fails | Likely bot detection — wait 60s and retry, or check Freedium mirror URL in `.env` |
| graphify not found | `pip install graphifyy` |

---

## Examples

```
/medium-to-markdown "spark shuffle"
→ query mode — ask for port, serve focused subgraph

/medium-to-markdown scrape
→ fetch new articles from reading list

/medium-to-markdown build-graph
→ run graphify + build_full_graph.py + push

/medium-to-markdown full --port 8080
→ serve complete graph on port 8080

/medium-to-markdown stop
→ kill running server
```
