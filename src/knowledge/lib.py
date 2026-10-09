"""Every capability of the knowledge tool. The CLI, the MCP server and the live view call these.

Each function takes a graph (a name, a path, or an open `Graph`) and ordinary arguments,
and returns ordinary dicts and lists. Model-backed functions (`ingest` with method "llm",
`ask`, `report`, `questions`, `reconcile`) take `provider`, `model`, `complete_cmd` or a
`complete(system, prompt) -> str` function; everything else needs no model and no key.
"""

from __future__ import annotations

import contextlib
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import analysis as an
from .errors import INPUT, MODEL_CALL, ToolError
from .extract import SYSTEM_PROMPT, check_triples, cooccurrence, normalise_triple, user_prompt
from .store import Graph, list_graphs, now, open_graph, parse_time
from .text import CHUNK_OVERLAP, CHUNK_SIZE, STOPWORDS, node_key, sha256, split_text

METHODS = ("llm", "cooccurrence", "agent")
SUPPORT_RELATIONS = {"supports", "confirms", "evidence_for", "supported_by", "demonstrates", "shows", "validates"}
CONTRA_RELATIONS = {"contradicts", "refutes", "disputes", "conflicts_with", "undermines", "challenges",
                    "evidence_against", "contradicted_by"}
OPPOSITES = [({"supports", "confirms", "validates"}, CONTRA_RELATIONS),
             ({"increases", "raises", "improves", "enables", "causes", "promotes"},
              {"decreases", "reduces", "lowers", "worsens", "prevents", "blocks", "inhibits"}),
             ({"is", "is_a", "includes", "has"}, {"is_not", "excludes", "lacks"})]
NEGATIONS = (" not ", " no ", " never ", "n't ", " without ", " fails to ", " cannot ")


@contextlib.contextmanager
def _open(graph, create: bool = True):
    if isinstance(graph, Graph):
        yield graph
        return
    g = open_graph(graph, create=create)
    try:
        yield g
    finally:
        g.close()


def _say(progress, message: str) -> None:
    if progress:
        progress(message)


# --- self-description ------------------------------------------------------------------------

def manifest() -> dict:
    """The manifest's fields and body, read from the copy shipped inside the package."""
    from .help import manifest as _manifest

    return _manifest()


def graphs() -> list[dict]:
    """Graphs in the per-user data folder: name, path, size and last change."""
    return list_graphs()


# --- writing ---------------------------------------------------------------------------------

def ingest(graph=None, text: str | None = None, *, documents: list[dict] | None = None, uri: str = "",
           title: str = "", method: str = "llm", agent: str = "", session: str = "", at: str | None = None,
           chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP, max_chunks: int | None = None,
           min_count: int | None = None, force: bool = False, provider: str | None = None,
           model: str | None = None, complete_cmd: str | None = None, complete=None, workers: int = 4,
           progress=None, urls: list[str] | None = None, allow_network: bool = False) -> dict:
    """Read material into the graph.

    `text` is one document; `documents` is a list of {uri, title, text}. Methods:
    llm (model-backed) extracts typed concepts and relations from each chunk; cooccurrence
    (deterministic) builds a word network; agent (deterministic) stores the chunks and
    returns them with the extraction prompt, for the calling agent to extract and `add`.

    `urls` are web pages to fetch first; fetching happens only with `allow_network`.

    Material already read (same text) is skipped unless `force`. A new version of a source
    (same uri, new text) closes the validity of the old version's edges.
    """
    if method not in METHODS:
        raise ToolError("usage", f"Unknown method \"{method}\".", hint="Use llm, cooccurrence or agent.", exit_code=2)
    docs = list(documents or [])
    for url in urls or []:
        if not allow_network:
            raise ToolError("invalid_input", f"{url} is a web address and fetching is off.",
                            hint="Add --allow-network (allow_network=True) to let the tool fetch it, or save the "
                                 "page's text and pass the file.")
        from .text import fetch_url

        _say(progress, f"Fetching {url}")
        docs.append(fetch_url(url))
    if text is not None:
        docs.append({"uri": uri or f"text:{sha256(text)[:12]}", "title": title or "pasted text", "text": text})
    docs = [d for d in docs if str(d.get("text", "")).strip()]
    if not docs:
        raise ToolError("invalid_input", "There is nothing to read: the material is empty.",
                        hint="Pass a file, a folder, --text, or - to read standard input.")
    route = None
    if method == "llm":
        from . import providers

        route = providers.resolve(provider, model, complete_cmd, complete, deterministic_route=(
            "Without a model: `knowledge ingest PATH --method agent` stores the chunks and gives you the "
            "extraction prompt; extract the relations yourself and load them with `knowledge add`. Or use "
            "`--method cooccurrence` for a word network with no model."))
        _say(progress, f"Extracting with {route.describe()}.")
    stamp = parse_time(at) or now()
    with _open(graph) as g:
        before = g.counts()
        report_sources, todo, task_chunks = [], [], []
        for doc in docs:
            body = str(doc["text"])
            digest = sha256(body)
            existing = g.source_by_sha(digest)
            if existing and not force:
                pending = [c for c in g.chunks_of(existing["id"]) if not c["extracted_at"]]
                if method == "llm" and pending and existing["method"] == "llm":
                    todo += [(existing["id"], c["id"], c["text"]) for c in pending]
                    report_sources.append({**_src(existing), "status": "resumed", "chunks": len(pending)})
                elif method == "agent":
                    # The stored chunks are the task, whichever method read them first.
                    task_chunks += [{"id": c["id"], "text": c["text"]} for c in g.chunks_of(existing["id"])]
                    report_sources.append({**_src(existing), "status": "unchanged"})
                else:
                    entry = {**_src(existing), "status": "unchanged", "chunks": 0}
                    if existing["method"] != method:
                        entry["note"] = (f"Already read with method {existing['method'] or 'unknown'}, so nothing "
                                         f"was added. --force reads it again with {method} and closes the "
                                         "relations from the earlier reading.")
                        _say(progress, f"{existing['uri']}: {entry['note']}")
                    report_sources.append(entry)
                continue
            src = g.add_source(uri=doc.get("uri") or f"text:{digest[:12]}", title=doc.get("title") or "",
                               text=body, kind=doc.get("kind", "text"), method=method, agent=agent,
                               session=session, at=stamp)
            replaced = 0
            for old in g.sources_by_uri(src["uri"]):
                if old["id"] != src["id"]:
                    replaced += g.replace_source(old["id"], src["id"], stamp)
            pieces = split_text(body, chunk_size, overlap)
            if max_chunks:
                pieces = pieces[:max_chunks]
            ids = [g.add_chunk(src["id"], i, piece) for i, piece in enumerate(pieces)]
            entry = {**_src(src), "status": "replaced" if replaced else "added", "chunks": len(ids)}
            if replaced:
                entry["edges_closed"] = replaced
            report_sources.append(entry)
            if method == "cooccurrence":
                _ingest_cooccurrence(g, src, list(zip(ids, pieces)), min_count, agent, session, stamp)
            elif method == "agent":
                task_chunks += [{"id": cid, "text": piece} for cid, piece in zip(ids, pieces)]
            else:
                todo += [(src["id"], cid, piece) for cid, piece in zip(ids, pieces)]
        g.commit()
        failed = []
        if method == "llm" and todo:
            failed = _ingest_llm(g, route, todo, agent, session, stamp, complete, workers, progress)
        after = g.counts()
        result = {
            "graph": g.name, "path": str(g.path), "method": method,
            "model": route.describe() if route else None,
            "sources": report_sources,
            "nodes_added": after["nodes"] - before["nodes"],
            "edges_added": after["edges"] + after["closed_edges"] - before["edges"] - before["closed_edges"],
            "totals": {"nodes": after["nodes"], "edges": after["edges"]},
        }
        if method == "agent":
            result["task"] = {
                "do": "Extract relations from each chunk with the system prompt below, then load them: "
                      "knowledge add FILE (or pass JSON on stdin with -). Put each chunk's id in its "
                      "relations' \"chunk\" field so every edge cites its words. Either "
                      "shape is accepted: the prompt's {node_1, node_2, edge} items or the format below.",
                "system": SYSTEM_PROMPT,
                "format": {"edges": [{"from": "concept", "from_type": "concept", "to": "concept",
                                      "to_type": "claim", "relation": "supports",
                                      "description": "one sentence", "confidence": 0.8, "chunk": "CHUNK_ID"}]},
                "chunks": task_chunks,
            }
        if failed:
            result["failed_chunks"] = failed
            raise ToolError("model_call_failed",
                            f"{len(failed)} of {len(todo)} chunks could not be read "
                            f"({failed[0]['error']}); {len(todo) - len(failed)} were added.",
                            hint="Check the model route named above, then run the same command again: chunks "
                                 "already read are skipped and only these are retried.",
                            exit_code=MODEL_CALL, result=result)
        return result


