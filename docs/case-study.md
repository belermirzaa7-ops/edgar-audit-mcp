# Eight ways SEC data answers your question wrongly, and nobody notices

*A case study from building `sec-edgar-mcp`, a read-only MCP server over SEC
EDGAR. Every number below was measured against live filings, and every behaviour
described is pinned by a test in the repository. Where a figure shows what the
tool did **before** a fix, it says so — those are recorded, not reproducible.*

---

## The problem is not missing data. It is confident wrong data.

SEC publishes everything: financial statements as tagged XBRL, the filings
themselves as text, ownership as XML. Getting a number out is easy. Getting the
**right** number out is where the work is, because the failures in this data do
not look like failures. They come back as HTTP 200, correctly typed, plausibly
sized, and wrong.

An agent that answers "Apple's fiscal 2015 revenue was $233.7 billion" is right.
An agent that answers "$182.8 billion" is wrong — and neither answer carries a
warning label. That is the whole problem, and it is why a tool server for this
data is a correctness project rather than an integration project.

Here are eight failures that shipped in real code — mine — and what each one
now does instead.

---

## 1. The fiscal year in SEC's data is the filing's year, not the data's

SEC's `companyconcept` API returns rows with an `fy` field. It reads like the
fiscal year of the value. It is not: it is the fiscal year of the **filing the
value appeared in**. A 10-K carries three years of comparatives, and all three
rows are stamped with the filing's year.

Building a revenue series on that field shifts the entire series by up to two
years. No error, no type mismatch, no gap in the output — just every number
against the wrong year.

**Now:** periods are derived from the `start` and `end` dates only. Annual is
300–400 days, quarterly is 60–120. The `fy` field is used for one narrow
purpose — as an anchor to learn how the company names its own years.

## 2. Two companies close the same day and call it a different year

Walmart's fiscal year ended 31 January 2026 and Walmart calls it **fiscal 2026**.
Target's fiscal year ended 31 January 2026 and Target calls it **fiscal 2025**.

There is no universal rule to apply here. "Name it by the calendar year it ends
in" is the majority convention and it is wrong for Target and Gap. "Name it by
the year it starts in" is wrong for Walmart, Nike and Microsoft. A tool that
picks either rule is silently wrong for a large minority of the market — and it
is wrong exactly when a user compares two retailers, which is the reason they
asked.

**Now:** the offset between a company's own label and its period-end year is
derived per company from its own filings. When there is no anchor to derive it
from, the response says `fiscal_year_derived: false` rather than guessing.

## 3. An accounting standard change truncates ten years of history

Apple reported revenue under `SalesRevenueNet` until ASC 606, then under
`RevenueFromContractWithCustomerExcludingAssessedTax`. Ask the modern tag and
you get 2017 onward. Ask the old tag and you get 2007–2017.

Measured on the version that stopped at the first tag that answered:

```
alias 'revenue'      ->  9 periods, FY2017 - FY2025
raw SalesRevenueNet  -> 11 periods, FY2007 - FY2017
```

A tool that stops at the first tag that answers returns a clean, complete-looking
nine-year series and silently drops a decade.

**Now:** every candidate tag is fetched and merged, the most recently filed
value wins for overlapping periods, and each data point carries `source_tag` so
the join is visible rather than hidden. Where two tags mean subtly different
things, the response shows which one each number came from instead of pretending
the difference is not there.

## 4. Segment figures do not add up to the total, and that is normal

Ask for revenue by business segment and the obvious move is to sum the segments.
That is wrong often enough that XBRL US publishes a data-quality rule
(DQC_0150) specifically to catch filings where the members do not reconcile.

Three separate reasons, all seen in real filings: some filings report no
entity-wide total at all; some tag the total on a parent member so the "total"
is itself dimensional; and a figure carrying two dimensions at once — segment
**and** geography — is an intersection, not a share, so adding it to a segment
sum counts part of the business twice.

**Now:** the tool refuses to decide. Ask for one axis and the response carries
the member sum and the entity-wide total side by side, the difference between
them, and a count of what was excluded from the sum and why. Nothing is summed
silently. On Tesla's segment gross profit the two agree exactly for 2023, 2024
and 2025; when they do not agree, the discrepancy is visible instead of
averaged away.

## 5. The 8-K you want is not in the 8-K

Tesla's quarterly production and delivery numbers are not in XBRL and not in the
10-K. They are in an exhibit attached to an 8-K. The 8-K's own primary document
is a cover page.

Worse, the obvious heuristic fails. Measured on Tesla's Q2 2026 delivery filing:

| File | Size | What it is |
|---|---|---|
| `tsla-20260702.htm` | 26,572 bytes | primary document — the cover page |
| `exhibit99111111.htm` | 13,243 bytes | the press release with the numbers |
| `R1.htm` | 38,047 bytes | a rendering SEC generated, not a filed document |

"Read the largest file" gets you SEC's own rendering. "Read the primary
document" gets you a cover page. The correct answer is the *second smallest*
file in that directory.

**Now:** every text response lists the readable documents in the filing with an
`is_primary` flag, SEC's generated renderings are filtered out, and any document
can be requested by name. Tables come back as rows and cells when asked, so the
delivery table is structure rather than numbers glued together by ` | `.

## 6. HTTP 200 with an empty body is not "the company doesn't report this"

Querying Coca-Cola's `Assets` through `companyconcept` returned HTTP 200, a
correct label, and an **empty** `units.USD` — 346 bytes. The same tag through
`companyfacts` returned 144 rows.

