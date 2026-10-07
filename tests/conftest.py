import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "agency-research"
STUB = f"{sys.executable} {ROOT / 'tests' / 'stub_model.py'}"
HOST_VARS = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_SANDBOX",
             "CODEX_CI", "AMPLIFIER_SESSION_ID", "KNOWLEDGE_HOST", "KNOWLEDGE_PROVIDER",
             "KNOWLEDGE_MODEL", "KNOWLEDGE_COMPLETE_CMD", "KNOWLEDGE_GRAPH", "ANTHROPIC_API_KEY", "OPENAI_API_KEY")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    """Every test runs outside any agent harness, with no keys and its own data folder."""
    for var in HOST_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("KNOWLEDGE_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("KNOWLEDGE_NO_BROWSER", "1")
    from knowledge import providers

    monkeypatch.setattr(providers, "_parent_commands", lambda limit=12: [])  # the suite may run under a harness
    monkeypatch.chdir(tmp_path)
    yield


@pytest.fixture
def graph(tmp_path):
    return str(tmp_path / "g.db")


@pytest.fixture
def example_graph(graph):
    import json

    import knowledge as kg

    kg.ingest(graph, documents=kg.load_documents(EXAMPLE / "notes"), method="cooccurrence")
    kg.add(graph, json.loads((EXAMPLE / "relations.json").read_text()))
    return graph


def run_cli(*args, stdin: str | None = None, env: dict | None = None):
    import subprocess

    full_env = {**os.environ, **(env or {})}
    return subprocess.run([sys.executable, str(ROOT / "bin" / "knowledge.py"), *args], input=stdin,
                          capture_output=True, text=True, env=full_env, timeout=120)
