# TIG Tuned: what we changed, why, and how it was measured

This branch (`tig-tuned`) is the research agent of `main` with six changes. Each change came from reading the cases the
agent got wrong in a benchmark, and each was measured before the next one was made. The agent's design is kept: the model
plans and writes, code decides what counts as evidence, and an answer still needs evidence for every requirement.

| Overall score | Mail round | Documents round |
|---|---|---|
| `main` (unedited) | 66% | 70% |
| After fixes 1 to 3 | 70% | 89% |
| After fixes 1 to 6 (this branch) | **96%** | **95%** |

Read the caveat at the end before quoting these numbers: the fixes were found on the same questions they were measured on.

---

## 1. How the agent was measured

**Two rounds, one corpus each.** The mail round searches a synthetic desk mailbox: 131 emails and the 20 attachments that
came with them (PDF term sheets and pitch decks). The documents round searches 101 standalone synthetic documents
(research notes, house views, term sheets and factsheets, about 30 of them in an older and a newer version). Each round
has 15 questions with known right answers, written by someone who read only the documents:

- lookups (find a named document, who sent it, when),
- figures (a coupon, a barrier level, a strike, stated in one document),
- thematic questions (a view across several documents),
- three controls about things the corpus does not hold, where the right answer is a refusal.

**One model, one adapter.** Every call went to Claude Sonnet 5 through the agent's own model seam
(`ResearchAgent(cfg, model=...)`), with the agent's response schemas passed through. Nothing else in the agent was
replaced. Mail arrives as `.eml`, which the agent does not read, so each mail was written as a `.txt` file (subject,
sender, date, cleaned body) before the catalog was built. The market database used was the one in `data/market_data/`.

**What was scored.** The same scorer was used for every run, and every flagged case was read by hand before a number was
kept.

| Row | Measure |
|---|---|
| Relevancy | the right document is the top result (of 12 questions with a right document) |
| Accuracy | the figure asked for is stated correctly |
| Recency | the current version is used where an older one is also held (documents round) |
| Hallucination | a control question answered by invention instead of refused |
| Grounding | share of the answer's figures found in what was retrieved |
| Routing | the question reached a document search |
| Latency, cost | median seconds per question; model calls and US$ for 15 questions |
| Overall | mean of the quality rows (relevancy, accuracy, recency where tested, hallucination as refusals kept, grounding, routing) |

---

## 2. What went wrong on `main`, by building block

| Block | What happened |
|---|---|
| Metadata builder and catalog | The catalog matched question words literally. Its alias list holds bank names only, and the `terminology` table in its schema was never filled, so "one-year" never met "12M", "USD/SGD" never met "USDSGD", "double-no-touch" never met "DNT". Extractive summaries often picked a mail's disclaimer. Decks carried no date. Three decks failed to index ("unrecognized shape type"). |
| Search scoring | A document's score added up the frequency of every matched term with no regard to length. One long deck that mentions many products was listed first for 6 of the 15 mail questions; the short mail holding the answer lost to it. |
| Mail and attachments | A mail and its attachments were unrelated files in the catalog. Several answers sit in an attached term sheet or deck, so finding the mail did not lead to them. |
| `inspect_document` | It returns a document from the start until `max_chars`. A figure on slide 6 of a long deck was never read, even with the right deck open. |
| Research loop | The tool-choice step had no response schema; a reply that was not a valid tool call was rejected without saying why, and the turn ended after two. Separately, a plan whose audit found an uncovered goal was blocked before any tool ran. Together these stopped 1 to 3 questions a round with no search at all. |

Working as designed, and left alone: the evidence gate (no answer ever invented on a control question), the SQL binding
path, and the final validation.

---

## 3. The six fixes

### Fix 1: vocabulary in the catalog and in the search

- **Problem.** Literal matching (see above).
- **Change.** `data/terminology.json` holds 631 terms: markets (every listed FX pair as written in several ways, such as
  "USD/SGD", "usd-sgd", "dollar-yen"), products ("double no touch" / "DNT", "dual range accrual" / "DRAN"), and tenors
  ("one-year" / "12M"). The builder writes them into the catalog's own `terminology` table and tags each document with
  every group it mentions. `search_documents` expands a query to every spelling of each group it names, so either
  spelling in a document matches.
