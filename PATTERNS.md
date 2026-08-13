# Failure Patterns

Every entry here is a bug that actually shipped in this repository, was
measured, and is now guarded. Nothing speculative goes in this file.

**If you are an agent working on this repo:** read the checklist below before
declaring work finished. Each pattern names the guard that enforces it, so you
can verify rather than remember.

---

## Before you finish

| # | Check | Guard |
|---|---|---|
| [P-1](#p-1) | Did I verify one externally-known value end to end? | manual |
| [P-2](#p-2) | Did I write a rule where the data could tell me the answer? | `test_kayma_target_tipi_eksi_bir`, `test_kayma_apple_tipi_sifir` |
| [P-3](#p-3) | Does stopping at the first match silently truncate anything? | `test_etiket_degisiminde_gecmis_kirpilmaz` |
| [P-4](#p-4) | Does my mock reproduce the real API's contract, including errors? | `arac/enjeksiyon.py` |
| [P-5](#p-5) | Did I re-run fault injection after changing code? | `arac/enjeksiyon.py` exits 1, CI job `fault-injection` |
| [P-6](#p-6) | Would this behave differently on another OS? | CI matrix includes `windows-latest` |
| [P-7](#p-7) | Can this check silently pass while seeing nothing? | `test_sig_klon_temiz_demez` |
| [P-8](#p-8) | Am I scanning current files when I should scan history? | `test_eklenip_silinen_sir_gecmiste_yakalanir` |
| [P-9](#p-9) | Did I confirm a rewrite actually removed the data? | **none — discipline only** |
| [P-10](#p-10) | Am I checking locally what only the remote can answer? | CI job `secret-scan` with `fetch-depth: 0` |
| [P-11](#p-11) | Does every tool and every parameter have a description? | `test_her_arac_ve_parametre_aciklamali` |
| [P-12](#p-12) | Am I making the model guess an external system's internal names? | `test_takma_ad_gercek_etikete_cozulur` |
| [P-13](#p-13) | Can the model act on my error message, or only read it? | `test_bilinmeyen_etiket_eyleme_donusturulebilir_hata_verir` |
| [P-14](#p-14) | Does the documentation describe behaviour the code actually has? | `test_env_example_gercekten_okunan_degiskeni_belgeler` |

Two of these have no automated guard. They are marked so, because pretending
otherwise is worse than the gap itself.

---

## A. External data sources

<a id="p-1"></a>
### P-1 · A metadata field does not mean what its name says

**Symptom.** Values are correct but attached to the wrong periods. No error, no
type mismatch, tests green.

**Root cause.** SEC's `fy` field is the fiscal year of the *filing the value
appeared in*, not of the value itself. An annual report carries three years of
comparatives and all three inherit the filing's `fy`.

**Detection.** Verify at least one externally-known value end to end on every
new data source. Apple's FY2021 revenue is $365.82B; the output showed that
figure on the FY2023 row.

**Incident.** 12 Aug 2026. The revenue series shipped shifted by two years and
was caught on the first live run, not by the test suite. Periods are now
derived only from `start`/`end` dates.

---

<a id="p-2"></a>
### P-2 · When the domain has no rule, derive instead of guessing

**Symptom.** Your heuristic is right for some cases and wrong for others.
Inverting it does not help — only which cases break changes.

**Root cause.** The domain genuinely has no convention. Walmart calls the year
ending 2026-01-31 **FY2026**; Target calls the year ending on **the same day**
FY2025. One names a fiscal year after the year it ends, the other after the
year it starts.

**Detection.** Whenever you write a heuristic, actively hunt for the case that
falsifies it. If you find one, look for a way to derive the answer from the
data — sources usually reveal their own convention somewhere.

**Incident.** 12 Aug 2026. "A period ending Jan–Jun belongs to the previous
year" was wrong for WMT, NKE and MSFT. Replaced by `_fy_kaymasi()`, which
derives each company's offset from its own filings and reports
`fiscal_year_derived: false` when no anchor exists instead of guessing.

---

<a id="p-3"></a>
### P-3 · Stopping at the first match truncates history silently

**Symptom.** A time series comes back shorter than expected. No error. Because
data *is* returned, nobody suspects it is incomplete.

**Root cause.** The source reported the same concept under different tags over
time (accounting standard change). Taking the first candidate that returns data
drops every period recorded under the older tag.

**Detection.** Compare the *data volume* of the alternatives. The discovery tool
reported 210 data points for `SalesRevenueNet` versus 117 for the modern tag —
that mismatch was the clue that led to the measurement.

**Incident.** 12 Aug 2026. Ten years of Apple revenue (FY2007–FY2017) were
being dropped. All candidate tags are now merged; on overlapping periods the
most recently filed value wins and every point carries its `source_tag`.

---

## B. Tests and verification

<a id="p-4"></a>
### P-4 · A mock that does not reproduce the real contract protects nothing

**Symptom.** The test is green. Remove the protection entirely — still green.

**Root cause.** The fake data did not behave like the real API. The fixture for
a filter test contained a *single* record, and that record already matched the
filter, so removing the filter had nothing to leak.

**Detection.** Fault injection. Break the protection deliberately and watch the
test go red. If it stays green, the test is theatre.

**Incident.** Two cases, 12 Aug 2026.
1. `test_filings_filter` — fixture had one form type. Fixed by putting 10-K,
   10-Q, 8-K and Form 4 in the fixture.
2. `test_kayma_ceyreklik_satirlari_capa_saymaz` — the scenario produced the
   same result with and without the filter. Rebuilt so removing the filter
   *must* change the answer.

---

<a id="p-5"></a>
### P-5 · Injection targets go stale after a refactor

**Symptom.** The harness reports "ENJEKSIYON UYGULANAMADI". That protection was
not exercised at all in that run.

**Root cause.** Injections locate a literal string in the source. Change the
code and the string is gone.

**Detection.** The harness must not pass over this quietly: it reports the
failure *and* exits non-zero so CI turns red. Rule: if code changed, the work
is not done until fault injection has been re-run.

**Incident.** 12 Aug 2026, six occurrences. The last one appeared when error
messages were translated from Turkish to English.

---

<a id="p-6"></a>
### P-6 · A local environment is structurally blind to a class of bugs

**Symptom.** Everything passes on the developer's machine and crashes elsewhere.

**Root cause.** Two concrete cases:
1. `subprocess.run(..., text=True)` decodes with the **local code page** on
   Windows (cp1254 on a Turkish install). Git's UTF-8 output raises
   `UnicodeDecodeError`, the reader thread dies, `stdout` comes back `None` and
   the caller gets an `AttributeError`. Fix: pass `encoding="utf-8",
   errors="replace"` explicitly and treat `stdout` as possibly empty.
2. A test called `rm -rf` for cleanup. That command does not exist on Windows.
   Fix: put temporary files *inside* `tmp_path` so the test framework cleans
   them, and build `file://` URIs with `Path.as_uri()` rather than by hand.

**Detection.** Put the target platforms in the CI matrix. Both bugs were
invisible to a Linux-only matrix.

**Incident.** 12 Aug 2026. Both surfaced on the user's Windows machine on first
run; development had been done on Linux.

---

## C. Checks and tooling

<a id="p-7"></a>
### P-7 · A check must not report "clean" when its scope is incomplete

**Symptom.** CI is green, the check appears to run, and it protects nothing.

**Root cause.** GitHub Actions checks out **shallow** by default. A tool that
scans git history then sees one commit and reports clean. The check always
passes and can never find anything.

**Detection.** The tool must detect its own incomplete scope and report
failure. "Found nothing" and "could not look" are different outcomes and need
different exit codes — this scanner returns 2, not 0, on a shallow clone.

**Incident.** 12 Aug 2026. Measured by cloning a temporary repository with
`--depth 1` and confirming the scanner refused. `fetch-depth: 0` added to CI.

---

<a id="p-8"></a>
### P-8 · Scanning the working tree cannot see history

**Symptom.** The secret scanner reports clean while the secret is publicly
readable.

**Root cause.** The secret was added in one commit and removed in the next. The
files are clean; the history is not.

**Detection.** Scan the *added* lines of `git log --all -p`.

**Incident.** 12 Aug 2026. A real email address was added to `dene.py` and
reverted. The working-tree scan said clean, and it was telling the truth about
what it could see.

---

<a id="p-9"></a>
### P-9 · Unreachable commits are outside `--all`

**Symptom.** A force push is done, history is presumed clean, and the data is
still reachable by SHA — where **no scanner will find it**.

**Root cause.** After a force push the old commits belong to no branch.
`git log --all` walks references only. The hosting platform keeps the objects
for an indeterminate time.

**Detection.** Do not verify a history rewrite by scanning. Verify it by
**trying to fetch the SHA directly.** If it resolves, nothing was removed. The
only reliable removal is a platform-side purge request or recreating the
repository.

**Incident.** 12 Aug 2026. After the force push, commit `5198c97` was fetched
and its contents were still present.

**Guard: none.** There is no way to test for this from inside the repository.
It is a manual step in any history-rewrite procedure.

---

<a id="p-10"></a>
### P-10 · A local scan cannot see remote-only history

**Symptom.** Local scan clean, remote dirty. The tool works correctly and is
looking in the wrong place.

**Root cause.** Commits authored through the hosting platform's web UI and
never pulled do not exist locally. `git log --all` walks local references only.

**Detection.** The authoritative check is the one in CI, because CI clones from
the remote. A local scan is a pre-filter, not evidence.

**Incident.** 12 Aug 2026. The local scan was predicted to go red and came back
clean. The prediction was wrong for this reason; the tool was right.

---

## D. LLM tool interfaces

<a id="p-11"></a>
### P-11 · A parameter with no description makes the model guess

**Symptom.** The model calls with wrong or missing arguments and burns turns.

**Root cause.** The parameter's `description` was empty. The model can see the
schema but not the meaning, so it infers from the type and bounds.

**Detection.** A structural test asserting that every tool *and every
parameter* carries a description. Written once, protects permanently.

**Incident.** 12 Aug 2026. The test found three undescribed `limit` parameters
the moment it was written. The model had been guessing how many records to ask
for.

---

<a id="p-12"></a>
### P-12 · Every place the model has to guess is a defect source

**Symptom.** The tool returns 404 or empty and the model keeps trying other
names.

**Root cause.** The tool expected the external system's internal identifiers
(XBRL tags) straight from the model. Companies report the same line item under
different tags, so guesses mostly missed.

**Detection.** Put the valid values **in the tool description**. Define
meaningful aliases and let the server do the translation. Add a discovery tool
and point at it from the error message.

**Incident.** 12 Aug 2026. The clue was that the demo script had to try three
tags in sequence — the model had no such fallback. Alias map and
`sec_edgar_list_available_concepts` were added.

---

<a id="p-13"></a>
### P-13 · An error message should be an instruction, not a notification

**Symptom.** The model receives the error, does not know what to do, and either
gives up or retries at random.

**Root cause.** A raw HTTP 404 was reaching the model. Sufficient for a human,
useless for an agent.

**Detection.** For every error path ask: *can the model make its next call
correctly after reading this?* If not, the message is incomplete.

**Incident.** 12 Aug 2026. Error messages now list the valid aliases and name
the tool and argument to call next. Fault injection guards this: strip the
guidance and the test goes red.

---

## E. Documentation

<a id="p-14"></a>
### P-14 · Documentation can promise behaviour that does not exist

**Symptom.** The setup instructions tell you to create a file that no code
reads.

**Root cause.** Copied from a template and never verified.

**Detection.** Pin it with a test: every configuration variable the docs
document must actually be read by the code. Manual review rots.

**Incident.** 12 Aug 2026. `.env.example` existed while nothing in the package
read `.env` — only Docker consumed it through `--env-file`.

---

## Adding an entry

An entry qualifies only if it **actually happened and was measured**. "This
could happen" and "people generally say" do not qualify. Four fields, all
required:

- **Symptom** — what is visible from outside, usually "no error, wrong result"
- **Root cause** — why it happens
- **Detection** — how it gets caught next time
- **Incident** — the concrete case, with a date

Name the guard in the checklist table. If there is no automated guard, say so
explicitly, as P-9 does.
