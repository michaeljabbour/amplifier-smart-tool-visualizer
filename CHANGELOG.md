# Changelog

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
