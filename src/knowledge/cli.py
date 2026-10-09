"""The command line: parse arguments, read files into data, call the library, print the result.

No capability lives here. Help text comes from `help.py`; every command calls one library function.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from . import help as h
from . import lib
from .errors import INTERRUPTED, OK, SETUP, USAGE, ToolError, classify

GLOBAL_FLAGS = {"--json", "-q", "--quiet", "--debug", "--no-color"}


class Options:
    json = False
    quiet = False
    debug = False


OPT = Options()


def progress(message: str) -> None:
    if not OPT.quiet:
        sys.stderr.write(message + "\n")
        sys.stderr.flush()


# --- argument parsing ------------------------------------------------------------------------

class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # noqa: D401 - argparse API
        raise ToolError("usage", message[:1].upper() + message[1:] + ".",
                        hint=f"Run `{self.prog} -h` for the arguments.", exit_code=USAGE)


class _Print(argparse.Action):
    def __init__(self, option_strings, render, dest=argparse.SUPPRESS, default=argparse.SUPPRESS, help=None):
        super().__init__(option_strings=option_strings, dest=dest, default=default, nargs=0, help=help)
        self.render = render

    def __call__(self, parser, namespace, values, option_string=None):
        sys.stdout.write(self.render(parser) + "\n")
        parser.exit(0)


def _cap(sub, name: str) -> argparse.ArgumentParser:
    p = sub.add_parser(name, add_help=False, prog=f"knowledge {name}")
    p.add_argument("-h", action=_Print, render=lambda parser: h.capability_short(name, parser.format_usage()))
    p.add_argument("--help", action=_Print, render=lambda parser: h.capability_skill(name))
    p.add_argument("--graph", default=None)
    p.set_defaults(command=name)
    return p


def _provider(p):
    p.add_argument("--provider")
    p.add_argument("--model")
    p.add_argument("--complete-cmd", dest="complete_cmd")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="knowledge", add_help=False)
    parser.add_argument("-h", action=_Print, render=lambda _p: h.short_help())
    parser.add_argument("--help", action=_Print, render=lambda _p: h.skill())
    parser.add_argument("-V", "--version", action=_Print, render=lambda _p: f"knowledge {h.VERSION}")
    sub = parser.add_subparsers(dest="command", parser_class=_Parser)

    p = _cap(sub, "ingest")
    p.add_argument("targets", nargs="*")
    p.add_argument("--text")
    p.add_argument("--method", default="llm", choices=lib.METHODS)
    p.add_argument("--title", default="")
    p.add_argument("--uri", default="")
    p.add_argument("--agent", default="")
    p.add_argument("--session", default="")
    p.add_argument("--at")
    p.add_argument("--chunk-size", type=int, default=1500)
    p.add_argument("--overlap", type=int, default=150)
    p.add_argument("--max-chunks", type=int)
    p.add_argument("--min-count", type=int)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--allow-network", action="store_true")
    p.add_argument("--force", action="store_true")
    _provider(p)

    p = _cap(sub, "add")
    p.add_argument("file")
    p.add_argument("--agent", default="")
    p.add_argument("--session", default="")
    p.add_argument("--at")

    p = _cap(sub, "relate")
    p.add_argument("source")
    p.add_argument("relation")
    p.add_argument("target")
    p.add_argument("--description", default="")
    p.add_argument("--confidence", type=float)
    p.add_argument("--source-type")
    p.add_argument("--target-type")
    p.add_argument("--evidence", default="")
    p.add_argument("--supersedes")
    p.add_argument("--agent", default="")
    p.add_argument("--session", default="")
    p.add_argument("--at")

    p = _cap(sub, "supersede")
    p.add_argument("edge")
    p.add_argument("--by")
    p.add_argument("--reason", default="")
    p.add_argument("--at")
    p.add_argument("--agent", default="")

    p = _cap(sub, "search")
    p.add_argument("query", nargs="+")
    p.add_argument("--limit", type=int, default=10)

    p = _cap(sub, "show")
    p.add_argument("concept", nargs="+")
    p.add_argument("--as-of")
    p.add_argument("--limit", type=int, default=50)

    p = _cap(sub, "path")
    p.add_argument("source")
    p.add_argument("target")
    p.add_argument("--k", type=int, default=3)
    p.add_argument("--as-of")

    p = _cap(sub, "timeline")
    p.add_argument("concept", nargs="+")

    p = _cap(sub, "evidence")
    p.add_argument("target", nargs="+")

    p = _cap(sub, "contradictions")
    p.add_argument("concept", nargs="*")
    p.add_argument("--as-of")
    p.add_argument("--limit", type=int, default=50)

    p = _cap(sub, "communities")
    p.add_argument("--method", default="louvain", choices=["louvain", "girvan-newman"])
    p.add_argument("--resolution", type=float, default=1.0)
    p.add_argument("--no-proximity", action="store_true")
    p.add_argument("--members", type=int, default=12)
    p.add_argument("--as-of")

    p = _cap(sub, "analyze")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--no-proximity", action="store_true")
    p.add_argument("--as-of")

    p = _cap(sub, "gaps")
    p.add_argument("--between", nargs=2)
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--as-of")

    p = _cap(sub, "context")
    p.add_argument("query", nargs="+")
    p.add_argument("--budget", type=int, default=12000)
    p.add_argument("--as-of")

    p = _cap(sub, "ask")
    p.add_argument("question", nargs="+")
    p.add_argument("--budget", type=int, default=12000)
    p.add_argument("--as-of")
    _provider(p)

    p = _cap(sub, "report")
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--no-save", action="store_true")
    p.add_argument("--as-of")
    _provider(p)

    p = _cap(sub, "questions")
    p.add_argument("--between", nargs=2)
    p.add_argument("--top", type=int, default=3)
    p.add_argument("--per-gap", type=int, default=2)
    p.add_argument("--save", action="store_true")
    p.add_argument("--as-of")
    _provider(p)

    p = _cap(sub, "reconcile")
    p.add_argument("--concept")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--dry-run", action="store_true")
    _provider(p)

    p = _cap(sub, "visualize")
    p.add_argument("--out")
    p.add_argument("--concept")
    p.add_argument("--depth", type=int, default=2)
    p.add_argument("--max-nodes", type=int, default=1500)
    p.add_argument("--no-proximity", action="store_true")
    p.add_argument("--title")
    p.add_argument("--open", action="store_true")
    p.add_argument("--as-of")
    p.add_argument("--for", dest="question")
    p.add_argument("--lens")
    p.add_argument("--to")

    p = _cap(sub, "serve")
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--open", action="store_true")
    p.add_argument("--max-nodes", type=int, default=1500)

    p = _cap(sub, "export")
    p.add_argument("--format", default="json")
    p.add_argument("--out")
    p.add_argument("--concept")
    p.add_argument("--depth", type=int, default=2)
    p.add_argument("--as-of")

    p = _cap(sub, "events")
    p.add_argument("--since", type=int, default=0)
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--follow", action="store_true")

    _cap(sub, "stats")
    _cap(sub, "graphs")
    p = _cap(sub, "doctor")
    p.add_argument("--complete-cmd", dest="complete_cmd")
    _cap(sub, "mcp")
    _cap(sub, "manifest")
    return parser


# --- reading inputs (a convenience of the command line; the library takes data) ---------------

def _read_json(path: str):
    if path == "-":
        if sys.stdin is None or sys.stdin.closed:
            raise ToolError("invalid_input", "Asked to read standard input, but it is closed.",
                            hint="Pass a file path instead of -, or pipe the JSON in.")
        return json.loads(sys.stdin.read() or "null")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _documents(args) -> list[dict]:
    from .text import load_documents

    docs = []
    for target in args.targets:
        if target == "-":
            data = sys.stdin.read() if sys.stdin and not sys.stdin.closed else ""
            docs.append({"uri": args.uri or "stdin", "title": args.title or "standard input", "text": data})
        elif target.startswith(("http://", "https://")):
            continue  # fetched by the library, which owns the --allow-network gate
        else:
            found = load_documents(target)
            if not found:
                raise ToolError("invalid_input", f"Nothing readable in {target}.",
                                hint="Text files (.md, .txt, .html, code, .jsonl sessions) are read; hidden and "
                                     "build folders are skipped.")
            docs += found
    return docs


# --- dispatch --------------------------------------------------------------------------------

def run(args) -> tuple[object, list[dict], list[str]]:
    """Call the library for one command. Returns (result, files written, next commands)."""
    c, g = args.command, args.graph
    gflag = f" --graph {g}" if g else ""
    prov = {k: getattr(args, k, None) for k in ("provider", "model", "complete_cmd")}
    if c == "ingest":
        if not args.targets and args.text is None:
            raise ToolError("missing_argument", "Give a file, a folder, - for standard input, or --text.",
                            hint="Example: knowledge ingest ./notes", exit_code=USAGE)
        docs = _documents(args)
        progress(f"Reading {len(docs) + (1 if args.text is not None else 0)} document(s) into graph "
                 f"\"{g or os.environ.get('KNOWLEDGE_GRAPH') or 'default'}\" ({args.method}).")
        r = lib.ingest(g, args.text, documents=docs, uri=args.uri, title=args.title, method=args.method,
                       agent=args.agent, session=args.session, at=args.at, chunk_size=args.chunk_size,
                       overlap=args.overlap, max_chunks=args.max_chunks, min_count=args.min_count,
                       force=args.force, workers=args.workers, progress=progress, allow_network=args.allow_network,
                       urls=[x for x in args.targets if x.startswith(("http://", "https://"))], **prov)
        nxt = ([f"knowledge add relations.json{gflag}"] if args.method == "agent" else
               [f"knowledge analyze{gflag}", f"knowledge visualize{gflag} --open"])
        return r, [], nxt
    if c == "add":
        r = lib.add(g, _read_json(args.file), agent=args.agent, session=args.session, at=args.at)
        return r, [], [f"knowledge visualize{gflag} --open"]
    if c == "relate":
        r = lib.relate(g, args.source, args.relation, args.target, description=args.description,
                       confidence=args.confidence, source_type=args.source_type, target_type=args.target_type,
                       evidence=args.evidence, agent=args.agent, session=args.session, valid_from=args.at,
                       supersedes=args.supersedes)
        return r, [], []
    if c == "supersede":
        return lib.supersede(g, args.edge, by=args.by, reason=args.reason, at=args.at, agent=args.agent), [], []
    if c == "search":
        return lib.search(g, " ".join(args.query), limit=args.limit), [], []
    if c == "show":
        return lib.show(g, " ".join(args.concept), as_of=args.as_of, limit=args.limit), [], []
    if c == "path":
        return lib.path(g, args.source, args.target, k=args.k, as_of=args.as_of), [], []
    if c == "timeline":
        return lib.timeline(g, " ".join(args.concept)), [], []
    if c == "evidence":
        return lib.evidence(g, " ".join(args.target)), [], []
    if c == "contradictions":
        r = lib.contradictions(g, " ".join(args.concept) or None, as_of=args.as_of, limit=args.limit)
        return r, [], r.get("next", [])
    if c == "communities":
        return lib.communities(g, method=args.method, resolution=args.resolution, as_of=args.as_of,
                               proximity=not args.no_proximity, members=args.members), [], []
    if c == "analyze":
        return lib.analyze(g, as_of=args.as_of, top=args.top, proximity=not args.no_proximity), [], \
            [f"knowledge gaps{gflag}", f"knowledge visualize{gflag} --open"]
    if c == "gaps":
        return lib.gaps(g, between=args.between, as_of=args.as_of, top=args.top), [], [f"knowledge questions{gflag}"]
    if c == "context":
        return lib.context(g, " ".join(args.query), budget=args.budget, as_of=args.as_of), [], []
    if c == "ask":
        return lib.ask(g, " ".join(args.question), budget=args.budget, as_of=args.as_of, **prov), [], []
    if c == "report":
        return lib.report(g, top=args.top, save=not args.no_save, as_of=args.as_of, progress=progress, **prov), [], []
    if c == "questions":
        return lib.questions(g, between=args.between, top=args.top, per_gap=args.per_gap, save=args.save,
                             as_of=args.as_of, **prov), [], []
    if c == "reconcile":
        return lib.reconcile(g, args.concept, limit=args.limit, apply=not args.dry_run, **prov), [], []
    if c == "visualize":
        r = lib.visualize(g, args.out, as_of=args.as_of, concept=args.concept, depth=args.depth,
                          max_nodes=args.max_nodes, title=args.title, proximity=not args.no_proximity,
                          question=args.question, lens=args.lens, to=args.to)
        progress(f"Wrote {r['path']} ({r['nodes']} concepts, {r['edges']} relations).")
        if r.get("lens"):
            progress(f"Opens on the {r['lens']} view: {r['why']}")
        if args.open:
            _open_browser(r["path"])
        return r, [{"path": r["path"], "kind": "view"}], []
    if c == "export":
        r = lib.export(g, args.format, args.out, as_of=args.as_of, concept=args.concept, depth=args.depth)
        progress(f"Wrote {r['path']}.")
        return r, [{"path": r["path"], "kind": args.format}], []
    if c == "events":
        if args.follow:
            return _follow(g, args.since), [], []
        return lib.events(g, since=args.since, limit=args.limit), [], []
    if c == "serve":
        return _serve(args), [], []
    if c == "stats":
        return lib.stats(g), [], []
    if c == "graphs":
        return lib.graphs(), [], []
    if c == "doctor":
        r = lib.doctor(g, complete_cmd=args.complete_cmd)
        if not r["ready"]["deterministic"]:
            raise ToolError("setup_incomplete", r["summary"], exit_code=SETUP, result=r)
        return r, [], []
    if c == "manifest":
        return lib.manifest(), [], []
    if c == "mcp":
        from .mcp_server import serve_stdio

        serve_stdio(g)
        return None, [], []
    raise ToolError("usage", f"Unknown command {c}.", exit_code=USAGE)


def _open_browser(path: str) -> None:
    if os.environ.get("KNOWLEDGE_NO_BROWSER"):
        progress(f"Open {path} in a browser.")
        return
    import webbrowser

    webbrowser.open("file://" + os.path.abspath(path) if not path.startswith("http") else path)


def _follow(graph, since: int):
    last = since
    try:
        while True:
            r = lib.events(graph, since=last, limit=500)
            for e in r["events"]:
                sys.stdout.write(json.dumps(e, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            last = r["last"]
            time.sleep(1.0)
    except KeyboardInterrupt:
        return {"last": last}


def _serve(args):
    from .serve import make_server
    from .store import graph_path

    if not graph_path(args.graph).exists():
        raise ToolError("graph_not_found", f"There is no graph at {graph_path(args.graph)}.",
                        hint="Ingest or relate something first, or pick a graph with --graph.")
    try:
        server = make_server(args.graph, port=args.port, max_nodes=args.max_nodes)
    except OSError as exc:
        raise ToolError("port_unavailable", f"Cannot listen on port {args.port}: {exc}.",
                        hint="Choose another with --port, or leave it out for a free one.", exit_code=SETUP) from None
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    line = {"ok": True, "command": "serve", "event": "started", "result": {"url": url}} if OPT.json else {"url": url}
    sys.stdout.write(json.dumps(line) + "\n")
    sys.stdout.flush()
    progress(f"Live view at {url} (Ctrl-C to stop).")
    if args.open:
        _open_browser(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return None


# --- output ----------------------------------------------------------------------------------

def as_text(value, indent: int = 0) -> str:
    """Readable text for a person at a terminal: nested keys and lists, no JSON punctuation."""
    pad = "  " * indent
    if isinstance(value, dict):
        lines = []
        for k, v in value.items():
            if v in (None, "", [], {}):
                continue
            if isinstance(v, (dict, list)):
                lines.append(f"{pad}{k}:")
                lines.append(as_text(v, indent + 1))
            else:
                lines.append(f"{pad}{k}: {v}")
        return "\n".join(lines)
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict):
                body = as_text(item, indent + 1).lstrip()
                lines.append(f"{pad}- {body}")
            else:
                lines.append(f"{pad}- {item}")
        return "\n".join(lines)
    return f"{pad}{value}"


def _preprocess(argv: list[str]) -> list[str]:
    out = []
    for a in argv:
        if a == "--json":
            OPT.json = True
        elif a in ("-q", "--quiet"):
            OPT.quiet = True
        elif a == "--debug":
            OPT.debug = True
        elif a == "--no-color":
            pass
        else:
            out.append(a)
    # --graph before the command name belongs to the command
    if len(out) >= 2 and out[0] == "--graph":
        out = out[2:3] + out[:2] + out[3:]
    return out


def main(argv: list[str] | None = None) -> int:
    argv = _preprocess(list(sys.argv[1:] if argv is None else argv))
    command = None
    try:
        parser = build_parser()
        if not argv:
            sys.stdout.write(h.short_help() + "\n")
            return OK
        args = parser.parse_args(argv)
        command = getattr(args, "command", None)
        if not command:
            raise ToolError("usage", "No capability was named.", hint="Run `knowledge -h` for the list.",
                            exit_code=USAGE)
        result, files, nxt = run(args)
        if command in ("serve", "mcp") or (command == "events" and args.follow):
            return OK
        if OPT.json:
            sys.stdout.write(json.dumps({"ok": True, "command": command, "result": result, "files": files,
                                         "next": nxt}, ensure_ascii=False, default=str) + "\n")
        elif sys.stdout.isatty():
            sys.stdout.write(as_text(result) + "\n")
            if nxt and not OPT.quiet:
                sys.stderr.write("Next: " + "  |  ".join(nxt) + "\n")
        else:
            sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=1, default=str) + "\n")
        return OK
    except SystemExit as exc:  # argparse printed help and exited 0
        return int(exc.code or 0)
    except BaseException as exc:  # noqa: BLE001 - every failure is reported the same way
        if OPT.debug and not isinstance(exc, (ToolError, KeyboardInterrupt)):
            import traceback

            traceback.print_exc()
        err = classify(exc)
        if OPT.json:
            doc = {"ok": False, "command": command, "files": [], "error": err.as_dict(), "exit_code": err.exit_code}
            if err.result is not None:
                doc["result"] = err.result
            sys.stdout.write(json.dumps(doc, ensure_ascii=False, default=str) + "\n")
        else:
            if err.result is not None and not sys.stdout.isatty():
                sys.stdout.write(json.dumps(err.result, ensure_ascii=False, indent=1, default=str) + "\n")
            sys.stderr.write(f"knowledge: {err.message}\n")
            if err.hint:
                sys.stderr.write(f"  {err.hint}\n")
        return INTERRUPTED if isinstance(exc, KeyboardInterrupt) else err.exit_code


if __name__ == "__main__":
    sys.exit(main())
