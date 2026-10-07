"""The MCP surface: the same capabilities as tools, over stdio (newline-delimited JSON-RPC).

No MCP package is needed. Over MCP the calling assistant is the model: model-backed tools
return a task (the assembled material and what to do with it) instead of calling a model,
unless KNOWLEDGE_MCP_ALLOW_MODEL=1 lets the tool use its own provider routing.
"""

from __future__ import annotations

import json
import os
import sys

from . import help as h
from . import lib
from .errors import classify
from .text import load_documents

PROTOCOL = "2025-06-18"

S = {"type": "string"}
I = {"type": "integer"}  # noqa: E741
B = {"type": "boolean"}
N = {"type": "number"}
ASOF = {"type": "string", "description": "Read the graph as it was at this date or time."}


def _allow_model() -> bool:
    return os.environ.get("KNOWLEDGE_MCP_ALLOW_MODEL") == "1"


def _ingest(g, a):
    docs = []
    for p in a.get("paths") or []:
        docs += load_documents(p)
    method = a.get("method") or ("llm" if _allow_model() else "agent")
    return lib.ingest(g, a.get("text"), documents=docs, title=a.get("title", ""), uri=a.get("uri", ""),
                      method=method, agent=a.get("agent", ""), session=a.get("session", ""), at=a.get("at"),
                      max_chunks=a.get("max_chunks"), urls=a.get("urls"), allow_network=a.get("allow_network", False))


def _ask(g, a):
    if _allow_model():
        return lib.ask(g, a["question"], as_of=a.get("as_of"))
    return lib.host_task(g, "ask", question=a["question"], as_of=a.get("as_of"), budget=a.get("budget", 12000))


def _report(g, a):
    if _allow_model():
        return lib.report(g, top=a.get("top", 5))
    return lib.host_task(g, "report")


def _questions(g, a):
    if _allow_model():
        return lib.questions(g, between=a.get("between"), save=a.get("save", False))
    return lib.host_task(g, "questions", between=a.get("between"))


def _reconcile(g, a):
    if _allow_model():
        return lib.reconcile(g, a.get("concept"))
    return lib.host_task(g, "reconcile", concept=a.get("concept"))


TOOLS = {
    "ingest": ({"text": S, "paths": {"type": "array", "items": S}, "method": {"type": "string",
                "enum": list(lib.METHODS)}, "title": S, "uri": S, "agent": S, "session": S, "at": S,
                "max_chunks": I, "urls": {"type": "array", "items": S}, "allow_network": B}, [], _ingest),
    "add": ({"payload": {"type": "object", "description": "{source?, agent?, nodes?, edges?, supersede?}"},
             "agent": S, "session": S, "at": S}, ["payload"],
            lambda g, a: lib.add(g, a["payload"], agent=a.get("agent", ""), session=a.get("session", ""), at=a.get("at"))),
    "relate": ({"source": S, "relation": S, "target": S, "description": S, "confidence": N, "source_type": S,
                "target_type": S, "evidence": S, "agent": S, "session": S, "valid_from": S, "supersedes": S},
               ["source", "relation", "target"],
               lambda g, a: lib.relate(g, **{k: v for k, v in a.items() if k != "graph"})),
    "supersede": ({"edge": S, "by": S, "reason": S, "at": S, "agent": S}, ["edge"],
                  lambda g, a: lib.supersede(g, **{k: v for k, v in a.items() if k != "graph"})),
    "search": ({"query": S, "limit": I}, ["query"], lambda g, a: lib.search(g, a["query"], limit=a.get("limit", 10))),
    "show": ({"concept": S, "as_of": ASOF, "limit": I}, ["concept"],
             lambda g, a: lib.show(g, a["concept"], as_of=a.get("as_of"), limit=a.get("limit", 50))),
    "path": ({"source": S, "target": S, "k": I, "as_of": ASOF}, ["source", "target"],
             lambda g, a: lib.path(g, a["source"], a["target"], k=a.get("k", 3), as_of=a.get("as_of"))),
    "timeline": ({"concept": S}, ["concept"], lambda g, a: lib.timeline(g, a["concept"])),
    "evidence": ({"target": S}, ["target"], lambda g, a: lib.evidence(g, a["target"])),
    "contradictions": ({"concept": S, "as_of": ASOF}, [],
                       lambda g, a: lib.contradictions(g, a.get("concept"), as_of=a.get("as_of"))),
    "communities": ({"method": S, "resolution": N, "as_of": ASOF}, [],
                    lambda g, a: lib.communities(g, method=a.get("method", "louvain"),
                                                 resolution=a.get("resolution", 1.0), as_of=a.get("as_of"))),
    "analyze": ({"top": I, "as_of": ASOF}, [], lambda g, a: lib.analyze(g, top=a.get("top", 10), as_of=a.get("as_of"))),
    "gaps": ({"between": {"type": "array", "items": S, "minItems": 2, "maxItems": 2}, "top": I, "as_of": ASOF}, [],
             lambda g, a: lib.gaps(g, between=a.get("between"), top=a.get("top", 5), as_of=a.get("as_of"))),
    "context": ({"query": S, "budget": I, "as_of": ASOF}, ["query"],
                lambda g, a: lib.context(g, a["query"], budget=a.get("budget", 12000), as_of=a.get("as_of"))),
    "ask": ({"question": S, "budget": I, "as_of": ASOF}, ["question"], _ask),
    "report": ({"top": I}, [], _report),
    "questions": ({"between": {"type": "array", "items": S}, "save": B}, [], _questions),
    "reconcile": ({"concept": S}, [], _reconcile),
    "visualize": ({"out": S, "concept": S, "depth": I, "as_of": ASOF}, [],
                  lambda g, a: lib.visualize(g, a.get("out"), concept=a.get("concept"), depth=a.get("depth", 2),
                                             as_of=a.get("as_of"))),
    "export": ({"format": {"type": "string", "enum": ["json", "cytoscape", "graphml", "csv", "obsidian", "canvas"]},
                "out": S, "concept": S}, ["format"],
               lambda g, a: lib.export(g, a["format"], a.get("out"), concept=a.get("concept"))),
    "events": ({"since": I, "limit": I}, [], lambda g, a: lib.events(g, since=a.get("since", 0), limit=a.get("limit", 200))),
    "stats": ({}, [], lambda g, a: lib.stats(g)),
    "graphs": ({}, [], lambda g, a: lib.graphs()),
    "manifest": ({}, [], lambda g, a: lib.manifest()),
}