def _src(row: dict) -> dict:
    return {"id": row["id"], "uri": row["uri"], "title": row["title"]}


def _ingest_cooccurrence(g: Graph, src: dict, chunks: list[tuple[str, str]], min_count, agent, session, stamp):
    total = sum(len(t) for _, t in chunks)
    threshold = min_count if min_count is not None else (2 if total > 4000 else 1)
    per_chunk = [(cid, *cooccurrence(text)) for cid, text in chunks]
    overall: dict[str, int] = {}
    for _, counts, _ in per_chunk:
        for w, c in counts.items():
            overall[w] = overall.get(w, 0) + c
    keep = {w for w, c in overall.items() if c >= threshold}
    for cid, counts, pairs in per_chunk:
        for w, c in counts.items():
            if w in keep:
                g.upsert_node(w, type="term", at=stamp)
                g.mention(node_key(w), cid, c)
        for (a, b), weight in pairs.items():
            if a in keep and b in keep:
                g.add_edge(node_key(a), node_key(b), "co_occurs", weight=weight, source_id=src["id"], chunk_id=cid,
                           agent=agent, session=session, method="cooccurrence", valid_from=stamp)
        g.mark_extracted(cid)
    g.commit()


def _ingest_llm(g: Graph, route, todo, agent, session, stamp, complete, workers, progress) -> list[dict]:
    from . import providers

    def work(item):
        _, cid, piece = item
        return providers.ask_json(route, SYSTEM_PROMPT, user_prompt(piece), complete=complete, check=check_triples)

    failed, done = [], 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(work, item): item for item in todo}
        for fut in as_completed(futures):
            sid, cid, _ = futures[fut]
            done += 1
            try:
                triples = fut.result()
            except ToolError as exc:
                failed.append({"chunk": cid, "error": exc.message})
                _say(progress, f"[{done}/{len(todo)}] {cid}: {exc.message}")
                continue
            for t in triples:
                _write_triple(g, t, source_id=sid, chunk_id=cid, agent=agent or "knowledge:llm", session=session,
                              method="llm", stamp=stamp)
            g.mark_extracted(cid)
            g.commit()
            _say(progress, f"[{done}/{len(todo)}] {cid}: {len(triples)} relations")
    return failed


def _write_triple(g: Graph, t: dict, *, source_id=None, chunk_id=None, agent="", session="", method="",
                  stamp=None) -> str:
    a = g.upsert_node(t["node_1"], type=t.get("node_1_type"), at=stamp)
    b = g.upsert_node(t["node_2"], type=t.get("node_2_type"), at=stamp)
    if chunk_id:
        g.mention(a, chunk_id)
        g.mention(b, chunk_id)
    return g.add_edge(a, b, t.get("relation") or "related_to", description=t.get("edge") or "",
                      weight=1.0, confidence=t.get("confidence"), source_id=source_id, chunk_id=chunk_id,
                      agent=agent, session=session, method=method, evidence=t.get("evidence") or "",
                      valid_from=t.get("valid_from") or stamp, valid_to=t.get("valid_to"))


def add(graph=None, payload=None, *, agent: str = "", session: str = "", at: str | None = None) -> dict:
    """Load nodes and relations written by a person or an agent. Deterministic.

    `payload` is a dict {source?, agent?, session?, nodes?, edges?, triples?} or a bare list of
    relations. Each relation is {from, to, relation, description?, confidence?, chunk?, evidence?,
    from_type?, to_type?, valid_from?, valid_to?}; {node_1, node_2, edge} is read too. A `chunk` id
    (from `ingest --method agent`) links the relation to its source words.
    """
    if payload is None:
        raise ToolError("invalid_input", "Nothing to add.", hint="Pass a JSON file, - for stdin, or use `relate`.")
    if isinstance(payload, list):
        payload = {"edges": payload}
    if not isinstance(payload, dict):
        raise ToolError("invalid_input", "The input must be a JSON object or a list of relations.")
    agent = payload.get("agent") or agent
    session = payload.get("session") or session
    stamp = parse_time(at) or now()
    with _open(graph) as g:
        source_id = None
        src = payload.get("source")
        if isinstance(src, dict) and (src.get("uri") or src.get("text")):
            body = str(src.get("text") or src.get("uri"))
            existing = g.source_by_sha(sha256(body))
            row = existing or g.add_source(uri=src.get("uri") or "", title=src.get("title") or "", text=body,
                                           kind=src.get("kind") or "note", method="agent", agent=agent,
                                           session=session, at=stamp)
            source_id = row["id"]
            if src.get("text") and not existing:
                for i, piece in enumerate(split_text(body)):
                    g.add_chunk(source_id, i, piece)
        node_ids, edge_ids, skipped = [], [], []
        for n in payload.get("nodes") or []:
            if isinstance(n, str):
                n = {"label": n}
            if not isinstance(n, dict) or not n.get("label"):
                skipped.append({"item": n, "why": "a node needs a label"})
                continue
            node_ids.append(g.upsert_node(n["label"], type=n.get("type"), summary=n.get("summary"),
                                          attrs=n.get("attrs"), at=stamp))
        for i, item in enumerate((payload.get("edges") or []) + (payload.get("triples") or [])):
            t = normalise_triple(item) if isinstance(item, dict) else None
            if not t:
                skipped.append({"item": i, "why": "a relation needs two different concepts (from, to)"})
                continue
            cid = t.get("chunk")
            sid = source_id
            if cid:
                chunk = g.chunk(cid)
                if not chunk:
                    skipped.append({"item": i, "why": f"no chunk {cid} in this graph"})
                    continue
                sid = chunk["source_id"]
                g.mark_extracted(cid)
            edge_ids.append(_write_triple(g, t, source_id=sid, chunk_id=cid, agent=agent, session=session,
                                          method=item.get("method") or "agent", stamp=stamp))
        for item in payload.get("supersede") or []:
            g.supersede(item["edge"], by=item.get("by"), reason=item.get("reason", ""), agent=agent, at=at)
        g.commit()
        if not node_ids and not edge_ids:
            raise ToolError("invalid_input", "Nothing in the input could be added.",
                            hint="Each relation needs from and to (or node_1 and node_2); see `knowledge add --help`.",
                            result={"skipped": skipped})
        return {"graph": g.name, "nodes": sorted(set(node_ids)), "edges": edge_ids, "skipped": skipped,
                "totals": {k: v for k, v in g.counts().items() if k in ("nodes", "edges")}}


