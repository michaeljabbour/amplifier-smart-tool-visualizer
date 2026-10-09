---
smart_tool_format: 1
name: knowledge
version: 0.2.0
description: >-
  Turns notes, papers, docs, code and agent sessions into a knowledge graph that any agent can
  query and add to, and people can explore: concepts and typed relations with sources, confidence and
  time, so it keeps what was believed, why, and what replaced it. Finds paths between ideas, the evidence
  behind a claim, contradictions, topics, central concepts and the gaps between topics, and draws it all
  as an interactive map, live while agents work. Use for 'build a knowledge graph', 'map these notes',
  'how does X relate to Y', 'what supports or contradicts this', 'what are we missing', 'what changed',
  'shared memory for agents', 'visualise this corpus', or exporting to Obsidian, Gephi or Cytoscape.
use_cases:
  - Read a folder of notes, papers or docs into a graph and see its main topics and central ideas
  - Give several agents one shared, lasting memory they can search, add claims to and cite
  - Trace how two ideas connect, step by step, with the passage behind each step
  - Check what supports or contradicts a claim, and which agent or source said so
  - See how understanding changed over time, with closed beliefs kept in the history
  - Find gaps between well-developed topics and turn them into research questions
  - Watch agents build the graph live, or share a self-contained interactive map
  - Export a graph as an Obsidian vault with a Canvas map, or for Gephi and Cytoscape
platforms:
  - macos
  - linux
requires:
  - name: ANTHROPIC_API_KEY
    purpose: >-
      Only for the model-backed steps (ingest with the default llm method, ask, report, questions,
      reconcile) run from a plain terminal. Not needed inside Claude Code, Codex or Amplifier, or over
      MCP, where the agent is the model, and not needed for any deterministic capability.
    install: https://docs.anthropic.com/en/api/getting-started
    optional: true
  - name: OPENAI_API_KEY
    purpose: >-
      The same model-backed steps, with OpenAI instead. Either key, a local Ollama model, or your own
      program through --complete-cmd will do.
    install: https://platform.openai.com/docs/quickstart
    optional: true
  - name: ollama
    purpose: >-
      Optional local model for the model-backed steps (--provider ollama). Without it, use a key or
      --complete-cmd; deterministic capabilities never need it.
    install: https://ollama.com/download
    optional: true
---
**Point it at material, then ask the graph.** `knowledge ingest ./notes` reads a folder into a
graph of concepts and typed relations, each with its source passage, the agent that added it, a
confidence and a validity window. Then `search`, `show`, `path`, `evidence`, `contradictions`,
`gaps` and `timeline` answer questions about it, and `visualize` draws it.

**The library is the tool.** `knowledge` (the Python package) holds every capability; the
command line reads files, calls the library and prints the result. To chain steps, call the
library from Python: results are plain dicts and lists, so there is nothing to parse.

```python
import knowledge as kg
kg.ingest("research", documents=kg.load_documents("./notes"), method="cooccurrence")
print(kg.path("research", "delegation", "human agency")["paths"][0]["nodes"])
```

## When to reach for it

- Someone wants to see what a body of material is about: its topics, central ideas, how ideas link.
- Agents need memory that outlives the session: one graph several agents read, cite and add to.
- A claim needs checking: what backs it, what contradicts it, who said it, when.
- Someone asks how two things relate, or what is missing between two areas of work.
- Understanding has changed and the history matters: what was believed before, and why it changed.
- A person wants an explorable map, or the graph in Obsidian, Gephi or Cytoscape.

## When not to

- A plain keyword lookup in a few files: use search or grep.
- One document to summarise: summarise it.
- Structured tables with fixed columns: use a database.
- Many people editing at once in real time: the graph is one local SQLite file per graph
  (concurrent agents are fine; it is not a collaborative editor).

## How the graph works

- **Nodes** are concepts keyed by lowercase label, with an open `type`: concept, person,
  organization, claim, evidence, hypothesis, method, decision, question, artifact, term, ...
- **Edges** are directed and typed (`supports`, `contradicts`, `depends_on`, `part_of`, `causes`,
  ...), with a one-sentence description, confidence 0-1, provenance (source, chunk, agent,
  session, method) and `valid_from` / `valid_to`. Nothing is deleted: `supersede` closes an
  edge, and `--as-of DATE` on any read shows the graph as it was then.
- **Shared-passage links**: concepts named in the same chunk are linked with weight 1 (an
  extracted relation weighs 4), as in the original notebook pipeline. They feed topics and
  centrality; `--no-proximity` turns them off.
- **Topics** come from Louvain (or Girvan-Newman for small graphs). **Influence** is betweenness
  centrality. **Gaps** are pairs of large topics with far fewer links than their size predicts.
- **Changed material**: re-ingesting a file whose text changed closes the old version's edges.
  The same text twice is skipped.
- Graphs live in the per-user data folder (`knowledge stats` shows where); `--graph NAME` picks
  one, `--graph ./file.db` uses a path, `KNOWLEDGE_HOME` moves the folder.

## Deterministic and model-backed

Everything runs with no model and no key except these: `ingest` with the default `llm` method,
`ask`, `report`, `questions` and `reconcile`. Each has a deterministic route:

| Model-backed | Without a model |
|---|---|
| `ingest` (llm) | `ingest --method agent` (you extract, then `add`), or `--method cooccurrence` |
| `ask` | `context` (the same numbered context; you answer) |
| `report` | `communities` |
| `questions` | `gaps` |
| `reconcile` | `contradictions`, then `supersede` or `relate A contradicts B` |

