"""Self-description: the manifest, the tool's skill, and one skill per capability.

Available with no credentials and without loading any provider. The CLI prints these and
adds nothing; the MCP server builds its tool list from the same table.
"""

from __future__ import annotations

import re
from importlib.metadata import PackageNotFoundError
from importlib.metadata import metadata as _metadata
from importlib.resources import files

NAME = "knowledge"
VERSION = "0.3.0"
DISTRIBUTION = "amplifier-smart-tool-visualizer"

_PROVIDER_ARGS = ("--provider / --model / --complete-cmd",
                  "Which model answers. Without these: KNOWLEDGE_PROVIDER, then the agent harness you run in "
                  "(stops with host_model, no key billed), then ANTHROPIC_API_KEY or OPENAI_API_KEY.")
_GRAPH_ARG = ("--graph", "Graph name (kept in the per-user data folder) or a path ending in .db. "
              "Default: KNOWLEDGE_GRAPH, else \"default\".")
_ASOF_ARG = ("--as-of", "Read the graph as it was at this date or time (relations valid then).")

CAPABILITIES: dict[str, dict] = {
    "ingest": {
        "kind": "model-backed",
        "summary": "Read files, folders, pages or text into the graph (deterministic with --method cooccurrence or agent).",
        "when": "To add material: notes, papers, docs, code, agent session logs (.jsonl), a web page. "
        "The default method, llm, has a model extract typed concepts and relations from each 1500-character "
        "chunk. --method cooccurrence builds a word network with no model (same answer every time). "
        "--method agent stores the chunks and returns them with the extraction prompt, so the calling "
        "agent extracts the relations itself and loads them with `add`; no model call happens in the tool. "
        "Material already read is skipped; a changed file closes the relations from its old version.",
        "args": [
            ("target", "Files or folders (walked, skipping hidden and build folders), a web address "
             "(with --allow-network), or - for standard input."),
            ("--text", "Text to read instead of a file."),
            ("--method", "llm (default, model-backed), cooccurrence or agent (both deterministic)."),
            ("--title / --uri", "Name and address to record for --text or stdin."),
            ("--agent / --session", "Who is adding this, recorded on every relation (provenance)."),
            ("--at", "When the material is valid from (default: now). A date or date-time."),
            ("--chunk-size / --overlap", "Characters per chunk (default 1500) and overlap (default 150)."),
            ("--max-chunks", "Read at most this many chunks per document (to try it cheaply)."),
            ("--min-count", "cooccurrence: keep words seen at least this often (default 1, or 2 for long texts)."),
            ("--workers", "Model calls in parallel (default 4)."),
            ("--allow-network", "Let the tool fetch a web address itself."),
            ("--force", "Read again even if this exact text was read before."),
            _PROVIDER_ARGS, _GRAPH_ARG,
        ],
        "example": "knowledge ingest ./notes --graph research\n"
                   "knowledge ingest paper.md --method agent --json   # inside an agent: you extract\n"
                   "knowledge ingest ./docs --method cooccurrence      # no model",
        "result": "{graph, method, model, sources: [{id, uri, title, status: added|replaced|unchanged|resumed, "
                  "chunks}], nodes_added, edges_added, totals}. With --method agent also task: {do, system, "
                  "format, chunks: [{id, text}]}.",
        "fails": "Empty material (exit 1); no model set up for --method llm (exit 3, names the deterministic "
                 "routes); inside an agent harness with no provider chosen (exit 3, host_model); some chunks "
                 "unreadable by the model (exit 4: the rest are kept, failed_chunks lists the others, run again "
                 "to retry only those).",
    },
    "add": {
        "kind": "deterministic",
        "summary": "Load concepts and relations from JSON (what an agent extracted or decided).",
        "when": "After `ingest --method agent`, or whenever an agent or person has relations to record: "
        "claims, evidence, decisions, contradictions. The single write path for agents.",
        "args": [
            ("file", "A JSON file, or - for standard input. Shape: {source?, agent?, session?, nodes: [{label, "
             "type?, summary?}], edges: [{from, to, relation, description?, confidence?, chunk?, evidence?, "
             "from_type?, to_type?, valid_from?, valid_to?}], supersede: [{edge, by?, reason?}]}. A bare list "
             "of edges works, and {node_1, node_2, edge} items are read too."),
            ("--agent / --session", "Provenance, when the JSON does not say."),
            ("--at", "When these relations hold from (default: now)."),
            _GRAPH_ARG,
        ],
        "example": "knowledge add relations.json --agent researcher\n"
                   "echo '[{\"from\":\"delegation\",\"to\":\"perceived agency\",\"relation\":\"reduces\"}]' | knowledge add -",
        "result": "{graph, nodes: [id], edges: [id], skipped: [{item, why}], totals}.",
        "fails": "Bad JSON (exit 1); nothing usable in it (exit 1, skipped says why); a chunk id that is not "
                 "in this graph is skipped with a reason.",
    },
    "relate": {
        "kind": "deterministic",
        "summary": "Add one relation: SOURCE RELATION TARGET.",
        "when": "To record one claim, link or decision by hand. Creates either concept if new. With "
        "--supersedes, the older relation is closed in favour of this one (history is kept).",
        "args": [
            ("source relation target", "For example: \"delegation\" reduces \"perceived agency\"."),
            ("--description", "One sentence on the relation."),
            ("--confidence", "0 to 1."),
            ("--source-type / --target-type", "claim, evidence, hypothesis, decision, question, person, ..."),
            ("--evidence", "A quote or reference backing it."),
            ("--supersedes", "An edge id this relation replaces."),
            ("--agent / --session / --at", "Provenance and when it holds from."),
            _GRAPH_ARG,
        ],
        "example": "knowledge relate \"experiment 14\" supports \"delegation reduces agency\" --source-type evidence "
                   "--target-type claim --confidence 0.7 --agent researcher",
        "result": "{graph, edge: {id, source, relation, target, ...}, superseded?}.",
        "fails": "A missing part (exit 2); an unknown --supersedes edge (exit 1).",
    },
    "supersede": {
        "kind": "deterministic",
        "summary": "Close a relation (it stays in the history), optionally naming what replaced it.",
        "when": "When something stopped being true or was corrected. Reads with --as-of before the close "
        "still see it; current reads do not.",
        "args": [("edge", "The edge id (from show, timeline or add)."), ("--by", "The edge id that replaces it."),
                 ("--reason", "Why."), ("--at", "When it stopped holding (default: now)."), ("--agent", "Who closed it."),
                 _GRAPH_ARG],
        "example": "knowledge supersede e-1a2b3c4d5e6f --by e-6f5e4d3c2b1a --reason \"newer measurement\"",
        "result": "{graph, edge} with valid_to and invalidated_by set.",
        "fails": "Unknown edge (exit 1); already closed (exit 1).",
    },
    "search": {
        "kind": "deterministic",
        "summary": "Find concepts by name, summary and the passages that mention them.",
        "when": "To find the right name before show, path or evidence, or to see what the graph knows about a word.",
        "args": [("query", "Words to look for."), ("--limit", "Most concepts to return (default 10)."), _GRAPH_ARG],
        "example": "knowledge search \"human agency\"",
        "result": "{query, nodes: [{id, label, type, summary, degree, score, matched}], passages: [{chunk, source, "
                  "uri, snippet}]}.",
        "fails": "No query (exit 2); no such graph (exit 1).",
    },
    "show": {
        "kind": "deterministic",
        "summary": "One concept: every relation in and out, with provenance, and where it is mentioned.",
        "when": "To look at a concept closely: what it says, what is said about it, by which agent, from which source.",
        "args": [("concept", "A concept's name (a unique part of it works)."), _ASOF_ARG,
                 ("--limit", "Most relations per direction (default 50)."), _GRAPH_ARG],
        "example": "knowledge show \"delegation\"",
        "result": "{node, degree, outgoing: [edge], incoming: [edge], neighbours, mentions: [{chunk, source, excerpt}]}. "
                  "Each edge: {id, source, relation, target, description, confidence, valid_from, valid_to, agent, "
                  "method, chunk, from_source}.",
        "fails": "Unknown concept (exit 1, with suggestions).",
    },
    "path": {
        "kind": "deterministic",
        "summary": "How two concepts connect: up to three independent paths, each step explained.",
        "when": "To trace reasoning across the graph: from a method to an outcome, a claim to its evidence, "
        "two ideas that seem unrelated.",
        "args": [("source target", "Two concepts."), ("--k", "Most paths (default 3); paths share no middle concept."),
                 _ASOF_ARG, _GRAPH_ARG],
        "example": "knowledge path \"prepared actions\" \"human agency\"",
        "result": "{from, to, connected, paths: [{nodes, hops, steps: [{from, to, relations, shared_passages}]}]}.",
        "fails": "Unknown concept (exit 1). Not connected is a normal result (connected: false, with a note).",
    },
    "timeline": {
        "kind": "deterministic",
        "summary": "Everything ever said about a concept, in time order, including closed relations.",
        "when": "To see how understanding changed: what was believed, when, and what replaced it.",
        "args": [("concept", "A concept."), _GRAPH_ARG],
        "example": "knowledge timeline \"recursive self-improvement\"",
        "result": "{node, entries: [{at, event: first seen|relation added|relation closed|conflict recorded, ...}], "
                  "current, closed}.",
        "fails": "Unknown concept (exit 1).",
    },
    "evidence": {
        "kind": "deterministic",
        "summary": "What backs a concept or an edge: passages, sources, supporting and contradicting relations.",
        "when": "Before trusting a claim, or to cite it.",
        "args": [("target", "A concept, or an edge id (e-...)."), _GRAPH_ARG],
        "example": "knowledge evidence \"delegation reduces agency\"",
        "result": "Concept: {node, supporting, contradicting, passages, sources}. Edge: {edge, quote, passage, "
                  "source, conflicts}.",
        "fails": "Unknown concept or edge (exit 1).",
    },
    "contradictions": {
        "kind": "deterministic",
        "summary": "Where the graph disagrees with itself: explicit, recorded, candidate and superseded.",
        "when": "To find tension in accumulated work. Candidates are opposite relations (supports / contradicts, "
        "increases / decreases) or a negated description between the same two concepts; `reconcile` asks a model "
        "to judge them.",
        "args": [("concept", "Optional: only around this concept."), _ASOF_ARG, ("--limit", "Most per list (default 50)."),
                 _GRAPH_ARG],
        "example": "knowledge contradictions \"agency\"",
        "result": "{explicit: [edge], recorded: [conflict], candidates: [{pair, why, a, b}], superseded: [edge], next}.",
        "fails": "Unknown concept (exit 1).",
    },
    "communities": {
        "kind": "deterministic",
        "summary": "Topics: groups of concepts linked more to each other than to the rest.",
        "when": "To see the main themes and their central concepts. Louvain by default; girvan-newman (the "
        "original notebook's method) for small graphs.",
        "args": [("--method", "louvain (default) or girvan-newman."), ("--resolution", "Louvain: above 1 gives smaller topics."),
                 ("--no-proximity", "Ignore shared-passage links; use typed relations only."),
                 ("--members", "Concepts listed per topic (default 12)."), _ASOF_ARG, _GRAPH_ARG],
        "example": "knowledge communities",
        "result": "{method, modularity, diversity: {state, advice}, communities: [{id, label, size, top, report?}], isolated}.",
        "fails": "girvan-newman on more than 1500 edges (exit 1: use louvain).",
    },
    "analyze": {
        "kind": "deterministic",
        "summary": "One overview: most influential concepts, bridges, topics, diversity, biggest gaps.",
        "when": "First look at a graph, or a periodic check of how a body of knowledge is shaped.",
        "args": [("--top", "How many per list (default 10)."), ("--no-proximity", "Typed relations only."), _ASOF_ARG,
                 _GRAPH_ARG],
        "example": "knowledge analyze",
        "result": "{size, most_influential (betweenness), most_connected, bridges, communities, diversity, gaps}.",
        "fails": "No such graph (exit 1).",
    },
    "gaps": {
        "kind": "deterministic",
        "summary": "Structural gaps: developed topics with little between them, or how far apart two concepts are.",
        "when": "To find what nobody has connected yet: a list of research directions. Score 1 means no link at "
        "all between two topics; the bridge candidates are each topic's most central concepts.",
        "args": [("--between", "Two concepts to compare instead (gives hops, shared neighbours and a verdict)."),
                 ("--top", "Most gaps (default 5)."), _ASOF_ARG, _GRAPH_ARG],
        "example": "knowledge gaps\nknowledge gaps --between \"human agency\" \"inference cost\"",
        "result": "{gaps: [{between, topics, score, observed_weight, expected_weight, size, bridge_candidates, prompt}]} "
                  "or, with --between, {verdict, hops, same_topic, direct_relations, shared_neighbours, topics, path}.",
        "fails": "Unknown concept (exit 1).",
    },
    "context": {
        "kind": "deterministic",
        "summary": "The numbered context a model needs to answer a question from the graph (no model call).",
        "when": "When you are the model: get the concepts, strongest relations, passages and topic reports for a "
        "question, numbered for citation, then answer yourself. Assembled by code, so the same question gets the "
        "same context.",
        "args": [("query", "The question."), ("--budget", "Most characters (default 12000)."), _ASOF_ARG, _GRAPH_ARG],
        "example": "knowledge context \"does delegation reduce agency?\" --json",
        "result": "{query, seeds, citations: [{n, kind: concept|relation|passage|report, text, ...}], text, chars, empty}.",
        "fails": "No such graph (exit 1). Nothing matching is a normal result (empty: true).",
    },
    "ask": {
        "kind": "model-backed",
        "summary": "Answer a question from the graph, citing the relations and passages used.",
        "when": "Graph-augmented answering for a person, or for an agent that wants the tool's model to do it. "
        "Inside an agent, prefer `context` and answer yourself.",
        "args": [("question", "The question."), ("--budget", "Context size in characters (default 12000)."), _ASOF_ARG,
                 _PROVIDER_ARGS, _GRAPH_ARG],
        "example": "knowledge ask \"what contradicts the claim that delegation reduces agency?\"",
        "result": "{question, answer, model, citations: [{n, kind, text, ...}], context_size}.",
        "fails": "Nothing in the graph matches (exit 1); no model set up (exit 3); the call failed (exit 4).",
    },
    "report": {
        "kind": "model-backed",
        "summary": "Name and summarise the biggest topics (community reports), saved for the view and context.",
        "when": "After a large ingest, so topics have readable names and summaries.",
        "args": [("--top", "How many topics (default 5)."), ("--no-save", "Return without saving."), _ASOF_ARG,
                 _PROVIDER_ARGS, _GRAPH_ARG],
        "example": "knowledge report --top 8",
        "result": "{model, reports: [{community, size, top, title, summary, findings, id?}], saved}.",
        "fails": "No model set up (exit 3); the call failed or the reply stayed unusable (exit 4).",
    },
    "questions": {
        "kind": "model-backed",
        "summary": "Turn structural gaps into research questions that would bridge them.",
        "when": "To generate hypotheses from what is missing. With --save, each question becomes a question node "
        "linked (bridges) to the concepts it would connect.",
        "args": [("--between", "Two concepts, instead of the graph's own gaps."), ("--top", "Gaps to use (default 3)."),
                 ("--per-gap", "Questions per gap (default 2)."), ("--save", "Add the questions to the graph."),
                 _ASOF_ARG, _PROVIDER_ARGS, _GRAPH_ARG],
        "example": "knowledge questions --save",
        "result": "{model, gaps, questions: [{gap, question, why, bridges}], saved: [node id]}.",
        "fails": "No gaps (exit 1); no model set up (exit 3); the call failed (exit 4).",
    },
    "reconcile": {
        "kind": "model-backed",
        "summary": "Judge conflict candidates; record contradictions and close relations that newer ones replace.",
        "when": "After new material arrives about something already in the graph, so old beliefs are marked as "
        "contradicted or superseded instead of silently sitting beside new ones.",
        "args": [("--concept", "Only around this concept."), ("--limit", "Most pairs (default 20)."),
                 ("--dry-run", "Judge but do not write."), _PROVIDER_ARGS, _GRAPH_ARG],
        "example": "knowledge reconcile --concept \"agency\"",
        "result": "{model, judged: [{a, b, verdict: contradicts|supersedes|compatible, reason, closed?}], applied}.",
        "fails": "No model set up (exit 3); the call failed (exit 4).",
    },
    "visualize": {
        "kind": "deterministic",
        "summary": "Write one self-contained interactive page: map, timeline, argument, steps, matrix and rhythm views.",
        "when": "To explore by eye or share a snapshot. Pass the person's question with --for and the view opens on the "
        "form that answers it and says why: a timeline for what changed, an argument for whether a claim holds, steps for how "
        "two ideas connect, a matrix for what is missing, a rhythm for when things were written, or the map; "
        "if the question does not say enough, it stops with needs_clarification and a question to ask them instead of "
        "guessing. No outside requests; opens from disk. Size shows influence, "
        "colour shows topic, green and red lines are supports and contradicts, dashed lines are closed relations, "
        "the slider replays the graph through time.",
        "args": [("--for", "The person's question, in their words: picks the view that answers it."),
                 ("--lens", "Choose the view yourself: overview, concept, path, evidence, contradictions, history, gaps."),
                 ("--to", "The second concept, for --lens path or gaps."),
                 ("--view", "The form to open on: map, timeline, argument, steps, matrix, rhythm (default: the one that "
                  "fits the question; every view file has all six as tabs)."),
                 ("--out", "File to write (default ./knowledge-GRAPH.html)."), ("--concept", "Only this concept's "
                 "neighbourhood (with --for or --lens: the concept the view is about)."),
                 ("--depth", "Neighbourhood depth with --concept (default 2)."), ("--max-nodes", "Keep the most "
                 "connected (default 1500)."), ("--no-proximity", "Hide shared-passage links."), ("--title", "Page title."),
                 ("--open", "Open it in the browser."), _ASOF_ARG, _GRAPH_ARG],
        "example": "knowledge visualize --for \"how does delegation relate to perceived agency?\" --open\n"
                   "knowledge visualize --lens history --concept \"shipped default\" --as-of 2026-09-26 --open\n"
                   "knowledge visualize --concept \"agency\" --depth 2 --out agency.html",
        "result": "{path, bytes, nodes, edges, topics, truncated}; with --for or --lens also {lens, view, concept, to, as_of, why, "
                  "alternatives: [{label, command}]}.",
        "fails": "The question is unclear (exit 1, needs_clarification: result.question is what to ask the person, "
                 "result.choices gives the command for each answer; ask them, do not pick); unknown lens (exit 2); "
                 "no such graph (exit 1); the file cannot be written (exit 3).",
    },
    "serve": {
        "kind": "deterministic",
        "summary": "Open the live view: the graph updates as agents add to it.",
        "when": "To watch agents work: every ingest, relate, supersede or reconcile from any process appears within "
        "seconds, with a ticker of who did what. Local only (127.0.0.1); runs until stopped.",
        "args": [("--port", "Port (default: a free one)."), ("--open", "Open it in the browser."),
                 ("--max-nodes", "Keep the most connected (default 1500)."), _GRAPH_ARG],
        "example": "knowledge serve --open",
        "result": "Prints {url} (with --json, one line) and serves until Ctrl-C.",
        "fails": "The port is taken (exit 3).",
    },
    "export": {
        "kind": "deterministic",
        "summary": "Write the graph for other tools: json, cytoscape, graphml, csv, obsidian vault, canvas.",
        "when": "To open it in Gephi (graphml), Cytoscape (cytoscape), a spreadsheet (csv), Obsidian (obsidian: one "
        "note per concept with wikilinks, topic notes, a gaps note and a Canvas map), or to hand the full document "
        "to code (json).",
        "args": [("--format", "json (default), cytoscape, graphml, csv, obsidian, canvas."), ("--out", "File or folder."),
                 ("--concept / --depth", "Only a neighbourhood."), _ASOF_ARG, _GRAPH_ARG],
        "example": "knowledge export --format obsidian --out ./vault\nknowledge export --format graphml",
        "result": "{format, path, files, nodes, edges}.",
        "fails": "Unknown format (exit 2); cannot write (exit 3).",
    },
    "events": {
        "kind": "deterministic",
        "summary": "The change log: what was added, closed or judged, by whom, when.",
        "when": "To follow what agents did, or to drive your own live display. --follow streams new events as JSON lines.",
        "args": [("--since", "Only events after this number."), ("--limit", "Most events (default 1000)."),
                 ("--follow", "Keep printing new events until stopped."), _GRAPH_ARG],
        "example": "knowledge events --since 120 --follow",
        "result": "{events: [{seq, at, kind, ...}], last}. With --follow, one event per line.",
        "fails": "No such graph (exit 1).",
    },
    "stats": {
        "kind": "deterministic",
        "summary": "Counts, node types, relation labels and where the graph file is.",
        "when": "To check what is in a graph.",
        "args": [_GRAPH_ARG],
        "example": "knowledge stats",
        "result": "{graph, path, nodes, edges, closed_edges, sources, chunks, conflicts, reports, events, node_types, relations}.",
        "fails": "No such graph (exit 1).",
    },
    "graphs": {
        "kind": "deterministic", "summary": "List the graphs in the per-user data folder.",
        "when": "To find a graph by name.", "args": [],
        "example": "knowledge graphs", "result": "[{name, path, bytes, modified}].", "fails": "Never.",
    },
    "doctor": {
        "kind": "deterministic",
        "summary": "Check the setup and say exactly what to fix. Never calls a model.",
        "when": "After installing, or when something fails.",
        "args": [("--complete-cmd", "A program you plan to route model calls through (looked up, not run)."), _GRAPH_ARG],
        "example": "knowledge doctor",
        "result": "{checks: [{id, status: ok|warn|fail, detail, fix}], ready, summary}.",
        "fails": "Exit 3 when something every user needs is broken.",
    },
    "mcp": {
        "kind": "deterministic",
        "summary": "Serve these capabilities to an MCP host over stdio.",
        "when": "For hosts that speak MCP (Claude Desktop, IDEs, other agents). Model-backed tools return a task for the "
        "calling assistant instead of calling a model, unless KNOWLEDGE_MCP_ALLOW_MODEL=1.",
        "args": [_GRAPH_ARG],
        "example": "knowledge mcp --graph research",
        "result": "Runs until the host closes standard input.",
        "fails": "Never at start.",
    },
    "manifest": {
        "kind": "deterministic",
        "summary": "Print the tool's manifest (what it is, what it needs) as JSON.",
        "when": "To decide whether this is the right tool, or for a catalog.",
        "args": [],
        "example": "knowledge manifest",
        "result": "{smart_tool_format, name, version, description, use_cases, platforms, requires, body, capabilities}.",
        "fails": "Never.",
    },
}

