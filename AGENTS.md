# Working on the knowledge tool

Read [docs/VISION.md](docs/VISION.md) and [contracts/](contracts/README.md) before changing
behaviour. The packaged `src/knowledge/SMART_TOOL.md` documents what is built; its body is what
`knowledge --help` prints.

## Architecture

- The library is the product. Every capability is a function in `src/knowledge/lib.py`; the CLI
  (`cli.py`) and the MCP server (`mcp_server.py`) only parse, read files into data, call it and
  print. Help text lives in `help.py`.
- Deterministic capabilities must import and run with no credentials and no network. The standard
  library only: SQLite for storage (`store.py`), pure-Python analysis (`analysis.py`).
- Model-backed capabilities (`ingest` llm, `ask`, `report`, `questions`, `reconcile`) resolve a
  route in `providers.py` before writing anything, parse replies as JSON, repair once, then fail
  with exit 4. Each has a deterministic route named in its `host_model` hint.
- Nothing is deleted from a graph. Changes close validity windows and append events.
- The view (`resources/viewer.html`) is one self-contained file: no outside requests, a strict
  content security policy, the graph embedded as JSON.
- State goes to the per-user data folder (`KNOWLEDGE_HOME`), never beside the source.

## Writing

Plain words and short sentences in help, errors and UI text. Every error says what to do next.
Examples are real public material with provenance (see examples/*/README.md), except the small
fictional corpus the tests use. Never add private or personal material to examples.

## Before committing

```sh
uv run --with pytest python -m pytest -q
uvx ruff check --isolated --line-length 132 --select E,F,W src tests
uv run path/to/amplifier-smart-tools/conformance/run.py .
```

Keep `version` in `pyproject.toml`, `SMART_TOOL.md` and `help.py` equal (a test checks).
Keep `contracts/graph.v1.md` identical to `src/knowledge/docs/graph-format.md`, and `contracts/cli.v1.md`
identical to `src/knowledge/docs/cli-contract.md` (a test checks both; the package ships the copies).
