"""
build_full_graph.py — generate the full interactive knowledge graph HTML
from graphify-out/graph.json and graphify-out/graph_labels.json.

Run this after `graphify update raw/` to regenerate the graph viewer.

Output:
  graphify-out/graph.html   — open locally or host via GitHub Pages
  docs/index.html           — GitHub Pages entry point (same file)

Usage:
    python build_full_graph.py
"""

import json
from pathlib import Path

GRAPH_FILE  = Path("graphify-out/graph.json")
LABELS_FILE = Path("graphify-out/graph_labels.json")
OUT_FILES   = [Path("graphify-out/graph.html"), Path("docs/index.html")]

COMMUNITY_COLORS = [
    "#6C8EBF","#E8A838","#E05C5C","#5BB5AE","#57A85A",
    "#C9A227","#9B6BB5","#E87D8A","#A07850","#7B9EAE",
    "#4DA6FF","#FF8C42","#44BBA4","#E94F37","#8B5CF6",
    "#06D6A0","#FFB703","#FB5607","#3A86FF","#FF006E",
]


def node_color(community_id):
    return COMMUNITY_COLORS[int(community_id) % len(COMMUNITY_COLORS)]


def inv_size(degree, min_deg, deg_range):
    norm = (degree - min_deg) / max(deg_range, 1)
    return round(12 + (1 - norm) * 26)


def build():
    if not GRAPH_FILE.exists():
        print(f"Error: {GRAPH_FILE} not found.")
        print("Run `graphify update raw/` first to build the graph.")
        return

    graph   = json.loads(GRAPH_FILE.read_text(encoding="utf-8"))
    labels  = json.loads(LABELS_FILE.read_text(encoding="utf-8")) if LABELS_FILE.exists() else {}

    url_map   = {n["id"]: (n.get("source_url") or "") for n in graph["nodes"]}
    label_map = {int(k): v for k, v in labels.items()}

    raw_nodes = graph["nodes"]
    raw_edges = graph.get("links", graph.get("edges", []))

    degrees   = [n.get("degree", 0) for n in raw_nodes]
    max_deg   = max(degrees) if degrees else 1
    min_deg   = min(degrees) if degrees else 0

    nodes_js = []
    for n in raw_nodes:
        cid    = n.get("community", 0)
        color  = node_color(cid)
        cname  = label_map.get(int(cid), f"Community {cid}")
        degree = n.get("degree", 0)
        size   = inv_size(degree, min_deg, max_deg - min_deg)
        url    = url_map.get(n["id"], "")
        label  = n.get("label", n["id"])
        words  = label.split()
        if len(label) > 22 and len(words) > 1:
            mid = len(words) // 2
            label = " ".join(words[:mid]) + "\n" + " ".join(words[mid:])
        nodes_js.append({
            "id":    n["id"],
            "label": label[:60],
            "shape": "dot",
            "color": {
                "background": color, "border": color,
                "highlight":  {"background": "#ffffff", "border": color},
                "hover":      {"background": "#ffffff", "border": color},
            },
            "size":        size,
            "borderWidth": 3 if size >= 28 else 2,
            "shadow":      {"enabled": True, "color": color + "88", "size": max(8, size // 2), "x": 0, "y": 0},
            "font":        {"size": max(10, min(14, size // 3)), "color": "#ffffff",
                            "strokeWidth": 3, "strokeColor": "#0a0a14"},
            "title":           n.get("label", n["id"]),
            "_community":      cid,
            "_community_name": cname,
            "_source_file":    n.get("source_file", ""),
            "_source_url":     url,
            "_file_type":      n.get("file_type", "document"),
            "_degree":         degree,
        })

    edges_js = []
    for e in raw_edges:
        conf  = e.get("confidence", "INFERRED")
        score = float(e.get("confidence_score", e.get("weight", 0.7)))
        edges_js.append({
            "from":   e.get("source"),
            "to":     e.get("target"),
            "title":  e.get("relation", ""),
            "dashes": conf == "AMBIGUOUS",
            "width":  3 if conf == "EXTRACTED" else max(1.5, score * 2.5),
            "color":  {"color": "#3d4f7c", "highlight": "#7eb3ff", "hover": "#7eb3ff", "opacity": 0.85},
            "smooth": {"type": "continuous", "roundness": 0.2},
            "arrows": {"to": {"enabled": False}},
        })

    # Article index for Q&A search
    article_index = {}
    for n in graph["nodes"]:
        sf  = n.get("source_file", "")
        url = n.get("source_url", "")
        lbl = n.get("label", "").lower()
        if sf not in article_index:
            article_index[sf] = {"url": url, "labels": []}
        article_index[sf]["labels"].append(lbl)

    def file_to_title(sf):
        return Path(sf).stem.replace("-", " ").title()

    article_list_js = json.dumps([
        {"title": file_to_title(sf), "url": info["url"],
         "labels": info["labels"], "file": sf}
        for sf, info in article_index.items()
    ], ensure_ascii=False)

    # Top keywords sorted by degree (for quick-pick tags)
    seen = set()
    keywords = []
    for n in sorted(raw_nodes, key=lambda x: x.get("degree", 0), reverse=True):
        lbl = n.get("label", "").strip()
        key = lbl.lower()
        if lbl and key not in seen and 2 < len(lbl) < 60:
            seen.add(key)
            keywords.append(lbl)
    keywords_js = json.dumps(keywords[:300], ensure_ascii=False)

    total_nodes    = len(nodes_js)
    total_edges    = len(edges_js)
    total_articles = len(article_index)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Knowledge Graph — medium-to-markdown</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{
  height: 100%; width: 100%; overflow: hidden;
  background: #111;
  font-family: 'Inter', -apple-system, sans-serif;
  color: #e4e4e4;
  -webkit-font-smoothing: antialiased;
}}
#graph-canvas {{ position: fixed; inset: 0; background: #111; }}

/* Top bar */
#topbar {{
  position: fixed; top: 0; left: 0; right: 0; z-index: 100;
  height: 48px; display: flex; align-items: center;
  padding: 0 20px; gap: 16px;
  background: #111; border-bottom: 1px solid #222;
}}
#topbar .brand {{ font-size: 13px; font-weight: 600; color: #e4e4e4; letter-spacing: -0.01em; flex-shrink: 0; }}
#topbar .sep {{ flex: 1; }}
#topbar .stats {{ display: flex; align-items: center; gap: 16px; }}
#topbar .stat {{ font-size: 12px; color: #555; }}
#topbar .stat span {{ color: #999; font-weight: 500; }}
#search-btn {{
  display: flex; align-items: center; gap: 6px;
  background: #1e1e1e; border: 1px solid #2e2e2e; border-radius: 6px;
  color: #999; font-size: 12px; font-family: inherit;
  padding: 5px 12px; cursor: pointer; transition: border-color 0.15s, color 0.15s;
}}
#search-btn:hover {{ border-color: #444; color: #e4e4e4; }}
#search-btn kbd {{
  background: #2a2a2a; border: 1px solid #333; border-radius: 3px;
  padding: 1px 5px; font-size: 10px; color: #666; font-family: inherit;
}}