GROUPS = [
    ("Write", ["ingest", "add", "relate", "supersede"]),
    ("Read", ["search", "show", "path", "timeline", "evidence", "context"]),
    ("Analyse", ["analyze", "communities", "gaps", "contradictions"]),
    ("Model-backed", ["ask", "report", "questions", "reconcile"]),
    ("View and share", ["visualize", "serve", "export", "events"]),
    ("Setup", ["stats", "graphs", "doctor", "mcp", "manifest"]),
]


def model_backed() -> list[str]:
    return [k for k, v in CAPABILITIES.items() if v["kind"] == "model-backed"]


# --- manifest -------------------------------------------------------------------------------

def _manifest_text() -> str:
    return files(NAME).joinpath("SMART_TOOL.md").read_text(encoding="utf-8")


def _split(text: str) -> tuple[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("SMART_TOOL.md has no frontmatter")
    end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    return "\n".join(lines[1:end]), "\n".join(lines[end + 1:]).strip()


def parse_frontmatter(text: str) -> dict:
    """A small YAML reader for the manifest's own shape: scalars, folded scalars, lists, lists of maps."""
    out: dict = {}
    lines = text.splitlines()
    i = 0

    def scalar(v: str):
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            return v[1:-1]
        if v in ("true", "false"):
            return v == "true"
        if re.fullmatch(r"-?\d+", v):
            return int(v)
        return v

    def block(start: int, indent: int) -> tuple[str, int]:
        parts = []
        j = start
        while j < len(lines) and (not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip()) >= indent):
            parts.append(lines[j].strip())
            j += 1
        return " ".join(p for p in parts if p), j

    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        key, _, rest = line.partition(":")
        key, rest = key.strip(), rest.strip()
        i += 1
        if rest in (">", ">-", "|", "|-"):
            out[key], i = block(i, 2)
        elif rest:
            out[key] = scalar(rest)
        else:
            items: list = []
            while i < len(lines) and lines[i].lstrip().startswith("- "):
                base = len(lines[i]) - len(lines[i].lstrip())
                first = lines[i].lstrip()[2:]
                i += 1
                if ":" in first and not first.startswith(("'", '"')):
                    entry = {}
                    k, _, v = first.partition(":")
                    pending = [(k.strip(), v.strip())]
                    while i < len(lines) and lines[i].strip() and len(lines[i]) - len(lines[i].lstrip()) > base \
                            and not lines[i].lstrip().startswith("- "):
                        k, _, v = lines[i].strip().partition(":")
                        pending.append((k.strip(), v.strip()))
                        i += 1
                        if v.strip() in (">", ">-", "|", "|-"):
                            text_block, i = block(i, base + 4)
                            pending[-1] = (k.strip(), text_block)
                    for k, v in pending:
                        entry[k] = scalar(v) if v not in (">", ">-") else ""
                    items.append(entry)
                else:
                    items.append(scalar(first))
            out[key] = items
    return out


