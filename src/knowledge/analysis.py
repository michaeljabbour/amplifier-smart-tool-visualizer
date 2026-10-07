"""Network analysis on a graph view. Deterministic, standard library only.

The weighting follows the original notebook: a relation a reader extracted counts 4,
and each chunk two concepts share adds 1 ("contextual proximity"). Communities come
from Louvain by default, or Girvan-Newman (the notebook's choice) for small graphs.
Centrality, structural gaps and the diversity reading follow text-network analysis:
the most central concepts, the bridges between topics, and the pairs of well-developed
topics with little between them.
"""

from __future__ import annotations

import heapq
import math
import random
from collections import defaultdict, deque

RELATION_WEIGHT = 4.0
PROXIMITY_WEIGHT = 1.0
MAX_PROXIMITY_GROUP = 40  # a chunk naming more concepts than this adds no proximity edges
BETWEENNESS_SAMPLE = 400  # above this many nodes, betweenness is estimated from a fixed sample


class View:
    """An undirected weighted graph built from the store, plus the typed edges behind it."""

    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.adj: dict[str, dict[str, float]] = defaultdict(dict)
        self.edges: list[dict] = []  # typed edges in the window
        self.pair_edges: dict[tuple[str, str], list[dict]] = defaultdict(list)
        self.proximity: dict[tuple[str, str], int] = defaultdict(int)

    def add_weight(self, a: str, b: str, w: float) -> None:
        if a == b:
            return
        self.adj[a][b] = self.adj[a].get(b, 0.0) + w
        self.adj[b][a] = self.adj[b].get(a, 0.0) + w

    @property
    def total_weight(self) -> float:
        return sum(sum(n.values()) for n in self.adj.values()) / 2

    def degree(self, n: str) -> int:
        return len(self.adj.get(n, {}))

    def strength(self, n: str) -> float:
        return sum(self.adj.get(n, {}).values())


def build_view(graph, *, as_of: str | None = None, proximity: bool = True, relations: list[str] | None = None,
               types: list[str] | None = None, include_closed: bool = False) -> View:
    view = View()
    for n in graph.nodes():
        if types and n["type"] not in types:
            continue
        view.nodes[n["id"]] = n
    for e in graph.edges(as_of=as_of, include_closed=include_closed):
        if relations and e["relation"] not in relations:
            continue
        if e["source"] not in view.nodes or e["target"] not in view.nodes:
            continue
        view.edges.append(e)
        a, b = sorted((e["source"], e["target"]))
        view.pair_edges[(a, b)].append(e)
        scale = e["weight"] if e["method"] == "cooccurrence" else RELATION_WEIGHT * (e["confidence"] or 1.0)
        view.add_weight(a, b, scale)
    if proximity and not relations:
        for members in graph.chunk_members().values():
            present = sorted({m for m in members if m in view.nodes})
            if len(present) < 2 or len(present) > MAX_PROXIMITY_GROUP:
                continue
            for i, a in enumerate(present):
                for b in present[i + 1:]:
                    view.proximity[(a, b)] += 1
                    view.add_weight(a, b, PROXIMITY_WEIGHT)
    for n in view.nodes:
        view.adj.setdefault(n, {})
    return view


# --- centrality ------------------------------------------------------------------------------

def betweenness(view: View, sample: int = BETWEENNESS_SAMPLE, seed: int = 7) -> dict[str, float]:
    """Brandes' betweenness on hop distance, normalised to 0..1. Sampled (with a fixed seed) on big graphs."""
    nodes = sorted(n for n in view.adj if view.adj[n])
    bc = dict.fromkeys(view.adj, 0.0)
    if len(nodes) < 3:
        return bc
    sources = nodes
    if len(nodes) > sample:
        sources = random.Random(seed).sample(nodes, sample)
    for s in sources:
        stack, pred = [], defaultdict(list)
        sigma = defaultdict(float)
        sigma[s] = 1.0
        dist = {s: 0}
        queue = deque([s])
        while queue:
            v = queue.popleft()
            stack.append(v)
            for w in view.adj[v]:
                if w not in dist:
                    dist[w] = dist[v] + 1
                    queue.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)
        delta = defaultdict(float)
        while stack:
            w = stack.pop()
            for v in pred[w]:
                delta[v] += sigma[v] / sigma[w] * (1 + delta[w])
            if w != s:
                bc[w] += delta[w]
    n = len(nodes)
    scale = (n / len(sources)) / ((n - 1) * (n - 2)) if n > 2 else 1.0
    return {k: v * scale for k, v in bc.items()}


def centrality(view: View) -> dict[str, dict]:
    bc = betweenness(view)
    max_deg = max((view.degree(n) for n in view.adj), default=1) or 1
    return {n: {"degree": view.degree(n), "strength": round(view.strength(n), 2),
                "degree_norm": round(view.degree(n) / max_deg, 4), "betweenness": round(bc.get(n, 0.0), 4)}
            for n in view.adj}


# --- communities -----------------------------------------------------------------------------

