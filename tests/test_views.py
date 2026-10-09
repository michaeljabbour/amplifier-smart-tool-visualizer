"""Choosing the view for a question, and asking instead of guessing when the question is unclear."""
import json

import pytest

import knowledge as kg
from knowledge.errors import ToolError
from tests.conftest import run_cli


def plan(graph, question, **kw):
    return kg.choose_view(graph, question, **kw)


def clarification(graph, question, **kw):
    with pytest.raises(ToolError) as info:
        kg.choose_view(graph, question, **kw)
    err = info.value
    assert err.code == "needs_clarification"
    assert err.result["question"]  # something to ask the person, in plain words
    assert err.result["choices"], "a clarification must offer answers"
    for choice in err.result["choices"]:
        assert choice["label"] and choice["command"].startswith("knowledge visualize")
    return err.result


def test_two_concepts_and_a_relating_question_draw_the_path(example_graph):
    p = plan(example_graph, "How does delegation relate to perceived agency?")
    assert (p["lens"], p["concept"], p["to"]) == ("path", "delegation", "perceived agency")
    assert "delegation" in p["why"] and p["alternatives"]


def test_contradiction_question_focuses_the_claim(example_graph):
    p = plan(example_graph, "What contradicts delegation reduces perceived agency?")
    assert p["lens"] == "contradictions" and p["concept"] == "delegation reduces perceived agency"
    assert p["closed"] is True


def test_supports_and_contradicts_together_is_evidence(example_graph):
    p = plan(example_graph, "What supports or contradicts delegation reduces perceived agency?")
    assert p["lens"] == "evidence"


def test_evidence_question(example_graph):
    p = plan(example_graph, "What is the evidence behind model routing?")
    assert (p["lens"], p["concept"]) == ("evidence", "model routing")


def test_change_question_shows_history(example_graph):
    p = plan(example_graph, "How has our view of delegation changed over time?")
    assert (p["lens"], p["concept"], p["closed"]) == ("history", "delegation", True)


def test_a_date_sets_the_moment_and_keeps_the_main_question(example_graph):
    p = plan(example_graph, "What did we believe about delegation as of 2026-02-15?")
    assert p["concept"] == "delegation" and p["as_of"].startswith("2026-02-15")
    assert p["lens"] == "history"


def test_missing_question_shows_gaps(example_graph):
    assert plan(example_graph, "What are we missing?")["lens"] == "gaps"


def test_overview_question(example_graph):
    assert plan(example_graph, "Give me the big picture")["lens"] == "overview"


def test_a_bare_concept_focuses_it(example_graph):
    p = plan(example_graph, "caching")
    assert (p["lens"], p["concept"]) == ("concept", "caching")


def test_what_relates_to_one_concept_is_its_neighbourhood(example_graph):
    p = plan(example_graph, "What is related to human oversight?")
    assert (p["lens"], p["concept"]) == ("concept", "human oversight")


def test_unclear_question_asks_with_choices(example_graph):
    r = clarification(example_graph, "show me stuff")
    assert {c["lens"] for c in r["choices"]} >= {"overview", "gaps", "history"}


def test_path_with_one_concept_asks_for_the_other(example_graph):
    r = clarification(example_graph, "How does delegation connect?")
    assert "delegation" in r["question"]
    assert all(c["lens"] == "path" for c in r["choices"])


def test_unknown_quoted_concept_asks_and_suggests(example_graph):
    r = clarification(example_graph, 'How does "deleg" relate to perceived agency?')
    assert "deleg" in r["question"]
    assert any("delegation" in c["command"] for c in r["choices"])


def test_two_different_asks_in_one_question_asks_which(example_graph):
    r = clarification(example_graph, "What are we missing, and what contradicts delegation reduces perceived agency?")
    assert {c["lens"] for c in r["choices"]} == {"gaps", "contradictions"}


def test_two_concepts_with_no_verb_asks(example_graph):
    r = clarification(example_graph, "delegation and caching")
    assert {c["lens"] for c in r["choices"]} >= {"path", "concept"}


def test_explicit_lens_without_its_concept_asks(example_graph):
    r = clarification(example_graph, None, lens="evidence")
    assert all(c["lens"] == "evidence" and "--concept" in c["command"] for c in r["choices"])


def test_explicit_lens_is_obeyed(example_graph):
    p = plan(example_graph, None, lens="path", concept="caching", to="latency")
    assert (p["lens"], p["concept"], p["to"]) == ("path", "caching", "latency")


def test_unknown_lens_is_a_usage_error(example_graph):
    with pytest.raises(ToolError) as info:
        plan(example_graph, None, lens="sideways")
    assert info.value.exit_code == 2


def test_visualize_for_a_question_embeds_the_plan(example_graph, tmp_path):
    r = kg.visualize(example_graph, str(tmp_path / "v.html"), question="How does delegation relate to perceived agency?")
    assert r["lens"] == "path" and r["why"]
    html = (tmp_path / "v.html").read_text()
    data = json.loads(html.split('id="data">', 1)[1].split("</script>", 1)[0])
    assert data["open"]["lens"] == "path" and data["open"]["question"].startswith("How does")
    assert "applyOpen" in html


def test_plain_visualize_is_unchanged(example_graph, tmp_path):
    r = kg.visualize(example_graph, str(tmp_path / "v.html"))
    assert "lens" not in r
    data = json.loads((tmp_path / "v.html").read_text().split('id="data">', 1)[1].split("</script>", 1)[0])
    assert data.get("open") is None


def test_cli_returns_the_question_to_ask(example_graph):
    p = run_cli("visualize", "--for", "show me stuff", "--graph", example_graph, "--json")
    doc = json.loads(p.stdout)
    assert p.returncode == 1 and doc["ok"] is False
    assert doc["error"]["code"] == "needs_clarification"
    assert doc["result"]["question"] and doc["result"]["choices"]


def test_cli_lens_and_to(example_graph, tmp_path):
    out = str(tmp_path / "p.html")
    p = run_cli("visualize", "--lens", "path", "--concept", "caching", "--to", "latency", "--out", out,
                "--graph", example_graph, "--json")
    doc = json.loads(p.stdout)
    assert p.returncode == 0 and doc["result"]["lens"] == "path"


def test_mcp_visualize_accepts_a_question(example_graph, tmp_path):
    from knowledge import mcp_server

    schema, _, call = mcp_server.TOOLS["visualize"]
    assert {"question", "lens", "to"} <= set(schema)
    r = call(example_graph, {"question": "What are we missing?", "out": str(tmp_path / "m.html")})
    assert r["lens"] == "gaps"


def test_a_common_word_does_not_hijack_an_overview_question(graph):
    kg.ingest(graph, text="The main finding is that routing saves cost. The main risk is cache loss. "
                          "Topics: routing, cost, cache. Main routing cost cache main.", method="cooccurrence")
    assert plan(graph, "What are the main topics?")["lens"] == "overview"


def test_a_partial_name_offers_the_concepts_that_contain_it(graph):
    from tests.conftest import EXAMPLE

    kg.add(graph, json.loads((EXAMPLE / "relations.json").read_text()))  # relations only: no single-word nodes
    r = clarification(graph, "Is routing worth it?")
    assert any(c["concept"] == "model routing" for c in r["choices"])


def test_missing_between_two_concepts_is_the_gap_between_them(example_graph):
    p = plan(example_graph, "What is missing between caching and delegation?")
    assert (p["lens"], p["concept"], p["to"]) == ("gaps", "caching", "delegation")
