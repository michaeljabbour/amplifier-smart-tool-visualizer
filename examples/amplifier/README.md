# Example: Amplifier, from its own docs (real)

Twenty real documents: fifteen pages of [microsoft/amplifier-docs](https://github.com/microsoft/amplifier-docs)
(architecture, kernel, modules, mount plans, events, agents, sessions, collections, profiles,
providers, the tool / hook / orchestrator / context contracts, the roadmap) and the five chapters of
the [Amplifier Smart Tools specification](https://github.com/microsoft/amplifier-smart-tools/tree/main/spec).
Both repositories are MIT licensed (see `LICENSE-sources`). The text is vendored in `sources/` so the
build is reproducible; `sources.json` records each file's repository, path, commit, date and permalink.

How the graph was made, with the tool's own agent route (no model inside the tool, no API key):

1. `knowledge ingest --method agent` read each document, dated by its last commit, into 100 chunks.
2. Four Claude Code agents (cartographer, analyst, skeptic, archivist) each took 25 chunks, extracted
   concepts and typed relations, and wrote them into the same graph with `knowledge add`, at the same
   time, while `knowledge serve` was recorded (`docs/images/live-demo.mp4`, sped up).
3. Every relation carries the chunk it came from and an exact quote. `relations/<agent>.json` is what
   each agent wrote; `scripts/build-examples.py` replays them.

Extraction is a model's reading of the text: check a relation with `knowledge evidence EDGE_ID`, which
shows the quote and the passage.
