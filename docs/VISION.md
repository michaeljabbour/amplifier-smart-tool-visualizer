# Vision: a knowledge graph as a smart tool

## The idea

Knowledge should outlive the agent that produced it. Agents are short-lived; what they learn,
claim, test and decide should land in one shared, inspectable place that any agent can read and
add to, and that people can explore. That place is a graph whose nodes are concepts, claims,
evidence, decisions and questions, and whose edges carry where they came from, how sure anyone
was, and when they held.

This is a **smart tool**, not an application and not an agent runtime. Any harness (Amplifier,
Claude Code, Codex, a Python script) calls it. It owns one contract (ingest, relate, search, path,
evidence, contradictions, gaps, timeline, visualize) and keeps its storage, its analysis and its
model use to itself.

## The test it is built for

> Can an agent discover a non-obvious relationship or contradiction from prior work that
> ordinary semantic retrieval fails to surface?

`path`, `gaps`, `contradictions` and `timeline` exist for that test. Search finds what you
already know to ask for. A path shows how two ideas connect through intermediate claims. A gap
shows two developed bodies of work with nothing between them. A contradiction shows where two
agents, or two sources, disagree. A timeline shows that something was believed, why, and what
replaced it.

## Gene transfer: what came from where

The core organism is [rahulnyk/knowledge_graph](https://github.com/rahulnyk/knowledge_graph).
The other projects contributed capabilities, not architectures. Each gene below names what it
does here and where it lives.

| Gene | From | Here |
|---|---|---|
| Recursive chunking, 1500 characters with 150 overlap | rahulnyk/knowledge_graph (LangChain splitter) | `text.split_text` |
| "Network graph maker" extraction prompt: terms, then pairs, then the relation | rahulnyk/knowledge_graph `helpers/prompts.py` | `extract.SYSTEM_PROMPT`, extended with node types, a relation label and a confidence; the original `{node_1, node_2, edge}` replies are still read |
| Lowercased concepts as identity | rahulnyk/knowledge_graph `graph2Df` | `text.node_key` |
| Contextual proximity: concepts in the same chunk are linked, extracted relations weigh 4, each shared chunk 1 | rahulnyk/knowledge_graph notebook | `analysis.build_view` (computed from mentions, never stored) |
| Girvan-Newman communities, second split | rahulnyk/knowledge_graph notebook | `analysis.girvan_newman`, `communities --method girvan-newman` |
| Colour by community, size by degree, interactive HTML | rahulnyk/knowledge_graph (pyvis) | `resources/viewer.html`, written from scratch with no outside requests |
| Ollama with a local model (mistral-openorca) | rahulnyk/knowledge_graph `ollama/client.py` | `providers.py`, `--provider ollama` |
| Temporal edges: valid_from / valid_to, invalidation instead of deletion, reading the graph at a point in time | Graphiti (bitemporal episodes and edge invalidation) | `store.Graph.supersede`, `--as-of` on every read, `timeline`, re-ingest closing a changed source's edges |
| Conflict judgment: a model decides whether new relations contradict or replace old ones | Graphiti (edge invalidation) and Utopia (conflict detection) | `reconcile`, with deterministic candidates in `contradictions` |
| Hybrid retrieval: names, summaries and passages, ranked with graph degree | Graphiti, LightRAG | `search` (SQLite FTS5) |
| Community reports: a model names and summarises each topic | Microsoft GraphRAG | `report`, stored and reused by `communities`, `context` and the view |
| Local-search context: seed concepts, their strongest relations, passages and topic reports, numbered for citation | Microsoft GraphRAG local search | `context` (deterministic) and `ask` (model-backed) |
| Louvain communities, modularity | GraphRAG (Leiden), network science | `analysis.louvain`, `analysis.modularity` |
| Betweenness as influence, bridges between topics | InfraNodus | `analysis.betweenness`, `analyze` |
| Structural gaps: pairs of developed topics with too few links, plus bridge candidates | InfraNodus | `analysis.structural_gaps`, `gaps` |
| Gaps turned into research questions | InfraNodus (its AI gap questions) | `questions --save` (question nodes linked with `bridges`) |
| Text network with no model: content words within a four-word window | InfraNodus | `ingest --method cooccurrence` |
| Diversity reading: biased, focused, diversified, dispersed | InfraNodus | `analysis.diversity` (approximate thresholds; stated as such) |
| Typed nodes beyond entities: claim, evidence, hypothesis, decision, question | LLM Graph Builder schemas, the research-instrument idea | open `type` field; `evidence` groups supports / contradicts |
| Provenance on every relation: source, chunk, agent, session, method | Neo4j LLM Graph Builder, GraphRAG text units | `edges` columns, `evidence` |
| The graph survives the agent; human-readable notes with wikilinks | claude-obsidian, Second Brain, Open Second Brain | `export --format obsidian` (concept notes, topic notes, `Gaps.md`) |
| Semantic Canvas maps rather than a force layout of links | GO-Obsidian | `export --format canvas` and `Topics map.canvas` in the vault |
| 2D exploration of graph artifacts with a time dimension | GraphRAG Visualizer, GraphRAG Workbench | the view's time slider, topic toggles and gap highlighting |
| GraphML for serious layout and analysis | Microsoft GraphRAG, Gephi | `export --format graphml` |
| Cytoscape elements | Cytoscape.js | `export --format cytoscape` |
| Agent sessions as material | agent-memory projects (Mem0, Cognee) | `.jsonl` session logs read as conversation text |
| A live observability surface for agents writing to shared memory | the visualizer and event-emitter work | `events` (append-only log), `serve` (polls it and flashes changes) |

From Amplifier's smart-tool family (decisioncraft): the library-first shape, the `--json`
envelope and exit codes, the host-model rule (inside an agent harness, the agent is the model and
no key is billed), `--complete-cmd` for any host's model, one repair of an unusable reply, a
strict-CSP self-contained HTML file, and help that is a skill.

## What was left behind, on purpose

- **Pandas, NetworkX, PyVis, LangChain, seaborn**: replaced by about 400 lines of standard-library
  analysis, so the deterministic paths install with nothing and start fast.
- **Neo4j, Kuzu, vector databases**: the protocol is the graph document and the CLI contract, not
  a database. One SQLite file per graph is enough for a person's or a team's research; another
  store can sit behind the same library later.
- **Embeddings**: hybrid search here is names, summaries and passages plus graph structure. Vector
  search would need a model on every ingest and every query; it belongs behind an optional
  capability, not in the deterministic core.
- **A fixed ontology**: types and relation labels are open strings. Claim, evidence and
  contradiction emerge from use rather than from a schema every caller must adopt.
- **A web application**: the view is one file. `serve` exists only for watching agents live and
  starts only when asked.

## Next steps worth trying

- Entity resolution: merge "LLM" and "large language model" with a model-backed `merge` and a
  `same_as` relation the analysis honours.
- Leiden instead of Louvain for better-connected communities on large graphs.
- An optional embedding index behind `search --semantic`.
- Code-aware ingest: functions, modules and imports as typed nodes.
- MCP Apps: render the view inside hosts that support it.
