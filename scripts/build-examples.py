#!/usr/bin/env python3
"""Build the example graphs and their views from real, public material. No model is called here.

- amplifier: 20 documents from microsoft/amplifier-docs and microsoft/amplifier-smart-tools (MIT),
  vendored in examples/amplifier/sources with their commit and date. Read with `ingest --method
  agent`; the relations in examples/amplifier/relations/ were extracted from those chunks by
  agents (see examples/amplifier/README.md) and are loaded with `add`, each tied to its chunk.
- amplifier-history: dated decisions from microsoft/amplifier-foundation's commit history, each
  citing its commit, replayed with `relate --supersedes` so replaced decisions stay in the history.
- this-repo: this repository's own docs as a word network (`--method cooccurrence`).

Writes graphs to .work/graphs/ and views to site/assets/<example>.html.

    python3 scripts/build-examples.py            # everything
    python3 scripts/build-examples.py --tasks    # also write extraction batches to .work/tasks/
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import knowledge as kg  # noqa: E402

EX = ROOT / "examples"
WORK = ROOT / ".work" / "graphs"
OUT = ROOT / "site" / "assets"
BATCHES = 4


def fresh(name: str) -> str:
    path = WORK / f"{name}.db"
    for suffix in ("", "-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)
    return str(path)


def amplifier_sources(graph: str) -> list[dict]:
    """Read the vendored documents, each dated by its last commit. Returns the chunks."""
    chunks = []
    for m in json.loads((EX / "amplifier" / "sources.json").read_text()):
        text = (EX / "amplifier" / "sources" / m["file"]).read_text()
        r = kg.ingest(graph, text, uri=m["uri"], title=f"{m['repo']}: {m['path']}", method="agent",
                      agent="librarian", at=m["date"])
        for c in r["task"]["chunks"]:
            chunks.append({**c, "source": f"{m['repo']}: {m['path']}", "date": m["date"]})
    return chunks


def amplifier(write_tasks: bool = False) -> tuple[str, str]:
    g = fresh("amplifier")
    chunks = amplifier_sources(g)
    bare = fresh("amplifier-chunks")  # the same chunks, no relations yet: the live demo starts here
    amplifier_sources(bare)
    if write_tasks:
        tasks = ROOT / ".work" / "tasks"
        tasks.mkdir(parents=True, exist_ok=True)
        for i in range(BATCHES):
            batch = chunks[i::BATCHES]
            (tasks / f"batch-{i + 1}.json").write_text(json.dumps(batch, indent=1))
        print(f"wrote {BATCHES} batches of about {len(chunks) // BATCHES} chunks to {tasks}")
    files = sorted((EX / "amplifier" / "relations").glob("*.json"))
    for f in files:
        kg.add(g, json.loads(f.read_text()))
    print(f"amplifier: {len(chunks)} chunks, {len(files)} relation files")
    return g, bare


def amplifier_history() -> str:
    g = fresh("amplifier-history")
    path = EX / "amplifier-history" / "journal.json"
    if not path.exists():
        return g
    ids: dict[str, str] = {}
    for step in json.loads(path.read_text()):
        r = kg.relate(g, step["from"], step["relation"], step["to"], description=step.get("description", ""),
                      source_type=step.get("from_type"), target_type=step.get("to_type"),
                      agent=step.get("agent", "historian"), valid_from=step["at"],
                      evidence=step.get("evidence", ""), supersedes=ids.get(step.get("supersedes", "")))
        if step.get("id"):
            ids[step["id"]] = r["edge"]["id"]
    return g


def this_repo() -> str:
    """This repository's own docs as a word network: no model, same result every time."""
    g = fresh("this-repo")
    files = [ROOT / "README.md", ROOT / "docs" / "VISION.md", ROOT / "src" / "knowledge" / "SMART_TOOL.md",
             ROOT / "AGENTS.md", ROOT / "contracts" / "cli.v1.md"]
    docs = [{"uri": str(f.relative_to(ROOT)), "title": f.name, "text": f.read_text()} for f in files]
    kg.ingest(g, documents=docs, method="cooccurrence", min_count=4, at="2026-10-06")
    return g


def main() -> None:
    os.environ.setdefault("KNOWLEDGE_HOME", str(ROOT / ".work" / "home"))
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    amp, _bare = amplifier(write_tasks="--tasks" in sys.argv)
    built = {
        "amplifier": (amp, "Amplifier, from its own docs"),
        "amplifier-history": (amplifier_history(), "amplifier-foundation, decisions over time"),
        "this-repo": (this_repo(), "This repository's docs, as a word network"),
    }
    for name, (graph, title) in built.items():
        try:
            r = kg.visualize(graph, str(OUT / f"{name}.html"), title=f"Knowledge: {title}", max_nodes=600)
        except kg.ToolError as exc:
            print(f"{name}: skipped ({exc.message})")
            continue
        print(f"{name}: {r['nodes']} concepts, {r['edges']} relations, {r['topics']} topics -> {r['path']}")


if __name__ == "__main__":
    main()
