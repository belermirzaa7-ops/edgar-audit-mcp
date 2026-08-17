# Benchmark: does this server change the answer?

A tool server is easy to describe and hard to justify. This is the measurement:
the same model answering the same 50 questions twice — once with nothing, once
with only this server's ten tools — graded against a public benchmark's own
expected answers.

**Headline: 24% correct without the server, 82% with it. No answer in either
arm was graded a confident wrong figure; the difference is that the control arm
could not answer 36% of the questions at all, while the tool arm could not
answer one.**

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
  data access, not a strawman.
- **Tool arm.** Five agents, ten questions each, restricted to this server's ten
  tools. No web search, no other fetching. Budget of about eight tool calls per
  question, with "not found via these tools" an allowed and expected answer.
- **Neither answering arm ever saw the expected answers.**
- **Grading** was done by a separate agent that saw the question, the expected
  answer, and two candidate answers in randomised order, without being told
  which system produced which. Grades: correct / partial / wrong / no answer,
  plus two flags — *period mismatch* and *invented figure*.
- Run 16 Aug 2026. Every artifact is in `evaluation/benchmark/`: the questions,
  both arms' raw answers, the grading input, the grades, and the arm key.

## Results

| | correct | partial | wrong | no answer |
|---|---|---|---|---|
| **With this server** | **41 (82%)** | 8 | 0 | 1 |
| Without tools | 12 (24%) | 20 | 0 | 18 |

By question type (correct / total):

| Type | With server | Without |
|---|---|---|
| Beat or Miss | **7/7** | 0/7 |
| Qualitative Retrieval | **9/9** | 2/9 |
| Numerical Reasoning | 6/8 | 2/8 |
| Quantitative Retrieval | 6/9 | 1/9 |
| Adjustments | 3/4 | 3/4 |
| Complex Retrieval | 3/3 | 2/3 |
| Financial Modeling | 3/4 | 0/4 |
| Trends | 2/3 | 1/3 |
| Market Analysis | 2/3 | 1/3 |

Cost: **239 tool calls for 50 questions — 4.8 per question** against 10.5 hours
of estimated expert time.

The sharpest split is *Beat or Miss* (7/7 against 0/7). Those questions ask
whether a company beat the guidance it gave in an earlier quarter, which means
finding two 8-K press-release exhibits filed months apart and comparing a number
in each. Without filing access a model can only recall the direction, and it
did: the control arm said "beat" for TJX and Micron and was right about the
direction both times, with the magnitude wrong both times (20-30bps against 70,
40bps against 140).

## What the number does not say

- **n = 50.** The public slice, not the full 537-question benchmark.
- **The grader is a language model**, blind to which arm produced which answer
  but not adversarial. Every grade is published per question so the judgement
  can be checked rather than trusted.
- **The control arm's answers were condensed to their factual claims** before
  grading, while the tool arm's were graded verbatim. The grader was told to
  ignore length, but this asymmetry exists and is not measurable away.
- **Five period mismatches.** The dataset was authored in 2025 and this run
  happened in August 2026, so "the last three years" and undated share counts
  resolve to different filings now. Those five answers were correctly sourced
  from the wrong fiscal period; counting them correct would put the tool arm at
  92%. They are counted as *not* correct in the headline.
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
| With this server | 82.0% | **80.6%** |
| Without tools | 24.0% | 29.6% |
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
this run — same model, same questions, same grader, 24% against 82% — and that
comparison says nothing about how it would place on a leaderboard.

## Reproducing it

```
evaluation/benchmark/sorular.json         the 50 questions with expected answers
evaluation/benchmark/mcp_0..4.json        tool-arm answers, with tool-call counts
evaluation/benchmark/kontrol_kolu.txt     control-arm answers
evaluation/benchmark/notlama_girdi.json   what the grader saw
evaluation/benchmark/notlar.json          the grades
evaluation/benchmark/anahtar.json         which arm was which
```

Arm order was assigned deterministically: for even question ids the tool arm was
shown first, for odd ids second.

## Per-question grades

| id | type | with server | without | tool calls |
|---|---|---|---|---|
| 0 | Market Analysis | correct | correct | 6 |
| 1 | Trends | correct | partial | 5 |
| 2 | Beat or Miss | correct | partial | 7 |
| 3 | Complex Retrieval | correct | correct | 5 |
| 4 | Qualitative Retrieval | correct | no answer | 7 |
| 5 | Complex Retrieval | correct | correct | 10 |
| 6 | Qualitative Retrieval | correct | correct | 3 |
| 7 | Quantitative Retrieval | correct | correct | 3 |
| 8 | Beat or Miss | correct | partial | 5 |
| 9 | Numerical Reasoning | partial (period) | partial | 1 |
| 10 | Quantitative Retrieval | partial (period) | no answer | 2 |
| 11 | Financial Modeling | partial (period) | no answer | 9 |
| 12 | Numerical Reasoning | correct | no answer | 3 |
| 13 | Trends | partial (period) | partial | 6 |
| 14 | Numerical Reasoning | correct | partial | 6 |
| 15 | Complex Retrieval | correct | partial | 4 |
| 16 | Trends | correct | correct | 5 |
| 17 | Qualitative Retrieval | correct | partial | 4 |
| 18 | Numerical Reasoning | partial (period) | no answer | 2 |
| 19 | Numerical Reasoning | correct | no answer | 5 |
| 20 | Qualitative Retrieval | correct | partial | 4 |
| 21 | Numerical Reasoning | correct | correct | 4 |
| 22 | Qualitative Retrieval | correct | no answer | 3 |
| 23 | Numerical Reasoning | correct | partial | 4 |
| 24 | Qualitative Retrieval | correct | partial | 5 |
| 25 | Numerical Reasoning | correct | correct | 3 |
| 26 | Qualitative Retrieval | correct | no answer | 4 |
| 27 | Quantitative Retrieval | correct | no answer | 2 |
| 28 | Qualitative Retrieval | correct | no answer | 4 |
| 29 | Financial Modeling | correct | no answer | 9 |
| 30 | Financial Modeling | correct | no answer | 4 |
| 31 | Quantitative Retrieval | correct | no answer | 3 |
| 32 | Adjustments | partial | partial | 4 |
| 33 | Quantitative Retrieval | no answer | partial | 10 |
| 34 | Adjustments | correct | correct | 4 |
| 35 | Quantitative Retrieval | partial | partial | 7 |
| 36 | Quantitative Retrieval | correct | no answer | 4 |
| 37 | Beat or Miss | correct | partial | 5 |
| 38 | Qualitative Retrieval | correct | correct | 4 |
| 39 | Adjustments | correct | correct | 2 |
| 40 | Quantitative Retrieval | correct | partial | 3 |
| 41 | Market Analysis | partial | partial | 4 |
| 42 | Financial Modeling | correct | partial | 5 |
| 43 | Quantitative Retrieval | correct | no answer | 2 |
| 44 | Adjustments | correct | correct | 1 |
| 45 | Market Analysis | correct | partial | 4 |
| 46 | Beat or Miss | correct | no answer | 7 |
| 47 | Beat or Miss | correct | partial | 6 |
| 48 | Beat or Miss | correct | no answer | 8 |
| 49 | Beat or Miss | correct | no answer | 12 |

Dataset: Vals AI Finance Agent Benchmark, CC-BY-4.0.
