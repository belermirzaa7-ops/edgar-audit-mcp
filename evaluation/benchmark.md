# Benchmark: does this server change the answer?

A tool server is easy to describe and hard to justify. This is the measurement:
the same model answering the same 50 questions twice — once with nothing, once
with only this server's tools — graded against a public benchmark's own expected
answers.

**Headline: 26% correct without the server, 90% with it.** Class-balanced, the
metric the benchmark's own paper reports: **32.6% against 91.9%**. The tool arm
stated no confident wrong figure; the control arm could not answer 34% of the
questions at all, and the tool arm could not answer one.

## Two runs, and why there are two

The first run (16 Aug 2026) scored **82%**. Five of its answers were graded
not-correct for one reason: the dataset was published on 16 May 2025 and the run
happened fifteen months later, so "the last three years" and "the most recent
annual report" had moved on. Those answers were correctly sourced from the wrong
year.

That was not a grading problem. It was an assumption inside the tools: every
"most recent" silently meant *most recent today*. The fix was a point-in-time
cutoff (`as_of`) on every tool that selects by recency, cutting on the **filing
date** rather than the period — a restated figure carries the same period end as
the original, so a filter on the period lets every restatement through while
appearing to work.

The second run (17 Aug 2026) is the same 50 questions with the cutoff set to
**2025-05-16**, the date the dataset was published (Zenodo record 15428639). It
scores **90%**.

**All fifty questions were re-run, not just the five that failed.** Re-running
only the failures would have been selective measurement: a cutoff can break an
answer that was previously right, and that has to be visible. It did. Six
answers changed grade — five upward (ids 9, 13, 18, 32, 41) and **one downward**
(id 49, correct in the first run, a period mismatch in the second). The net is
+4, not +5, and the movement in both directions is in the published grades.

Both runs' raw data is published. The first is the honest starting point; the
second is what the tools do now.

## The dataset