def manifest() -> dict:
    front, body = _split(_manifest_text())
    data = parse_frontmatter(front)
    data["body"] = body
    data["capabilities"] = {k: v["kind"] for k, v in CAPABILITIES.items()}
    return data


# --- skills ---------------------------------------------------------------------------------

def _repository() -> str | None:
    try:
        meta = _metadata(DISTRIBUTION)
    except PackageNotFoundError:
        return None
    for entry in meta.get_all("Project-URL") or []:
        label, _, url = entry.partition(",")
        if label.strip().lower() in ("repository", "source", "homepage"):
            return url.strip()
    return None


def _head(name: str) -> str:
    out = [f'<skill_content name="{name}">', f"Skill directory: {files(NAME)}"]
    repo = _repository()
    if repo:
        out.append(f"Repository: {repo}")
    out.append("Relative paths in this skill are relative to the skill directory.")
    return "\n".join(out) + "\n\n"


def skill() -> str:
    _, body = _split(_manifest_text())
    caps = []
    for group, names in GROUPS:
        caps.append(f"\n{group}:\n")
        caps += [f"- `{k}` [{CAPABILITIES[k]['kind']}] -- {CAPABILITIES[k]['summary']}" for k in names]
    return (_head(NAME) + f"# {NAME}\n\n" + body + "\n\n## Capabilities\n\n"
            f"Each has its own skill: `{NAME} <capability> --help`.\n" + "\n".join(caps) + "\n\n"
            "<skill_resources>\n  <file>SMART_TOOL.md</file>\n  <file>lib.py</file>\n  <file>store.py</file>\n"
            "  <file>analysis.py</file>\n  <file>docs/graph-format.md</file>\n  <file>docs/cli-contract.md</file>\n"
            "</skill_resources>\n</skill_content>")


