"""Choose the view that answers a question, or say what is unclear and ask.

Deterministic: the question's wording picks a lens (path, evidence, contradictions, history,
gaps, overview, concept) and the concepts it names are matched against the graph. When the
question does not say enough to choose, nothing is guessed: `choose_view` raises
`needs_clarification` with a question to put to the person and the exact command for each
answer. The tool never prompts; the caller asks.
"""

from __future__ import annotations

import re

from .errors import INPUT, USAGE, ToolError
from .store import parse_time

LENSES = {
    "overview": "the whole map: topics, central concepts and gaps",
    "concept": "one concept and its neighbourhood",
    "path": "how two concepts connect",
    "evidence": "what backs a claim, and what argues against it",
    "contradictions": "where the graph disagrees with itself",
    "history": "what changed over time, with closed relations shown",
    "gaps": "topics that should be linked but barely are",
}
NEEDS = {"path": 2, "evidence": 1, "concept": 1}  # concepts a lens cannot do without

_INTENTS = [
    ("path", r"\bhow (?:does|do|is|are|did)\b.*\b(?:relate[sd]?|connect(?:s|ed)?|link(?:s|ed)?|lead(?:s)? to|affect(?:s|ed)?)\b"
             r"|\bbetween\b.+\band\b|\bpath\b|\bconnection\b|\brelationship\b"),
    ("contradictions", r"\b(?:contradict\w*|disagree\w*|conflict\w*|inconsisten\w*|tensions?|disput\w*|at odds)\b"),
    ("evidence", r"\b(?:evidence|backs?|backed|backing|supports?|supported|supporting|proves?|proof|sources?|cites?|"
                 r"citations?|justif\w*|why (?:do|should) (?:we|i) (?:believe|trust)|is (?:it|this|that) true)\b"),
    ("history", r"\b(?:when|changed?|changes|changing|over time|history|historical|timeline|evolv\w*|used to|"
                r"replaced|superseded|as of|back then|believe[ds]?|thought)\b"),
    ("gaps", r"\b(?:gaps?|missing|blind ?spots?|unexplored|under-?studied|overlooked|disconnected|not connected)\b"),
    ("overview", r"\b(?:overview|big picture|topics?|themes?|what is (?:this|it) about|landscape|summar\w*|"
                 r"whole graph|everything)\b"),
]
_NEIGHBOURHOOD = re.compile(r"\bwhat(?:'s| is| are)? (?:related|connected|linked) to\b|\bwhat (?:relates|connects|links) to\b")
_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2}(?:[t ]\d{2}:\d{2}(?::\d{2})?z?)?)\b")
_QUOTED = re.compile(r"[\"“]([^\"”]+)[\"”]")
_PREFIX = re.compile(r"^(?:claim|finding|decision|question|review[^:]*|evidence|hypothesis):\s*")
_STOP = {"the", "and", "what", "how", "does", "did", "this", "that", "with", "from", "about", "between", "over",
         "time", "when", "have", "has", "our", "its", "are", "is", "show", "graph", "view", "into", "for", "of", "to",
         "main", "kind", "thing", "things", "stuff", "part", "way", "use", "used", "tell", "give", "make", "need",
         "want", "look", "see", "find", "should", "could", "would", "worth", "really", "much", "many", "some", "any",
         "all", "more", "most", "here", "there", "which", "who", "why", "where", "can", "will", "was", "were", "been",
         "then", "than", "them", "they", "you", "your", "me", "my", "we", "us", "it", "on", "in", "at", "by", "or", "an", "a"}


def _intent_words() -> set[str]:
    return {w for _, rx in _INTENTS for w in re.findall(r"[a-z]{3,}", rx)}


def _normalise(text: str) -> str:
    text = text.lower().replace("’", "'")
    text = re.sub(r"[?!,;()\[\]“”\"]", " ", text)
    text = re.sub(r"\.(\s|$)", r" \1", text)
    return " " + re.sub(r"\s+", " ", text).strip() + " "


