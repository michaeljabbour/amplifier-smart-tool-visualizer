"""Model-backed capabilities: routing, refusal without a provider, repair, partial failure."""

import json

import pytest

import knowledge as kg
from knowledge.errors import ToolError
from conftest import STUB


def fake_extractor(system, prompt):
    if "network graph maker" in system:
        return json.dumps([{"node_1": "routing", "node_1_type": "method", "node_2": "cost", "node_2_type": "metric",
                            "relation": "reduces", "edge": "Routing lowers cost.", "confidence": 0.9}])
    raise AssertionError("unexpected prompt")


def test_llm_ingest_with_a_function(graph):
    r = kg.ingest(graph, "Routing lowers cost.", complete=fake_extractor)
    assert r["model"] == "the function you passed" and r["edges_added"] == 1
    e = kg.show(graph, "routing")["outgoing"][0]
    assert (e["relation"], e["confidence"], e["method"]) == ("reduces", 0.9, "llm")
    assert kg.show(graph, "routing")["node"]["type"] == "method"
    # the relation cites its chunk, so evidence shows the words
    assert kg.evidence(graph, e["id"])["passage"] == "Routing lowers cost."


def test_llm_ingest_through_complete_cmd(graph):
    from conftest import EXAMPLE

    r = kg.ingest(graph, documents=kg.load_documents(EXAMPLE / "notes"), complete_cmd=STUB)
    assert r["edges_added"] >= 4
    assert "notes" in [n["id"] for n in kg.search(graph, "notes")["nodes"]]  # old {node_1, node_2, edge} shape read


def test_no_provider_fails_with_the_deterministic_route(graph):
    with pytest.raises(ToolError) as exc:
        kg.ingest(graph, "some text")
    assert exc.value.code == "provider_not_configured" and exc.value.exit_code == 3
    assert "--method agent" in exc.value.hint
    with pytest.raises(ToolError):
        kg.stats(graph)  # nothing was written before the refusal


def test_inside_an_agent_harness_no_key_is_billed(graph, monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-used")
    with pytest.raises(ToolError) as exc:
        kg.ask(graph, "anything")
    assert exc.value.code == "host_model"
    assert "knowledge context" in exc.value.hint
    monkeypatch.setenv("KNOWLEDGE_HOST", "none")
    from knowledge import providers

    assert providers.resolve().kind == "anthropic"


def test_unusable_reply_is_repaired_once_then_fails(graph):
    calls = []

    def bad(system, prompt):
        calls.append(prompt)
        return "no json here" if len(calls) < 2 else json.dumps([{"node_1": "a", "node_2": "b", "edge": "x"}])

    r = kg.ingest(graph, "a and b", complete=bad)
    assert r["edges_added"] == 1 and len(calls) == 2 and "could not be used" in calls[1]

    with pytest.raises(ToolError) as exc:
        kg.ingest(graph, "c and d", complete=lambda s, p: "still not json")
    assert exc.value.code == "model_call_failed"
    assert exc.value.result["failed_chunks"][0]["error"].startswith("The model's reply was still unusable")


def test_partial_failure_keeps_the_rest_and_resumes(graph):
    text = "\n\n".join(["First part about routing. " * 20, "Second part about caching. " * 20])
    state = {"fail": True}

    def flaky(system, prompt):
        if "caching" in prompt and state["fail"]:
            raise RuntimeError("timeout")
        word = "caching" if "caching" in prompt else "routing"
        return json.dumps([{"node_1": word, "node_2": "cost", "relation": "reduces"}])

    with pytest.raises(ToolError) as exc:
        kg.ingest(graph, text, complete=flaky, chunk_size=600, overlap=0)
    assert exc.value.exit_code == 4
    assert exc.value.result["failed_chunks"] and exc.value.result["edges_added"] >= 1
    state["fail"] = False
    r = kg.ingest(graph, text, complete=flaky, chunk_size=600, overlap=0)
    assert r["sources"][0]["status"] == "resumed"
    assert "caching" in [n["id"] for n in kg.search(graph, "caching")["nodes"]]


def test_agent_method_round_trip(graph):
    r = kg.ingest(graph, "Experiment 14 supports the delegation claim.", method="agent")
    task = r["task"]
    assert "network graph maker" in task["system"] and task["chunks"]
    cid = task["chunks"][0]["id"]
    kg.add(graph, {"agent": "me", "edges": [{"from": "experiment 14", "to": "delegation claim", "relation": "supports",
                                             "chunk": cid, "from_type": "evidence", "to_type": "claim"}]})
    e = kg.show(graph, "experiment 14")["outgoing"][0]
    assert e["chunk"] == cid and kg.evidence(graph, e["id"])["passage"].startswith("Experiment 14")


def test_ask_report_questions_reconcile_via_stub(example_graph):
    a = kg.ask(example_graph, "does delegation reduce agency", complete_cmd=STUB)
    assert "[1]" in a["answer"] and a["citations"]
    rep = kg.report(example_graph, top=2, complete_cmd=STUB)
    assert rep["reports"][0]["title"] == "Stub topic"
    assert any(c.get("report") for c in kg.communities(example_graph)["communities"])
    q = kg.questions(example_graph, save=True, complete_cmd=STUB)
    assert q["saved"] and kg.show(example_graph, q["saved"][0])["node"]["type"] == "question"
    rec = kg.reconcile(example_graph, complete_cmd=STUB)
    assert rec["judged"][0]["verdict"] == "contradicts"
    assert kg.contradictions(example_graph)["recorded"]


def test_a_harness_found_by_its_parent_process_bills_no_key(graph, monkeypatch):
    from knowledge import providers

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.setattr(providers, "_parent_commands",
                        lambda limit=12: ["/bin/bash -c knowledge ask q", "/opt/py/bin/python3 /opt/bin/amplifier run"])
    with pytest.raises(ToolError) as exc:
        kg.ask(graph, "anything")
    assert exc.value.code == "host_model" and "Amplifier" in exc.value.message
    # A path that only contains the word is not the harness.
    monkeypatch.setattr(providers, "_parent_commands",
                        lambda limit=12: ["python3 /src/amplifier-smart-tool-visualizer/bin/knowledge.py ask q"])
    assert providers.resolve().kind == "anthropic"


def test_agent_route_returns_chunks_read_by_another_method(graph):
    text = "Experiment 14 supports the delegation claim."
    first = kg.ingest(graph, text, method="cooccurrence")
    assert first["sources"][0]["status"] == "added"
    again = kg.ingest(graph, text, method="agent")
    assert again["task"]["chunks"], "the stored chunks are the agent's task"
    other = kg.ingest(graph, text, method="cooccurrence")
    assert "note" not in other["sources"][0]
    graph2 = graph.replace(".db", "-2.db") if graph.endswith(".db") else graph + "-2"
    kg.ingest(graph2, text, method="agent")
    skipped = kg.ingest(graph2, text, method="cooccurrence")["sources"][0]
    assert skipped["status"] == "unchanged" and "--force" in skipped["note"]


def test_host_task_is_the_deterministic_half(example_graph):
    for cap, key in (("ask", "context"), ("report", "communities"), ("questions", "gaps"),
                     ("reconcile", "contradictions")):
        r = kg.host_task(example_graph, cap, question="agency")
        assert r["task"] and key in r


def test_web_pages_need_allow_network_in_the_library(graph):
    with pytest.raises(ToolError) as exc:
        kg.ingest(graph, urls=["https://example.invalid/page"], method="cooccurrence")
    assert "allow_network" in exc.value.hint
