# The graph document (knowledge-graph/1)

`knowledge export --format json`, `knowledge.graph_data(...)`, the view's embedded data and the
live server's `/api/graph` all return the same document. Draft: fields may be added; existing
ones keep their meaning.

```json
{
  "format": "knowledge-graph/1",
  "graph": "research",
  "generated_at": "2026-10-06T22:00:00Z",
  "as_of": null,
  "focus": null,
  "truncated": false,
  "last_event": 459,
  "counts": {"nodes": 118, "edges": 331, "proximity": 40, "topics": 11},
  "nodes": [
    {"id": "delegation", "label": "delegation", "type": "concept", "summary": "",
     "community": 3, "color": "#e15759", "degree": 20, "strength": 44.6, "degree_norm": 0.74,
     "betweenness": 0.198, "created_at": "2026-02-01T00:00:00Z",
     "passages": [{"source": "delegation-study.md", "uri": "/notes/delegation-study.md",
                   "chunk": "s-d70d148159b5#0", "excerpt": "Participants who delegated..."}]}
  ],
  "edges": [
    {"id": "e-71ac3683367b", "source": "delegation", "target": "perceived agency",
     "relation": "increases", "description": "When people choose what to delegate...",
     "confidence": 0.55, "weight": 1.0, "method": "agent", "agent": "researcher",
     "valid_from": "2026-03-10T00:00:00Z", "valid_to": null, "invalidated_by": null,
     "chunk": null, "evidence": "Participants who delegated...", "from_source": "delegation-study.md"}
  ],
  "proximity": [{"source": "delegation", "target": "human oversight", "count": 2}],
  "topics": [{"id": 3, "label": "agency, perceived, delegation", "size": 19, "color": "#e15759",
              "summary": ""}],
  "gaps": [{"between": [0, 1], "topics": ["...", "..."], "score": 1.0, "observed_weight": 0.0,
            "expected_weight": 57.2, "size": [24, 20],
            "bridge_candidates": [["boundary", "control"], ["cost", "task"]], "prompt": "..."}],
  "diversity": {"state": "diversified", "modularity": 0.64, "top_topic_share": 0.2,
                "advice": "..."},
  "time": {"first": "2026-01-15T00:00:00Z", "last": "2026-10-06T22:00:00Z", "marks": ["..."]}
}
```

## Nodes

- `id` is the lowercase, single-spaced label: the concept's identity. `label` keeps the first
  spelling seen.
- `type` is open. Common values: concept, term (from the co-occurrence method), entity, person,
  organization, place, event, claim, evidence, hypothesis, method, artifact, decision, question,
  metric, report. A more specific type replaces `concept` when a later relation names one.
- `community` is the topic index (Louvain), -1 when the node has no links.
- `degree` counts linked neighbours; `strength` sums link weights; `betweenness` is normalised
  0-1 (estimated from a fixed sample above 400 nodes).
- `created_at` is the earliest of when the node was first stored and when any of its relations
  became valid.

## Edges

- Directed: `source` `relation` `target`. `relation` is a lowercase label with underscores.
- `evidence` is the quote the relation was written from (first 300 characters, empty if none was given);
  `from_source` is the title of the material it was read from (null for relations written by hand).
- `method` is how it was made: `llm` (extracted by a model), `agent` (written through add or
  relate), `cooccurrence` (word window; `weight` is the window score).
- `valid_from` / `valid_to` bound when the relation held. `valid_to` set means closed;
  `invalidated_by` says why: `edge:ID` (replaced by that edge), `source:ID` (a newer version of the
  material), `note:TEXT`, or `closed`.
- Closed edges are included so the view can replay time; filter `valid_to == null` for the
  current graph, or pass `as_of` to get the graph as it was.

## Weights used by analysis

An extracted or written relation weighs 4 × confidence (confidence defaults to 1); a
co-occurrence edge weighs its window score; each chunk two concepts share adds 1 (proximity, only
for material read for meaning, and only when a chunk names 40 concepts or fewer).

## Storage

One SQLite file per graph (tables: sources, chunks, nodes, mentions, edges, conflicts, reports,
events). Read it directly if you like; write through the library so events are logged.