[Vals AI Finance Agent Benchmark](https://huggingface.co/datasets/vals-ai/finance_agent_benchmark),
CC-BY-4.0 — the public 50-question slice of a 537-question expert-authored set
built around recent SEC filings. Question types: Beat or Miss, Quantitative and
Qualitative Retrieval, Numerical Reasoning, Adjustments, Trends, Complex
Retrieval, Financial Modeling, Market Analysis. The dataset carries an expert
time estimate per question; the 50 together are **631 minutes — 10.5 hours** of
analyst work.

It was chosen because it is public, agentic (written for a model with tools
rather than for a retrieval index), and not authored by anyone with an interest
in this repository.

## Method

- **Control arm.** One agent, no tools of any kind, answering from prior
  knowledge. Instructed not to invent precise-looking figures and to say so when
  it did not know — so the control is the *strong* version of a model without
  data access, not a strawman. **The control was not re-run for the second run:
  the same answers were re-graded.** It has no tools, so a cutoff cannot change
  what it can reach.
- **Tool arm.** Five agents, ten questions each, restricted to this server's
  tools. No web search, no other fetching. Budget of about eight tool calls per
  question, with "not found via these tools" an allowed and expected answer. In
  the second run every call carried `as_of="2025-05-16"`.
- **Neither answering arm ever saw the expected answers.**
- **Grading** was done by a separate agent that saw the question, the expected
  answer, and two candidate answers in randomised order, without being told
  which system produced which. Grades: correct / partial / wrong / no answer,
  plus two flags — *period mismatch* and *invented figure*. Arm order was
  assigned by the same deterministic rule in both runs, so the two are
  comparable.
- Runs on 16 and 17 Aug 2026. Every artifact is in `evaluation/benchmark/`.

## Was the cutoff actually respected?

Asserting a cutoff is not the same as keeping it. Every accession number the
tool arm reported reading was checked against SEC:

| | |
|---|---|
| distinct filings cited | 64 |
| filed in 2025, so needing a date check | 37 |
| filed before 2025, unambiguous | 27 |
| **filed after the 2025-05-16 cutoff** | **0** |
| dates that could not be established | 0 |

The latest filing used anywhere in the run was dated **2025-05-09**, a week
inside the cutoff. Raw audit: `evaluation/benchmark/kesimli_denetim.json`.

This checks compliance, not capability: one tool
(`sec_edgar_compare_companies`) cannot honour a cutoff at all, because SEC's
frame endpoint reports no filing date per row. Under a session-wide cutoff it
refuses the call; in this run the agents were told to avoid it, and the audit
shows nothing slipped through.

## Results

Second run, point-in-time to 2025-05-16:

| | correct | partial | wrong | no answer |
|---|---|---|---|---|
| **With this server** | **45 (90%)** | 4 | 0 | 1 |
| Without tools | 13 (26%) | 17 | 3 | 17 |

By question type (correct / total):

| Type | With server | Without |
|---|---|---|
| Numerical Reasoning | **8/8** | 2/8 |
| Qualitative Retrieval | **9/9** | 2/9 |
| Beat or Miss | 6/7 | 0/7 |
| Quantitative Retrieval | 6/9 | 1/9 |
| Adjustments | **4/4** | 4/4 |
| Complex Retrieval | 3/3 | 2/3 |
| Trends | 3/3 | 1/3 |
| Market Analysis | 3/3 | 1/3 |
| Financial Modeling | 3/4 | 1/4 |

Class-balanced — each type weighted equally, which is what the benchmark's own
paper reports — **91.9% against 32.6%**.

Cost: **202 tool calls for 50 questions — 4.0 per question** against 10.5 hours
of estimated expert time. The first run took 4.8 per question; the cutoff made
the search narrower, not wider.

The sharpest split is *Beat or Miss* (6/7 against 0/7). Those questions ask
whether a company beat the guidance it gave in an earlier quarter, which means
finding two 8-K press-release exhibits filed months apart and comparing a number
in each. Without filing access a model can only recall the direction, and it
did: the control arm said "beat" for TJX and Micron and was right about the
direction both times, with the magnitude wrong both times (20-30bps against 70,
40bps against 140).

For reference, the first run (no cutoff) was 41 correct (82%), 8 partial, 0
wrong, 1 no answer — 80.6% class-balanced.

## How much of this is the grader?

The second run re-graded the **identical** control-arm answers with a fresh
grader. That was not designed as an experiment, but it is one, and it is the
only direct measurement here of how much the grader itself moves the number:

| | agreement on the same 50 answers |
|---|---|
| exact grade (correct / partial / wrong / no answer) | 43/50 — **86%** |
| binary, correct or not | 47/50 — **94%** |
| effect on the headline | 12 correct → 13 correct |

So the control arm's 24% and 26% are the same measurement graded twice, not a
change in the control. Read every figure here as carrying roughly **±2
percentage points** of grader noise before any other source of error. That is
small next to a 64-point gap, and it is not small next to the 8-point difference
between the two tool-arm runs — which is why the period mismatches were fixed in
the tools and re-measured, rather than argued about in the grading.

## What the number does not say

- **n = 50.** The public slice, not the full 537-question benchmark.
- **The grader is a language model**, blind to which arm produced which answer
  but not adversarial. Every grade is published per question so the judgement
  can be checked rather than trusted. Two graders on the same 50 control answers
  agreed 86% of the time (see above), so treat every figure as ±2 points before
  anything else.
- **The control arm's answers were condensed to their factual claims** before
  grading, while the tool arm's were graded verbatim. The grader was told to
  ignore length, but this asymmetry exists and is not measurable away.
- **Three period mismatches survive** (ids 10, 11, 49), down from five. The
  cutoff removed the ones caused by the run happening later than the dataset was
  written; these three are not that. They are counted as *not* correct in the
  headline. The projection before the second run was 92% and the measurement
  came in at 90% — the projection assumed all five would clear and that one
  answer would not move the other way. Both assumptions were wrong, which is
  what re-running all fifty was for.
- **Two expected answers look internally questionable** — id 0 describes a
  rejected $7.3bn offer where the filings show a $55.00/share agreement, and
  id 9 applies a three-year exponent to a two-year span. Both were graded
  against what the question asks, and both are noted in the grades file.
- **The control arm was told to admit ignorance.** That is why it has zero
  confident wrong answers and eighteen refusals. A model told to always produce
  an answer would trade those refusals for wrong figures — which is the failure
  this server exists to prevent, but it is not what was measured here.
- **The published baseline for this benchmark is not a like-for-like
  comparison** — see the section below, which sets out what it does and does
  not establish.

## The benchmark's own published baseline

The authors published results for 23 models on this benchmark ([arXiv
2508.00828](https://arxiv.org/abs/2508.00828)). The best of them, **o3, scored
46.8% ± 2.2**, and **no model reached 50%**. Those agents were not working
blind: the paper lists their toolset as `GoogleSearch`, `EdgarSearch` ("a tool
to access the EDGAR database, containing public SEC filings"), `ParseHTML` and
`RetrieveInformation`. So the published baseline is a model with both web search
*and* SEC filing access.

Their metric is **class-balanced accuracy** — each task category counts equally,
rather than each question. Computed the same way from the per-question grades
published here:

| | raw accuracy | class-balanced |
|---|---|---|
| With this server, point-in-time | 90.0% | **91.9%** |
| With this server, first run | 82.0% | 80.6% |
| Without tools | 26.0% | 32.6% |
| Published best (o3, full set) | — | 46.8% ± 2.2 |

**Four reasons this is not a like-for-like comparison**, all of them real:

1. **Different questions.** Their figure covers all 537; this run covers the 50
   public ones. The public split is a sample of the same set, not the set.
2. **Different grader.** They use rubric-based grading with a dedicated
   contradiction rubric. This run used a single blind judge with four grades.
   Two graders on the same answers do not have to agree.
3. **Different tools.** Their agents had general web search; this run had ten
   SEC tools and nothing else. That cuts both ways — web search reaches
   material this server cannot, and this server reaches filing structure a
   search box does not.
4. **Different model generation.** Their evaluation ran on 2025 models (o3,
   Claude 3.7 Sonnet). This run used a 2026 model, so part of any gap is the
   model improving, not the server.

**What it does establish:** the published state of the art on this benchmark,
with EDGAR and web access, sat below 50%, and the difficulty of the questions is
therefore not in doubt. **What it does not establish:** that this server beats
o3. The comparison that isolates what this server contributes is the one inside
this run — same model, same questions, same grader, 26% against 90% — and that
comparison says nothing about how it would place on a leaderboard.

## Reproducing it

```
evaluation/benchmark/sorular.json                 the 50 questions with expected answers
evaluation/benchmark/kontrol_kolu.txt             control-arm answers (both runs)
evaluation/benchmark/anahtar.json                 which arm was which (both runs)

  first run, 16 Aug 2026, no cutoff
evaluation/benchmark/mcp_0..4.json                tool-arm answers, with tool-call counts
evaluation/benchmark/notlama_girdi.json           what the grader saw
evaluation/benchmark/notlar.json                  the grades

  second run, 17 Aug 2026, point-in-time to 2025-05-16
evaluation/benchmark/kesimli_mcp_0..4.json        tool-arm answers, with accession numbers
evaluation/benchmark/kesimli_notlama_girdi.json   what the grader saw
evaluation/benchmark/kesimli_notlar.json          the grades
evaluation/benchmark/kesimli_denetim.json         the cutoff-compliance audit
```

Arm order was assigned deterministically: for even question ids the tool arm was
shown first, for odd ids second.

## Per-question grades

Second run (point-in-time). The first run's grades are in `notlar.json`.

| id | type | with server | without | tool calls |
|---|---|---|---|---|
| 0 | Market Analysis | correct | correct | 6 |
| 1 | Trends | correct | partial | 4 |
| 2 | Beat or Miss | correct | wrong | 7 |
| 3 | Complex Retrieval | correct | correct | 6 |
| 4 | Qualitative Retrieval | correct | no answer | 5 |
| 5 | Complex Retrieval | correct | correct | 7 |
| 6 | Qualitative Retrieval | correct | correct | 1 |
| 7 | Quantitative Retrieval | correct | correct | 6 |
| 8 | Beat or Miss | correct | wrong | 3 |
| 9 | Numerical Reasoning | correct | correct | 2 |
| 10 | Quantitative Retrieval | partial (period) | no answer | 1 |
| 11 | Financial Modeling | partial (period) | no answer | 9 |
| 12 | Numerical Reasoning | correct | no answer | 3 |
| 13 | Trends | correct | partial | 3 |
| 14 | Numerical Reasoning | correct | partial | 6 |
| 15 | Complex Retrieval | correct | partial | 4 |
| 16 | Trends | correct | correct | 4 |
| 17 | Qualitative Retrieval | correct | partial | 2 |
| 18 | Numerical Reasoning | correct | no answer | 1 |
| 19 | Numerical Reasoning | correct | no answer | 2 |
| 20 | Qualitative Retrieval | correct | partial | 5 |
| 21 | Numerical Reasoning | correct | correct | 3 |
| 22 | Qualitative Retrieval | correct | no answer | 2 |
| 23 | Numerical Reasoning | correct | wrong | 1 |
| 24 | Qualitative Retrieval | correct | partial | 3 |
| 25 | Numerical Reasoning | correct | correct | 1 |
| 26 | Qualitative Retrieval | correct | no answer | 2 |
| 27 | Quantitative Retrieval | correct | no answer | 2 |
| 28 | Qualitative Retrieval | correct | partial | 4 |
| 29 | Financial Modeling | correct | no answer | 4 |
| 30 | Financial Modeling | correct | no answer | 4 |
| 31 | Quantitative Retrieval | correct | no answer | 2 |
| 32 | Adjustments | correct | partial | 4 |
| 33 | Quantitative Retrieval | no answer | partial | 6 |
| 34 | Adjustments | correct | correct | 2 |
| 35 | Quantitative Retrieval | partial | partial | 5 |
| 36 | Quantitative Retrieval | correct | no answer | 3 |
| 37 | Beat or Miss | correct | partial | 6 |
| 38 | Qualitative Retrieval | correct | partial | 5 |
| 39 | Adjustments | correct | correct | 2 |
| 40 | Quantitative Retrieval | correct | partial | 3 |
| 41 | Market Analysis | correct | partial | 11 |
| 42 | Financial Modeling | correct | correct | 2 |
| 43 | Quantitative Retrieval | correct | no answer | 2 |
| 44 | Adjustments | correct | correct | 1 |
| 45 | Market Analysis | correct | partial | 3 |
| 46 | Beat or Miss | correct | no answer | 6 |
| 47 | Beat or Miss | correct | partial | 9 |
| 48 | Beat or Miss | correct | no answer | 10 |
| 49 | Beat or Miss | partial (period) | no answer | 7 |
