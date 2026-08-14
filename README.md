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
| `sec_edgar_list_filings` | Recent filings with links, filterable by form type |
| `sec_edgar_get_concept_series` | Time series for one financial concept |
| `sec_edgar_get_fact_revisions` | How a reported figure changed across filings — restatements, with the accession number of each change |
| `sec_edgar_read_filing_text` | The narrative XBRL does not carry: MD&A, risk factors, the tax and segment notes |
| `sec_edgar_list_available_concepts` | Which tags a company actually reports, in any taxonomy it uses |

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

Calling the tool without a section returns the headings the filing actually
has, so the next call names one instead of guessing.

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

Available aliases: `capex`, `cash`, `eps_diluted`, `gross_profit`,
`net_income`, `operating_cash_flow`, `operating_income`, `revenue`,
`rnd_expense`, `stockholders_equity`, `total_assets`, `total_liabilities`.
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

[`evaluation/questions.xml`](evaluation/questions.xml) holds ten questions that
can only be answered by calling the tools: cross-company fiscal year labels,
tag merges across an accounting standard change, ratios that need two series,
and the pagination fields. Every answer was produced by running the tools
against live SEC data and reading the result — none is written from memory —
and each question records the exact calls used, so the measurement can be
repeated instead of trusted.

A test keeps the file structurally honest: ten pairs, every pair carrying a
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
