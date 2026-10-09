# Example: Python type annotations, from the PEPs (real)

Ten excerpts from the Python Enhancement Proposals on type annotations: PEP 484 (type hints),
PEP 526 (variable annotations), PEP 585 (generics in standard collections), PEP 604 (`X | Y`
unions), PEP 649 (deferred evaluation of annotations) and PEP 749 (implementing PEP 649), plus
PEP 563 (postponed evaluation) four times: as accepted in 2017, as revised in 2020 and 2021, and
as it reads now. The text comes from [python/peps](https://github.com/python/peps), pinned to
exact commits. The PEPs are in the public domain or under CC0-1.0-Universal (see `LICENSE-sources`).

## Why it is a useful example for developers

Most Python developers have written `from __future__ import annotations` and many were told
annotations would become strings by default. The PEPs tell a different story, one revision at a
time. PEP 563 planned string annotations by default in Python 4.0, then in 3.10, then said it was
unclear pending PEP 649. Its Resolution now says the plan never became the default and was
replaced by deferred evaluation (PEP 649 and PEP 749). PEP 749 says the future import keeps
working in 3.14, is deprecated no sooner than the first release after 3.13's end-of-life, and is
removed after at least two more releases. The graph keeps every step, so you can see what held
when, and the passage that says so.

## How the graph was made

With the tool's own agent route: no model inside the tool, no API key.

1. `knowledge ingest --method agent` read each excerpt, dated as in `sources.json`, into 34 chunks.
2. An agent (`python-typing-reader`) read the chunks and wrote 149 typed relations into
   `relations.json`. Every relation names its chunk and carries an exact quote from it.
3. `timeline.json` holds 13 dated steps (the planned default, the future import, PEP 563's status,
   PEP 649's target version, the `SOURCE` format renamed `STRING`). It is replayed with
   `relate --supersedes`, so each step closes the one it replaced and the time slider shows it.

Dates: PEPs 484, 526, 585 and 604 use the Created date in the header; PEPs 649 and 749 use the
Resolution date in the header; the four PEP 563 files use the date of the commit that produced
that text. Extraction is a model's reading of the text: check any relation with
`knowledge evidence EDGE_ID`, which shows the quote and the passage.

## Questions to try

- What replaced PEP 563's plan to make stringized annotations the default? (history)
- When will from __future__ import annotations be removed? (history)
- How does from __future__ import annotations relate to deferred evaluation of annotations? (path)
- What is the evidence that stringized annotations caused problems? (evidence)
- Which PEPs conflict with PEP 563? (contradictions)
- What about annotations? (too vague: the tool asks which one you mean)

Add a date to see the past: "What was the plan for stringized annotations as of 2020-06-01?"
shows the plan to make it the default in Python 3.10.

## Commands

```
export KNOWLEDGE_HOME=$PWD/.work/home
for f in examples/python-typing/sources/*.md; do   # use each file's date from sources.json
  knowledge ingest "$f" --method agent --at DATE --graph python-typing
done
knowledge add examples/python-typing/relations.json --graph python-typing
# then replay timeline.json in order:
#   knowledge relate FROM RELATION TO --at AT --evidence ... --supersedes <edge id of the step it replaces>
knowledge visualize --for "What replaced PEP 563's plan to make stringized annotations the default?" --graph python-typing --open
```