def relate(graph=None, source: str = "", relation: str = "", target: str = "", *, description: str = "",
           confidence: float | None = None, source_type: str | None = None, target_type: str | None = None,
           evidence: str = "", agent: str = "", session: str = "", valid_from: str | None = None,
           supersedes: str | None = None) -> dict:
    """Add one relation (creating either concept if new). With `supersedes`, close that edge in favour of this one."""
    if not source or not target or not relation:
        raise ToolError("missing_argument", "relate needs a source, a relation and a target.",
                        hint='Example: knowledge relate "delegation" reduces "perceived agency"', exit_code=2)
    with _open(graph) as g:
        a = g.upsert_node(source, type=source_type)
        b = g.upsert_node(target, type=target_type)
        eid = g.add_edge(a, b, relation, description=description, confidence=confidence, agent=agent,
                         session=session, method="agent", evidence=evidence, valid_from=valid_from)
        # the old relation stops holding when the new one starts
        closed = g.supersede(supersedes, by=eid, agent=agent, at=valid_from) if supersedes else None
        g.commit()
        out = {"graph": g.name, "edge": g.edge(eid)}
        if closed:
            out["superseded"] = closed
        return out


def supersede(graph=None, edge: str = "", *, by: str | None = None, reason: str = "", at: str | None = None,
              agent: str = "") -> dict:
    """Close an edge's validity (it stays in the history). `by` names the edge that replaces it."""
    with _open(graph, create=False) as g:
        row = g.supersede(edge, by=by, reason=reason, at=at, agent=agent)
        g.commit()
        return {"graph": g.name, "edge": row}


# --- reading ---------------------------------------------------------------------------------

def stats(graph=None) -> dict:
    """Counts, node types and relation labels, and where the graph lives."""
    with _open(graph, create=False) as g:
        types: dict[str, int] = {}
        for r in g.db.execute("SELECT type, COUNT(*) FROM nodes GROUP BY type ORDER BY 2 DESC"):
            types[r[0]] = r[1]
        rels: dict[str, int] = {}
        for r in g.db.execute("SELECT relation, COUNT(*) FROM edges WHERE valid_to IS NULL "
                              "GROUP BY relation ORDER BY 2 DESC LIMIT 30"):
            rels[r[0]] = r[1]
        return {"graph": g.name, "path": str(g.path), "created_at": g.meta("created_at"), **g.counts(),
                "node_types": types, "relations": rels, "fts": g.fts, "last_event": g.last_event()}


def search(graph=None, query: str = "", *, limit: int = 10) -> dict:
    """Find concepts by name, summary and the passages that mention them. Deterministic."""
    if not query.strip():
        raise ToolError("missing_argument", "Give something to search for.", exit_code=2)
    with _open(graph, create=False) as g:
        scores: dict[str, float] = {}
        why: dict[str, set] = {}
        key = node_key(query)
        terms = [t for t in key.split() if len(t) > 1 and t not in STOPWORDS] or [t for t in key.split() if len(t) > 1]
        for row in g.db.execute("SELECT id FROM nodes WHERE id LIKE ?", (f"%{key}%",)):
            s = 3.0 if row[0] == key else 2.0
            scores[row[0]] = scores.get(row[0], 0) + s
            why.setdefault(row[0], set()).add("name")
        passages = []
        if g.fts and terms:
            match = " OR ".join('"' + t.replace('"', "") + '"' for t in terms)
            try:
                for row in g.db.execute("SELECT id, bm25(search_nodes) FROM search_nodes WHERE search_nodes MATCH ? "
                                        "ORDER BY 2 LIMIT 50", (match,)):
                    scores[row[0]] = scores.get(row[0], 0) + 1.0
                    why.setdefault(row[0], set()).add("summary")
                rows = g.db.execute("SELECT id, snippet(search_chunks, 1, '[', ']', ' ... ', 24) FROM search_chunks "
                                    "WHERE search_chunks MATCH ? ORDER BY bm25(search_chunks) LIMIT 20",
                                    (match,)).fetchall()
            except Exception:  # noqa: BLE001 - odd query syntax falls back to LIKE below
                rows = []
        else:
            rows = [(r[0], r[1][:300]) for r in g.db.execute(
                "SELECT id, text FROM chunks WHERE text LIKE ? LIMIT 20", (f"%{query}%",))]
        for rank, (cid, snippet) in enumerate(rows):
            chunk = g.chunk(cid)
            src = g.source(chunk["source_id"]) if chunk else None
            if rank < 8:
                passages.append({"chunk": cid, "source": src["title"] if src else "", "uri": src["uri"] if src else "",
                                 "snippet": " ".join(str(snippet).split())})
            for m in g.db.execute("SELECT node_id FROM mentions WHERE chunk_id=?", (cid,)):
                scores[m[0]] = scores.get(m[0], 0) + 0.5 / (1 + rank)
                why.setdefault(m[0], set()).add("passage")
        degree = {r[0]: r[1] for r in g.db.execute(
            "SELECT n, COUNT(*) FROM (SELECT source AS n FROM edges WHERE valid_to IS NULL UNION ALL "
            "SELECT target FROM edges WHERE valid_to IS NULL) GROUP BY n")}
        ranked = sorted(scores, key=lambda n: (-(scores[n] + 0.05 * min(degree.get(n, 0), 20)), n))[:limit]
        nodes = []
        for n in ranked:
            row = g.node(n)
            if row:
                nodes.append({"id": n, "label": row["label"], "type": row["type"], "summary": row["summary"],
                              "degree": degree.get(n, 0), "score": round(scores[n], 3), "matched": sorted(why[n])})
        return {"query": query, "nodes": nodes, "passages": passages}


def show(graph=None, concept: str = "", *, as_of: str | None = None, limit: int = 50) -> dict:
    """One concept: what it is, every relation in and out (with provenance), and where it is mentioned."""
    as_of = parse_time(as_of)
    with _open(graph, create=False) as g:
        key = g.resolve(concept)
        node = g.node(key)
        out_edges, in_edges = [], []
        for e in g.edges(node=key, as_of=as_of):
            item = _edge_view(g, e, key)
            (out_edges if e["source"] == key else in_edges).append(item)
        out_edges.sort(key=lambda e: (-(e["confidence"] or 0.5), e["relation"]))
        in_edges.sort(key=lambda e: (-(e["confidence"] or 0.5), e["relation"]))
        mentions = g.mentions_of(key, limit=5)
        neighbours = sorted({e["other"] for e in out_edges + in_edges})
        return {"graph": g.name, "node": node, "as_of": as_of, "degree": len(neighbours),
                "outgoing": out_edges[:limit], "incoming": in_edges[:limit], "neighbours": neighbours[:limit],
                "mentions": [{"chunk": m["chunk_id"], "source": m["title"], "uri": m["uri"],
                              "excerpt": _excerpt(m["text"], node["label"])} for m in mentions]}


def _edge_view(g: Graph, e: dict, focus: str | None = None) -> dict:
    src = g.source(e["source_id"]) if e["source_id"] else None
    return {"id": e["id"], "source": e["source"], "relation": e["relation"], "target": e["target"],
            "other": e["target"] if e["source"] == focus else e["source"],
            "description": e["description"], "confidence": e["confidence"], "weight": e["weight"],
            "valid_from": e["valid_from"], "valid_to": e["valid_to"], "invalidated_by": e["invalidated_by"],
            "agent": e["agent"], "method": e["method"], "chunk": e["chunk_id"],
            "from_source": src["title"] if src else None}