An agent reading the first response concludes the company does not report total
assets. It was measured five ways — repeat request, cache-buster, different
User-Agent, uncompressed, second endpoint — and only the fallback endpoint had
data.

**Now:** a zero-row response falls back to the second endpoint, the response
says which endpoint answered, and if both are empty the tool **raises an error**
instead of returning an empty success. An empty success is indistinguishable
from a real "no data", and that indistinguishability is the bug.

## 7. The same filing, the same code, two different answers

The HTML-to-text extractor mapped a tag to a **set** of tags it implicitly
closes and stopped at the first match. CPython randomises string hashing per
process, so the iteration order of that set changed from run to run.

Measured: with `PYTHONHASHSEED` 0 and 2 a financial table came back in full;
with 1 and 3 the table was gone and the section had vanished from the response
entirely. Same input, same code, different process.

The server's own description says "deterministic tool calls". For one process in
four it was not true.

**Now:** ordered containers where order is behaviour, every applicable tag
closed rather than the first, and a test that runs the extractor in five
subprocesses under different hash seeds and requires the five outputs to be
identical. That class of bug is invisible from inside a single process.

## 8. A position grows a thousandfold without a share changing hands

SEC changed 13F value reporting from thousands of dollars to whole dollars for
filings made from January 2023. Berkshire Hathaway reported the identical Apple
position in two consecutive quarters:

| Filed | Shares | Value as filed | Implied price per share |
|---|---|---|---|
| 14 Nov 2022 | 669,429,166 | 92,515,111 | $0.14 |
| 14 Feb 2023 | 669,429,166 | 86,841,985,318 | $129.72 |

Apple closed 2022-12-30 at about $129.93, so the second filing is the one in
whole dollars. An agent comparing the two quarters, in good faith, reports that
Berkshire's Apple stake grew by a factor of a thousand in three months.

**Now:** both are returned in whole dollars, and `value_basis` names the
convention the filing itself used.

---

## Does any of this change the answer? Measured.

Fixing traps is only interesting if it moves the outcome. So the same model
answered the 50 public questions of the
[Vals AI Finance Agent Benchmark](https://huggingface.co/datasets/vals-ai/finance_agent_benchmark)
twice — once with no tools at all, once with only this server's tools:

| | correct | partial | wrong | could not answer |
|---|---|---|---|---|
| **With the server** | **45 (90%)** | 4 | 0 | 1 |
| Without tools | 13 (26%) | 17 | 3 | 17 |

The sharpest split is on questions asking whether a company beat the guidance it
gave a quarter earlier: **6/7 with the server, 0/7 without**. Those need two
8-K exhibits filed months apart. Without filing access the model could only
recall the direction — it said "beat" for both TJX and Micron and was right both
times, while missing the magnitude by 3-4x (20-30bps against an actual 70bps;
40bps against an actual 140bps).

The run is **point-in-time**: the dataset was published on 16 May 2025, so the
tools were told to ignore anything SEC received after that date. Otherwise a
question written in 2025 asking about "the most recent annual report" gets
answered from a 2026 filing — correctly sourced, wrong year. Every accession
number the tool arm read was then checked against SEC: none postdates the
cutoff. An earlier run without the cutoff scored 82%, and both runs are
published.

Neither answering side ever saw the expected answers, and a separate grader saw
the two answers in randomised order without being told which system produced
which — though it was not told rather than unable to tell, since the two arms'
answers do not look alike. The full method, the raw answers from both runs, the grades and the
limits of the number are in
[`evaluation/benchmark.md`](../evaluation/benchmark.md) — including the three
period mismatches that survive, and a direct measurement of how much the grader
itself moves the number: two graders agreed on 86% of the same fifty answers, so
read every figure as carrying about ±2 points.

## How it is kept true

- **286 tests**, no network access — SEC responses are mocked from real captured
  payloads.
- **199 fault injections.** Every guard above is deliberately broken by an
  automated harness, and the test that should catch it must turn red. A guard
  that nothing catches is reported as `KORUMASIZ` — unprotected — and the run
  fails. This has caught guards that looked protected and were not, including
  two that were redundant with each other in a way that made both untestable.
- **A 22-question evaluation set**, every answer produced by running the tools
  against live SEC data with the exact calls recorded, so any answer can be
  re-measured rather than trusted.
- **[`PATTERNS.md`](../PATTERNS.md)** — 36 failures that actually shipped in
  this repository, each with symptom, root cause, how it is detected now, and
  the test that guards it. A separate test suite keeps that document from
  drifting: every test it names must exist.
- CI on Ubuntu and Windows, Python 3.11 through 3.14, plus a Docker job that
  queries the container from outside.

## What this does not do

Stated here rather than discovered later: no price or market data (it is not in
SEC), no write access of any kind (read-only by design), US registrants only,
no XBRL before 2009 because it does not exist, and full-text search that is
practically limited to 2001 onward — measured, not assumed: a 1996-2000 search
for a word as common as "revenue" returns 14 filings, so an empty result for
older periods proves nothing.

---

**Repository:** https://github.com/belermirzaa7-ops/sec-edgar-mcp

If you are building an agent on financial filings — or on any regulated data
source where a plausible wrong number is worse than no number — this is the
class of problem I work on: finding the failures that return HTTP 200, and
turning each one into a test that fails loudly the next time.