def tool_list() -> list[dict]:
    out = []
    for name, (props, required, _) in TOOLS.items():
        cap = h.CAPABILITIES[name]
        desc = cap["summary"] + " " + cap["when"]
        if cap["kind"] == "model-backed" and not _allow_model() and name != "ingest":
            desc += " Over MCP this returns a task for you (you are the model)."
        if name == "ingest" and not _allow_model():
            desc += " Over MCP the default method is agent: you get the chunks and the prompt, then call knowledge_add."
        schema = {"type": "object", "properties": {"graph": {"type": "string", "description": "Graph name or .db path."},
                                                   **props}}
        if required:
            schema["required"] = required
        out.append({"name": f"knowledge_{name}", "description": desc[:1024], "inputSchema": schema})
    return out


def handle(message: dict, graph=None) -> dict | None:
    method, mid = message.get("method"), message.get("id")
    if mid is None:
        return None  # a notification
    try:
        if method == "initialize":
            result = {"protocolVersion": message.get("params", {}).get("protocolVersion", PROTOCOL),
                      "capabilities": {"tools": {}},
                      "serverInfo": {"name": "knowledge", "version": h.VERSION},
                      "instructions": "A knowledge graph any agent can query and add to. Start with knowledge_stats "
                                      "or knowledge_search; write with knowledge_relate or knowledge_add."}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": tool_list()}
        elif method == "tools/call":
            params = message.get("params", {})
            name = str(params.get("name", "")).removeprefix("knowledge_")
            if name not in TOOLS:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"Unknown tool {name}"}}
            args = params.get("arguments") or {}
            try:
                value = TOOLS[name][2](args.get("graph") or graph, args)
                result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, default=str)}],
                          "structuredContent": value if isinstance(value, dict) else {"items": value}}
            except BaseException as exc:  # noqa: BLE001 - tool errors go back to the assistant
                err = classify(exc)
                result = {"isError": True, "content": [{"type": "text", "text": json.dumps(
                    {"error": err.as_dict(), **({"result": err.result} if err.result else {})}, default=str)}]}
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Unknown method {method}"}}
    except Exception as exc:  # noqa: BLE001
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(exc)}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve_stdio(graph=None) -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            reply = handle(message, graph)
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False, default=str) + "\n")
            sys.stdout.flush()
