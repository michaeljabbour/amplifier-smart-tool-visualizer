# Example: federal rules on agency use of AI, 2023-2025 (real)

Seven US federal government documents on how executive agencies use AI, excerpted from the
primary sources:

| Date | Document | What it does here |
|---|---|---|
| 2023-10-30 | Executive Order 14110 | Directs OMB to issue guidance on agency AI use within 150 days (Sec. 10.1). |
| 2024-03-28 | OMB Memorandum M-24-10 | That guidance: Chief AI Officers, governance boards, AI strategies, use case inventories, minimum practices for safety- and rights-impacting AI by December 1, 2024. |
| 2024-09-24 | OMB Memorandum M-24-18 | AI acquisition: contracts for rights- or safety-impacting AI to comply with M-24-10 by December 1, 2024. |
| 2025-01-20 | Executive Order 14148 | Revokes Executive Order 14110 (Sec. 2, item (ggg)). Only that part is excerpted. |
| 2025-01-23 | Executive Order 14179 | Orders a review of actions taken under Executive Order 14110, and a revision of M-24-10 and M-24-18 within 60 days. |
| 2025-04-03 | OMB Memorandum M-25-21 | Rescinds and replaces M-24-10. Minimum practices now apply to "high-impact AI"; new deadlines. |
| 2025-04-03 | OMB Memorandum M-25-22 | Rescinds and replaces M-24-18 on AI acquisition. |

The text is vendored in `sources/` so the build is reproducible. `sources.json` records each
file's title, issuer, date, permalink, checksum (for the PDFs) and which sections were kept.

## Why this is a useful example

It is written for people in policy, legal, compliance, procurement and operations roles who
need three answers: what applies now, what replaced what, and what is required by when.
This material is a clean case of rules being replaced over time. A memo you may still have on
file (M-24-10) was rescinded; several of its requirements carried over with new deadlines,
and its "safety-impacting" and "rights-impacting" categories gave way to "high-impact AI".
The graph keeps both versions, dated, so you can see what held on any day.

The headline answer: **M-25-21 (April 3, 2025) rescinds and replaces M-24-10.** Under it,
each agency retains or designates a Chief AI Officer within 60 days, CFO Act agencies
convene an AI Governance Board within 90 days (was 60) and publish an AI Strategy within
180 days (was 365), and agencies document minimum practices for high-impact AI within 365
days, or safely stop using it. M-25-22 does the same for M-24-18 on acquisition.

The descriptions are factual and neutral. They say what each document states, with the
sentence it states it in; they do not characterise any administration.

## How the graph was made

With the tool's own agent route: no model inside the tool, no API key.

1. `knowledge ingest --method agent` read each file, dated by the day it was signed or
   issued, into 43 chunks of up to 1500 characters.
2. An agent (Claude, acting as `federal-ai-policy-reader`) read every chunk and wrote 199
   typed relations into `relations.json`. Each relation names the chunk it came from and an
   exact quote from it; a script checked every quote against its chunk.
3. Relations taken from a document that was later revoked or rescinded carry a `valid_to`
   date: 2025-01-20 for Executive Order 14110, 2025-04-03 for M-24-10 and M-24-18. So the
   current view shows what applies now, and the history view shows the rest as closed.
4. `timeline.json` holds 23 dated entries (agent `historian`): which document was current,
   each document's status, and deadlines and scope that changed. Eleven of them supersede an
   earlier entry. Each cites the revoking or rescinding sentence as
   `"DOCUMENT TITLE: exact quote"`. They are replayed with `knowledge relate --supersedes`, so
   the time slider shows what held when.

Extraction is a model's reading of the text. Check any relation with
`knowledge evidence EDGE_ID`, which shows the quote and the passage, and read the source
before relying on it. This is an example of the tool, not legal advice.

## Provenance and licence

Works of the United States Government are not subject to copyright (17 U.S.C. 105). Each
document here was issued by the President or the Director of OMB as part of their official
duties. See `LICENSE-sources` for the statutes and the publishing sites' statements.

- Executive Orders: Federal Register full text from federalregister.gov; the official PDF on
  govinfo.gov is linked in `sources.json`.
- M-24-10 and M-24-18: PDFs on the archived White House site, bidenwhitehouse.archives.gov.
- M-25-21 and M-25-22: PDFs on whitehouse.gov.

What was changed, and only this: excerpts keep whole sections and mark every cut with
"[...]"; footnotes were left out; line breaks were joined; each file starts with a heading
added here. M-25-21 and M-25-22 are scanned PDFs, so obvious character-recognition errors
were corrected to the printed text (for example "0MB" to "OMB", "11." to "ii." in list
labels); M-25-21's table headings were read from the page image. Some minimum practices are
kept as headings only, with their bodies cut.

Not included: the deadlines are given as the documents state them ("within 180 days of the
issuance of this memorandum"); calendar dates were not worked out. Later documents (for
example the AI action plan ordered by Executive Order 14179, or any later OMB memoranda) are
not part of this example.

## Questions to try

From `questions.json` (the first is the headline):

| Question | View it opens |
|---|---|
| What replaced M-24-10? | history of m-24-10 |
| What did agencies have to do as of 2024-12-01? | the whole graph as it stood on 2024-12-01 |
| When is the AI strategy due now? | history of ai strategy: 365 days, then 180 days |
| How does executive order 14179 connect to M-25-21? | path |
| What is the source for the high-impact AI rules? | evidence for high-impact ai |
| What do I need to know? | none: the tool asks what you are trying to find out |

## Commands

From the repository root:

```bash
G=.work/federal-ai-policy/scratch.db
# 1. Read the sources into chunks (ids depend only on the text).
for row in $(python3 -c "import json;[print(s['file']+'@'+s['date']) for s in json.load(open('examples/federal-ai-policy/sources.json'))]"); do
  knowledge ingest "examples/federal-ai-policy/sources/${row%@*}" --method agent --at "${row#*@}" --agent librarian --graph $G
done
# 2. Load the relations.
knowledge add examples/federal-ai-policy/relations.json --graph $G
# 3. Replay timeline.json in order: for each entry,
#    knowledge relate FROM RELATION TO --at AT --description ... --evidence ... --agent historian \
#      [--supersedes EDGE_ID_OF_THE_ENTRY_NAMED_IN_supersedes] --graph $G
# 4. Ask.
knowledge visualize --for "What replaced M-24-10?" --graph $G --open
```