def _excerpt(text: str, label: str, width: int = 280) -> str:
    flat = " ".join(str(text).split())
    i = flat.lower().find(str(label).lower())
    if i < 0:
        return flat[:width] + ("..." if len(flat) > width else "")
    start = max(0, i - width // 3)
    piece = flat[start:start + width]
    return ("..." if start else "") + piece + ("..." if start + width < len(flat) else "")


def path(graph=None, source: str = "", target: str = "", *, k: int = 3, as_of: str | None = None) -> dict:
    """How two concepts connect: up to k paths with no shared middle concept, each step explained."""
    as_of = parse_time(as_of)
    with _open(graph, create=False) as g:
        a, b = g.resolve(source), g.resolve(target)
        view = an.build_view(g, as_of=as_of)
        paths = an.alternative_paths(view, a, b, k=k)
        out = []
        for p in paths:
            steps = []
            for x, y in zip(p, p[1:]):
                typed = view.pair_edges.get(tuple(sorted((x, y))), [])
                steps.append({"from": x, "to": y,
                              "relations": [{"id": e["id"], "source": e["source"], "relation": e["relation"],
                                             "target": e["target"], "description": e["description"]} for e in typed[:3]],
                              "shared_passages": view.proximity.get(tuple(sorted((x, y))), 0)})
            out.append({"nodes": p, "hops": len(p) - 1, "steps": steps})
        result = {"graph": g.name, "from": a, "to": b, "as_of": as_of, "connected": bool(paths), "paths": out}
        if not paths:
            result["note"] = ("No path: these concepts are in parts of the graph with nothing between them. "
                              "`knowledge gaps --between` explains the gap; `knowledge questions` proposes bridges.")
        return result


def timeline(graph=None, concept: str = "") -> dict:
    """Everything that was ever said about a concept, in time order, including closed relations."""
    with _open(graph, create=False) as g:
        key = g.resolve(concept)
        node = g.node(key)
        all_edges = g.edges(node=key, include_closed=True)
        first = min([node["created_at"]] + [e["valid_from"] for e in all_edges if e["valid_from"]])
        entries = [{"at": first, "event": "first seen", "node": key}]
        edge_ids = set()
        for e in all_edges:
            edge_ids.add(e["id"])
            v = _edge_view(g, e, key)
            entries.append({"at": e["valid_from"], "event": "relation added", **v})
            if e["valid_to"]:
                entries.append({"at": e["valid_to"], "event": "relation closed", "id": e["id"],
                                "relation": e["relation"], "other": v["other"], "invalidated_by": e["invalidated_by"]})
        for c in g.conflicts():
            if c["edge_a"] in edge_ids or c["edge_b"] in edge_ids:
                entries.append({"at": c["created_at"], "event": "conflict recorded", **c})
        entries.sort(key=lambda x: (x["at"] or "", x["event"]))
        return {"graph": g.name, "node": key, "entries": entries,
                "current": sum(1 for x in entries if x["event"] == "relation added" and not x.get("valid_to")),
                "closed": sum(1 for x in entries if x["event"] == "relation closed")}


def evidence(graph=None, target: str = "") -> dict:
    """What backs a concept or an edge: the passages, the sources, and supporting and contradicting relations."""
    with _open(graph, create=False) as g:
        if target.startswith("e-") and g.edge(target):
            e = g.edge(target)
            chunk = g.chunk(e["chunk_id"]) if e["chunk_id"] else None
            src = g.source(e["source_id"]) if e["source_id"] else None
            confl = [c for c in g.conflicts() if target in (c["edge_a"], c["edge_b"])]
            return {"graph": g.name, "edge": _edge_view(g, e), "quote": e["evidence"] or None,
                    "passage": chunk["text"] if chunk else None,
                    "source": {"id": src["id"], "uri": src["uri"], "title": src["title"],
                               "ingested_at": src["ingested_at"], "agent": src["agent"]} if src else None,
                    "conflicts": confl}
        key = g.resolve(target)
        support, against = [], []
        for e in g.edges(node=key, include_closed=True):
            v = _edge_view(g, e, key)
            if e["relation"] in SUPPORT_RELATIONS:
                support.append(v)
            elif e["relation"] in CONTRA_RELATIONS:
                against.append(v)
        mentions = g.mentions_of(key, limit=10)
        sources = {}
        for m in mentions:
            sources[m["source_id"]] = {"id": m["source_id"], "title": m["title"], "uri": m["uri"]}
        return {"graph": g.name, "node": key, "supporting": support, "contradicting": against,
                "passages": [{"chunk": m["chunk_id"], "source": m["title"],
                              "excerpt": _excerpt(m["text"], key, 400)} for m in mentions],
                "sources": list(sources.values())}


def contradictions(graph=None, concept: str | None = None, *, as_of: str | None = None, limit: int = 50) -> dict:
    """Where the graph disagrees with itself. Deterministic.

    explicit: edges whose relation is contradicts (or similar). recorded: judgments from
    `reconcile`. candidates: pairs of current relations between the same two concepts that look
    opposed (opposite labels, or one description negated). superseded: relations that were closed.
    """
    as_of = parse_time(as_of)
    with _open(graph, create=False) as g:
        focus = g.resolve(concept) if concept else None
        current = g.edges(node=focus, as_of=as_of)
        explicit = [_edge_view(g, e, focus) for e in current if e["relation"] in CONTRA_RELATIONS]
        candidates = _conflict_candidates(current)[:limit]
        recorded = g.conflicts()
        if focus:
            ids = {e["id"] for e in g.edges(node=focus, include_closed=True)}
            recorded = [c for c in recorded if c["edge_a"] in ids or c["edge_b"] in ids]
        reviewed = {tuple(sorted((c["edge_a"], c["edge_b"]))) for c in g.conflicts()}
        candidates = [c for c in candidates if tuple(sorted((c["a"]["id"], c["b"]["id"]))) not in reviewed]
        superseded = [_edge_view(g, e, focus) for e in g.edges(node=focus, include_closed=True) if e["valid_to"]]
        return {"graph": g.name, "concept": focus, "as_of": as_of, "explicit": explicit[:limit],
                "recorded": recorded[:limit], "candidates": candidates, "superseded": superseded[:limit],
                "next": ["knowledge reconcile" + (f' --concept "{focus}"' if focus else "")] if candidates else []}


def _conflict_candidates(edges: list[dict]) -> list[dict]:
    by_pair: dict[tuple[str, str], list[dict]] = {}
    for e in edges:
        if e["method"] == "cooccurrence":
            continue
        by_pair.setdefault(tuple(sorted((e["source"], e["target"]))), []).append(e)
    out = []
    for pair, group in sorted(by_pair.items()):
        for i, x in enumerate(group):
            for y in group[i + 1:]:
                why = _opposed(x, y)
                if why:
                    out.append({"pair": list(pair), "why": why,
                                "a": {k: x[k] for k in ("id", "source", "relation", "target", "description", "agent",
                                                        "valid_from")},
                                "b": {k: y[k] for k in ("id", "source", "relation", "target", "description", "agent",
                                                        "valid_from")}})
    return out


def _opposed(x: dict, y: dict) -> str | None:
    rx, ry = x["relation"], y["relation"]
    for left, right in OPPOSITES:
        if (rx in left and ry in right) or (rx in right and ry in left):
            return f"opposite relations: {rx} / {ry}"
    if rx == ry and x["description"] and y["description"]:
        nx = any(n in f" {x['description'].lower()} " for n in NEGATIONS)
        ny = any(n in f" {y['description'].lower()} " for n in NEGATIONS)
        if nx != ny:
            return "one description is negated"
    return None


# --- analysis --------------------------------------------------------------------------------

def _communities(view, method: str, resolution: float):
    if method == "girvan-newman":
        return an.girvan_newman(view)
    if method != "louvain":
        raise ToolError("usage", f"Unknown method \"{method}\".", hint="Use louvain or girvan-newman.", exit_code=2)
    return an.louvain(view, resolution=resolution)


def _label(group, cent):
    return ", ".join(an.top_nodes(group, cent, 3))


def communities(graph=None, *, method: str = "louvain", resolution: float = 1.0, as_of: str | None = None,
                proximity: bool = True, members: int = 12) -> dict:
    """Topics: groups of concepts more linked to each other than to the rest, with their central concepts."""
    as_of = parse_time(as_of)
    with _open(graph, create=False) as g:
        view = an.build_view(g, as_of=as_of, proximity=proximity)
        groups = _communities(view, method, resolution)
        cent = an.centrality(view)
        q = an.modularity(view, groups)
        reports = g.reports()
        out = []
        for i, grp in enumerate(groups):
            if len(grp) < 2:
                continue
            item = {"id": i, "label": _label(grp, cent), "size": len(grp),
                    "top": an.top_nodes(grp, cent, members), "members": grp if len(grp) <= members else None}
            rep = _match_report(grp, reports)
            if rep:
                item["report"] = {"title": rep["title"], "summary": rep["summary"], "findings": rep["findings"]}
            out.append(item)
        return {"graph": g.name, "method": method, "as_of": as_of, "modularity": q,
                "diversity": an.diversity(view, groups, q), "communities": out,
                "isolated": sum(1 for grp in groups if len(grp) == 1)}


def _match_report(group, reports):
    s = set(group)
    best, score = None, 0.0
    for r in reports:
        m = set(r["members"])
        j = len(s & m) / max(1, len(s | m))
        if j > score:
            best, score = r, j
    return best if score >= 0.5 else None


def analyze(graph=None, *, as_of: str | None = None, top: int = 10, proximity: bool = True) -> dict:
    """One overview: the most central concepts, the bridges, the topics, how diverse it is, and the biggest gaps."""
    as_of = parse_time(as_of)
    with _open(graph, create=False) as g:
        view = an.build_view(g, as_of=as_of, proximity=proximity)
        cent = an.centrality(view)
        groups = an.louvain(view)
        q = an.modularity(view, groups)
        label = {n: i for i, grp in enumerate(groups) for n in grp}
        by_bc = sorted(cent, key=lambda n: (-cent[n]["betweenness"], -cent[n]["degree"], n))
        by_deg = sorted(cent, key=lambda n: (-cent[n]["strength"], n))
        bridges = [n for n in by_bc if cent[n]["betweenness"] > 0 and
                   {label.get(nb) for nb in view.adj[n]} - {label.get(n)}][:top]
        gaps = an.structural_gaps(view, groups, cent, top=3)
        return {
            "graph": g.name, "as_of": as_of,
            "size": {"nodes": len(view.nodes), "edges": len(view.edges),
                     "linked_pairs": sum(len(v) for v in view.adj.values()) // 2},
            "most_influential": [{"node": n, **cent[n], "community": label.get(n)} for n in by_bc[:top]],
            "most_connected": [{"node": n, **cent[n], "community": label.get(n)} for n in by_deg[:top]],
            "bridges": bridges,
            "communities": [{"id": i, "label": _label(grp, cent), "size": len(grp)}
                            for i, grp in enumerate(groups) if len(grp) > 1][:top],
            "diversity": an.diversity(view, groups, q),
            "gaps": [_gap_view(gp, groups, cent) for gp in gaps],
        }


def _gap_view(gap, groups, cent):
    i, j = gap["between"]
    return {**gap, "topics": [_label(groups[i], cent), _label(groups[j], cent)],
            "prompt": f"Two developed topics are barely linked: [{_label(groups[i], cent)}] and "
                      f"[{_label(groups[j], cent)}]. What would connect "
                      f"{gap['bridge_candidates'][0][0]} and {gap['bridge_candidates'][1][0]}?"}


def gaps(graph=None, *, between: list[str] | None = None, as_of: str | None = None, top: int = 5) -> dict:
    """Structural gaps: well-developed topics with little between them, or how far apart two concepts are."""
    as_of = parse_time(as_of)
    with _open(graph, create=False) as g:
        view = an.build_view(g, as_of=as_of)
        cent = an.centrality(view)
        groups = an.louvain(view)
        if between:
            if len(between) != 2:
                raise ToolError("usage", "--between takes exactly two concepts.", exit_code=2)
            a, b = (g.resolve(x) for x in between)
            label = {n: i for i, grp in enumerate(groups) for n in grp}
            distance = an.hops(view, a, b)
            common = sorted(set(view.adj[a]) & set(view.adj[b]))
            direct = view.pair_edges.get(tuple(sorted((a, b))), [])
            same = label.get(a) == label.get(b)
            if direct:
                verdict = "linked directly"
            elif distance is None:
                verdict = "no connection at all: a true gap"
            elif distance >= 3 and not same:
                verdict = "far apart, in different topics: a gap worth exploring"
            elif not same:
                verdict = "close, but in different topics"
            else:
                verdict = "close, in the same topic"
            return {"graph": g.name, "between": [a, b], "verdict": verdict, "hops": distance,
                    "same_topic": same, "direct_relations": [_edge_view(g, e) for e in direct],
                    "shared_neighbours": common[:20],
                    "topics": [_label(groups[label[a]], cent) if a in label else None,
                               _label(groups[label[b]], cent) if b in label else None],
                    "path": an.shortest_path(view, a, b)}
        found = an.structural_gaps(view, groups, cent, top=top)
        return {"graph": g.name, "as_of": as_of, "gaps": [_gap_view(gp, groups, cent) for gp in found],
                "note": None if found else "No large gaps: the main topics are already linked, or the graph is "
                "too small to have distinct topics yet."}


def context(graph=None, query: str = "", *, budget: int = 12000, as_of: str | None = None, seeds: int = 5) -> dict:
    """The material a model needs to answer a question from the graph, assembled by code (no model).

    Finds the concepts the question names, their strongest relations, the passages that
    mention them and the reports of their topics, numbered [1], [2], ... for citation. Hand
    `text` to any model, or read it yourself. `ask` does exactly this and then asks a model.
    """
    as_of = parse_time(as_of)
    hits = search(graph, query, limit=seeds)
    with _open(graph, create=False) as g:
        view = an.build_view(g, as_of=as_of)
        seed_ids = [n["id"] for n in hits["nodes"]][:seeds]
        used = 0
        cites: list[dict] = []

        def cite(kind: str, text: str, ref: dict) -> bool:
            nonlocal used
            if used + len(text) > budget:
                return False
            cites.append({"n": len(cites) + 1, "kind": kind, "text": text, **ref})
            used += len(text)
            return True

        for n in seed_ids:
            node = g.node(n)
            if node and node["summary"]:
                cite("concept", f"{node['label']} ({node['type']}): {node['summary']}", {"node": n})
        seen = set()
        typed: dict[str, list[dict]] = {}
        for e in view.edges:
            if e["method"] != "cooccurrence":
                typed.setdefault(e["source"], []).append(e)
                typed.setdefault(e["target"], []).append(e)
        for n in seed_ids:
            for e in sorted(typed.get(n, []), key=lambda x: (-(x["confidence"] or 0.5), x["id"]))[:12]:
                if e["id"] in seen:
                    continue
                seen.add(e["id"])
                line = f"{e['source']} --{e['relation']}--> {e['target']}"
                if e["description"]:
                    line += f": {e['description']}"
                if e["confidence"] is not None:
                    line += f" (confidence {e['confidence']:.2f})"
                cite("relation", line, {"edge": e["id"]})
        for p in hits["passages"][:6]:
            chunk = g.chunk(p["chunk"])
            if chunk:
                cite("passage", f"From {p['source']}: {' '.join(chunk['text'].split())[:1200]}",
                     {"chunk": p["chunk"], "uri": p["uri"]})
        reports = g.reports()
        groups = an.louvain(view) if reports else []
        for grp in groups:
            if set(grp) & set(seed_ids):
                rep = _match_report(grp, reports)
                if rep:
                    cite("report", f"Topic \"{rep['title']}\": {rep['summary']}", {"report": rep["id"]})
        text = "\n".join(f"[{c['n']}] {c['text']}" for c in cites)
        return {"graph": g.name, "query": query, "seeds": seed_ids, "citations": cites, "text": text,
                "chars": len(text), "budget": budget, "empty": not cites}


# --- model-backed ----------------------------------------------------------------------------

ASK_SYSTEM = """You answer questions from a knowledge graph. Use only the numbered context you are given.
Cite the numbers you rely on in square brackets, like [2] or [3][5]. If the context does not answer
the question, say what is missing instead of guessing. Point out where the context disagrees with itself.
Be brief and plain."""


def host_task(graph=None, capability: str = "ask", *, question: str = "", between: list[str] | None = None,
              concept: str | None = None, as_of: str | None = None, budget: int = 12000) -> dict:
    """The deterministic half of a model-backed capability, for a caller that is itself the model.

    Returns {task, ...material}: what to do and the graph material to do it with, so the caller does
    the model's part and writes back with `add`, `relate` or `supersede`. No model is called.
    """
    if capability == "ask":
        return {"task": "Answer the question from this numbered context only, citing [n]. Say what is missing if "
                        "it does not answer it.", "question": question,
                "context": context(graph, question, as_of=as_of, budget=budget)}
    if capability == "report":
        return {"task": "Write a short title and a two-sentence summary for each topic from its central concepts. "
                        "To keep them, add nodes of type report (knowledge add).",
                "communities": communities(graph, as_of=as_of)}
    if capability == "questions":
        return {"task": "For each gap, propose questions that would connect the two topics. To keep one, relate "
                        "it: source = the question, relation = bridges, source_type = question.",
                "gaps": gaps(graph, between=between, as_of=as_of)}
    if capability == "reconcile":
        return {"task": "Judge each candidate pair: contradicts, supersedes (which is newer) or compatible. Record a "
                        "contradiction with relate (relation contradicts); close a replaced relation with supersede.",
                "contradictions": contradictions(graph, concept, as_of=as_of)}
    raise ToolError("usage", f"\"{capability}\" has no host task.", hint="Use ask, report, questions or reconcile.",
                    exit_code=2)

def ask(graph=None, question: str = "", *, budget: int = 12000, as_of: str | None = None,
        provider: str | None = None, model: str | None = None, complete_cmd: str | None = None,
        complete=None) -> dict:
    """Answer a question from the graph, citing the relations and passages used. Model-backed."""
    from . import providers

    route = providers.resolve(provider, model, complete_cmd, complete, deterministic_route=(
        f"Without a model: `knowledge context \"{question}\"` assembles the same numbered context; "
        "answer from it yourself."))
    ctx = context(graph, question, budget=budget, as_of=as_of)
    if ctx["empty"]:
        raise ToolError("no_context", "Nothing in the graph matches this question.",
                        hint="Search with other words (`knowledge search`), or ingest material about it first.")
    answer = providers.call(route, ASK_SYSTEM, f"Context:\n{ctx['text']}\n\nQuestion: {question}", complete=complete)
    import re

    used = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer)})
    return {"graph": ctx["graph"], "question": question, "answer": answer.strip(), "model": route.describe(),
            "citations": [c for c in ctx["citations"] if c["n"] in used], "context_size": ctx["chars"]}


