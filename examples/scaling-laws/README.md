# Example: LLM scaling laws and emergent abilities, from arXiv abstracts (real)

Eight arXiv abstracts from 2020 to 2024 on how language models scale: Kaplan et al. 2020 (scaling
laws), Ganguli et al. 2022 (predictability and surprise), Hoffmann et al. 2022 (Chinchilla), Wei et
al. 2022 (emergent abilities), Schaeffer et al. 2023 (emergence as a mirage), Muennighoff et al. 2023
(data-constrained scaling), Sardana et al. 2023 (beyond Chinchilla-optimal) and Besiroglu et al. 2024
(a Chinchilla replication). Only the title, authors and abstract of each paper are here, copied word
for word from the arXiv API. arXiv releases this metadata under CC0 (see `LICENSE-sources`).
`sources.json` records each paper's arXiv id, the version the abstract came from, its permalink and
the date the first version was submitted.

## Why it is a useful example for researchers

It is a small literature map: claims, counter-claims and a replication, each tied to the sentence
that makes it. Two arguments run through it:

- **Emergence.** Wei et al. say some abilities appear only in larger models and cannot be predicted
  from smaller ones. Schaeffer et al. say the jump comes from the choice of metric: nonlinear metrics
  make it, linear ones make it smooth.
- **Compute-optimal training.** Kaplan et al. advise very large models on modest data. Hoffmann et al.
  find models undertrained and advise scaling size and tokens equally. Sardana et al. add inference
  cost and advise smaller models trained longer. Muennighoff et al. ask what to do when data runs out.
  Besiroglu et al. dispute one of the three Chinchilla fits.

A link drawn here is only as strong as the abstract. Where two abstracts disagree without naming
each other (Hoffmann does not cite Kaplan by name in its abstract), the relation says so and has a
lower confidence.

## How the graph was made

With the tool's own agent route. There is no model inside the tool and no API key.

1. `knowledge ingest --method agent` read each abstract, dated by its first arXiv version, into 10
   chunks.
2. One agent (`scaling-laws-reader`) read the chunks and wrote 97 typed relations in
   `relations.json`: claims, the evidence each abstract gives, and where the papers support,
   challenge or contradict each other. Every relation carries the chunk it came from and an exact
   quote, and every quote was checked against its chunk.
3. `timeline.json` holds 8 dated entries, replayed with `relate --supersedes`. The time slider then
   shows the compute-optimal advice changing in 2020, 2022 and 2023, and the Chinchilla parametric
   fit being disputed in 2024. The two explanations of emergence are both kept open: one does not
   close the other.

Extraction is a model's reading of the text. Check any relation with `knowledge evidence EDGE_ID`,
which shows the quote and the passage. The abstracts are not the papers: read the paper before you
cite a claim from this map.

## Questions to try

- What contradicts the claim that emergent abilities appear suddenly and unpredictably?
- What evidence says emergent abilities come from the choice of metric?
- How has the compute-optimal allocation advice changed over time?
- Who disputes the Chinchilla parametric loss fit, and on what grounds?
- How does inference cost connect to the chinchilla scaling laws?
- What about scaling? (too vague: the tool asks back)

## Commands

```sh
export G=.work/scaling-laws/scratch.db
# ingest each source (title, uri and date as in sources.json), for example:
knowledge ingest examples/scaling-laws/sources/kaplan-2020-scaling-laws.md --method agent \
  --at 2020-01-23 --title "Scaling Laws for Neural Language Models" \
  --uri https://arxiv.org/abs/2001.08361v1 --agent librarian --graph $G
knowledge add examples/scaling-laws/relations.json --graph $G
# replay timeline.json in order with: knowledge relate FROM RELATION TO --at AT [--supersedes EDGE] --graph $G
knowledge visualize --for "What contradicts the claim that emergent abilities appear suddenly and unpredictably?" --graph $G --open
```

Note: the Hoffmann et al. abstract reads "4$\times$ more more data". That is how arXiv has it; it is
kept as is.
