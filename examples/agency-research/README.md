# Example: a small research corpus (fictional)

Four short notes about delegation to AI agents and the cost of running them, plus
`relations.json`: what an agent extracted from them, with claims, evidence and one
contradiction. Everything here is made up to show the tool; none of it is real research.

```
knowledge ingest notes --method cooccurrence --graph example     # no model: a word network
knowledge add relations.json --graph example                      # what an agent extracted
knowledge analyze --graph example
knowledge contradictions --graph example
knowledge visualize --graph example --open
```