REPORT_SYSTEM = """You write short reports on one topic of a knowledge graph: a group of closely linked concepts.
From the concepts and relations given, reply with JSON only:
{"title": "a short name for the topic", "summary": "two or three plain sentences on what the topic is about",
 "findings": ["up to five specific statements the relations support, each naming the concepts involved"]}"""


def report(graph=None, *, top: int = 5, as_of: str | None = None, save: bool = True, provider: str | None = None,
           model: str | None = None, complete_cmd: str | None = None, complete=None, progress=None) -> dict:
    """Name and summarise the biggest topics (community reports). Model-backed; saved for `context` and the view."""
    from . import providers

    route = providers.resolve(provider, model, complete_cmd, complete, deterministic_route=(
        "Without a model: `knowledge communities --json` lists each topic's concepts; write a title and summary "
        "yourself and save it with `knowledge add` as a node of type report, or skip saving."))
    as_of = parse_time(as_of)
    with _open(graph, create=False) as g:
        view = an.build_view(g, as_of=as_of)
        cent = an.centrality(view)
        groups = [grp for grp in an.louvain(view) if len(grp) >= 3][:top]
        out = []
        for i, grp in enumerate(groups):
            members = an.top_nodes(grp, cent, 25)
            mset = set(members)
            lines = [f"{e['source']} --{e['relation']}--> {e['target']}: {e['description']}"
                     for e in view.edges if e["source"] in mset and e["target"] in mset and e["method"] != "cooccurrence"]
            if len(lines) < 3:
                lines += [f"{a} and {b} appear together in {c} passages" for (a, b), c in
                          sorted(view.proximity.items(), key=lambda kv: -kv[1]) if a in mset and b in mset][:20]
            prompt = "Concepts: " + ", ".join(members) + "\n\nRelations:\n" + "\n".join(lines[:80])
            _say(progress, f"Topic {i + 1}/{len(groups)}: {_label(grp, cent)}")

            def check(v):
                if not isinstance(v, dict) or not v.get("title") or not v.get("summary"):
                    raise ValueError("expected {title, summary, findings}")
                v["findings"] = [str(x) for x in v.get("findings") or []][:5]
                return v

            rep = providers.ask_json(route, REPORT_SYSTEM, prompt, complete=complete, check=check)
            item = {"community": i, "size": len(grp), "top": members[:8], **rep}
            if save:
                item["id"] = g.add_report(grp, rep["title"], rep["summary"], rep["findings"], agent="knowledge:report")
            out.append(item)
        g.commit()
        return {"graph": g.name, "model": route.describe(), "reports": out, "saved": save}