/* Node card */
#node-card {{
  position: fixed; bottom: 20px; left: 20px; z-index: 100;
  width: 280px; background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 8px;
  padding: 16px; opacity: 0; pointer-events: none;
  transform: translateY(8px); transition: opacity 0.15s, transform 0.15s;
}}
#node-card.visible {{ opacity: 1; pointer-events: all; transform: translateY(0); }}
#node-card-close {{
  position: absolute; top: 10px; right: 10px; width: 20px; height: 20px;
  background: none; border: none; color: #555; font-size: 13px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  border-radius: 4px; transition: background 0.1s, color 0.1s;
}}
#node-card-close:hover {{ background: #2a2a2a; color: #e4e4e4; }}
.nc-meta {{ font-size: 11px; color: #555; margin-bottom: 6px; display: flex; align-items: center; gap: 6px; }}
.nc-dot {{ width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }}
#nc-title {{ font-size: 14px; font-weight: 500; color: #e4e4e4; line-height: 1.4; margin-bottom: 12px; }}
#nc-degree {{ font-size: 11px; color: #555; margin-bottom: 12px; }}
#nc-link {{
  display: flex; align-items: center; justify-content: center; gap: 5px;
  width: 100%; padding: 7px;
  background: #222; border: 1px solid #333; border-radius: 6px;
  color: #aaa; font-size: 12px; font-family: inherit;
  text-decoration: none; transition: border-color 0.15s, color 0.15s;
}}
#nc-link:hover {{ border-color: #555; color: #e4e4e4; }}

