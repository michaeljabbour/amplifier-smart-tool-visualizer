"""The graph store: one SQLite file per graph. Standard library only.

What it keeps:

- sources: every piece of material read, with a hash, who added it and how.
- chunks: the numbered pieces of each source, so every edge can cite its words.
- nodes: concepts, keyed by a normalised label, with an open `type` (concept, person,
  claim, evidence, hypothesis, decision, question, artifact, agent, session, ...).
- edges: typed, directed relations with a description, weight, confidence, provenance
  (source, chunk, agent, session, method) and a validity window (valid_from, valid_to).
  Nothing is deleted; superseding an edge closes its window, so the history stays.
- mentions: which chunks mention which nodes, for evidence and contextual proximity.
- conflicts and reports: judgments recorded by `reconcile` and `report`.
- events: an append-only log of every change, read by `events` and the live view.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from .errors import INPUT, SETUP, ToolError, not_found
from .text import node_key, sha256

FORMAT = "knowledge-graph/1"
SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY, uri TEXT, title TEXT, kind TEXT, sha256 TEXT, chars INTEGER,
  method TEXT, agent TEXT, session TEXT, ingested_at TEXT, replaced_by TEXT);
CREATE TABLE IF NOT EXISTS chunks (
  id TEXT PRIMARY KEY, source_id TEXT, idx INTEGER, text TEXT, extracted_at TEXT);
CREATE TABLE IF NOT EXISTS nodes (
  id TEXT PRIMARY KEY, label TEXT, type TEXT, summary TEXT, attrs TEXT,
  created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS mentions (
  node_id TEXT, chunk_id TEXT, count INTEGER DEFAULT 1, PRIMARY KEY (node_id, chunk_id));
CREATE TABLE IF NOT EXISTS edges (
  id TEXT PRIMARY KEY, source TEXT, target TEXT, relation TEXT, description TEXT,
  weight REAL, confidence REAL, source_id TEXT, chunk_id TEXT, agent TEXT, session TEXT,
  method TEXT, evidence TEXT, valid_from TEXT, valid_to TEXT, invalidated_by TEXT,
  created_at TEXT, attrs TEXT);
CREATE TABLE IF NOT EXISTS conflicts (
  id TEXT PRIMARY KEY, edge_a TEXT, edge_b TEXT, verdict TEXT, reason TEXT, agent TEXT,
  created_at TEXT);
CREATE TABLE IF NOT EXISTS reports (
  id TEXT PRIMARY KEY, members TEXT, title TEXT, summary TEXT, findings TEXT, agent TEXT,
  created_at TEXT);
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, kind TEXT, data TEXT);
CREATE INDEX IF NOT EXISTS edges_source ON edges(source);
CREATE INDEX IF NOT EXISTS edges_target ON edges(target);
CREATE INDEX IF NOT EXISTS mentions_chunk ON mentions(chunk_id);
CREATE INDEX IF NOT EXISTS chunks_source ON chunks(source_id);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS search_nodes USING fts5(id UNINDEXED, label, summary);
CREATE VIRTUAL TABLE IF NOT EXISTS search_chunks USING fts5(id UNINDEXED, text);
"""


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(value: str | None) -> str | None:
    """Accept a date or a date-time; return the stored UTC form. None stays None."""
    if value in (None, ""):
        return None
    text = str(value).strip()
    if text.lower() == "now":
        return now()
    try:
        if len(text) == 10:
            dt = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ToolError("invalid_input", f"\"{value}\" is not a date.",
                        hint="Use a date like 2026-03-01 or a time like 2026-03-01T14:00:00Z.") from None


# --- where graphs live ----------------------------------------------------------------------

def data_home() -> Path:
    """The per-user folder for graphs: KNOWLEDGE_HOME, else the platform's data folder."""
    if os.environ.get("KNOWLEDGE_HOME"):
        return Path(os.environ["KNOWLEDGE_HOME"]).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "knowledge"
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home())) / "knowledge"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "knowledge"


def graph_path(graph: str | os.PathLike | None = None) -> Path:
    """A graph name (`research`) lives in the data folder; a path (`./x.db`) is used as given."""
    name = str(graph or os.environ.get("KNOWLEDGE_GRAPH") or "default")
    if name == ":memory:":
        return Path(name)
    if "/" in name or "\\" in name or name.endswith((".db", ".sqlite", ".sqlite3")):
        return Path(name).expanduser()
    if not all(c.isalnum() or c in "-_." for c in name):
        raise ToolError("invalid_input", f"\"{name}\" is not a usable graph name.",
                        hint="Use letters, digits, - and _, or pass a path ending in .db.")
    return data_home() / "graphs" / f"{name}.db"


