"""
query_graph.py — search the knowledge graph, generate a focused subgraph HTML,
serve it on a local HTTP port with a random URL, auto-stop after TTL seconds.

Usage:
    python query_graph.py --query "spark shuffle"
    python query_graph.py --query "kafka airflow" --port 9090 --ttl 1800
    python query_graph.py --stop
"""

import argparse
import json
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

GRAPH_FILE = Path("graphify-out/graph.json")
SERVE_DIR  = Path("docs")
PID_FILE   = Path(".query_server.pid")

COMMUNITY_COLORS = [
    "#6C8EBF","#E8A838","#E05C5C","#5BB5AE","#57A85A",
    "#C9A227","#9B6BB5","#E87D8A","#A07850","#7B9EAE",
    "#4DA6FF","#FF8C42","#44BBA4","#E94F37","#8B5CF6",
    "#06D6A0","#FFB703","#FB5607","#3A86FF","#FF006E",
]


def parse_args():
    p = argparse.ArgumentParser(
        description="Query the knowledge graph and serve a focused interactive subgraph."
    )
    p.add_argument("--query", default="", help="Search query (topics, keywords, article names)")
    p.add_argument("--port",  type=int, default=8765, help="Local HTTP port to serve on (default: 8765)")
    p.add_argument("--ttl",   type=int, default=1800, help="Seconds before auto-stop (default: 1800)")
    p.add_argument("--stop",  action="store_true", help="Stop a running server")
    return p.parse_args()


