# Command line results, errors and exit codes (draft, v1)

## Streams

- **stdout** carries the result. With `--json`: one envelope. Without it: readable text on a
  terminal, the bare result as JSON when piped.
- **stderr** carries progress and errors for people. `-q` silences progress; errors always print.
- It never prompts. With stdin closed, a command completes or fails.

## Envelope (`--json`, before or after the command name)

```json
{"ok": true, "command": "visualize", "result": {"path": "/abs/knowledge-research.html", "bytes": 201157,
 "nodes": 118, "edges": 331, "topics": 11, "truncated": false},
 "files": [{"path": "/abs/knowledge-research.html", "kind": "view"}], "next": []}
```

```json
{"ok": false, "command": "show", "files": [],
 "error": {"code": "concept_not_found", "message": "No concept called \"deleg\" in this graph.",
           "hint": "Did you mean: delegation, delegated?", "suggestions": ["delegation", "delegated"]},
 "exit_code": 1}
```

`ok` is true exactly when the exit code is 0. A failure that still did some work (an `ingest`
where some chunks failed) also carries `result`, saying what succeeded.

`serve --json` prints one line `{"ok": true, "command": "serve", "event": "started", "result": {"url"}}`
and keeps serving. `events --follow` prints one event per line.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Finished. |
| 1 | The input has problems: missing file, bad JSON, unknown concept or edge, nothing usable, or a question too unclear to choose a view (`needs_clarification`: `result.question` is what to ask the person, `result.choices` the command for each answer). |
| 2 | The command line is wrong: unknown command or flag, missing argument. |
| 3 | Set something up first: no model provider (`provider_not_configured`), running inside an agent harness with no provider chosen (`host_model`), a missing optional package, no write access, a taken port. |
| 4 | A model call failed, or its reply was unusable after one repair (`model_call_failed`, `reply_invalid`). |
| 130 | Interrupted. Stopping `serve` or `events --follow` with Ctrl-C is a normal end (0). |

## Error codes

`usage`, `missing_argument`, `file_not_found`, `bad_json`, `invalid_input`, `concept_not_found`,
`edge_not_found`, `graph_not_found`, `needs_clarification`, `already_closed`, `graph_too_large`, `no_context`, `no_gaps`,
`bad_graph`, `provider_not_configured`, `host_model`, `missing_prerequisite`, `no_write_access`,
`port_unavailable`, `setup_incomplete`, `model_call_failed`, `reply_invalid`, `interrupted`,
`unexpected` (a bug: run again with `--debug`).

## Environment

| Variable | Effect |
|---|---|
| `KNOWLEDGE_HOME` | Folder for named graphs (default: the platform's per-user data folder). |
| `KNOWLEDGE_GRAPH` | Default graph name or path. |
| `KNOWLEDGE_PROVIDER`, `KNOWLEDGE_MODEL`, `KNOWLEDGE_COMPLETE_CMD` | Model choice for model-backed steps. |
| `KNOWLEDGE_HOST` | Declare the agent harness (`none` turns host detection off). |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OLLAMA_HOST` | Provider access. |
| `KNOWLEDGE_MCP_ALLOW_MODEL=1` | Let MCP tools call the tool's own model instead of returning a task. |
| `KNOWLEDGE_NO_BROWSER` | `--open` prints the path instead of opening a browser. |