- **Files.** `metadata/terminology.py` (new), `metadata/builders/enrichment.py`, `agent_api/metadata_retrieval.py`,
  `data/terminology.json` (new).

### Fix 2: a cleaner catalog

- **Problem.** Summaries that were disclaimers, decks with no date, decks that failed to index.
- **Change.** Summary sentences skip boilerplate (disclaimers, "not investment advice", "for professional investors" and
  similar). A mail's subject leads its summary. Decks and Word files carry their created date. A shape `python-pptx`
  cannot type no longer fails the whole deck (all 101 documents now index; 98 did before).
- **File.** `metadata/builders/enrichment.py`.

### Fix 3: the research loop recovers instead of stopping

- **Problem.** Early stops before any search.
- **Change.**
  1. The tool-choice step gets a schema: `action` is `tool` (with `tool` limited to the catalog's tool names and `args`
     an object) or `clarify`. A final answer stays disallowed while requirements are missing. With Ollama the schema is
     enforced by structured output; with a hosted model it is stated in the prompt.
  2. A rejected reply is explained back to the model (what was expected, what it sent) and a third try is allowed.
  3. In a plan that already searches documents, a goal the audit finds uncovered becomes a mandatory `search_documents`
     requirement instead of a block. A SQL plan whose repair fails still blocks, as `main`'s own test requires. The
     evidence gate is unchanged.
- **Files.** `agent_api/core.py`, `agent_api/output_contracts.py`.

### Fix 4: read where the question is answered

- **Problem.** `inspect_document` read from the start.
- **Change.** When a document is longer than `max_chars`, the pages, slides or blocks that best match a focus are
  returned, in document order, each with its own locator, so citations stay exact. The focus defaults to the question;
  the model may pass one (`focus`). A short document is read whole as before.
- **File.** `agent_api/core.py`.

### Fix 5: length-adjusted ranking

- **Problem.** Long documents won by mentioning more words.
- **Change.** The body-term part of the score is BM25: a matched word counts by how rare it is across the catalog,
  repeats saturate, and the score is tempered by the document's length against the average. Entity tags count by rarity,
  so a tag most documents carry ("USD", "FX") says little. Matches in the file name and summary keep their weight.
- **File.** `agent_api/metadata_retrieval.py`.

### Fix 6: a mail is linked to its attachments

- **Problem.** A mail and its attachments were unrelated in the catalog.
- **Change.** The builder links each file to the attachment files it lists (an `.msg` file's attachments, or an
  "Attachments:" line in a text mail) as `concept_relationships` rows (`has_attachment`). The two share their subject and
  tags, a search gives a mail its best attachment's score and the other way round, and each result lists its linked
  files so the agent can open the attachment.
- **Files.** `metadata/builders/enrichment.py`, `agent_api/metadata_retrieval.py`.

---

## 4. How each fix was checked

**A free check before any model call.** Each benchmark question's text was sent to `search_documents` on the catalog,
and the rank of the right document was recorded. This is a guide, not the score: in a real run the model writes its own
search queries.

| Right document ranked first (of 12) | `main` | Fixes 1, 2 | Fixes 1, 2, 5, 6 |
|---|---|---|---|
| Mail round | 6 | 7 | 9 |
| Documents round | 5 | 10 | 10 |

| Right document in the top 3 (of 12) | `main` | Fixes 1, 2 | Fixes 1, 2, 5, 6 |
|---|---|---|---|
| Mail round | 7 | 8 | 11 |
| Documents round | 7 | 10 | 10 |

Fix 4 was checked directly on the long deck that `main` read from the start: read from the start, the reader returned
slides 1 to 5 and missed the figure on slide 6; focused, it returned slides 3, 4 and 6.

**Then full runs with the model**, both rounds, the same questions and scorer.

---

## 5. Results by stage

### Mail round