QUESTIONS_SYSTEM = """You find research questions in the gaps of a knowledge graph. You are given pairs of
well-developed topics that have almost no links between them, with each topic's most central concepts.
For each gap, propose questions that, if answered, would connect the two topics. Reply with JSON only:
[{"gap": 0, "question": "...", "why": "one sentence on why this bridge may exist",
  "bridges": ["a concept from the first topic", "a concept from the second topic"]}]"""


def questions(graph=None, *, between: list[str] | None = None, top: int = 3, per_gap: int = 2, save: bool = False,
              as_of: str | None = None, provider: str | None = None, model: str | None = None,
              complete_cmd: str | None = None, complete=None) -> dict:
    """Turn structural gaps into research questions that would bridge them. Model-backed.

    With `save`, each question becomes a node of type question, linked to the concepts it would bridge.
    """
    from . import providers

    route = providers.resolve(provider, model, complete_cmd, complete, deterministic_route=(
        "Without a model: `knowledge gaps` lists the gaps with a prompt for each; write questions yourself and "
        "save them with `knowledge relate \"QUESTION\" bridges \"CONCEPT\" --source-type question`."))
    found = gaps(graph, between=between, as_of=as_of, top=top)
    if between:
        gap_list = [{"topics": found["topics"], "bridge_candidates": [[found["between"][0]], [found["between"][1]]],
                     "verdict": found["verdict"]}]
    else:
        gap_list = found["gaps"]
    if not gap_list:
        raise ToolError("no_gaps", "The graph has no structural gaps to ask about.",
                        hint="Ingest more material, or name two concepts with --between.")
    prompt = "\n".join(f"Gap {i}: topic A [{gp['topics'][0]}] (central: {', '.join(gp['bridge_candidates'][0])}) "
                       f"and topic B [{gp['topics'][1]}] (central: {', '.join(gp['bridge_candidates'][1])})"
                       for i, gp in enumerate(gap_list))
    prompt += f"\n\nGive {per_gap} questions per gap."

    def check(v):
        if isinstance(v, dict):
            v = v.get("questions", [])
        if not isinstance(v, list) or not all(isinstance(x, dict) and x.get("question") for x in v):
            raise ValueError("expected a list of {gap, question, why, bridges}")
        return v

    qs = providers.ask_json(route, QUESTIONS_SYSTEM, prompt, complete=complete, check=check)
    saved = []
    if save:
        with _open(graph) as g:
            for q in qs:
                qid = g.upsert_node(q["question"], type="question", summary=q.get("why", ""))
                for b in (q.get("bridges") or [])[:2]:
                    with contextlib.suppress(ToolError):
                        g.add_edge(qid, g.resolve(b), "bridges", description=q.get("why", ""),
                                   agent="knowledge:questions", method="llm")
                saved.append(qid)
            g.commit()
    return {"graph": found["graph"], "model": route.describe(), "gaps": gap_list, "questions": qs, "saved": saved}