/* Search panel */
#search-overlay {{
  position: fixed; inset: 0; z-index: 200;
  background: rgba(0,0,0,0); pointer-events: none; transition: background 0.2s;
}}
#search-overlay.open {{ background: rgba(0,0,0,0.6); pointer-events: all; }}
#search-panel {{
  position: fixed; top: 0; right: 0; bottom: 0; z-index: 300; width: 360px;
  background: #161616; border-left: 1px solid #222;
  display: flex; flex-direction: column;
  transform: translateX(100%); transition: transform 0.2s ease;
}}
#search-panel.open {{ transform: translateX(0); }}
#sp-header {{
  padding: 14px 16px; border-bottom: 1px solid #222;
  flex-shrink: 0; display: flex; align-items: center; gap: 10px;
}}
#sp-header svg {{ color: #555; flex-shrink: 0; }}
#search-input {{
  flex: 1; background: none; border: none;
  color: #e4e4e4; font-size: 13px; font-family: inherit; outline: none;
}}
#search-input::placeholder {{ color: #444; }}
#search-close {{
  background: none; border: none; color: #555; font-size: 16px;
  cursor: pointer; padding: 2px 4px; border-radius: 4px; transition: color 0.1s;
}}
#search-close:hover {{ color: #e4e4e4; }}
#search-results {{ flex: 1; overflow-y: auto; padding: 8px; }}
#search-results::-webkit-scrollbar {{ width: 3px; }}
#search-results::-webkit-scrollbar-thumb {{ background: #2a2a2a; border-radius: 2px; }}
.search-hint {{ padding: 12px 8px 6px; font-size: 11px; color: #555; }}
.keywords-wrap {{ padding: 0 8px 12px; display: flex; flex-wrap: wrap; gap: 5px; }}
.kw-tag {{
  font-size: 11px; color: #888; background: #1e1e1e; border: 1px solid #2a2a2a;
  border-radius: 4px; padding: 3px 9px; cursor: pointer;
  transition: border-color 0.1s, color 0.1s; white-space: nowrap;
}}
.kw-tag:hover {{ border-color: #444; color: #e4e4e4; }}
.search-count {{ font-size: 11px; color: #555; padding: 6px 8px 4px; }}
.article-card {{ padding: 10px 12px; border-radius: 6px; transition: background 0.1s; }}
.article-card:hover {{ background: #1e1e1e; }}
.ac-title {{ font-size: 12px; font-weight: 500; color: #ccc; line-height: 1.5; margin-bottom: 4px; }}
.ac-link {{ font-size: 11px; color: #555; text-decoration: none; transition: color 0.1s; }}
.ac-link:hover {{ color: #aaa; }}
</style>
</head>
<body>

<div id="graph-canvas"></div>

<div id="topbar">
  <div class="brand">medium-to-markdown · Knowledge Graph</div>
  <div class="sep"></div>
  <div class="stats">
    <div class="stat"><span>{total_nodes}</span> nodes</div>
    <div class="stat"><span>{total_edges}</span> edges</div>
    <div class="stat"><span>{total_articles}</span> articles</div>
  </div>
  <button id="search-btn" onclick="openSearch()">
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
    Search
    <kbd>/</kbd>
  </button>
</div>

<div id="node-card">
  <button id="node-card-close" onclick="closeCard()">✕</button>
  <div class="nc-meta">
    <div class="nc-dot" id="nc-dot"></div>
    <span id="nc-community-name"></span>
  </div>
  <div id="nc-title"></div>
  <div id="nc-degree"></div>
  <a id="nc-link" href="#" target="_blank" style="display:none">Open on Medium ↗</a>
</div>

<div id="search-overlay" onclick="closeSearch()"></div>

<div id="search-panel">
  <div id="sp-header">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
    <input id="search-input" placeholder="Search articles and topics..." autocomplete="off" />
    <button id="search-close" onclick="closeSearch()">✕</button>
  </div>
  <div id="search-results"></div>
</div>

<script>
const RAW_NODES = {json.dumps(nodes_js, ensure_ascii=False)};
const RAW_EDGES = {json.dumps(edges_js, ensure_ascii=False)};
const ARTICLE_INDEX = {article_list_js};
const KEYWORDS = {keywords_js};

const nodesDS = new vis.DataSet(RAW_NODES);
const edgesDS = new vis.DataSet(RAW_EDGES.map((e,i) => ({{...e, id:i}})));
const container = document.getElementById('graph-canvas');
const network = new vis.Network(container, {{nodes:nodesDS, edges:edgesDS}}, {{
  nodes: {{
    shape: 'dot', borderWidth: 2, borderWidthSelected: 4,
    chosen: {{ node: (v,id,sel,hov) => {{ if(sel||hov){{ v.size+=5; v.borderWidth=4; }} }} }},
  }},
  edges: {{
    smooth: {{ type: 'continuous', roundness: 0.2 }},
    selectionWidth: 3, hoverWidth: 2,
  }},
  physics: {{
    solver: 'forceAtlas2Based',
    forceAtlas2Based: {{
      gravitationalConstant: -50, centralGravity: 0.005,
      springLength: 160, springConstant: 0.08, damping: 0.4, avoidOverlap: 0.5,
    }},
    stabilization: {{ enabled: false }}, minVelocity: 0.1, maxVelocity: 50,
  }},
  interaction: {{
    hover: true, tooltipDelay: 80, hideEdgesOnDrag: true,
    navigationButtons: false, keyboard: {{ enabled: false }},
  }},
}});

function esc(s) {{ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}

function showNodeCard(nodeId) {{
  const n = nodesDS.get(nodeId);
  if (!n) return;
  const color = n.color?.background || '#555';
  document.getElementById('nc-dot').style.background = color;
  document.getElementById('nc-community-name').textContent = n._community_name || ('Community ' + n._community);
  document.getElementById('nc-title').textContent = (n.title || n.label || '').replace(/\\n/g,' ');
  document.getElementById('nc-degree').textContent = n._degree + ' connection' + (n._degree !== 1 ? 's' : '');
  const link = document.getElementById('nc-link');
  if (n._source_url) {{ link.href = n._source_url; link.style.display = 'flex'; }}
  else {{ link.style.display = 'none'; }}
  document.getElementById('node-card').classList.add('visible');
}}

function closeCard() {{
  document.getElementById('node-card').classList.remove('visible');
  network.unselectAll();
}}

network.on('click', p => {{
  if (p.nodes.length > 0) showNodeCard(p.nodes[0]);
  else closeCard();
}});
container.addEventListener('mousemove', () => container.style.cursor = 'default');
network.on('hoverNode', () => container.style.cursor = 'pointer');
network.on('blurNode',  () => container.style.cursor = 'default');

function openSearch() {{
  document.getElementById('search-panel').classList.add('open');
  document.getElementById('search-overlay').classList.add('open');
  setTimeout(() => document.getElementById('search-input').focus(), 200);
}}
function closeSearch() {{
  document.getElementById('search-panel').classList.remove('open');
  document.getElementById('search-overlay').classList.remove('open');
}}

document.addEventListener('keydown', e => {{
  if (e.key === '/' && !e.target.matches('input')) {{ e.preventDefault(); openSearch(); }}
  if (e.key === 'Escape') {{ closeSearch(); closeCard(); }}
}});

function renderKeywords() {{
  const out = document.getElementById('search-results');
  out.innerHTML =
    '<div class="search-hint">Topics — click to search</div>' +
    '<div class="keywords-wrap">' +
    KEYWORDS.map(k => `<span class="kw-tag" onclick="selectKeyword(${{JSON.stringify(k)}})">${{esc(k)}}</span>`).join('') +
    '</div>';
}}

function selectKeyword(kw) {{
  const input = document.getElementById('search-input');
  input.value = kw;
  input.dispatchEvent(new Event('input'));
}}

renderKeywords();

document.getElementById('search-input').addEventListener('input', e => {{
  const q = e.target.value.trim().toLowerCase();
  const out = document.getElementById('search-results');
  if (!q) {{ renderKeywords(); return; }}
  const terms = q.split(/\\s+/);
  const scored = ARTICLE_INDEX.map(a => {{
    let score = 0;
    const hay = a.labels.join(' ') + ' ' + a.title.toLowerCase();
    for (const t of terms) if (hay.includes(t)) score += a.title.toLowerCase().includes(t) ? 3 : 1;
    return {{ ...a, score }};
  }}).filter(a => a.score > 0).sort((a,b) => b.score - a.score).slice(0, 30);

  if (!scored.length) {{ out.innerHTML = '<div class="search-hint">No results — try a different term</div>'; return; }}
  out.innerHTML = `<div class="search-count">${{scored.length}} article${{scored.length>1?'s':''}}</div>` +
    scored.map(a => `<div class="article-card">
      <div class="ac-title">${{esc(a.title)}}</div>
      ${{a.url ? `<a class="ac-link" href="${{a.url}}" target="_blank">Open on Medium ↗</a>` : ''}}
    </div>`).join('');
}});
</script>
</body>
</html>"""

    for out in OUT_FILES:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"Written: {out}  ({out.stat().st_size // 1024} KB)")

    print(f"\nGraph: {total_nodes} nodes · {total_edges} edges · {total_articles} articles")


if __name__ == "__main__":
    build()
