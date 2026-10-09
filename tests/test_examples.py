"""The website's audience examples: their relations still match their sources, and every question
in questions.json opens the view it was written for (or asks back when it is meant to)."""
import importlib.util
import json

import pytest

from tests.conftest import ROOT

spec = importlib.util.spec_from_file_location("build_examples", ROOT / "scripts" / "build-examples.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


@pytest.mark.parametrize("name", sorted(build.AUDIENCE))
def test_audience_example_builds_and_routes(name, tmp_path, monkeypatch):
    monkeypatch.setattr(build, "WORK", tmp_path)
    graph = build.corpus(name)
    build.check_questions(name, graph)
    sources = json.loads((ROOT / "examples" / name / "sources.json").read_text())
    assert all(s["uri"].startswith("https://") and s["licence"] for s in sources)