def louvain(view: View, resolution: float = 1.0, seed: int = 7) -> list[list[str]]:
    """Louvain community detection. Deterministic: nodes are visited in a seeded fixed order."""
    m2 = 2 * view.total_weight
    isolated = [[n] for n in sorted(view.adj) if not view.adj[n]]
    if m2 == 0:
        return isolated
    # each "super node" holds a list of original nodes
    members = {n: [n] for n in view.adj if view.adj[n]}
    adj = {n: dict(nb) for n, nb in view.adj.items() if nb}
    rng = random.Random(seed)
    while True:
        comm = {n: n for n in adj}
        # a super node's self-loop already holds its inside weight in both directions
        k = {n: sum(adj[n].values()) for n in adj}
        tot = dict(k)
        order = sorted(adj)
        rng.shuffle(order)
        moved_any, improved = False, True
        while improved:
            improved = False
            for n in order:
                current = comm[n]
                links: dict[str, float] = defaultdict(float)
                for nb, w in adj[n].items():
                    if nb != n:
                        links[comm[nb]] += w
                tot[current] -= k[n]
                best, best_gain = current, links.get(current, 0.0) - resolution * tot[current] * k[n] / m2
                for c, w in sorted(links.items()):
                    gain = w - resolution * tot[c] * k[n] / m2
                    if gain > best_gain + 1e-12:
                        best, best_gain = c, gain
                tot[best] += k[n]
                if best != current:
                    comm[n] = best
                    improved = moved_any = True
        if not moved_any:
            break
        # aggregate communities into super nodes
        new_members: dict[str, list[str]] = defaultdict(list)
        for n, c in comm.items():
            new_members[c].extend(members[n])
        new_adj: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for n, nbs in adj.items():
            for nb, w in nbs.items():
                new_adj[comm[n]][comm[nb]] += w
        members = dict(new_members)
        adj = {c: dict(nb) for c, nb in new_adj.items()}
        if len(adj) == 1:
            break
    groups = [sorted(g) for g in members.values()] + isolated
    return sorted(groups, key=lambda g: (-len(g), g[0]))


def girvan_newman(view: View, levels: int = 2, max_edges: int = 1500) -> list[list[str]]:
    """Split by removing the edge with the highest betweenness until the graph breaks apart.

    The notebook took the second split. This is slow (cubic), so it refuses big graphs.
    """
    if sum(len(v) for v in view.adj.values()) // 2 > max_edges:
        from .errors import ToolError

        raise ToolError("graph_too_large", f"Girvan-Newman is too slow above {max_edges} edges.",
                        hint="Use the default method (--method louvain).")
    adj = {n: set(nb) for n, nb in view.adj.items()}
    base = len(_components(adj))
    target = base + levels
    while len(_components(adj)) < target:
        eb = _edge_betweenness(adj)
        if not eb:
            break
        (a, b), _ = max(eb.items(), key=lambda kv: (kv[1], kv[0]))
        adj[a].discard(b)
        adj[b].discard(a)
    return sorted((sorted(c) for c in _components(adj)), key=lambda g: (-len(g), g[0]))


def _components(adj: dict[str, set]) -> list[set]:
    seen, out = set(), []
    for n in sorted(adj):
        if n in seen:
            continue
        comp, queue = set(), deque([n])
        while queue:
            v = queue.popleft()
            if v in comp:
                continue
            comp.add(v)
            queue.extend(adj[v] - comp)
        seen |= comp
        out.append(comp)
    return out


def _edge_betweenness(adj: dict[str, set]) -> dict[tuple[str, str], float]:
    eb: dict[tuple[str, str], float] = defaultdict(float)
    for s in adj:
        stack, pred, sigma, dist = [], defaultdict(list), defaultdict(float), {s: 0}
        sigma[s] = 1.0
        queue = deque([s])
        while queue:
            v = queue.popleft()
            stack.append(v)
            for w in adj[v]:
                if w not in dist:
                    dist[w] = dist[v] + 1
                    queue.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)
        delta = defaultdict(float)
        while stack:
            w = stack.pop()
            for v in pred[w]:
                c = sigma[v] / sigma[w] * (1 + delta[w])
                eb[tuple(sorted((v, w)))] += c
                delta[v] += c
    return eb


def modularity(view: View, groups: list[list[str]]) -> float:
    m2 = 2 * view.total_weight
    if m2 == 0:
        return 0.0
    label = {n: i for i, g in enumerate(groups) for n in g}
    q = 0.0
    tot: dict[int, float] = defaultdict(float)
    inside: dict[int, float] = defaultdict(float)
    for n, nbs in view.adj.items():
        tot[label.get(n, -1)] += sum(nbs.values())
        for nb, w in nbs.items():
            if label.get(n) == label.get(nb):
                inside[label.get(n, -1)] += w
    for c in tot:
        q += inside[c] / m2 - (tot[c] / m2) ** 2
    return round(q, 4)


