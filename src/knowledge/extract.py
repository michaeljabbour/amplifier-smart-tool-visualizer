"""Turning text into nodes and edges.

Two ways:

- `llm` (model-backed): the original pipeline's "network graph maker" prompt, extended so
  each concept carries a type and each relation a short label and a confidence. Replies in
  the original {node_1, node_2, edge} shape are still read.
- `cooccurrence` (deterministic): a text network. Content words in the same sentence are
  linked within a four-word window (adjacent 3, two apart 2, three apart 1), as text-network
  analysis does. No model, same answer every time.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from .text import content_words, node_key, sentences

NODE_TYPES = ("concept", "entity", "person", "organization", "place", "event", "claim", "evidence",
              "hypothesis", "method", "artifact", "decision", "question", "metric")

# Adapted from rahulnyk/knowledge_graph (MIT, Copyright (c) 2026 Rahul Nayak); see NOTICE.
SYSTEM_PROMPT = """You are a network graph maker who extracts terms and their relations from a given context.
You are provided with a context chunk (delimited by ```). Your task is to extract the ontology of terms
mentioned in the given context. These terms should represent the key concepts as per the context.

Thought 1: While traversing through each sentence, think about the key terms mentioned in it.
  Terms may include object, entity, location, organization, person, condition, acronym, document,
  service, concept, claim, method, metric, decision, etc. Terms should be as atomistic as possible.
Thought 2: Think about how these terms can have one-on-one relations with other terms.
  Terms mentioned in the same sentence or the same paragraph are typically related to each other.
  Terms can be related to many other terms.
Thought 3: Find out the relation between each such related pair of terms.
  Name it with a short lowercase verb label (for example: causes, supports, contradicts, part_of,
  depends_on, measured_by, authored, uses, is_a), and describe it in one sentence.
  If the text argues for or against a statement, use supports or contradicts.
  Give a confidence from 0 to 1 for how clearly the text states the relation.

Format your output as a JSON list. Each element holds a pair of terms and the relation between them:
[
  {
    "node_1": "a concept from the extracted ontology",
    "node_1_type": "one of: TYPES",
    "node_2": "a related concept from the extracted ontology",
    "node_2_type": "one of: TYPES",
    "relation": "short_verb_label",
    "edge": "the relationship between node_1 and node_2 in one sentence",
    "confidence": 0.8
  }
]
Reply with the JSON list only.""".replace("TYPES", ", ".join(NODE_TYPES))


def user_prompt(chunk: str) -> str:
    return f"context: ```{chunk}``` \n\n output: "


def check_triples(value) -> list[dict]:
    """Validate a model reply: a list of relations, each with two terms. Raises ValueError otherwise."""
    if isinstance(value, dict):
        for key in ("triples", "relations", "edges", "items"):
            if isinstance(value.get(key), list):
                value = value[key]
                break
    if not isinstance(value, list):
        raise ValueError("expected a JSON list of relations")
    out = []
    for item in value:
        if not isinstance(item, dict):
            continue
        t = normalise_triple(item)
        if t:
            out.append(t)
    if value and not out:
        raise ValueError("no element had both node_1 and node_2")
    return out


def normalise_triple(item: dict) -> dict | None:
    """Accept {node_1, node_2, edge}, {from, to, relation} or {subject, predicate, object}."""
    a = item.get("node_1") or item.get("from") or item.get("subject") or item.get("source")
    b = item.get("node_2") or item.get("to") or item.get("object") or item.get("target")
    if not a or not b or not node_key(a) or not node_key(b) or node_key(a) == node_key(b):
        return None
    description = str(item.get("edge") or item.get("description") or "").strip()
    relation = str(item.get("relation") or item.get("predicate") or item.get("type") or "").strip()
    if not relation:
        relation = "related_to"
    conf = item.get("confidence")
    try:
        conf = None if conf is None else max(0.0, min(1.0, float(conf)))
    except (TypeError, ValueError):
        conf = None
    return {
        "node_1": str(a).strip(), "node_2": str(b).strip(),
        "node_1_type": _type(item.get("node_1_type") or item.get("from_type")),
        "node_2_type": _type(item.get("node_2_type") or item.get("to_type")),
        "relation": relation, "edge": description, "confidence": conf,
        "evidence": str(item.get("evidence") or "").strip(),
        "valid_from": item.get("valid_from"), "valid_to": item.get("valid_to"),
        "chunk": item.get("chunk") or item.get("chunk_id"),
    }


def _type(value) -> str | None:
    if not value:
        return None
    t = "_".join(str(value).strip().lower().split())
    return t[:40] or None


# --- deterministic text network --------------------------------------------------------------

WINDOW_WEIGHTS = (3.0, 2.0, 1.0)  # distance 1, 2, 3 inside a sentence


def cooccurrence(chunk: str, *, min_count: int = 1) -> tuple[Counter, dict[tuple[str, str], float]]:
    """Words and weighted word pairs for one chunk. Returns (word counts, {(a, b): weight})."""
    counts: Counter = Counter()
    pairs: dict[tuple[str, str], float] = defaultdict(float)
    for sentence in sentences(chunk):
        words = content_words(sentence)
        counts.update(words)
        for i, w in enumerate(words):
            for d, weight in enumerate(WINDOW_WEIGHTS, start=1):
                if i + d >= len(words):
                    break
                other = words[i + d]
                if other != w:
                    a, b = sorted((w, other))
                    pairs[(a, b)] += weight
    if min_count > 1:
        keep = {w for w, c in counts.items() if c >= min_count}
        counts = Counter({w: c for w, c in counts.items() if w in keep})
        pairs = {p: v for p, v in pairs.items() if p[0] in keep and p[1] in keep}
    return counts, dict(pairs)