def list_graphs() -> list[dict]:
    folder = data_home() / "graphs"
    if not folder.is_dir():
        return []
    out = []
    for f in sorted(folder.glob("*.db")):
        out.append({"name": f.stem, "path": str(f), "bytes": f.stat().st_size,
                    "modified": datetime.fromtimestamp(f.stat().st_mtime, timezone.utc)
                    .strftime("%Y-%m-%dT%H:%M:%SZ")})
    return out


def open_graph(graph: str | os.PathLike | None = None, *, create: bool = True) -> "Graph":
    return Graph(graph_path(graph), create=create)


class Graph:
    """A knowledge graph backed by one SQLite file."""

    def __init__(self, path: str | os.PathLike, *, create: bool = True):
        self.path = Path(path)
        memory = str(path) == ":memory:"
        if not memory and not self.path.exists():
            if not create:
                raise ToolError("graph_not_found", f"There is no graph at {self.path}.",
                                hint="Run `knowledge graphs` to list graphs, or ingest something first.")
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise ToolError("no_write_access", f"Cannot create {self.path.parent}: {exc}.",
                                hint="Set KNOWLEDGE_HOME to a folder you can write, or pass --graph ./x.db.",
                                exit_code=SETUP) from None
        self.db = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL" if not memory else "PRAGMA journal_mode=MEMORY")
        self.db.executescript(SCHEMA)
        try:
            self.db.executescript(FTS_SCHEMA)
            self.fts = True
        except sqlite3.OperationalError:
            self.fts = False
        if self.meta("format") is None:
            self.set_meta("format", FORMAT)
            self.set_meta("schema_version", str(SCHEMA_VERSION))
            self.set_meta("created_at", now())
        self.db.commit()

    @property
    def name(self) -> str:
        return "memory" if str(self.path) == ":memory:" else self.path.stem

    def close(self) -> None:
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # --- meta and events ---

    def meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))

    def emit(self, kind: str, data: dict) -> None:
        self.db.execute("INSERT INTO events (at, kind, data) VALUES (?, ?, ?)",
                        (now(), kind, json.dumps(data, ensure_ascii=False)))

    def events(self, since: int = 0, limit: int = 1000) -> list[dict]:
        rows = self.db.execute("SELECT * FROM events WHERE seq > ? ORDER BY seq LIMIT ?", (since, limit))
        return [{"seq": r["seq"], "at": r["at"], "kind": r["kind"], **json.loads(r["data"])} for r in rows]

    def last_event(self) -> int:
        row = self.db.execute("SELECT MAX(seq) FROM events").fetchone()
        return row[0] or 0

    def commit(self) -> None:
        self.db.commit()

    # --- sources and chunks ---

    def source_by_sha(self, digest: str) -> dict | None:
        row = self.db.execute("SELECT * FROM sources WHERE sha256=? ORDER BY ingested_at DESC", (digest,)).fetchone()
        return dict(row) if row else None

    def sources_by_uri(self, uri: str) -> list[dict]:
        rows = self.db.execute("SELECT * FROM sources WHERE uri=? AND replaced_by IS NULL", (uri,))
        return [dict(r) for r in rows]

    def add_source(self, *, uri: str, title: str, text: str, kind: str = "text", method: str = "",
                   agent: str = "", session: str = "", at: str | None = None) -> dict:
        digest = sha256(text)
        sid = "s-" + digest[:12]
        n = 1
        while self.db.execute("SELECT 1 FROM sources WHERE id=?", (sid,)).fetchone():
            n += 1
            sid = f"s-{digest[:12]}-{n}"
        row = {"id": sid, "uri": uri, "title": title, "kind": kind, "sha256": digest, "chars": len(text),
               "method": method, "agent": agent, "session": session, "ingested_at": at or now(),
               "replaced_by": None}
        self.db.execute("INSERT INTO sources VALUES (:id,:uri,:title,:kind,:sha256,:chars,:method,:agent,"
                        ":session,:ingested_at,:replaced_by)", row)
        self.emit("source_added", {"source": sid, "uri": uri, "title": title, "agent": agent})
        return row

    def add_chunk(self, source_id: str, idx: int, text: str) -> str:
        cid = f"{source_id}#{idx}"
        self.db.execute("INSERT OR REPLACE INTO chunks VALUES (?, ?, ?, ?, NULL)", (cid, source_id, idx, text))
        if self.fts:
            self.db.execute("INSERT INTO search_chunks (id, text) VALUES (?, ?)", (cid, text))
        return cid

    def chunk(self, cid: str) -> dict | None:
        row = self.db.execute("SELECT * FROM chunks WHERE id=?", (cid,)).fetchone()
        return dict(row) if row else None

    def chunks_of(self, source_id: str) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM chunks WHERE source_id=? ORDER BY idx", (source_id,))]

    def mark_extracted(self, cid: str) -> None:
        self.db.execute("UPDATE chunks SET extracted_at=? WHERE id=?", (now(), cid))

    def source(self, sid: str) -> dict | None:
        row = self.db.execute("SELECT * FROM sources WHERE id=?", (sid,)).fetchone()
        return dict(row) if row else None

    def sources(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM sources ORDER BY ingested_at")]

    def replace_source(self, old_id: str, new_id: str, at: str) -> int:
        """A newer version of the same material arrived: close the windows of the old version's edges."""
        self.db.execute("UPDATE sources SET replaced_by=? WHERE id=?", (new_id, old_id))
        rows = self.db.execute("SELECT id FROM edges WHERE source_id=? AND valid_to IS NULL", (old_id,)).fetchall()
        for r in rows:
            self.db.execute("UPDATE edges SET valid_to=?, invalidated_by=? WHERE id=?", (at, f"source:{new_id}", r[0]))
        self.emit("source_replaced", {"source": old_id, "by": new_id, "edges_closed": len(rows)})
        return len(rows)

    # --- nodes ---

    def upsert_node(self, label: str, *, type: str | None = None, summary: str | None = None,
                    attrs: dict | None = None, at: str | None = None) -> str:
        key = node_key(label)
        if not key:
            raise ToolError("invalid_input", "A node needs a label with at least one letter or digit.")
        stamp = at or now()
        row = self.db.execute("SELECT * FROM nodes WHERE id=?", (key,)).fetchone()
        if row is None:
            self.db.execute("INSERT INTO nodes VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (key, str(label).strip(), type or "concept", summary or "",
                             json.dumps(attrs or {}), stamp, stamp))
            if self.fts:
                self.db.execute("INSERT INTO search_nodes (id, label, summary) VALUES (?, ?, ?)",
                                (key, str(label).strip(), summary or ""))
            self.emit("node_added", {"node": key, "label": str(label).strip(), "type": type or "concept"})
            return key
        changed = {}
        # a more specific type wins over the default; a new summary replaces an empty one or is appended
        if type and type != row["type"] and (row["type"] == "concept" or type != "concept"):
            changed["type"] = type
        if summary and summary not in (row["summary"] or ""):
            changed["summary"] = summary if not row["summary"] else row["summary"] + " " + summary
        if attrs:
            merged = {**json.loads(row["attrs"] or "{}"), **attrs}
            changed["attrs"] = json.dumps(merged)
        if changed:
            sets = ", ".join(f"{k}=?" for k in changed)
            self.db.execute(f"UPDATE nodes SET {sets}, updated_at=? WHERE id=?", (*changed.values(), stamp, key))
            if self.fts and "summary" in changed:
                self.db.execute("DELETE FROM search_nodes WHERE id=?", (key,))
                self.db.execute("INSERT INTO search_nodes (id, label, summary) VALUES (?, ?, ?)",
                                (key, row["label"], changed["summary"]))
            self.emit("node_updated", {"node": key, "fields": sorted(changed)})
        return key

    def node(self, key: str) -> dict | None:
        row = self.db.execute("SELECT * FROM nodes WHERE id=?", (key,)).fetchone()
        if not row:
            return None
        out = dict(row)
        out["attrs"] = json.loads(out["attrs"] or "{}")
        return out

    def nodes(self) -> list[dict]:
        out = []
        for row in self.db.execute("SELECT * FROM nodes ORDER BY id"):
            d = dict(row)
            d["attrs"] = json.loads(d["attrs"] or "{}")
            out.append(d)
        return out

    def resolve(self, name: str) -> str:
        """Find a node by label: exact, then a unique prefix or word match, else fail with suggestions."""
        key = node_key(name)
        if self.db.execute("SELECT 1 FROM nodes WHERE id=?", (key,)).fetchone():
            return key
        like = self.db.execute(
            "SELECT n.id, (SELECT COUNT(*) FROM edges e WHERE e.source=n.id OR e.target=n.id) AS deg "
            "FROM nodes n WHERE n.id LIKE ? ORDER BY deg DESC, length(n.id) LIMIT 8", (f"%{key}%",)).fetchall()
        if len(like) == 1:
            return like[0]["id"]
        exactish = [r["id"] for r in like if r["id"].startswith(key + " ") or r["id"].endswith(" " + key)]
        if len(exactish) == 1:
            return exactish[0]
        suggestions = [r["id"] for r in like]
        if not suggestions:
            words = [w for w in key.split() if len(w) > 2]
            for w in words:
                suggestions += [r[0] for r in self.db.execute(
                    "SELECT id FROM nodes WHERE id LIKE ? LIMIT 5", (f"%{w}%",))]
        raise not_found("concept", name, list(dict.fromkeys(suggestions))[:8])

    def mention(self, node_id: str, chunk_id: str, count: int = 1) -> None:
        self.db.execute("INSERT INTO mentions VALUES (?, ?, ?) ON CONFLICT(node_id, chunk_id) "
                        "DO UPDATE SET count = count + excluded.count", (node_id, chunk_id, count))

    # --- edges ---

    def add_edge(self, source: str, target: str, relation: str, *, description: str = "",
                 weight: float = 1.0, confidence: float | None = None, source_id: str | None = None,
                 chunk_id: str | None = None, agent: str = "", session: str = "", method: str = "",
                 evidence: str = "", valid_from: str | None = None, valid_to: str | None = None,
                 attrs: dict | None = None) -> str:
        """Add one relation. The same relation from the same chunk is stored once (its weight grows)."""
        relation = normalise_relation(relation)
        if source == target:
            raise ToolError("invalid_input", f"An edge needs two different nodes (got \"{source}\" twice).")
        for key in (source, target):
            if not self.db.execute("SELECT 1 FROM nodes WHERE id=?", (key,)).fetchone():
                raise not_found("concept", key)
        if confidence is not None:
            confidence = max(0.0, min(1.0, float(confidence)))
        stamp = now()
        ident = "e-" + sha256("|".join([source, target, relation, description, source_id or "", chunk_id or "",
                                        agent, valid_from or ""]))[:12]
        existing = self.db.execute("SELECT id FROM edges WHERE id=?", (ident,)).fetchone()
        if existing:
            self.db.execute("UPDATE edges SET weight = weight + ? WHERE id=?", (weight, ident))
            return ident
        self.db.execute(
            "INSERT INTO edges VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ident, source, target, relation, description, weight, confidence, source_id, chunk_id, agent, session,
             method, evidence, parse_time(valid_from) or stamp, parse_time(valid_to), None, stamp,
             json.dumps(attrs or {})))
        self.emit("edge_added", {"edge": ident, "source": source, "target": target, "relation": relation,
                                 "description": description[:200], "agent": agent, "method": method})
        return ident

    def edge(self, ident: str) -> dict | None:
        row = self.db.execute("SELECT * FROM edges WHERE id=?", (ident,)).fetchone()
        return _edge_row(row) if row else None

    def edges(self, *, as_of: str | None = None, include_closed: bool = False, node: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM edges WHERE 1=1", []
        if node:
            sql += " AND (source=? OR target=?)"
            args += [node, node]
        if as_of:
            sql += " AND valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)"
            args += [as_of, as_of]
        elif not include_closed:
            sql += " AND valid_to IS NULL"
        sql += " ORDER BY valid_from, id"
        return [_edge_row(r) for r in self.db.execute(sql, args)]

    def supersede(self, ident: str, *, by: str | None = None, at: str | None = None, reason: str = "",
                  agent: str = "") -> dict:
        row = self.edge(ident)
        if not row:
            raise not_found("edge", ident)
        if row["valid_to"]:
            raise ToolError("already_closed", f"Edge {ident} was already closed at {row['valid_to']}.",
                            hint="See its history with: knowledge timeline \"" + row["source"] + "\"")
        if by and not self.edge(by):
            raise not_found("edge", by)
        stamp = parse_time(at) or now()
        marker = f"edge:{by}" if by else (f"note:{reason}" if reason else "closed")
        self.db.execute("UPDATE edges SET valid_to=?, invalidated_by=? WHERE id=?", (stamp, marker, ident))
        self.emit("edge_superseded", {"edge": ident, "by": by, "reason": reason, "agent": agent,
                                      "source": row["source"], "target": row["target"], "relation": row["relation"]})
        return {**row, "valid_to": stamp, "invalidated_by": marker}

    # --- conflicts and reports ---

    def add_conflict(self, edge_a: str, edge_b: str, verdict: str, reason: str, agent: str = "") -> str:
        ident = "c-" + sha256(f"{edge_a}|{edge_b}|{verdict}")[:12]
        self.db.execute("INSERT OR REPLACE INTO conflicts VALUES (?,?,?,?,?,?,?)",
                        (ident, edge_a, edge_b, verdict, reason, agent, now()))
        self.emit("conflict_recorded", {"conflict": ident, "edge_a": edge_a, "edge_b": edge_b, "verdict": verdict})
        return ident

    def conflicts(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM conflicts ORDER BY created_at")]

    def add_report(self, members: list[str], title: str, summary: str, findings: list[str], agent: str = "") -> str:
        ident = "r-" + sha256("|".join(sorted(members)))[:12]
        self.db.execute("INSERT OR REPLACE INTO reports VALUES (?,?,?,?,?,?,?)",
                        (ident, json.dumps(sorted(members)), title, summary, json.dumps(findings), agent, now()))
        self.emit("report_saved", {"report": ident, "title": title})
        return ident

    def reports(self) -> list[dict]:
        out = []
        for r in self.db.execute("SELECT * FROM reports ORDER BY created_at"):
            d = dict(r)
            d["members"] = json.loads(d["members"])
            d["findings"] = json.loads(d["findings"] or "[]")
            out.append(d)
        return out

    # --- reading ---

    def mentions_of(self, node_id: str, limit: int = 20) -> list[dict]:
        rows = self.db.execute(
            "SELECT m.chunk_id, m.count, c.text, c.source_id, s.uri, s.title FROM mentions m "
            "JOIN chunks c ON c.id=m.chunk_id LEFT JOIN sources s ON s.id=c.source_id "
            "WHERE m.node_id=? ORDER BY m.count DESC, m.chunk_id LIMIT ?", (node_id, limit))
        return [dict(r) for r in rows]

    def chunk_members(self) -> dict[str, list[str]]:
        """Chunk id -> nodes mentioned in it, for chunks whose source was read for meaning (not word windows)."""
        rows = self.db.execute(
            "SELECT m.chunk_id, m.node_id FROM mentions m JOIN chunks c ON c.id=m.chunk_id "
            "JOIN sources s ON s.id=c.source_id WHERE s.method != 'cooccurrence' AND s.replaced_by IS NULL")
        out: dict[str, list[str]] = {}
        for r in rows:
            out.setdefault(r[0], []).append(r[1])
        return out

    def counts(self) -> dict:
        q = lambda sql: self.db.execute(sql).fetchone()[0]  # noqa: E731
        return {
            "nodes": q("SELECT COUNT(*) FROM nodes"),
            "edges": q("SELECT COUNT(*) FROM edges WHERE valid_to IS NULL"),
            "closed_edges": q("SELECT COUNT(*) FROM edges WHERE valid_to IS NOT NULL"),
            "sources": q("SELECT COUNT(*) FROM sources"),
            "chunks": q("SELECT COUNT(*) FROM chunks"),
            "conflicts": q("SELECT COUNT(*) FROM conflicts"),
            "reports": q("SELECT COUNT(*) FROM reports"),
            "events": q("SELECT COUNT(*) FROM events"),
        }


def _edge_row(row) -> dict:
    d = dict(row)
    d["attrs"] = json.loads(d.get("attrs") or "{}")
    return d


def normalise_relation(relation: str) -> str:
    rel = "_".join(str(relation or "").strip().lower().replace("-", " ").split())
    rel = "".join(c for c in rel if c.isalnum() or c == "_")[:60]
    if not rel:
        raise ToolError("invalid_input", "An edge needs a relation, such as supports or depends_on.",
                        exit_code=INPUT)
    return rel