def capability_skill(name: str) -> str:
    c = CAPABILITIES[name]
    args = "\n".join(f"- `{a}` -- {d}" for a, d in c["args"]) or "None."
    kind = (" Needs a model and costs tokens; a second run may differ."
            if c["kind"] == "model-backed" else " Runs with no model and no credentials; same input, same result.")
    if name == "ingest":
        kind = (" The default method, llm, needs a model and costs tokens. --method cooccurrence and "
                "--method agent run with no model and no credentials.")
    return (_head(f"{NAME} {name}") + f"# {NAME} {name}\n\n{c['summary']}\n\n**Kind:** {c['kind']}.{kind}\n\n"
            f"## When to use it\n\n{c['when']}\n\n## Arguments\n\n{args}\n\n"
            f"Every command also takes `--json` (one envelope on stdout: {{ok, command, result, files, next}} or "
            f"{{ok: false, error: {{code, message, hint}}, exit_code}}) and `-q` (no progress on stderr).\n\n"
            f"## Example\n\n```\n{c['example']}\n```\n\n## Result\n\n{c['result']}\n\n"
            f"## When it fails\n\n{c['fails']}\n\nExit codes: 0 done, 1 input problem, 2 wrong command line, "
            f"3 set something up first, 4 model call failed, 130 interrupted.\n</skill_content>")


def short_help() -> str:
    lines = [f"usage: {NAME} <capability> [options]      {NAME} {VERSION}", ""]
    for group, names in GROUPS:
        lines.append(f"{group}:")
        for k in names:
            tag = " [model]" if CAPABILITIES[k]["kind"] == "model-backed" else ""
            lines.append(f"  {k:<15}{CAPABILITIES[k]['summary']}{tag}")
        lines.append("")
    lines += ["  -h                       this summary",
              "  --help                   the tool's skill, for an agent driving it",
              f"  {NAME} <capability> --help   one capability in full ( -h for its short form )",
              "  --json                   one JSON envelope on stdout, for scripts and agents"]
    return "\n".join(lines)


def capability_short(name: str, usage: str) -> str:
    c = CAPABILITIES[name]
    return f"{usage.strip()}\n\n{c['summary']} [{c['kind']}]\n\nExample:\n  " + c["example"].replace("\n", "\n  ")
