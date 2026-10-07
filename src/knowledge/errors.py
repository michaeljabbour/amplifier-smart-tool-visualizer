"""One error type for every surface: what went wrong, what to do next, and an exit code.

The CLI, the MCP server and the library all raise `ToolError`, so a caller reads the same
code, message and hint whichever way it reached the tool.
"""

from __future__ import annotations

# Exit codes. Documented in contracts/cli.v1.md; keep the two in step.
OK = 0
INPUT = 1  # the input has problems: a missing file, bad JSON, an unknown concept
USAGE = 2  # the command line itself is wrong: unknown command or flag, missing argument
SETUP = 3  # something must be set up first: a provider, an optional package, write access
MODEL_CALL = 4  # a model was asked and the call failed, or its reply stayed unreadable
INTERRUPTED = 130  # stopped with Ctrl-C before finishing

EXIT_CODES = {
    OK: "Finished.",
    INPUT: "The input has problems (missing file, bad JSON, unknown concept or edge).",
    USAGE: "The command line is wrong (unknown command or flag, missing argument).",
    SETUP: "Something must be set up first (a model provider, an optional package, write access).",
    MODEL_CALL: "A model call failed, or its reply was still unreadable after one repair.",
    INTERRUPTED: "Stopped with Ctrl-C before finishing.",
}


class ToolError(Exception):
    """A failure with a stable code, a plain message and the next thing to try."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        hint: str = "",
        exit_code: int = INPUT,
        result: dict | None = None,
        suggestions: list[str] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.exit_code = exit_code
        # A partial result, for failures that still did some of the work (see `ingest`).
        self.result = result
        self.suggestions = suggestions or []

    def as_dict(self) -> dict:
        out: dict = {"code": self.code, "message": self.message, "hint": self.hint}
        if self.suggestions:
            out["suggestions"] = self.suggestions
        return out


def not_found(kind: str, name: str, suggestions: list[str] | None = None) -> ToolError:
    hint = "Run: knowledge search \"" + name + "\" to find the right name."
    if suggestions:
        hint = "Did you mean: " + ", ".join(suggestions[:5]) + "?"
    return ToolError(f"{kind}_not_found", f"No {kind} called \"{name}\" in this graph.",
                     hint=hint, suggestions=suggestions)


def classify(error: BaseException) -> ToolError:
    """Turn any exception into a ToolError so every surface reports it the same way."""
    import json
    import sqlite3

    if isinstance(error, ToolError):
        return error
    if isinstance(error, KeyboardInterrupt):
        return ToolError("interrupted", "Stopped before finishing.", exit_code=INTERRUPTED)
    if isinstance(error, FileNotFoundError):
        return ToolError("file_not_found", f"No such file or folder: {error.filename}",
                         hint="Check the path, or pass text with --text.")
    if isinstance(error, PermissionError):
        return ToolError("no_write_access", f"Not allowed to read or write {error.filename}.",
                         hint="Choose another place with --graph or --out, or set KNOWLEDGE_HOME.",
                         exit_code=SETUP)
    if isinstance(error, json.JSONDecodeError):
        return ToolError("bad_json", f"That is not valid JSON: {error.msg} (line {error.lineno}).",
                         hint="Check the file; `knowledge add --help` shows the shape it reads.")
    if isinstance(error, sqlite3.DatabaseError):
        return ToolError("bad_graph", f"The graph file could not be read: {error}.",
                         hint="Point --graph at a file this tool wrote, or start a new graph name.")
    if isinstance(error, (ValueError, TypeError)):
        return ToolError("invalid_input", str(error), hint="Run the command with --help for its arguments.")
    return ToolError("unexpected", f"{type(error).__name__}: {error}",
                     hint="This is a bug. Run again with --debug and report the traceback.")