RECONCILE_SYSTEM = """You check pairs of statements from a knowledge graph for conflicts. Each pair links the
same two concepts. For each pair decide:
- "contradicts": both cannot be true at once.
- "supersedes": one is a newer or corrected version of the other (say which is newer: "a" or "b").
- "compatible": both can be true.
Reply with JSON only: [{"pair": 0, "verdict": "contradicts|supersedes|compatible", "newer": "a|b|null",
"reason": "one sentence"}]"""


def reconcile(graph=None, concept: str | None = None, *, limit: int = 20, apply: bool = True,
              provider: str | None = None, model: str | None = None, complete_cmd: str | None = None,
              complete=None) -> dict:
    """Judge conflict candidates: record contradictions, and close relations that newer ones replace. Model-backed."""
    from . import providers

    route = providers.resolve(provider, model, complete_cmd, complete, deterministic_route=(
        "Without a model: `knowledge contradictions` lists the candidate pairs; judge them yourself, then "
        "`knowledge supersede EDGE --by EDGE` or `knowledge relate A contradicts B`."))
    found = contradictions(graph, concept, limit=limit)
    pairs = found["candidates"]
    if not pairs:
        with _open(graph, create=False) as g:
            # no labelled opposites: look at any two relations between the same concepts
            current = g.edges(node=g.resolve(concept) if concept else None)
        groups: dict = {}
        for e in current:
            if e["method"] != "cooccurrence" and e["description"]:
                groups.setdefault(tuple(sorted((e["source"], e["target"]))), []).append(e)
        for pair, grp in sorted(groups.items()):
            for i, x in enumerate(grp):
                for y in grp[i + 1:]:
                    if len(pairs) < limit:
                        keys = ("id", "source", "relation", "target", "description", "agent", "valid_from")
                        pairs.append({"pair": list(pair), "why": "same concepts",
                                      "a": {k: x[k] for k in keys}, "b": {k: y[k] for k in keys}})
    if not pairs:
        return {"graph": found["graph"], "model": route.describe(), "judged": [], "note": "Nothing to reconcile."}
    prompt = "\n".join(f"Pair {i}: (a) {p['a']['source']} {p['a']['relation']} {p['a']['target']}: "
                       f"{p['a']['description']} [added {p['a']['valid_from']}]\n"
                       f"        (b) {p['b']['source']} {p['b']['relation']} {p['b']['target']}: "
                       f"{p['b']['description']} [added {p['b']['valid_from']}]" for i, p in enumerate(pairs))

    def check(v):
        if isinstance(v, dict):
            v = v.get("verdicts", [])
        if not isinstance(v, list):
            raise ValueError("expected a list of verdicts")
        for x in v:
            if not isinstance(x, dict) or x.get("verdict") not in ("contradicts", "supersedes", "compatible"):
                raise ValueError("each verdict must be contradicts, supersedes or compatible")
        return v

    verdicts = providers.ask_json(route, RECONCILE_SYSTEM, prompt, complete=complete, check=check)
    judged = []
    with _open(graph) as g:
        for v in verdicts:
            try:
                p = pairs[int(v.get("pair", -1))]
            except (ValueError, IndexError):
                continue
            item = {"a": p["a"]["id"], "b": p["b"]["id"], "verdict": v["verdict"], "reason": v.get("reason", "")}
            if apply:
                g.add_conflict(p["a"]["id"], p["b"]["id"], v["verdict"], v.get("reason", ""), agent="knowledge:reconcile")
                if v["verdict"] == "supersedes" and v.get("newer") in ("a", "b"):
                    old, new = (p["b"], p["a"]) if v["newer"] == "a" else (p["a"], p["b"])
                    with contextlib.suppress(ToolError):
                        g.supersede(old["id"], by=new["id"], reason=v.get("reason", ""), agent="knowledge:reconcile")
                        item["closed"] = old["id"]
            judged.append(item)
        g.commit()
    return {"graph": found["graph"], "model": route.describe(), "judged": judged, "applied": apply}


# --- views and exports -----------------------------------------------------------------------

PALETTE = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#76b7b2", "#edc948", "#b07aa1", "#ff9da7",
           "#9c755f", "#86bcb6", "#d37295", "#8cd17d", "#499894", "#f1ce63", "#a0cbe8", "#ffbe7d"]


def graph_data(graph=None, *, as_of: str | None = None, concept: str | None = None, depth: int = 2,
               max_nodes: int = 1500, proximity: bool = True, passages: int = 3) -> dict:
    """The whole picture as one JSON document: nodes (with topic and centrality), typed edges with their
    validity windows (closed ones too, for the time slider), proximity links, topics and gaps.
    This is what `visualize` embeds, `serve` streams and `export --format json` writes."""
    as_of = parse_time(as_of)
    with _open(graph, create=False) as g:
        view = an.build_view(g, as_of=as_of, proximity=proximity)
        cent = an.centrality(view)
        groups = an.louvain(view)
        label = {n: i for i, grp in enumerate(groups) for n in grp}
        keep = set(view.nodes)
        if concept:
            start = g.resolve(concept)
            keep, frontier = {start}, {start}
            for _ in range(max(0, depth)):
                frontier = {nb for n in frontier for nb in view.adj.get(n, {})} - keep
                keep |= frontier
        truncated = False
        if len(keep) > max_nodes:
            keep = set(sorted(keep, key=lambda n: (-cent[n]["strength"], n))[:max_nodes])
            truncated = True
        reports = g.reports()
        topics = []
        for i, grp in enumerate(groups):
            if len(grp) < 2:
                continue
            rep = _match_report(grp, reports)
            topics.append({"id": i, "label": rep["title"] if rep else _label(grp, cent), "size": len(grp),
                           "color": PALETTE[i % len(PALETTE)], "summary": rep["summary"] if rep else ""})
        first_seen: dict[str, str] = {}
        for e in g.edges(include_closed=True):
            for end in (e["source"], e["target"]):
                if e["valid_from"] and (end not in first_seen or e["valid_from"] < first_seen[end]):
                    first_seen[end] = e["valid_from"]
        nodes = []
        for n in sorted(keep):
            row = view.nodes[n]
            c = label.get(n, -1)
            item = {"id": n, "label": row["label"], "type": row["type"], "summary": row["summary"],
                    "community": c, "color": PALETTE[c % len(PALETTE)] if c >= 0 and len(groups[c]) > 1 else "#9aa0a6",
                    **cent.get(n, {}), "created_at": min(row["created_at"], first_seen.get(n, row["created_at"]))}
            if passages:
                item["passages"] = [{"source": m["title"], "uri": m["uri"], "chunk": m["chunk_id"],
                                     "excerpt": _excerpt(m["text"], row["label"])}
                                    for m in g.mentions_of(n, limit=passages)]
            nodes.append(item)
        edges = []
        titles = {s["id"]: s["title"] for s in g.sources()}
        for e in g.edges(include_closed=True):
            if e["source"] in keep and e["target"] in keep:
                if as_of and e["valid_from"] > as_of:
                    continue
                edges.append({"id": e["id"], "source": e["source"], "target": e["target"], "relation": e["relation"],
                              "description": e["description"], "confidence": e["confidence"], "weight": e["weight"],
                              "method": e["method"], "agent": e["agent"], "valid_from": e["valid_from"],
                              "valid_to": e["valid_to"], "invalidated_by": e["invalidated_by"],
                              "chunk": e["chunk_id"], "evidence": (e["evidence"] or "")[:300],
                              "from_source": titles.get(e["source_id"])})
        prox = [{"source": a, "target": b, "count": c} for (a, b), c in view.proximity.items()
                if a in keep and b in keep]
        gp = an.structural_gaps(view, groups, cent, top=5)
        times = sorted({e["valid_from"] for e in edges if e["valid_from"]} |
                       {e["valid_to"] for e in edges if e["valid_to"]})
        return {"format": "knowledge-graph/1", "graph": g.name, "generated_at": now(), "as_of": as_of,
                "focus": concept, "truncated": truncated, "last_event": g.last_event(),
                "counts": {"nodes": len(nodes), "edges": len(edges), "proximity": len(prox), "topics": len(topics)},
                "nodes": nodes, "edges": edges, "proximity": prox, "topics": topics,
                "gaps": [_gap_view(x, groups, cent) for x in gp],
                "diversity": an.diversity(view, groups, an.modularity(view, groups)),
                "time": {"first": times[0] if times else None, "last": times[-1] if times else None,
                         "marks": times[-400:]}}