def stop_server():
    if not PID_FILE.exists():
        print("No server running.")
        return
    pid = int(PID_FILE.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Stopped server (PID {pid})")
    except ProcessLookupError:
        print("Server already stopped.")
    PID_FILE.unlink(missing_ok=True)


def node_color(community_id):
    return COMMUNITY_COLORS[int(community_id) % len(COMMUNITY_COLORS)]


def search_graph(graph, query):
    """Return (matched_node_ids, matched_files_dict) sorted by relevance."""
    terms = [t.strip().lower() for t in query.replace(",", " ").split() if len(t.strip()) > 1]
    if not terms:
        return [], {}

    node_scores = {}
    for node in graph["nodes"]:
        label    = node.get("label", "").lower()
        src_file = node.get("source_file", "").lower()
        norm     = node.get("norm_label", "").lower()
        haystack = f"{label} {norm} {src_file}"
        score = 0
        for t in terms:
            if t in label:      score += 3
            elif t in norm:     score += 2
            elif t in src_file: score += 1
        if score > 0:
            node_scores[node["id"]] = score

    if not node_scores:
        return [], {}

    sorted_ids = sorted(node_scores, key=lambda x: -node_scores[x])

    id_to_node = {n["id"]: n for n in graph["nodes"]}
    matched_files = {}
    for nid in sorted_ids:
        n  = id_to_node[nid]
        sf = n.get("source_file", "")
        url = n.get("source_url", "")
        if sf and sf not in matched_files:
            matched_files[sf] = {"url": url, "score": node_scores[nid]}

    return sorted_ids, matched_files


def build_subgraph(graph, matched_node_ids, max_nodes=120):
    """Expand matched nodes to include 1-hop neighbors, cap at max_nodes."""
    id_to_node  = {n["id"]: n for n in graph["nodes"]}
    matched_set = set(matched_node_ids[:max_nodes])

    neighbor_set = set()
    for edge in graph.get("edges", graph.get("links", [])):
        s, t = edge.get("source", ""), edge.get("target", "")
        if s in matched_set and t not in matched_set:
            neighbor_set.add(t)
        elif t in matched_set and s not in matched_set:
            neighbor_set.add(s)

    all_ids   = matched_set | set(list(neighbor_set)[:max(0, max_nodes - len(matched_set))])
    sub_nodes = [n for n in graph["nodes"] if n["id"] in all_ids]
    sub_edges = [e for e in graph.get("edges", graph.get("links", []))
                 if e.get("source") in all_ids and e.get("target") in all_ids]

    return sub_nodes, sub_edges


def make_html(query, sub_nodes, sub_edges, article_list):
    degrees   = [n.get("degree", 0) for n in sub_nodes]
    max_deg   = max(degrees) if degrees else 1
    min_deg   = min(degrees) if degrees else 0
    deg_range = max(max_deg - min_deg, 1)

    def inv_size(degree):
        norm = (degree - min_deg) / deg_range
        return round(12 + (1 - norm) * 26)

    nodes_js = []
    for n in sub_nodes:
        cid   = n.get("community", 0)
        color = node_color(cid)
        cname = n.get("community_name", f"Community {cid}")
        size  = inv_size(n.get("degree", 0))
        url   = n.get("source_url", "")
        label = n.get("label", n["id"])
        words = label.split()
        if len(label) > 20 and len(words) > 1:
            mid = len(words) // 2
            label = " ".join(words[:mid]) + "\n" + " ".join(words[mid:])
        nodes_js.append({
            "id": n["id"], "label": label[:60], "shape": "dot",
            "color": {
                "background": color, "border": color,
                "highlight":  {"background": "#ffffff", "border": color},
                "hover":      {"background": "#ffffff", "border": color},
            },
            "size": size, "borderWidth": 3 if size >= 28 else 2,
            "shadow": {"enabled": True, "color": color + "88", "size": max(8, size // 2), "x": 0, "y": 0},
            "font":  {"size": max(10, min(14, size // 3)), "color": "#ffffff",
                      "strokeWidth": 3, "strokeColor": "#0a0a14"},
            "title": n.get("label", n["id"]),
            "_community_name": cname,
            "_source_file": n.get("source_file", ""),
            "_source_url":  url,
            "_degree": n.get("degree", 0),
        })

    edges_js = []
    for e in sub_edges:
        conf  = e.get("confidence", "INFERRED")
        score = float(e.get("confidence_score", 0.7))
        edges_js.append({
            "from": e.get("source"), "to": e.get("target"),
            "title": e.get("relation", ""),
            "dashes": conf == "AMBIGUOUS",
            "width":  3 if conf == "EXTRACTED" else max(1.5, score * 2.5),
            "color":  {"color": "#3d4f7c", "highlight": "#7eb3ff", "hover": "#7eb3ff", "opacity": 0.85},
            "smooth": {"type": "continuous", "roundness": 0.2},
            "arrows": {"to": {"enabled": False}},
        })

    def file_to_title(sf):
        return Path(sf).stem.replace("-", " ").title()

    def article_card(sf, info):
        title = file_to_title(sf)
        url   = info.get("url", "")
        link  = f'<a href="{url}" target="_blank">Open on Medium ↗</a>' if url else ""
        return f'<div class="article-card"><div class="title">{title}</div>{link}</div>'

    articles_html = "".join(
        article_card(sf, info)
        for sf, info in sorted(article_list.items(), key=lambda x: -x[1].get("score", 0))
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Graph: {query}</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{
  background: #080c14; color: #d0d8e8;
  font-family: 'Inter', -apple-system, sans-serif;
  display: flex; height: 100vh; overflow: hidden;
}}
#graph {{ flex:1; background: radial-gradient(ellipse at center, #0d1529 0%, #080c14 100%); }}
#sidebar {{
  width: 320px;
  background: linear-gradient(180deg, #0e1628 0%, #0a1020 100%);
  border-left: 1px solid #1e2d4a;
  display: flex; flex-direction: column; overflow: hidden;
  box-shadow: -4px 0 24px rgba(0,0,0,0.4);
}}
#header {{ padding: 16px 18px 14px; border-bottom: 1px solid #1e2d4a; background: linear-gradient(135deg, #0f1e3a 0%, #0e1628 100%); }}
#header .label {{ font-size: 10px; color: #4a6fa5; text-transform: uppercase; letter-spacing: .12em; font-weight: 600; margin-bottom: 6px; }}
#header .query {{ font-size: 15px; color: #e8f0ff; font-weight: 600; line-height: 1.4; margin-bottom: 8px; }}
#header .stats {{ display: flex; gap: 12px; }}
#header .stat {{ font-size: 11px; color: #4a6fa5; background: #0a1628; padding: 3px 8px; border-radius: 20px; border: 1px solid #1e2d4a; }}
#info-panel {{ padding: 16px 18px; border-bottom: 1px solid #1e2d4a; min-height: 130px; }}
#info-panel .panel-label {{ font-size: 10px; color: #4a6fa5; text-transform: uppercase; letter-spacing: .12em; font-weight: 600; margin-bottom: 10px; }}
#info-content {{ font-size: 13px; color: #b0bcd4; line-height: 1.6; }}
#info-content .empty {{ color: #2a3a5a; font-style: italic; font-size: 12px; }}
#info-content .node-title {{ font-size: 14px; font-weight: 600; color: #e8f0ff; margin-bottom: 5px; line-height: 1.4; }}
#info-content .community-tag {{ display: inline-block; font-size: 10px; color: #4a6fa5; background: #0a1628; border: 1px solid #1e2d4a; border-radius: 20px; padding: 2px 8px; margin-bottom: 10px; }}
#info-content .open-link {{ display: inline-flex; align-items: center; gap: 5px; color: #4a8eff; font-size: 12px; font-weight: 500; text-decoration: none; padding: 5px 12px; background: #0a1628; border: 1px solid #1e3a6a; border-radius: 6px; transition: all 0.2s; }}
#info-content .open-link:hover {{ background: #1e3a6a; color: #7eb3ff; }}
#articles-wrap {{ display:flex; flex-direction:column; flex:1; overflow:hidden; }}
#articles-header {{ padding: 12px 18px 8px; font-size: 10px; color: #4a6fa5; text-transform: uppercase; letter-spacing: .12em; font-weight: 600; border-bottom: 1px solid #1e2d4a; }}
#articles-list {{ flex:1; overflow-y:auto; padding: 10px 12px; }}
#articles-list::-webkit-scrollbar {{ width: 4px; }}
#articles-list::-webkit-scrollbar-thumb {{ background: #1e2d4a; border-radius: 4px; }}
.article-card {{ margin-bottom: 8px; padding: 10px 12px; background: #0a1020; border-radius: 8px; border: 1px solid #1a2a42; border-left: 3px solid #2a5aaa; transition: all 0.2s; }}
.article-card:hover {{ border-color: #4a8eff; background: #0e1830; }}
.article-card .title {{ color: #c8d8f0; font-size: 12px; line-height: 1.5; margin-bottom: 5px; font-weight: 500; }}
.article-card a {{ color: #4a8eff; font-size: 11px; text-decoration: none; font-weight: 500; }}
.article-card a:hover {{ color: #7eb3ff; }}
</style>
</head>
<body>
<div id="graph"></div>
<div id="sidebar">
  <div id="header">
    <div class="label">Knowledge Graph Query</div>
    <div class="query">"{query}"</div>
    <div class="stats">
      <span class="stat">{len(sub_nodes)} nodes</span>
      <span class="stat">{len(sub_edges)} edges</span>
      <span class="stat">{len(article_list)} articles</span>
    </div>
  </div>
  <div id="info-panel">
    <div class="panel-label">Selected Node</div>
    <div id="info-content"><span class="empty">Click a node to see details</span></div>
  </div>
  <div id="articles-wrap">
    <div id="articles-header">Matched Articles ({len(article_list)})</div>
    <div id="articles-list">{articles_html}</div>
  </div>
</div>
<script>
const RAW_NODES = {json.dumps(nodes_js, ensure_ascii=False)};
const RAW_EDGES = {json.dumps(edges_js, ensure_ascii=False)};
const nodesDS = new vis.DataSet(RAW_NODES);
const edgesDS = new vis.DataSet(RAW_EDGES.map((e,i) => ({{...e, id:i}})));
const container = document.getElementById('graph');
const network = new vis.Network(container, {{nodes:nodesDS, edges:edgesDS}}, {{
  nodes: {{ shape:'dot', borderWidth:2, borderWidthSelected:4,
    chosen: {{ node: (v,id,sel,hov) => {{ if(sel||hov){{ v.size+=6; v.borderWidth=4; }} }} }} }},
  edges: {{ smooth:{{type:'continuous',roundness:0.2}}, selectionWidth:3, hoverWidth:2 }},
  physics: {{
    solver:'forceAtlas2Based',
    forceAtlas2Based:{{ gravitationalConstant:-80, centralGravity:0.005, springLength:160, springConstant:0.06, damping:0.9, avoidOverlap:0.5 }},
    stabilization:{{iterations:180, fit:true}},
  }},
  interaction:{{ hover:true, tooltipDelay:80, hideEdgesOnDrag:true, keyboard:{{enabled:true}} }},
}});
function esc(s) {{ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}
function showInfo(nodeId) {{
  const n = nodesDS.get(nodeId);
  if (!n) return;
  const link = n._source_url ? `<a href="${{n._source_url}}" target="_blank" class="open-link">Open on Medium ↗</a>` : '';
  document.getElementById('info-content').innerHTML = `<div class="node-title">${{esc(n.title||n.label)}}</div><div class="community-tag">${{esc(n._community_name)}}</div><br>${{link}}`;
}}
let hoveredNode = null;
network.on('hoverNode', p => {{ hoveredNode = p.node; container.style.cursor='pointer'; }});
network.on('blurNode',  () => {{ hoveredNode = null; container.style.cursor='default'; }});
network.on('click', p => {{ if(p.nodes.length>0) showInfo(p.nodes[0]); }});
</script>
</body>
</html>"""


def start_server(port, serve_dir, ttl_seconds):
    if PID_FILE.exists():
        stop_server()

    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--directory", str(serve_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    PID_FILE.write_text(str(proc.pid))

    def _killer():
        time.sleep(ttl_seconds)
        try:
            proc.terminate()
            print(f"\n[graph-query] Server auto-stopped after {ttl_seconds // 60} minutes.")
        except Exception:
            pass
        PID_FILE.unlink(missing_ok=True)

    threading.Thread(target=_killer, daemon=True).start()
    return proc.pid


def main():
    args = parse_args()

    if args.stop:
        stop_server()
        return

    if not args.query.strip():
        print("Error: --query is required.")
        print("Example: python query_graph.py --query 'spark shuffle'")
        sys.exit(1)

    if not GRAPH_FILE.exists():
        print(f"Error: {GRAPH_FILE} not found.")
        print("Run `graphify update raw/` then `python build_full_graph.py` first.")
        sys.exit(1)

    graph = json.loads(GRAPH_FILE.read_text(encoding="utf-8"))

    matched_ids, matched_files = search_graph(graph, args.query)

    if not matched_ids:
        print(f"No articles matched '{args.query}'. Try broader or different keywords.")
        sys.exit(0)

    sub_nodes, sub_edges = build_subgraph(graph, matched_ids)

    token   = secrets.token_hex(6)
    out_dir = SERVE_DIR / token
    out_dir.mkdir(parents=True, exist_ok=True)
    html    = make_html(args.query, sub_nodes, sub_edges, matched_files)
    (out_dir / "index.html").write_text(html, encoding="utf-8")

    SERVE_DIR.mkdir(exist_ok=True)
    pid = start_server(args.port, SERVE_DIR, args.ttl)

    url = f"http://localhost:{args.port}/{token}/"
    print(f"\n[graph-query] Query:   '{args.query}'")
    print(f"[graph-query] Matched: {len(matched_files)} articles · {len(sub_nodes)} nodes · {len(sub_edges)} edges")
    print(f"[graph-query] URL:     {url}")
    print(f"[graph-query] Stops:   in {args.ttl // 60} minutes (PID {pid})")
    print(f"[graph-query] Stop:    python query_graph.py --stop")


if __name__ == "__main__":
    main()
