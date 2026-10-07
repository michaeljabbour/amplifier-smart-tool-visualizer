"""Writing, reading and time: the deterministic core."""

import pytest

import knowledge as kg
from knowledge.errors import ToolError
from knowledge.text import split_text


def test_split_text_respects_size_and_overlap():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 120 for i in range(10))
    chunks = split_text(text, 1500, 150)
    assert len(chunks) > 3
    assert all(len(c) <= 1500 for c in chunks)
    # overlap: the start of each chunk repeats the end of the one before
    assert chunks[1].split()[0] in chunks[0]


def test_cooccurrence_ingest_is_deterministic_and_idempotent(graph):
    text = "Model routing reduces inference cost. Routing sends easy requests to small models."
    first = kg.ingest(graph, text, method="cooccurrence")
    assert first["nodes_added"] > 3 and first["edges_added"] > 3
    again = kg.ingest(graph, text, method="cooccurrence")
    assert again["sources"][0]["status"] == "unchanged"
    assert again["edges_added"] == 0
    assert kg.show(graph, "routing")["degree"] >= 3


def test_changed_source_closes_old_edges(graph):
    kg.ingest(graph, "Alpha beta gamma.", uri="note.md", method="cooccurrence")
    r = kg.ingest(graph, "Alpha delta epsilon.", uri="note.md", method="cooccurrence")
    assert r["sources"][0]["status"] == "replaced"
    assert r["sources"][0]["edges_closed"] >= 1
    s = kg.stats(graph)
    assert s["closed_edges"] >= 1
    current = {e["other"] for e in kg.show(graph, "alpha")["outgoing"] + kg.show(graph, "alpha")["incoming"]}
    assert "beta" not in current and "delta" in current


def test_relate_supersede_and_as_of(graph):
    old = kg.relate(graph, "model x", "outperforms", "model y", valid_from="2026-03-01")["edge"]
    new = kg.relate(graph, "model y", "outperforms", "model x", valid_from="2026-04-01", supersedes=old["id"])
    assert new["superseded"]["invalidated_by"] == f"edge:{new['edge']['id']}"
    then = kg.show(graph, "model x", as_of="2026-03-15")
    assert [e["relation"] for e in then["outgoing"]] == ["outperforms"]
    now = kg.show(graph, "model x")
    assert not now["outgoing"] and now["incoming"][0]["source"] == "model y"
    events = [e["event"] for e in kg.timeline(graph, "model x")["entries"]]
    assert events.count("relation added") == 2 and "relation closed" in events
    with pytest.raises(ToolError) as exc:
        kg.supersede(graph, old["id"])
    assert exc.value.code == "already_closed"


def test_add_reads_every_relation_shape_and_reports_skips(graph):
    r = kg.add(graph, {"agent": "a1", "edges": [
        {"from": "A", "to": "B", "relation": "supports"},
        {"node_1": "C", "node_2": "D", "edge": "C relates to D"},
        {"subject": "E", "predicate": "causes", "object": "F"},
        {"from": "same", "to": "same"},
    ]})
    assert len(r["edges"]) == 3
    assert r["skipped"][0]["item"] == 3
    assert kg.show(graph, "a")["outgoing"][0]["agent"] == "a1"
    with pytest.raises(ToolError):
        kg.add(graph, {"edges": [{"from": "x"}]})


def test_unknown_concept_suggests(example_graph):
    with pytest.raises(ToolError) as exc:
        kg.show(example_graph, "deleg")
    assert exc.value.code == "concept_not_found"
    assert any("delegat" in s for s in exc.value.suggestions)


def test_search_finds_names_and_passages(example_graph):
    r = kg.search(example_graph, "routing cost")
    ids = [n["id"] for n in r["nodes"]]
    assert "model routing" in ids or "routing" in ids
    assert r["passages"]


def test_evidence_and_contradictions(example_graph):
    ev = kg.evidence(example_graph, "delegation reduces perceived agency")
    assert [e["other"] for e in ev["supporting"]] == ["experiment 14"]
    assert [e["other"] for e in ev["contradicting"]] == ["2025 boundary survey"]
    c = kg.contradictions(example_graph)
    assert c["explicit"] and c["candidates"]
    assert "opposite" in c["candidates"][0]["why"]
    edge = kg.evidence(example_graph, c["explicit"][0]["id"])
    assert edge["source"]["title"].startswith("Researcher")


def test_path_and_gap_between(example_graph):
    p = kg.path(example_graph, "human oversight", "delegation")
    assert p["connected"] and p["paths"][0]["nodes"][0] == "human oversight"
    g = kg.gaps(example_graph, between=["human oversight", "inference cost"])
    assert "gap" in g["verdict"]


def test_events_log_every_change(graph):
    kg.relate(graph, "a", "supports", "b", agent="tester")
    ev = kg.events(graph)["events"]
    kinds = [e["kind"] for e in ev]
    assert kinds.count("node_added") == 2 and "edge_added" in kinds
    last = kg.events(graph)["last"]
    kg.relate(graph, "b", "supports", "c")
    assert all(e["seq"] > last for e in kg.events(graph, since=last)["events"])


def test_context_is_numbered_and_stable(example_graph):
    a = kg.context(example_graph, "does delegation reduce agency")
    b = kg.context(example_graph, "does delegation reduce agency")
    assert a["text"] == b["text"] and a["text"].startswith("[1] ")
    assert any(c["kind"] == "relation" for c in a["citations"])


def test_missing_graph_is_a_clear_error(tmp_path):
    with pytest.raises(ToolError) as exc:
        kg.stats(str(tmp_path / "nope.db"))
    assert exc.value.code == "graph_not_found"