def choose_view(graph=None, question: str | None = None, *, lens: str | None = None, concept: str | None = None,
                to: str | None = None, as_of: str | None = None, view: str | None = None) -> dict:
    """Pick the view that answers a question: a lens (overview, concept, path, evidence, contradictions,
    history, gaps) and the concepts it is about. Raises `needs_clarification` with a question to ask the
    person, and the command for each answer, when the question does not say enough to choose."""
    from .lenses import choose_view as _choose

    with _open(graph, create=False) as g:
        return _choose(g, question, lens=lens, concept=concept, to=to, as_of=as_of, view=view)


def visualize(graph=None, out: str | None = None, *, as_of: str | None = None, concept: str | None = None,
              depth: int = 2, max_nodes: int = 1500, title: str | None = None, proximity: bool = True,
              question: str | None = None, lens: str | None = None, to: str | None = None,
              view: str | None = None) -> dict:
    """Write one self-contained interactive HTML file (no outside requests) and return where it is.
    With `question` (or `lens`), the view opens on the lens that answers it, and says why."""
    from .render import render_html

    plan = None
    if view is not None and question is None and lens is None:
        from .lenses import lens_for_view

        lens = lens_for_view(view, concept)
    if question is not None or lens is not None:
        plan = choose_view(graph, question, lens=lens, concept=concept, to=to, as_of=as_of, view=view)
        data = graph_data(graph, max_nodes=max_nodes, proximity=proximity)
        shown = {n["id"] for n in data["nodes"]}
        if any(c and c not in shown for c in (plan["concept"], plan["to"])):  # trimmed away: draw its neighbourhood
            data = graph_data(graph, concept=plan["concept"], depth=depth, max_nodes=max_nodes, proximity=proximity)
        data["open"] = {k: plan[k] for k in ("lens", "view", "concept", "to", "as_of", "closed", "question", "why",
                                             "alternatives", "description")}
    else:
        data = graph_data(graph, as_of=as_of, concept=concept, depth=depth, max_nodes=max_nodes, proximity=proximity)
    html = render_html(data, title=title)
    focus = concept if plan is None else plan["concept"]
    target = out or f"knowledge-{data['graph']}{'-' + node_key(focus).replace(' ', '-') if focus else ''}.html"
    with open(target, "w", encoding="utf-8") as fh:
        fh.write(html)
    result = {"path": os.path.abspath(target), "bytes": len(html.encode()), "nodes": data["counts"]["nodes"],
              "edges": data["counts"]["edges"], "topics": data["counts"]["topics"], "truncated": data["truncated"]}
    if plan:
        result.update({k: plan[k] for k in ("lens", "view", "concept", "to", "as_of", "why", "alternatives")})
    return result


def export(graph=None, format: str = "json", out: str | None = None, *, as_of: str | None = None,
           concept: str | None = None, depth: int = 2) -> dict:
    """Write the graph for other tools: json, cytoscape, graphml (Gephi), csv, obsidian (a vault folder),
    or canvas (an Obsidian Canvas map of one concept's neighbourhood or the main topics)."""
    from . import exporters as ex

    if format not in ex.FORMATS:
        raise ToolError("usage", f"Unknown format \"{format}\".", hint="Use one of: " + ", ".join(ex.FORMATS),
                        exit_code=2)
    data = graph_data(graph, as_of=as_of, concept=concept, depth=depth, max_nodes=100000, passages=5)
    return ex.write(data, format, out)


def events(graph=None, *, since: int = 0, limit: int = 1000) -> dict:
    """The change log after event number `since`: what was added, closed or judged, by whom, when."""
    with _open(graph, create=False) as g:
        items = g.events(since=since, limit=limit)
        return {"graph": g.name, "events": items, "last": items[-1]["seq"] if items else since}


def doctor(graph=None, *, complete_cmd: str | None = None) -> dict:
    """Check the setup and say what to fix. Never calls a model."""
    import shlex
    import shutil
    import sqlite3

    from . import providers
    from .store import data_home, graph_path

    checks = []

    def check(cid, status, detail, fix=""):
        checks.append({"id": cid, "status": status, "detail": detail, "fix": fix})

    py = sys.version_info
    check("python", "ok" if py >= (3, 10) else "fail", f"Python {py.major}.{py.minor}", "Use Python 3.10 or later.")
    fts = True
    try:
        sqlite3.connect(":memory:").execute("CREATE VIRTUAL TABLE t USING fts5(x)")
    except sqlite3.OperationalError:
        fts = False
    check("sqlite", "ok" if fts else "warn", f"SQLite {sqlite3.sqlite_version}, full-text search "
          + ("on" if fts else "off"), "" if fts else "Search falls back to plain matching; it still works.")
    home = data_home()
    try:
        home.mkdir(parents=True, exist_ok=True)
        probe = home / ".write-test"
        probe.write_text("ok")
        probe.unlink()
        check("data_folder", "ok", str(home))
    except OSError as exc:
        check("data_folder", "fail", f"{home}: {exc}", "Set KNOWLEDGE_HOME to a folder you can write.")
    check("graph", "ok" if graph_path(graph).exists() else "warn", str(graph_path(graph)),
          "" if graph_path(graph).exists() else "Created on first ingest, add or relate.")
    host = providers.detect_host()
    try:
        route = providers.resolve(complete_cmd=complete_cmd)
        check("model", "ok", f"Model-backed steps use {route.describe()} ({route.why}).")
    except ToolError as exc:
        status = "ok" if exc.code == "host_model" else "warn"
        check("model", status, exc.message, exc.hint)
    if complete_cmd:
        prog = shlex.split(complete_cmd)[0] if shlex.split(complete_cmd) else ""
        found = bool(shutil.which(prog) or os.path.exists(prog))
        check("complete_cmd", "ok" if found else "fail", f"{prog}: {'found' if found else 'not found'}",
              "" if found else "Give the full path to the program.")
    try:
        import pypdf  # noqa: F401
        check("pdf", "ok", "pypdf installed: PDFs can be read.")
    except ImportError:
        check("pdf", "warn", "pypdf not installed: PDFs are skipped.", "pip install pypdf")
    ready = {"deterministic": all(c["status"] != "fail" for c in checks if c["id"] in ("python", "data_folder")),
             "model_backed": any(c["id"] == "model" and c["status"] == "ok" and "inside" not in c["detail"]
                                 for c in checks),
             "host": host}
    return {"checks": checks, "ready": ready,
            "summary": "Ready." if ready["deterministic"] else "Something every user needs is broken; see fail lines."}


__all__ = ["manifest", "graphs", "ingest", "add", "relate", "supersede", "stats", "search", "show", "path",
           "timeline", "evidence", "contradictions", "communities", "analyze", "gaps", "context", "ask", "report",
           "questions", "reconcile", "host_task", "graph_data", "visualize", "export", "events", "doctor", "INPUT"]