## Which model answers

First that applies wins; `ingest` says which on stderr, and every result names it in `model`.

1. An explicit choice: `--complete-cmd 'program'`, `--provider anthropic|openai|ollama`
   (`--model` to pin one), or `KNOWLEDGE_COMPLETE_CMD` / `KNOWLEDGE_PROVIDER` / `KNOWLEDGE_MODEL`.
2. The agent harness it runs in (Claude Code, Codex, Amplifier, or `KNOWLEDGE_HOST=name`): the
   agent is the model, so the step stops with `host_model` (exit 3) and names the deterministic
   route. **No key is billed**, even if one is set. `KNOWLEDGE_HOST=none` turns this off.
3. `ANTHROPIC_API_KEY` (default `claude-sonnet-5-5`), then `OPENAI_API_KEY` (default `gpt-5.5`).
   **Billed to that key.** Ollama defaults to `mistral-openorca`, the original pipeline's model.

`--complete-cmd` runs your program once per call with `{"system": ..., "prompt": ...}` on stdin;
print the model's reply and exit 0. No SDK is needed for any route.

## If you are an agent

Use the deterministic routes; you are the model.

```
knowledge ingest paper.md --method agent --graph research --json
#   result.task.system is the extraction prompt; result.task.chunks are [{id, text}]
#   extract relations from each chunk, keep each chunk id, write relations.json:
#   {"agent": "researcher", "edges": [{"from": "...", "to": "...", "relation": "supports",
#     "description": "...", "confidence": 0.8, "from_type": "evidence", "to_type": "claim",
#     "chunk": "s-...#0"}]}
knowledge add relations.json --graph research
knowledge context "does delegation reduce agency?" --graph research --json   # answer from it, cite [n]
knowledge relate "claim 27" contradicts "claim 11" --agent reviewer --graph research
knowledge gaps --graph research --json                                        # where to look next
```

**Show the view that answers the person's question, and ask when it is unclear.** Pass their
question, in their words, to `visualize --for`. The view opens on the lens that answers it (how
two concepts connect, what backs a claim, where the material disagrees, what changed, the gaps,
one concept, or the overview) and says why. If the question does not say enough, the command stops
with `needs_clarification`: `result.question` is the question to put to the person and
`result.choices` the command for each answer. Ask them; do not pick for them.

```
knowledge visualize --for "how does delegation relate to perceived agency?" --graph research --open
```

Over MCP (`knowledge mcp`), the same capabilities are tools named `knowledge_<capability>`;
model-backed tools return a task for you instead of calling a model.

## For scripts

- `--json` on any command prints one envelope: `{ok, command, result, files, next}`, or
  `{ok: false, command, error: {code, message, hint}, exit_code}`. `ok` is true exactly when the
  exit code is 0. Without `--json`, a terminal gets readable text and a pipe gets the bare result
  as JSON.
- Exit codes: 0 done, 1 input problem, 2 wrong command line, 3 set something up first, 4 model
  call failed, 130 interrupted.
- It never prompts. Progress goes to stderr (`-q` silences it); results go to stdout.
- The full contract: `docs/cli-contract.md` and `docs/graph-format.md` (shipped in the package).

## Recipes

**A research corpus, with a model.**

```
knowledge ingest ./papers ./notes --graph research --agent librarian
knowledge report --graph research                 # name the topics
knowledge analyze --graph research                # central ideas, bridges, gaps
knowledge visualize --for "what are the main topics?" --graph research --open
```

**No model at all.** `knowledge ingest ./notes --method cooccurrence`, then `analyze`, `gaps`,
`visualize`: a text network of which words appear together, with topics, influence and gaps.

**Agent sessions as memory.** Session logs (`.jsonl` with role and content) are read as
conversation text: `knowledge ingest ~/.sessions/*.jsonl --agent archivist --session ID`.

**Beliefs that change.**

```
knowledge relate "model x" outperforms "model y" --agent bench --at 2026-03-01
knowledge relate "model y" outperforms "model x" --agent bench --supersedes e-...   # closes the old one
knowledge timeline "model x"                    # both, with when each held
knowledge show "model x" --as-of 2026-03-15     # the graph as it was
```

**Watch agents work.** `knowledge serve --open` in one terminal; anything any process writes to
that graph appears within seconds, with a ticker of who did what.

**Into Obsidian.** `knowledge export --format obsidian --out ./vault`: one note per concept with
`[[wikilinks]]` and quoted evidence, a note per topic, `Gaps.md`, and `Topics map.canvas`.

## Sharp edges

- Extraction quality depends on the model; read the relations before trusting them. Each one
  cites its chunk, so `evidence` shows the words it came from.
- Concepts merge by exact lowercase label. "LLM" and "large language model" stay separate unless
  an agent relates them (`relate llm same_as "large language model"`).
- The co-occurrence method makes word networks, not claims: good for topics and gaps, not for
  `contradictions`.
- Betweenness is estimated from a fixed sample above 400 concepts; Girvan-Newman refuses graphs
  above 1500 edges. The view keeps the 1500 most connected concepts unless `--max-nodes` says otherwise.
- PDFs need the `[pdf]` extra (pypdf). Web pages are fetched only with `--allow-network`.

## Install and check

```
uv tool install "amplifier-smart-tool-visualizer @ git+https://github.com/michaeljabbour/amplifier-smart-tool-visualizer"
knowledge doctor
```

Python 3.10 or later, no other dependencies. Add `[pdf]` to read PDFs. `doctor` never calls a
model and says exactly what to fix.
