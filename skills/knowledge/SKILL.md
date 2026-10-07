---
name: knowledge
description: "Turns notes, papers, docs, code and agent sessions into a knowledge graph that any agent can query and add to, and people can explore: concepts and typed relations with sources, confidence and time, so it keeps what was believed, why, and what replaced it. Finds paths between ideas, the evidence behind a claim, contradictions, topics, central concepts and the gaps between topics, and draws it all as an interactive map, live while agents work. Use for 'build a knowledge graph', 'map these notes', 'how does X relate to Y', 'what supports or contradicts this', 'what are we missing', 'what changed', 'shared memory for agents', 'visualise this corpus', or exporting to Obsidian, Gephi or Cytoscape."
---

# knowledge

This is the `knowledge` smart tool. If `knowledge` is not on your PATH, install it, then let it
teach you the rest:

```
uv tool install "amplifier-smart-tool-visualizer @ git+https://github.com/michaeljabbour/amplifier-smart-tool-visualizer@main"
knowledge --help
```

Run `knowledge --help` and follow it. For one capability: `knowledge <capability> --help`.

## You are the model

Inside an agent harness (Amplifier, Claude Code, Codex) the model-backed commands stop with
`host_model` (exit 3) instead of spending an API key. That is expected: do that step yourself
with the deterministic route.

| Instead of | Do |
|---|---|
| `ingest` | `ingest PATH --method agent --json`, extract relations from `result.task.chunks` with `result.task.system`, then `add relations.json` |
| `ask` | `context "QUESTION" --json`, then answer from it and cite `[n]` |
| `report` | `communities` |
| `questions` | `gaps` |
| `reconcile` | `contradictions`, then `supersede EDGE_ID` or `relate A contradicts B` |

Do not add `--provider` unless the person asks to spend a key.

Graphs are kept in a per-user data folder (`knowledge stats` shows where). Set `KNOWLEDGE_HOME`
to keep one project's graphs apart, and name graphs with `--graph NAME`.