| | `main` | Fixes 1 to 3 | Fixes 1 to 6 |
|---|---|---|---|
| Right document ranked first | 6/12 | 7/12 | **11/12** |
| Correct figure | 0/3 | 0/3 | **3/3** |
| Control answered by invention | 0/3 | 0/3 | 0/3 |
| Grounding | 100% | 100% | 89% |
| Reached a search | 12/15 | 14/15 | **15/15** |
| Median seconds | 37 | 44 | 37 |
| Model calls / US$ (15 questions) | 90 / 1.50 | 119 / 2.13 | 104 / 1.81 |
| **Overall** | 66% | 70% | **96%** |

### Documents round

| | `main` | Fixes 1 to 3 | Fixes 1 to 6 |
|---|---|---|---|
| Right document ranked first | 5/12 | 8/12 | **11/12** |
| Correct figure | 2/4 | **4/4** | **4/4** |
| Current version used | 2/3 | **3/3** | **3/3** |
| Control answered by invention | 0/3 | 0/3 | 0/3 |
| Grounding | 81% | 86% | 80% |
| Reached a search | 12/15 | 12/15 | **15/15** |
| Median seconds | 44 | 40 | 47 |
| Model calls / US$ (15 questions) | 90 / 1.53 | 91 / 1.46 | 114 / 1.95 |
| **Overall** | 70% | 89% | **95%** |

What the last stage changed, case by case: a coupon in an attached term sheet is now read through the mail's attachment
link (fix 6); a figure on slide 6 of a long deck is now read (fix 4); a short launch mail now outranks a long deck that
only mentions the same market (fix 5). The thematic questions that stopped early on `main` now answer. Two questions
slipped: one lookup fell from first to eighth, and one thematic question from first to sixth.

---

## 6. Caveat: this is a development score

The fixes were found by reading the agent's misses on these 30 questions, and then measured on the same 30. The numbers
show the fixes work on the cases they were built for; they do not yet show how the branch does on questions it has not
seen. The fair check is a fresh set of questions on the same corpus, run on `main` and this branch alike. Until then,
quote the gain over `main` with this caveat.

The model's replies also vary from run to run (the hosted model takes no temperature setting), so a single run can move a
question either way. One lookup failed once on `main` and answered correctly on the next run.

---

## 7. Open points

- Cost and time rose with the recoveries: about US$1.81 and US$1.95 for 15 questions against US$1.50 on `main`.
- Grounding dipped (89% mail, 80% documents): longer answers state more figures, and a few are not in what was retrieved.
  Worth reading case by case.
- Rejected tool choices still happen (one to three on some questions); fix 3 recovers from them rather than preventing
  them.
- `data/terminology.json` must grow with the corpus. A new market, product or way of writing a tenor needs a row; the
  builder reads the file at build time.
- The 8 failing tests in `test_core_regression.py` fail on `main` as well (each returns `PARTIAL_EVIDENCE` where
  `COMPLETED` is expected). None was changed or added to here.

---

## 8. Build, run and test

The build and the service are unchanged in use. Rebuild the catalog after pulling this branch, so the vocabulary,
summaries, dates and attachment links are written:

```bash
python -m scripts.build_metadata          # writes data/metadata.db, now with terminology and attachment links
python -m uvicorn agent_api.server:app --host 127.0.0.1 --port 8000
```

`.msg` mail links to its attachments with no extra step (the builder reads the `.msg` attachment list). A mail stored as
text can list its attachments on an `Attachments: name1; name2` line after its `Date:` line.

Tests added on this branch, all offline with a scripted model:

```bash
python -m unittest test_tuned_fix3 test_tuned_fix4 test_tuned_fix56
```

`test_metadata_end_to_end`, `test_binding_repair`, `test_sqlite_binding_adapter` and `test_binding_integration` pass as
on `main`; `test_core_regression` has the same 8 failures as on `main`.

## 9. Files changed

| File | Fixes |
|---|---|
| `metadata/terminology.py` (new) | 1 |
| `data/terminology.json` (new) | 1 |
| `metadata/builders/enrichment.py` | 1, 2, 6 |
| `agent_api/metadata_retrieval.py` | 1, 5, 6 |
| `agent_api/output_contracts.py` | 3 |
| `agent_api/core.py` | 3, 4 |
| `test_tuned_fix3.py`, `test_tuned_fix4.py`, `test_tuned_fix56.py` (new) | 3, 4, 5 and 6 |
