"""Network analysis on known shapes."""

import knowledge as kg
from knowledge import analysis as an


def two_cliques(graph, bridge=True):
    left = ["a1", "a2", "a3", "a4", "a5"]
    right = ["b1", "b2", "b3", "b4", "b5"]
    for group in (left, right):
        for i, x in enumerate(group):
            for y in group[i + 1:]:
                kg.relate(graph, x, "related_to", y)
    if bridge:
        kg.relate(graph, "a1", "related_to", "b1")
    return left, right


def view(graph):
    with kg.open_graph(graph) as g:
        return an.build_view(g)


def test_louvain_splits_two_cliques(graph):
    left, right = two_cliques(graph)
    groups = an.louvain(view(graph))
    assert sorted(map(sorted, groups)) == sorted([sorted(left), sorted(right)])


def test_girvan_newman_matches_on_small_graph(graph):
    left, right = two_cliques(graph)
    groups = an.girvan_newman(view(graph), levels=1)
    assert sorted(map(sorted, groups)) == sorted([sorted(left), sorted(right)])


def test_bridge_nodes_have_highest_betweenness(graph):
    two_cliques(graph)
    bc = an.betweenness(view(graph))
    top = sorted(bc, key=lambda n: -bc[n])[:2]
    assert sorted(top) == ["a1", "b1"]
    assert kg.analyze(graph)["bridges"][:2] in (["a1", "b1"], ["b1", "a1"])


def test_structural_gap_found_between_unlinked_topics(graph):
    two_cliques(graph, bridge=False)
    gaps = kg.gaps(graph)["gaps"]
    assert gaps and gaps[0]["score"] == 1.0
    assert {gaps[0]["bridge_candidates"][0][0][0], gaps[0]["bridge_candidates"][1][0][0]} == {"a", "b"}


def test_modularity_and_diversity(graph):
    two_cliques(graph)
    c = kg.communities(graph)
    assert c["modularity"] > 0.3
    assert c["diversity"]["state"] in ("focused", "diversified")


def test_paths_share_no_middle_node(graph):
    for mid in ("m1", "m2", "m3"):
        kg.relate(graph, "start", "to", mid)
        kg.relate(graph, mid, "to", "end")
    paths = kg.path(graph, "start", "end", k=3)["paths"]
    middles = [p["nodes"][1] for p in paths]
    assert len(paths) == 3 and len(set(middles)) == 3


def test_as_of_changes_the_view(graph):
    kg.relate(graph, "x", "linked", "y", valid_from="2026-01-01")
    kg.relate(graph, "y", "linked", "z", valid_from="2026-06-01")
    assert not kg.path(graph, "x", "z", as_of="2026-02-01")["connected"]
    assert kg.path(graph, "x", "z")["connected"]