def _find_concepts(g, question: str) -> tuple[list[str], list[dict], set[str]]:
    """Concepts named in the question, in the order they appear. Quoted names must resolve;
    unquoted ones match whole node labels, longest first, without overlapping."""
    found: list[tuple[int, str]] = []
    unclear: list[dict] = []
    taken: list[tuple[int, int]] = []
    for name in _QUOTED.findall(question):
        try:
            found.append((question.find(name), g.resolve(name)))
        except ToolError as err:
            unclear.append({"name": name, "suggestions": err.suggestions})
    text = _normalise(_QUOTED.sub(" ", question))
    skip = _STOP | _intent_words()
    variants = []
    nodes = g.nodes()
    words = {n["id"] for n in nodes if n.get("type") == "term"}  # word-network nodes: every common word is one
    for node in nodes:
        variants.append((node["id"], node["id"]))
        bare = _PREFIX.sub("", node["id"])
        if bare != node["id"]:
            variants.append((bare, node["id"]))  # people say the claim, not "claim: ..."
    for said, label in sorted(variants, key=lambda v: -len(v[0])):
        if len(said) < 3 or said in skip:
            continue
        at = text.find(" " + said + " ")
        if at < 0:
            continue
        span = (at, at + len(said) + 1)
        if any(a < span[1] and span[0] < b for a, b in taken):
            continue
        taken.append(span)
        found.append((10_000 + at, label))
    ordered = []
    for _, label in sorted(found):
        if label not in ordered:
            ordered.append(label)
    quoted = {lab for at, lab in found if at < 10_000}
    return ordered, unclear, {c for c in ordered if c in words and c not in quoted}


def _partial(g, question: str, k: int = 5) -> list[str]:
    """Concepts whose labels contain a content word of the question, most connected first."""
    deg: dict[str, int] = {}
    for e in g.edges():
        deg[e["source"]] = deg.get(e["source"], 0) + 1
        deg[e["target"]] = deg.get(e["target"], 0) + 1
    skip = _STOP | _intent_words()
    terms = [w for w in re.findall(r"[a-z0-9][a-z0-9.\-]{2,}", question.lower()) if w not in skip]
    hits = [n for n in deg if any(re.search(r"(?:^|[\s:-])" + re.escape(t) + r"(?:$|[\s-])", n) for t in terms)]
    return sorted(hits, key=lambda n: (-deg[n], len(n)))[:k]


def _central(g, k: int = 5) -> list[str]:
    deg: dict[str, int] = {}
    for e in g.edges():
        deg[e["source"]] = deg.get(e["source"], 0) + 1
        deg[e["target"]] = deg.get(e["target"], 0) + 1
    return [n for n, _ in sorted(deg.items(), key=lambda x: (-x[1], x[0]))[:k]]


def _command(graph_name: str, lens: str, concept: str | None = None, to: str | None = None,
             as_of: str | None = None) -> str:
    parts = ["knowledge visualize", "--lens", lens]
    if concept:
        parts += ["--concept", f'"{concept}"']
    if to:
        parts += ["--to", f'"{to}"']
    if as_of:
        parts += ["--as-of", as_of[:10]]
    parts += ["--graph", f'"{graph_name}"', "--open"]
    return " ".join(parts)


def _choice(graph_name, lens, label, concept=None, to=None, as_of=None) -> dict:
    return {"lens": lens, "label": label, "concept": concept, "to": to,
            "command": _command(graph_name, lens, concept, to, as_of)}


def _ask(question: str, choices: list[dict], understood: dict) -> ToolError:
    lines = [f"- {c['label']}: {c['command']}" for c in choices]
    return ToolError(
        "needs_clarification", question,
        hint="Ask the person this question (do not pick for them), then run the command for their answer:\n"
             + "\n".join(lines),
        exit_code=INPUT,
        result={"question": question, "choices": choices, "understood": understood},
    )