def diversity(view: View, groups: list[list[str]], q: float) -> dict:
    """How spread out the discourse is, after text-network analysis: biased, focused, diversified, dispersed.

    An approximate reading from modularity and the share of the biggest topic; use it to
    decide whether to look for gaps (diversified, dispersed) or for missing viewpoints (biased).
    """
    connected = [g for g in groups if len(g) > 1]
    total = sum(len(g) for g in connected) or 1
    top_share = (len(connected[0]) / total) if connected else 1.0
    if q < 0.2 or top_share > 0.6:
        state, advice = "biased", "One topic dominates. Look for viewpoints and material that are missing."
    elif q < 0.4:
        state, advice = "focused", "A few closely linked topics. Good for depth; widen if exploring."
    elif q < 0.65:
        state, advice = "diversified", "Several distinct, linked topics. Look at the gaps between them."
    else:
        state, advice = "dispersed", "Many loosely linked topics. Find the bridges, or narrow the focus."
    return {"state": state, "modularity": q, "top_topic_share": round(top_share, 3), "advice": advice}


# --- paths -----------------------------------------------------------------------------------

def shortest_path(view: View, a: str, b: str, *, weighted: bool = True, avoid: set | None = None) -> list[str] | None:
    """Dijkstra; strong ties are short (cost 1/weight). None when the two are not connected."""
    avoid = avoid or set()
    dist, prev = {a: 0.0}, {}
    heap = [(0.0, a)]
    done = set()
    while heap:
        d, v = heapq.heappop(heap)
        if v in done:
            continue
        done.add(v)
        if v == b:
            break
        for w, weight in view.adj.get(v, {}).items():
            if w in avoid and w != b:
                continue
            nd = d + ((1.0 / weight) if weighted and weight > 0 else 1.0)
            if nd < dist.get(w, math.inf):
                dist[w], prev[w] = nd, v
                heapq.heappush(heap, (nd, w))
    if b not in dist:
        return None
    path = [b]
    while path[-1] != a:
        path.append(prev[path[-1]])
    return path[::-1]


def alternative_paths(view: View, a: str, b: str, k: int = 3) -> list[list[str]]:
    """Up to k paths that share no middle node, shortest first."""
    paths, avoid = [], set()
    for _ in range(k):
        p = shortest_path(view, a, b, avoid=avoid)
        if not p:
            break
        paths.append(p)
        middle = set(p[1:-1])
        if not middle:
            break
        avoid |= middle
    return paths


def hops(view: View, a: str, b: str) -> int | None:
    p = shortest_path(view, a, b, weighted=False)
    return None if p is None else len(p) - 1


# --- structural gaps -------------------------------------------------------------------------

def community_links(view: View, groups: list[list[str]]) -> dict[tuple[int, int], float]:
    label = {n: i for i, g in enumerate(groups) for n in g}
    links: dict[tuple[int, int], float] = defaultdict(float)
    for n, nbs in view.adj.items():
        for nb, w in nbs.items():
            ca, cb = label.get(n), label.get(nb)
            if ca is not None and cb is not None and ca < cb:
                links[(ca, cb)] += w
    return links


def structural_gaps(view: View, groups: list[list[str]], cent: dict[str, dict], *, top: int = 5,
                    min_size: int = 3) -> list[dict]:
    """Pairs of substantial topics with far fewer links between them than their size predicts.

    score = 1 - observed / expected, where expected = vol_a * vol_b / 2m (the configuration
    model). 1.0 means no link at all; near 0 means as linked as chance. Bigger topics first.
    """
    m2 = 2 * view.total_weight
    if m2 == 0:
        return []
    vol = [sum(view.strength(n) for n in g) for g in groups]
    links = community_links(view, groups)
    candidates = [i for i, g in enumerate(groups) if len(g) >= min_size][:12]
    gaps = []
    for x, i in enumerate(candidates):
        for j in candidates[x + 1:]:
            expected = vol[i] * vol[j] / m2
            observed = links.get((min(i, j), max(i, j)), 0.0)
            if expected <= 0:
                continue
            score = max(0.0, 1.0 - observed / expected)
            if score < 0.5:
                continue
            gaps.append({
                "between": [i, j],
                "score": round(score, 3),
                "observed_weight": round(observed, 2),
                "expected_weight": round(expected, 2),
                "size": [len(groups[i]), len(groups[j])],
                "bridge_candidates": [_top(groups[i], cent, 3), _top(groups[j], cent, 3)],
            })
    gaps.sort(key=lambda g: (-g["score"] * math.log(2 + min(g["size"])), g["between"]))
    return gaps[:top]


def _top(group: list[str], cent: dict[str, dict], k: int) -> list[str]:
    return sorted(group, key=lambda n: (-cent.get(n, {}).get("betweenness", 0),
                                        -cent.get(n, {}).get("degree", 0), n))[:k]


def top_nodes(group: list[str], cent: dict[str, dict], k: int = 5) -> list[str]:
    return sorted(group, key=lambda n: (-cent.get(n, {}).get("strength", 0), n))[:k]
