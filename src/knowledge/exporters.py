"""Writing a graph document (from `lib.graph_data`) in formats other tools read. Deterministic.

- json: this tool's own format (knowledge-graph/1), the same document the viewer embeds.
- cytoscape: {elements: {nodes, edges}} for Cytoscape.js and Cytoscape desktop.
- graphml: for Gephi, yEd and networkx; topics, centrality and validity windows as attributes.
- csv: one row per relation, node_1,node_2,edge,relation,... (the original notebook's shape, extended).
- obsidian: a vault folder: one note per concept with [[wikilinks]], a note per topic, a gaps note,
  and a Canvas map of the main topics.
- canvas: a single Obsidian Canvas (JSON Canvas 1.0) file.
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
import re
from xml.sax.saxutils import escape, quoteattr

FORMATS = ("json", "cytoscape", "graphml", "csv", "obsidian", "canvas")


def write(data: dict, fmt: str, out: str | None) -> dict:
    base = f"knowledge-{data['graph']}"
    default = {"json": f"{base}.json", "cytoscape": f"{base}.cyjs", "graphml": f"{base}.graphml",
               "csv": f"{base}.csv", "obsidian": f"{base}-vault", "canvas": f"{base}.canvas"}[fmt]
    target = out or default
    files = []
    if fmt == "obsidian":
        files = obsidian(data, target)
    else:
        body = {"json": lambda: json.dumps(data, indent=1, ensure_ascii=False), "cytoscape": lambda: cytoscape(data),
                "graphml": lambda: graphml(data), "csv": lambda: to_csv(data), "canvas": lambda: canvas(data)}[fmt]()
        with open(target, "w", encoding="utf-8", newline="") as fh:
            fh.write(body)
        files = [os.path.abspath(target)]
    return {"format": fmt, "path": os.path.abspath(target), "files": len(files),
            "nodes": data["counts"]["nodes"], "edges": data["counts"]["edges"]}


def _current(data: dict) -> list[dict]:
    return [e for e in data["edges"] if not e["valid_to"]]


def cytoscape(data: dict) -> str:
    nodes = [{"data": {k: v for k, v in n.items() if k != "passages"}} for n in data["nodes"]]
    edges = [{"data": {**e, "id": e["id"]}} for e in data["edges"]]
    edges += [{"data": {"id": f"p-{i}", "source": p["source"], "target": p["target"],
                        "relation": "contextual_proximity", "weight": p["count"]}}
              for i, p in enumerate(data["proximity"])]
    return json.dumps({"format_version": "1.0", "generated_by": "knowledge", "data": {"name": data["graph"]},
                       "elements": {"nodes": nodes, "edges": edges}}, indent=1, ensure_ascii=False)


def graphml(data: dict) -> str:
    node_keys = [("label", "string"), ("type", "string"), ("community", "int"), ("degree", "int"),
                 ("strength", "double"), ("betweenness", "double"), ("summary", "string")]
    edge_keys = [("relation", "string"), ("description", "string"), ("weight", "double"),
                 ("confidence", "double"), ("valid_from", "string"), ("valid_to", "string"), ("agent", "string")]
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">']
    for k, t in node_keys:
        out.append(f'  <key id="n_{k}" for="node" attr.name="{k}" attr.type="{t}"/>')
    for k, t in edge_keys:
        out.append(f'  <key id="e_{k}" for="edge" attr.name="{k}" attr.type="{t}"/>')
    out.append(f'  <graph id={quoteattr(data["graph"])} edgedefault="directed">')
    for n in data["nodes"]:
        out.append(f'    <node id={quoteattr(n["id"])}>')
        for k, _ in node_keys:
            if n.get(k) not in (None, ""):
                out.append(f'      <data key="n_{k}">{escape(str(n[k]))}</data>')
        out.append("    </node>")
    for e in data["edges"]:
        out.append(f'    <edge id={quoteattr(e["id"])} source={quoteattr(e["source"])} target={quoteattr(e["target"])}>')
        for k, _ in edge_keys:
            if e.get(k) not in (None, ""):
                out.append(f'      <data key="e_{k}">{escape(str(e[k]))}</data>')
        out.append("    </edge>")
    for i, p in enumerate(data["proximity"]):
        out.append(f'    <edge id="p-{i}" source={quoteattr(p["source"])} target={quoteattr(p["target"])}>'
                   f'<data key="e_relation">contextual_proximity</data><data key="e_weight">{p["count"]}</data></edge>')
    out += ["  </graph>", "</graphml>"]
    return "\n".join(out) + "\n"


def to_csv(data: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["node_1", "node_2", "edge", "relation", "weight", "confidence", "chunk_id", "agent", "valid_from",
                "valid_to"])
    for e in data["edges"]:
        w.writerow([e["source"], e["target"], e["description"], e["relation"], e["weight"], e["confidence"],
                    e["chunk"], e["agent"], e["valid_from"], e["valid_to"]])
    for p in data["proximity"]:
        w.writerow([p["source"], p["target"], "contextual proximity", "contextual_proximity", p["count"], "", "", "",
                    "", ""])
    return buf.getvalue()


# --- Obsidian -------------------------------------------------------------------------------

def _file_name(label: str) -> str:
    name = re.sub(r'[\\/:*?"<>|#^\[\]]', " ", label).strip()
    return re.sub(r"\s+", " ", name)[:120] or "untitled"


def _unique(names: dict) -> dict:
    """File names that differ by case only, or not at all, get a number so no note overwrites another."""
    seen: dict[str, int] = {}
    out = {}
    for key, name in names.items():
        low = name.lower()
        if low in seen:
            seen[low] += 1
            name = f"{name} ({seen[low]})"
        else:
            seen[low] = 1
        out[key] = name
    return out


def obsidian(data: dict, folder: str) -> list[str]:
    os.makedirs(os.path.join(folder, "Concepts"), exist_ok=True)
    os.makedirs(os.path.join(folder, "Topics"), exist_ok=True)
    names = _unique({n["id"]: _file_name(n["label"]) for n in data["nodes"]})
    topic_names = _unique({t["id"]: _file_name(t["label"]) for t in data["topics"]})
    topics = {t["id"]: t for t in data["topics"]}
    out_edges: dict[str, list] = {}
    in_edges: dict[str, list] = {}
    for e in data["edges"]:
        out_edges.setdefault(e["source"], []).append(e)
        in_edges.setdefault(e["target"], []).append(e)
    files = []
    for n in data["nodes"]:
        topic = topics.get(n["community"])
        lines = ["---", f"type: {n['type']}", f"degree: {n.get('degree', 0)}",
                 f"betweenness: {n.get('betweenness', 0)}"]
        if topic:
            lines.append(f'topic: "[[{topic_names[topic["id"]]}]]"')
        lines += [f"tags: [knowledge/{n['type']}]", "---", "", f"# {n['label']}", ""]
        if n.get("summary"):
            lines += [n["summary"], ""]
        if out_edges.get(n["id"]) or in_edges.get(n["id"]):
            lines += ["## Relations", ""]
            for e in out_edges.get(n["id"], []):
                lines.append(_relation_line(e, names.get(e["target"], e["target"]), "→"))
            for e in in_edges.get(n["id"], []):
                lines.append(_relation_line(e, names.get(e["source"], e["source"]), "←"))
            lines.append("")
        if n.get("passages"):
            lines += ["## Evidence", ""]
            for p in n["passages"]:
                lines += [f"> {p['excerpt']}", f"> — {p['source']}", ""]
        path = os.path.join(folder, "Concepts", names[n["id"]] + ".md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        files.append(path)
    members: dict[int, list] = {}
    for n in data["nodes"]:
        members.setdefault(n["community"], []).append(n)
    for t in data["topics"]:
        group = sorted(members.get(t["id"], []), key=lambda n: -n.get("strength", 0))
        lines = ["---", "type: topic", f"size: {t['size']}", "---", "", f"# {t['label']}", ""]
        if t.get("summary"):
            lines += [t["summary"], ""]
        lines += ["## Concepts", ""] + [f"- [[{names[n['id']]}]]" for n in group] + [""]
        path = os.path.join(folder, "Topics", topic_names[t["id"]] + ".md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        files.append(path)
    gap_lines = ["# Gaps", "", "Pairs of developed topics with little between them. Each is a question worth asking.", ""]
    for gp in data["gaps"]:
        a, b = gp["bridge_candidates"][0][0], gp["bridge_candidates"][1][0]
        gap_lines += [f"## {gp['topics'][0]}  ↔  {gp['topics'][1]}", "",
                      f"Gap score {gp['score']}. {gp['prompt']}", "",
                      f"Start from [[{names.get(a, a)}]] and [[{names.get(b, b)}]].", ""]
    for name, body in (("Gaps.md", "\n".join(gap_lines)), ("Topics map.canvas", canvas(data, names=names))):
        path = os.path.join(folder, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        files.append(path)
    return files


def _relation_line(e: dict, other: str, arrow: str) -> str:
    rel = e["relation"].replace("_", " ")
    text = f"- {arrow} *{rel}* [[{other}]]"
    if e.get("description"):
        text += f" — {e['description']}"
    if e.get("valid_to"):
        text += f" ~~(closed {e['valid_to'][:10]})~~"
    if e.get("confidence") is not None:
        text += f" `{e['confidence']:.2f}`"
    return text


def canvas(data: dict, names: dict | None = None) -> str:
    """JSON Canvas 1.0: the main topics as groups, their central concepts as cards, typed edges as arrows."""
    colors = ["1", "2", "3", "4", "5", "6"]
    by_topic: dict[int, list] = {}
    for n in data["nodes"]:
        by_topic.setdefault(n["community"], []).append(n)
    chosen = [t for t in data["topics"]][:8] or [{"id": -1, "label": data["graph"], "size": len(data["nodes"])}]
    cards, groups, edges = [], [], []
    placed = set()
    cols = max(1, math.ceil(math.sqrt(len(chosen))))
    for i, t in enumerate(chosen):
        gx, gy = (i % cols) * 1100, (i // cols) * 900
        members = sorted(by_topic.get(t["id"], data["nodes"] if t["id"] == -1 else []),
                         key=lambda n: -n.get("strength", 0))[:12]
        groups.append({"id": f"g{i}", "type": "group", "label": t["label"], "x": gx, "y": gy, "width": 1000,
                       "height": 800, "color": colors[i % len(colors)]})
        for j, n in enumerate(members):
            angle = 2 * math.pi * j / max(1, len(members))
            r = 0 if j == 0 else 300
            x = gx + 500 + r * math.cos(angle) - 110
            y = gy + 400 + r * math.sin(angle) - 50
            card = {"id": _cid(n["id"]), "x": round(x), "y": round(y), "width": 220, "height": 100}
            if names:
                card.update({"type": "file", "file": f"Concepts/{names[n['id']]}.md"})
            else:
                text = f"**{n['label']}**\n{n['type']}"
                if n.get("summary"):
                    text += f"\n\n{n['summary'][:160]}"
                card.update({"type": "text", "text": text})
            cards.append(card)
            placed.add(n["id"])
    for e in _current(data):
        if e["source"] in placed and e["target"] in placed:
            edges.append({"id": e["id"], "fromNode": _cid(e["source"]), "toNode": _cid(e["target"]),
                          "label": e["relation"].replace("_", " ")})
    return json.dumps({"nodes": groups + cards, "edges": edges[:400]}, indent=1, ensure_ascii=False)


def _cid(node_id: str) -> str:
    import hashlib

    return "n" + hashlib.sha1(node_id.encode()).hexdigest()[:12]