def _why(lens: str, concept, to, as_of) -> str:
    when = f" as it stood on {as_of[:10]}" if as_of else ""
    return {
        "overview": f"The whole map{when}: topics, the most central concepts and the gaps between topics.",
        "concept": f"“{concept}” and what is linked to it{when}.",
        "path": f"How “{concept}” connects to “{to}”{when}, step by step.",
        "evidence": f"What backs “{concept}” and what argues against it{when}, with the passages each relation came from.",
        "contradictions": (f"Where the graph disagrees about “{concept}”{when}, including relations that were closed."
                           if concept else f"Where the graph disagrees with itself{when}, including closed relations."),
        "history": (f"What was said about “{concept}” over time{when}; closed relations are shown so the changes are visible."
                    if concept else f"The graph through time{when}; press Play to replay it, closed relations shown."),
        "gaps": (f"How far apart “{concept}” and “{to}” are{when}." if concept and to else
                 f"Topics that should be linked but barely are{when}; the first gap is opened."),
    }[lens]


def _alternatives(graph_name, lens, concepts, as_of) -> list[dict]:
    alts = []
    c = concepts[0] if concepts else None
    if lens != "evidence" and c:
        alts.append(_choice(graph_name, "evidence", f"what backs “{c}”", c, as_of=as_of))
    if lens != "history" and c:
        alts.append(_choice(graph_name, "history", f"how “{c}” changed over time", c))
    if lens not in ("path", "gaps") and len(concepts) >= 2:
        alts.append(_choice(graph_name, "path", f"how “{concepts[0]}” connects to “{concepts[1]}”", *concepts[:2]))
    if lens != "overview":
        alts.append(_choice(graph_name, "overview", "the whole map", as_of=as_of))
    return alts[:3]


