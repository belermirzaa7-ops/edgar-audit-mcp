# SEC EDGAR MCP Server

*[Türkçe README](README.tr.md)*

A [Model Context Protocol](https://modelcontextprotocol.io) server that lets an
LLM read **official SEC financial data** instead of recalling it from training.
Every number an agent returns through these tools can be traced back to a
specific SEC filing, a specific US-GAAP tag and a specific filing date.

Built against the **2026-07-28 MCP specification** using the Python SDK `v2.0.0`.

[![CI](https://github.com/OWNER/sec-edgar-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/sec-edgar-mcp/actions/workflows/ci.yml)

---

## Why this exists

Ask a language model for a company's revenue and it will answer from memory.
The answer is often close, sometimes wrong, and never verifiable. For financial
work that is unusable.

This server replaces recall with a lookup. But "just call the SEC API" is not
enough either — SEC's XBRL data has several traps that produce **silently wrong**
answers. The interesting part of this project is handling them.

## Tools

| Tool | Purpose |
|---|---|
| `sec_edgar_get_company_profile` | Ticker → CIK, registrant name, SIC industry, fiscal year end |
| `sec_edgar_list_filings` | A company's filings with links, filterable by form type; reaches past SEC's ~1000-entry recent feed with `include_older` |
| `sec_edgar_search_filings` | Full-text search across every filer — finds the filings that contain a phrase, down to the exhibit that carries it |
| `sec_edgar_get_concept_series` | Time series for one financial concept |
| `sec_edgar_get_fact_revisions` | How a reported figure changed across filings — restatements, with the accession number of each change |
| `sec_edgar_read_filing_text` | The narrative XBRL does not carry: MD&A, risk factors, the tax and segment notes — including 8-K exhibits and in-filing search |
| `sec_edgar_list_available_concepts` | Which tags a company actually reports, in any taxonomy it uses |
| `sec_edgar_compare_companies` | One concept across every company that reported it for a period, ranked |
| `sec_edgar_list_fact_dimensions` | Which breakdowns a filing contains — segments, geographies, product lines |
| `sec_edgar_get_dimensional_facts` | The numbers behind a consolidated total, with the total shown next to them |

Every tool returns a Pydantic model, so MCP `outputSchema` is generated
automatically and clients consume the results type-safely. List-returning tools
report `total_matching` / `returned` / `has_more` so the model can tell a
complete answer from a truncated one.

Concepts are addressed by alias (`revenue`, `net_income`, `public_float`, ...)
or by raw tag. A tag may be qualified with its taxonomy — `dei:EntityPublicFloat`
— and defaults to `us-gaap` when it is not. `sec_edgar_list_available_concepts`
reports which taxonomies a company actually files under, so the model discovers
them instead of guessing: financial statements live in `us-gaap`, while public
float and shares outstanding live in `dei`.

The four tools that can take several seconds — reading a filing, parsing an
XBRL instance, ranking a frame of thousands of companies — report progress
while they work, which the 2026-07-28 spec defines for exactly this case. The
rest do not: progress on a call that returns in milliseconds is noise. Nothing
else beyond `tools` is implemented, deliberately — for a read-only data server
`resources`, `prompts` and `completions` would be decoration, and `logging`,
`sampling` and `roots` were deprecated in this very spec revision.

Every tool is annotated `readOnlyHint: true`. That annotation is a hint,
not a guarantee — the guarantee is that the package contains no write path at
all, which a test enforces.

### Reading the filing text

XBRL carries the numbers, not the reasons. `sec_edgar_read_filing_text` reads
the filing itself and hands back a named section — MD&A, risk factors, the
income-tax note.

Two things make that harder than it sounds, and both are guarded by tests:

- **The table of contents says the same thing as the section.** "Item 7.
  Management's Discussion and Analysis" appears at least twice in a 10-K: once
  as a contents entry, once as the section. Taking the first match hands the
  model two lines of navigation and an apparently empty section. A heading only
  counts when real text follows it, and when a heading still appears twice, the
  longer block wins.
- **Filings are millions of characters.** Text comes back in bounded chunks
  with `offset` / `has_more`. The *converted text* is cached, not the raw HTML:
  converting 2.2 MB of HTML measured at 0.61 s, so re-parsing on every page
  turn wasted seconds, and the text is some twenty times smaller than the
  markup it came from.
- **The document a filing points to is not always the one with the content.**
  SEC names one primary document per filing; on an 8-K that is the cover page
  and the substance is in an exhibit. Measured on Tesla's Q2 2026 delivery
  release (`0001628280-26-046717`): the cover is 26,572 bytes and carries no
  figures, the exhibit is 13,243 bytes and carries all of them. Every readable
  file in the filing is listed on every call, with the primary one flagged, and
  `document` reads any of them.

Calling the tool without a section returns the headings the filing actually
has, so the next call names one instead of guessing. When the right heading is
not obvious, `search` reports how many times a phrase occurs and where; each
position can be passed straight back as `offset`.

### Addressing a filer that has no ticker

Every tool that takes a `ticker` also takes a CIK — `320193`, `0000320193` or
`CIK0000320193` all work. That is not a convenience: SEC's ticker file lists
only symbols that trade, so funds and foreign private issuers have none, and
full-text search returns those filers with a null ticker. Without CIK
addressing the server could find a document it could not then open.

A symbol asked for is echoed back as asked — `GOOGL` stays `GOOGL` rather than
becoming the alphabetically first symbol on the same CIK. Ask by CIK and the
symbol is looked up in SEC's file, and stays null when there is none rather
than being invented.

### Reading the tables, not just the text

Filings put their most quotable figures in tables — the financial statements,
the tax reconciliation, the production and delivery release that XBRL never
tags. Converted to plain text a table becomes cells joined by ` | `, and
whoever reads it has to align the columns by eye.

Passing `tables` to `sec_edgar_read_filing_text` returns the tables that begin
inside the text being returned, as rows and cells. Some care is in it:

- A table's `text_offset` is in the same coordinate space as `offset`, so a
  table can be matched to the passage it belongs to rather than to the document
  as a whole. Ask for a section and the offsets move with it.
- EDGAR filings use tables for page layout as much as for data. Tables with a
  single row or a single column are left out — and counted in
  `layout_tables_skipped`, because silence about them would read as "this
  filing has no tables".
- Nested tables come back separately rather than merged, and the inner table's
  text is not copied into the outer cell: the same figures returned twice would
  invite a model to count them twice.
- Row and cell limits exist, and each says so: `total_rows` against
  `row_count`, plus `rows_truncated` and `cells_truncated`.

Nothing here is new data — the same numbers are in the text. It is the
structure, returned so the model does not have to reconstruct it.

### Comparing across companies

The other tools answer about one company. `sec_edgar_compare_companies` reads
SEC's `frames` endpoint, which holds one period's value for every company that
reported a tag — 2,543 companies in the CY2025Q1 revenue frame, measured.

A frame looks like a like-for-like ranking and is not quite one, so the response
says so in data rather than in a footnote:

- **The periods inside one frame are not the same period.** SEC assigns each
  company's nearest fiscal period to a calendar frame. In CY2025Q1 the period
  ends run from 2025-02-23 to 2025-05-04 — seventy days apart. Apple appears
  there with its own fiscal second quarter, 2024-12-29 to 2025-03-29. Every row
  carries its own `period_end`, and the response reports the spread across the
  whole frame.
- **A missing company has not necessarily failed to report the concept.** It may
  tag it differently, or have no period that fits. Requested tickers that the
  frame does not hold come back in `missing_tickers` instead of being dropped.
- **A balance-sheet tag has no duration frame.** `Assets` in `CY2025Q1` is a
  404; `CY2025Q1I` is the frame that exists. Both are tried and the one that
  answered is named in the response.

Rank is always computed against the whole frame, so asking about three companies
does not make one of them "first".

### Segment data, and why the REST API does not have it

SEC describes `companyconcept`, `companyfacts` and `frames` as aggregating
facts that "apply to the entire filing entity". A segment figure applies to a
part of it, so those endpoints do not carry breakdowns. (SEC does not use the
word "dimensional"; that reading of the sentence is inference, and measurement
agrees with it — Tesla's segment split is absent from `companyfacts` and
present in the filing's XBRL.)

`sec_edgar_list_fact_dimensions` reads the filing's XBRL instance and reports
the axes and members it actually contains, so the next call names them instead
of guessing. `sec_edgar_get_dimensional_facts` returns the facts, each with its
context id, unit, period and the axes qualifying it.

**The part worth reading twice.** A breakdown and its total are two separate
claims, and this tool refuses to turn them into one equation:

- Some filings report no entity-wide total for a concept at all; some tag the
  total on a parent member, so it is itself dimensional.
- The members do not always sum to the total. XBRL US publishes a data-quality
  rule (DQC_0150) specifically to catch filings where they do not — which means
  filings where they do not exist.
- A figure carrying two axes at once, say segment *and* geography, is an
  intersection, not one segment's share. Adding it to a segment sum counts part
  of the business twice.
- A total tagged `xsi:nil` is not zero.

So nothing is summed silently. Ask for one axis and the response carries the
member sum and the entity-wide total side by side, with the difference, and
names what it excluded from the sum and why — `members_counted` and
`excluded_from_sum` carry the counts, by reason. The sum is computed over every
matching fact in the filing, not over the page returned, so changing `limit`
never moves it. Deciding which number is right is left to the reader, who is
the only one who can.

A note on provenance: the file being read, `<name>_htm.xml`, is SEC's
extraction from the filer's inline XBRL document — SEC's own dissemination
spec lists it among EDGAR-generated outputs. The values and contexts are the
filer's; the container is SEC's. The chain reaches further than that, and it
was measured rather than assumed: every one of the first 200 fact ids taken
from Tesla's FY2025 instance also appears in the 2.4 MB inline document the
company filed, so the `fact_id` on a returned figure locates the tagged span
in the filer's own document, not just a row in SEC's extraction. Filings from before inline XBRL was phased in
(fiscal periods ending 2019-06-15 for large accelerated filers, 2020 and 2021
for smaller ones) carry a filer-submitted instance instead, and that is read
instead.

That fallback used to be described here as untested, which was honest but
unsatisfying. It was measured on 15 Aug 2026 against Tesla's 10-K for fiscal
2011, filed February 2012: the filing has no `_htm.xml` at all, carries a
769 KB instance the company submitted itself, and that instance holds
dimensional facts in the same shape as a modern one — `xbrldi:explicitMember`
inside `entity/segment`, including contexts qualified by two axes at once. Its
label linkbase resolved too, and doing so proved a design decision right: the
2011 file declares no namespace prefix and names its locators
`us-gaap_Assets` against label resources named `us-gaap_Assets_lbl`, so a
reader that matched labels by naming convention rather than by following the
arc would have returned nothing at all for that filing.

The real boundary is earlier and it is not ours to move: XBRL was phased in
from fiscal periods ending after 15 June 2009, and nothing before that carries
tagged data in any form. For those filings the figures exist only as text, and
the text tools are the whole answer.

### Searching the text of every filer

`sec_edgar_search_filings` goes the other way round from the tools above: it
starts from a phrase, not from a company. It queries EDGAR's full-text index,
so a question like "which filers discussed a tariff in an annual report" has an
answer that does not depend on knowing the company first.

Three things about it are worth stating plainly, because all three change how
the result should be read:

- **A hit is a document, not a filing.** Measured on 15 Aug 2026: the oldest
  match for *tariff* in Tesla's annual reports is not a 10-K at all but an
  exhibit inside one, a supply agreement. Results therefore carry both the
  accession number and the file name, and both go straight into
  `sec_edgar_read_filing_text`.
- **The total can be a lower bound.** SEC reports large result counts with a
  `gte` relation rather than a count; `total_is_exact` says which one arrived.
- **Coverage starts around 2001, and an empty result proves little before
  that.** SEC's own page says the index holds filings "since 2001". A measured
  search of 1996-2000 annual reports for a word as common as *revenue* returned
  14 filings, the oldest dated 1999-03-31 — so a few older documents are
  indexed and most are not. The response says so itself: a search that returns
  nothing, or that reaches before 2001, comes back with a `coverage_note`
  rather than a bare zero.

The endpoint refuses to page past 10000 ranked results, which the schema
declares as a bound on `offset` instead of leaving the model to discover it
through an error.

One more measured quirk, found in live use a day after this tool shipped: SEC
drops a one-sided date range **silently**. Asking for filings from 2026 with no
end date returned 162 matches reaching back to 2009 — a filtered-looking answer
that was not filtered. The missing bound is now filled in (EDGAR's own
beginning, or today) and the range actually sent comes back in
`date_range_applied`.

### Filings older than the recent feed

SEC's `submissions` endpoint caps its recent-filings feed at roughly a thousand
entries and moves the rest into separate files. For an active filer that cap is
not a long history: Tesla's recent feed holds 1,053 filings and reaches back
only to May 2018, while its one older file holds 1,096 more going back to
February 2005 (measured 15 Aug 2026).

`sec_edgar_list_filings` reads the recent feed by default and says whether more
exists. Pass `include_older` and it reads the older feeds too, merges them and
sorts by date. It reads at most four of them and reports how many it skipped,
because a bound nobody mentions reads as completeness. Older feeds do not
always name a primary document, so `primary_document_url` can be null; when
the filing is then opened by accession number, the tool picks the largest
readable file and marks the choice as a guess with `primary_document_known:
false` rather than presenting it as SEC's designation.

### Human-readable names for tags and members

`tsla:OperatingLeaseVehiclesMember` is a name a filing uses, not a name a person
would write. The filing itself carries the translation, in its label linkbase
(`*_lab.xml`), and the dimension tools read it: axes, members and tags come back
with `axis_label`, `member_label` and `tag_label` next to the tags themselves.

The linkbase links a name to a label through an *arc*, and the code follows the
arc rather than the `loc_`/`lab_` naming convention that generators happen to
use — a fault injection takes the shortcut and the test turns red. Where an
element carries labels in several roles the standard one wins, and the
`documentation` role, which is a definition paragraph rather than a name, is
never used as one. Nothing is invented: an element the filing does not label
comes back as its tag, and `label_source` names the file the labels came from,
or is null when the filing has no linkbase at all.

Labels cost one extra download — 1.21 MB against a 2.68 MB instance on Tesla's
FY2025 annual report — so `include_labels` turns them off.

## Three traps this server handles

### 1. `fy` is the filing's year, not the data's year

SEC's `companyconcept` API attaches `fy` and `fp` to every fact. It is tempting
to read `fy` as the fiscal year of the value. It is not — it is the fiscal year
of the **filing the value appeared in**. A 10-K contains three years of
comparatives and all three carry the filing's `fy`.

Using `fy` naively shifted Apple's revenue series by two years without raising
an error. Periods here are determined only from `start`/`end` dates: annual is
300–400 days, quarterly is 60–120.

### 2. Fiscal year naming has no universal rule

Walmart's fiscal year ending 2026-01-31 is **FY2026**. Target's fiscal year
ending 2026-01-31 is **FY2025**. Same end date, different label — Walmart names
a fiscal year after the calendar year it ends in, Target after the year it
starts in. No fixed rule gets both right.

So no rule is used. `_fy_kaymasi()` derives the offset per company from SEC's
own data: within each `fy` group, the latest-ending annual period is the
filing's own period, which anchors `offset = fy − end_year`. If no anchor
exists, the response sets `fiscal_year_derived: false` rather than guessing
silently.

### 3. Tag changes truncate history

Apple reported revenue under `SalesRevenueNet` before ASC 606 and under
`RevenueFromContractWithCustomerExcludingAssessedTax` after. Stopping at the
first tag that returns data silently dropped **ten years** of history.

Aliases merge every candidate tag. Where periods overlap, the most recently
filed value wins. Each point carries a `source_tag` so the provenance of every
number stays visible — different tags may not measure a concept identically,
and that difference is surfaced rather than hidden.

## Usage

Concepts are requested by alias, not by raw XBRL tag:

```
sec_edgar_get_concept_series(ticker="MSFT", concept="revenue", limit=5)
```

Available aliases: `capex`, `cash`, `eps_diluted`, `gross_profit`, `net_income`, `operating_cash_flow`, `operating_income`, `public_float`, `revenue`, `rnd_expense`, `shares_diluted`, `shares_outstanding`, `stockholders_equity`, `total_assets`, `total_liabilities`.
Raw US-GAAP tags are accepted too. When a concept is not found the error
message names the valid aliases and points at the discovery tool — errors are
written for the model to act on, not just to report failure.

## Install

```bash
uv sync                      # or: pip install -e ".[dev]"
cp .env.example .env         # set SEC_USER_AGENT to your name and email
```

The SEC requires automated clients to identify themselves with a contact email
in the `User-Agent` header and to stay under 10 requests per second
([SEC Webmaster FAQ](https://www.sec.gov/os/webmaster-faq#developers)). This
server self-limits to 8 req/s and **refuses to start** without `SEC_USER_AGENT`.

**Where the variable comes from.** The MCP server takes its environment from
whatever launches it — the `env` block in a Claude Desktop config, `--env-file`
in Docker, or your shell. The core package deliberately does not read `.env`;
that would add a runtime dependency that buys nothing on those paths. The local
scripts (`dene.py`, `dogrula.py`) do read `.env`, via `python-dotenv` from the
`[dev]` extra, so you don't have to export the variable in every new terminal.

## Run

```bash
uv run mcp dev src/edgar_mcp/server.py    # MCP Inspector
uv run sec-edgar-mcp                      # stdio, for Claude Desktop etc.
docker build -t sec-edgar-mcp . && docker run --env-file .env -p 8000:8000 sec-edgar-mcp
```

Claude Desktop config:

```json
{
  "mcpServers": {
    "sec-edgar": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "edgar_mcp.server"],
      "env": { "SEC_USER_AGENT": "Your Name you@example.com" }
    }
  }
}
```

## Tests

```bash
pytest -q                  # HTTP layer mocked; never calls sec.gov
python arac/enjeksiyon.py  # fault injection
python arac/sir_tarama.py --gecmis   # secret scan, working tree + git history
python dogrula.py          # live verification against real SEC data
python arac/tani.py KO Assets           # inspect one raw SEC concept response
python arac/tani.py KO Assets --matris   # same data under varied conditions, to isolate a cause
python arac/tani.py --tarama             # how many companies are affected
python arac/tani.py TSLA --etiket        # does the label parser resolve a real linkbase
```

### Fault injection

A test that has never been observed to fail is not evidence. `arac/enjeksiyon.py`
deliberately breaks each protection in turn and asserts that the matching test
turns red, then restores the file and verifies the restore by hash.

This is not decorative. It caught two tests in this repo that passed while
protecting nothing — in both cases the mock did not reproduce the real API's
contract, so the code path under test was never exercised. It also catches
injections that have gone stale after a refactor, which is why it runs in CI.

### Secret scanning

`arac/sir_tarama.py` scans the working tree; `--gecmis` additionally scans git
history. The distinction matters: a secret that was committed and then removed
is gone from the files but still readable in history, and a working-tree-only
scan reports "clean" while the secret is public.

The scanner refuses to report clean when it cannot see full history — a shallow
clone returns exit code 2, not 0. CI therefore checks out with `fetch-depth: 0`.
A check that silently does nothing is worse than no check.

### Transport verification

The README's own instructions are executed by the suite, not just written down.
One test boots the streamable-HTTP transport on a free port and asks for
`tools/list` over real HTTP with no handshake, which is also what the
2026-07-28 stateless core requires. Another launches `python -m
edgar_mcp.server` over stdio through the SDK's own client — the exact path a
desktop MCP client uses. A CI job builds the Docker image and queries the
running container from outside it.

That job exists because of a real defect: the SDK binds `127.0.0.1` by default,
which inside a container leaves the published port dead. The image had never
been run, so nothing had noticed.

### Live verification

Mocks cannot prove behaviour against the real system. `dogrula.py` checks the
fiscal-year derivation and the tag-merging logic against live SEC data for
companies with calendar-year, ending-year and starting-year fiscal conventions.

### Evaluation set

[`evaluation/questions.xml`](evaluation/questions.xml) holds twenty questions that
can only be answered by calling the tools: cross-company fiscal year labels,
tag merges across an accounting standard change, ratios that need two series,
and the pagination fields. Every answer was produced by running the tools
against live SEC data and reading the result — none is written from memory —
and each question records the exact calls used, so the measurement can be
repeated instead of trusted.

A test keeps the file structurally honest: twenty pairs, every pair carrying a
question, an answer and a verification block, every tool it names actually
existing on the server, and no question anchored to "the latest" period.

## Failure patterns

[`PATTERNS.md`](PATTERNS.md) catalogues every bug that actually shipped in this
repository — symptom, root cause, how it is detected now, and the incident that
produced it — together with the specific test that guards each one. The entries
that have no automated guard say so in both the checklist and the entry body,
because claiming otherwise would be worse than the gap.

A test suite keeps that document honest: every test, tool and CI job it names
must exist, every entry must carry all four fields, and every incident must be
dated. Rename a test and the document fails CI rather than quietly lying.

## Project layout

```
src/edgar_mcp/server.py   MCP tools and schemas
src/edgar_mcp/client.py   SEC HTTP client, rate limiter, caching
tests/                    mocked unit tests
tests/dil.py              language gate for the outward-facing surface
tests/test_http_tasima.py runs the documented HTTP and stdio transports
evaluation/questions.xml  ten measured questions with their tool calls
arac/enjeksiyon.py        fault-injection harness
arac/sir_tarama.py        secret scanner
arac/tani.py              raw single-response diagnostic for one SEC concept
dogrula.py                live verification against SEC
CLAUDE.md                 decision records - why things are the way they are (Turkish)
PATTERNS.md               failure patterns - what to watch out for
```

Code comments and decision records are in Turkish; the public interface —
tool descriptions, schemas, error messages, this README — is in English.

## License

MIT
