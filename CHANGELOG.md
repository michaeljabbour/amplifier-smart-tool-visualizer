# Changelog

## 0.2.0 (2026-10-08)

- `visualize --for "QUESTION"` opens the view that answers the person's question: how two concepts
  connect, what backs or contradicts a claim, what changed over time (at a date, if given), the gaps,
  one concept, or the overview. A note in the view says why it opened there and the command for
  the nearest other view.
- When the question does not say enough (no concept named, two asks at once, a name not in the
  graph, two concepts and no verb), it stops with `needs_clarification` (exit 1) and returns the
  question to put to the person with the exact command for each answer, instead of guessing.
- `--lens` and `--to` choose the view directly; `choose_view` in the library and the MCP
  `knowledge_visualize` tool take the same arguments.
- Three new examples for the people who use it, each from real public material and each opening on
  a question someone in that job would ask: Python's typing PEPs for developers (public domain /
  CC0), arXiv abstracts on scaling laws and emergent abilities for researchers (CC0), and US federal
  AI policy for policy, legal and operations work (public domain). `scripts/build-examples.py`
  builds them and fails if any question stops opening the view it was written for;
  `tests/test_examples.py` checks the same.
- `knowledge -V` prints the version, as `--version` does (the conformance kit's new `cli-version`
  check; 17/17).
- Product page and README lead with those examples; new recordings (developers, scientists, work,
  asks) and a new trailer.

## 0.1.0 (2026-10-07)

First public release: the rahulnyk/knowledge_graph pipeline rebuilt as an Amplifier Smart Tool.

- Library, thin CLI and dependency-free MCP server; deterministic capabilities need no model or key.
- Temporal provenance edges: every relation has its source chunk, agent, confidence and validity
  window; `supersede`, `--as-of` and `timeline`; a changed source closes its old relations.
- Network analysis: topics (Louvain, Girvan-Newman), influence, bridges, structural gaps, diversity.
- Contradiction finding, and model-backed reconciliation, community reports, questions and answers.
- Inside Claude Code, Codex or Amplifier, model-backed commands stop with `host_model` instead of
  billing a key (Amplifier is detected from its parent process; its shell exports no variable).
- A self-contained interactive view (path tracing, time replay, gaps), a live view, and exports to
  JSON, Cytoscape, GraphML, CSV, an Obsidian vault and Canvas.
- Amplifier integration: `bundle.md`, `behaviors/knowledge.yaml` (skill) and optional
  `behaviors/knowledge-mcp.yaml`.
- Real examples: Amplifier's public docs extracted live by four agents, and amplifier-foundation's
  decision history; a product page with demo videos.
- Passes the Amplifier Smart Tools conformance kit (16/16). Reviewed by Amplifier's expert agents.