def choose_view(g, question: str | None = None, *, lens: str | None = None, concept: str | None = None,
                to: str | None = None, as_of: str | None = None) -> dict:
    """Pick the lens and its concepts for a question (or an explicit lens). Returns
    {lens, concept, to, as_of, closed, why, alternatives, question}; raises needs_clarification
    when the question does not say enough to choose."""
    name = g.name
    if lens is not None and lens not in LENSES:
        raise ToolError("usage", f"Unknown lens \"{lens}\".", hint="Use one of: " + ", ".join(LENSES), exit_code=USAGE)
    q = (question or "").strip()
    text = _normalise(q)
    intents = [i for i, rx in _INTENTS if re.search(rx, text)]
    if _NEIGHBOURHOOD.search(text) and "path" in intents:
        intents.remove("path")
    date = _DATE.search(text)
    as_of = parse_time(as_of or (date.group(1).upper().replace(" ", "T") if date else None))

    concepts, unclear, weak = _find_concepts(g, q) if q else ([], [], set())
    if "gaps" in intents and "path" in intents:
        intents.remove("path")  # "what is missing between X and Y": the gap between them
    if weak and intents and set(intents) <= {"overview", "gaps"} and " between " not in text:
        concepts = [c for c in concepts if c not in weak]  # "the main topics": a common word is not the subject
    concepts = [g.resolve(c) for c in (concept, to) if c] or concepts
    understood = {"intents": intents, "concepts": concepts, "as_of": as_of}

    if unclear:
        u = unclear[0]
        sugg = u["suggestions"][:5]
        want = lens or next((i for i in intents if i not in ("history", "overview")), None) or "concept"
        others = [c for c in concepts]
        choices = []
        for s in sugg:
            if want == "path" and others:
                choices.append(_choice(name, "path", f"“{s}” and “{others[0]}”", s, others[0], as_of))
            else:
                choices.append(_choice(name, want if NEEDS.get(want, 0) <= 1 else "concept", f"“{s}”", s, as_of=as_of))
        if not choices:
            choices = [_choice(name, "overview", "show the whole map instead", as_of=as_of)]
        raise _ask(f"I couldn't find “{u['name']}” in this graph. Which concept did you mean?", choices, understood)

    if lens is None:
        if "evidence" in intents and "contradictions" in intents and concepts:
            intents.remove("contradictions")
        modifiers = {"history"} if len(intents) > 1 else set()
        if len(intents) > 1 and "overview" in intents:
            modifiers.add("overview")
        main = [i for i in intents if i not in modifiers]
        if len(main) > 1:
            choices = [_choice(name, i, LENSES[i], concepts[0] if concepts and i != "gaps" else None,
                               concepts[1] if i == "path" and len(concepts) > 1 else None, as_of) for i in main]
            raise _ask("That asks two things. Which do you want to see first?", choices, understood)
        if main == ["overview"] and concepts:
            main = []
        if main:
            lens = main[0]
        elif "history" in intents:
            lens = "history"
        elif len(concepts) == 1:
            lens = "concept"
        elif len(concepts) >= 2:
            a, b = concepts[:2]
            raise _ask(f"What do you want to see about “{a}” and “{b}”?",
                       [_choice(name, "path", f"how “{a}” connects to “{b}”", a, b, as_of),
                        _choice(name, "concept", f"“{a}” and its neighbourhood", a, as_of=as_of),
                        _choice(name, "concept", f"“{b}” and its neighbourhood", b, as_of=as_of)], understood)
        else:
            near = _partial(g, q) if q else []
            if near:
                choices = [_choice(name, "concept", f"“{c}”", c, as_of=as_of) for c in near]
                choices.append(_choice(name, "overview", "none of these: show the big picture", as_of=as_of))
                raise _ask("Which of these do you mean? I couldn't match the question to one concept.", choices, understood)
            central = _central(g, 3)
            choices = [_choice(name, "overview", "the big picture: topics and central concepts", as_of=as_of),
                       _choice(name, "gaps", "what is missing between topics", as_of=as_of),
                       _choice(name, "history", "what changed over time"),
                       _choice(name, "contradictions", "where the material disagrees", as_of=as_of)]
            choices += [_choice(name, "concept", f"one concept, for example “{c}”", c, as_of=as_of) for c in central[:2]]
            raise _ask("What are you trying to find out? I couldn't tell from the question.", choices, understood)

    need = NEEDS.get(lens, 0)
    if len(concepts) < need:
        central = [c for c in _central(g, 6) if c not in concepts]
        if lens == "path" and concepts:
            a = concepts[0]
            raise _ask(f"How “{a}” connects to what? Name the second concept.",
                       [_choice(name, "path", f"“{a}” and “{c}”", a, c, as_of) for c in central[:4]], understood)
        raise _ask(f"Which concept should the {lens} view be about?",
                   [_choice(name, lens, f"“{c}”", c, central[i + 1] if lens == "path" and i + 1 < len(central) else None,
                            as_of) for i, c in enumerate(central[:4])], understood)
    if lens in ("path", "gaps") and len(concepts) > 2 or lens in ("evidence", "concept", "history", "contradictions") \
            and len(concepts) > 1 and not (concept or to):
        if lens in ("path", "gaps"):
            pairs = [(a, b) for i, a in enumerate(concepts[:4]) for b in concepts[i + 1:4]][:5]
            choices = [_choice(name, lens, f"“{a}” and “{b}”", a, b, as_of) for a, b in pairs]
            raise _ask("Which two concepts do you mean?", choices, understood)
        choices = [_choice(name, lens, f"“{c}”", c, as_of=as_of) for c in concepts[:5]]
        if len(concepts) >= 2:
            choices.append(_choice(name, "path", f"how “{concepts[0]}” connects to “{concepts[1]}”", *concepts[:2], as_of))
        raise _ask(f"The question names {len(concepts)} concepts. Which one should the view be about?", choices, understood)

    if lens in ("overview",):
        c, t = None, None
    elif lens in ("path", "gaps"):
        c, t = (concepts + [None, None])[:2]
    else:
        c, t = (concepts[0] if concepts else None), None
    return {"lens": lens, "concept": c, "to": t, "as_of": as_of,
            "closed": lens in ("history", "contradictions") or "history" in intents,
            "question": q or None, "why": _why(lens, c, t, as_of),
            "alternatives": _alternatives(name, lens, [x for x in (c, t) if x] or concepts, as_of),
            "understood": understood, "description": LENSES[lens]}
