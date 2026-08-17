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
| [P-1](#p-1) | Did I verify one externally-known value end to end? | **none — manual step** |
| [P-2](#p-2) | Did I write a rule where the data could tell me the answer? | `test_kayma_target_tipi_eksi_bir`, `test_kayma_apple_tipi_sifir` |
| [P-3](#p-3) | Does stopping at the first match silently truncate anything? | `test_etiket_degisiminde_gecmis_kirpilmaz` |
| [P-4](#p-4) | Does my mock reproduce the real API's contract, including errors? | `arac/enjeksiyon.py` |
| [P-5](#p-5) | Did I re-run fault injection after changing code? | `arac/enjeksiyon.py` exits 1, CI job `fault-injection` |
| [P-6](#p-6) | Would this behave differently on another OS? | CI matrix includes `windows-latest` |
| [P-7](#p-7) | Can this check silently pass while seeing nothing? | `test_sig_klon_temiz_demez` |
| [P-8](#p-8) | Am I scanning current files when I should scan history? | `test_eklenip_silinen_sir_gecmiste_yakalanir` |
| [P-9](#p-9) | Did I confirm a rewrite actually removed the data? | **none — manual step** |
| [P-10](#p-10) | Am I checking locally what only the remote can answer? | CI job `secret-scan` with `fetch-depth: 0` |
| [P-11](#p-11) | Does every tool and every parameter have a description? | `test_her_arac_ve_parametre_aciklamali` |
| [P-12](#p-12) | Am I making the model guess an external system's internal names? | `test_takma_ad_gercek_etikete_cozulur` |
| [P-13](#p-13) | Can the model act on my error message, or only read it? | `test_bilinmeyen_etiket_eyleme_donusturulebilir_hata_verir` |
| [P-14](#p-14) | Does the documentation describe behaviour the code actually has? | `test_env_example_gercekten_okunan_degiskeni_belgeler` |
| [P-15](#p-15) | Is my injection target unique in the file? | `arac/enjeksiyon.py` reports the wrong test |
| [P-16](#p-16) | Are the helper scripts covered, not just the library? | `tests/test_scriptler.py` |
| [P-17](#p-17) | Did I inspect the whole outward surface, and can my detector see words I did not think of? | `test_arac_tanimlari_ingilizce`, `test_hata_mesajlari_ingilizce`, `test_dil_kontrolu_bilinen_ornekleri_ayirt_ediyor` |
| [P-18](#p-18) | Is the live client running the code I just changed? | **none — manual step** |
| [P-19](#p-19) | Does a 200 from upstream actually carry rows, and did I check the second endpoint? | `test_bos_companyconcept_yanitinda_companyfacts_e_dusulur`, `test_iki_uc_da_bossa_sessiz_basari_yerine_hata` |
| [P-20](#p-20) | Have I actually run the deployment path the README promises? | `test_http_tasimasi_araclari_el_sikismasiz_listeler`, `test_stdio_tasimasi_resmi_istemciyle_araclari_listeliyor`, `test_dockerfile_loopback_disina_baglaniyor`, CI job `docker` |
| [P-21](#p-21) | Did my fault injection actually compile, or did it just break the import? | `test_enjeksiyon_bozuk_sozdizimini_koruma_eksigi_sanmiyor` |
| [P-22](#p-22) | Could two copies of this tool be running at once? | `test_enjeksiyon_ayni_anda_iki_kez_calismiyor` |
| [P-23](#p-23) | Is the document I am reading the one that carries the content, or the one that announces it? | `test_8k_govdesi_ekte_oldugunda_ek_okunabiliyor` |
| [P-24](#p-24) | Did I edit the working tree by hand to test an idea, and is that edit still there? | `arac/enjeksiyon.py` refuses to start while any test is red |
| [P-25](#p-25) | Does my tooling recognise the test names pytest actually prints? | `test_enjeksiyon_parametreli_testi_de_taniyor` |
| [P-26](#p-26) | Am I treating a breakdown and its total as arithmetic that must agree? | `test_tutmayan_toplam_gizlenmiyor`, `test_raporlanmayan_toplam_sifir_sanilmiyor` |
| [P-27](#p-27) | Does a bound I added for display leak into a number I compute? | `test_mutabakat_sayfalama_sinirindan_etkilenmiyor` |
| [P-28](#p-28) | Does any behaviour depend on the iteration order of a set? | `test_metin_cikarimi_surecten_surece_ayni_sonucu_veriyor` |
| [P-29](#p-29) | Does a filter compare strings the caller wrote by hand, and does a miss look like an empty answer? | `test_form_filtresi_buyuk_kucuk_harf_duyarsiz` |
| [P-30](#p-30) | Does a missing optional dependency turn a loader into a silent no-op? | `test_env_yukleyici_bagimlilik_olmadan_da_yukluyor`, `test_env_yukleyici_bom_lu_dosyayi_okuyor` |
| [P-31](#p-31) | Does my cleanup depend on my process getting a chance to run it? | `test_enjeksiyon_kontrol_modu_yarim_kalan_kosuyu_goruyor`, `test_enjeksiyon_parcali_kosu_hicbir_enjeksiyonu_dusurmuyor` |
| [P-32](#p-32) | Is "the latest filing" the latest as of *when* — and does my filter cut on the period or on the filing date? | `test_as_of_o_tarihte_bilinen_degeri_donduruyor`, `test_as_of_bilinmeyen_tarih_iceri_alinmiyor` |

Three of these — **P-1**, **P-9** and **P-18** — have no automated guard and
are marked `none` in the table and `Guard: none` in the entry. All three are
manual steps in a procedure, not properties of the code, so nothing in the test
suite can enforce them. Saying so is better than implying coverage that does not exist; a test
asserts that this marking stays consistent.

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

**Guard: none.** The specific bug is covered by
`test_donem_yili_bitis_tarihinden_gelir`, but the practice this pattern asks
for — checking a value you know independently against a *new* data source —
cannot be tested from inside the repository. It is a manual step.

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

<a id="p-15"></a>
### P-15 · A substring target matches in more places than you think

**Symptom.** Fault injection reports a protection as verified, but the test that
went red is not the one you expected. The protection you meant to break was
never touched.

**Root cause.** Two functions used the same local variable name, so
`has_more=len(eslesen) > limit,` appeared twice in the file. The harness
replaces the first occurrence, so it broke the other function.

**Detection.** The harness prints which test caught each injection. Read that
column — a mismatch between the injection name and the test that fired means
the target is ambiguous. Before adding an injection, confirm the target string
occurs exactly once.

**Incident.** 13 Aug 2026. Adding pagination to `sec_edgar_list_filings`
created a collision with `sec_edgar_list_available_concepts`. The variable in
the first was renamed to make both targets unique.

This is the code-level form of a general rule: substring predicates match wider
than intended.

---

<a id="p-16"></a>
### P-16 · Helper scripts drift out of the test suite

**Symptom.** The whole suite is green and the demo script crashes on the first
run with an `AttributeError`.

**Root cause.** A response model field was renamed (`resolved_concept` →
`resolved_concepts`). The library and its tests were updated together; the
standalone script that consumes the same models was not, because nothing
imported it during testing.

**Detection.** Run the scripts against the same mocks the library tests use and
assert on their output. If a field disappears, the script fails in CI rather
than in front of whoever runs the demo.

**Incident.** 13 Aug 2026. Caught while adding pagination, before the user ran
the script — but only because the output was being read by hand, not by a test.
`tests/test_scriptler.py` now covers it.

---

## F. The outward surface and the live client

<a id="p-17"></a>
### P-17 · A keyword blacklist only sees the vocabulary it was written with

**Symptom.** Turkish text shipped to a live client in three separate places
while the test asserting "the outward surface is English" stayed green.

**Root cause.** Two compounding gaps. First, the surface was enumerated by
hand: the test read `t.description` only, so parameter descriptions, response
schema descriptions and error messages were never inspected. Second — and this
is the one that keeps coming back — the detector was a blacklist of Turkish
substrings (`" ve "`, `"dondurur"`, ...). A blacklist can only reject what its
author already imagined. Widening the surface did not help by itself: the very
first injection written to prove the widened test worked came back
**KORUMASIZ**, because the injected string `"Ticker bulunamadi: ..."` contained
no listed word and no Turkish-specific letter.

**Detection.** Enumerate the surface from the schema itself (tool description,
every input property, every `$defs` and top-level output property) plus an AST
walk over every `raise` in `src/`, since error messages reach the model but
never appear in a schema. Then check with a **positive** list: every word must
be in `tests/kelime_dagarcigi.txt`, identifiers excluded. An unknown word turns
the test red regardless of which language it comes from. The blacklist is kept
as a cheap first layer, not as the guarantee.

**Incident.** 13 Aug 2026, three times in one session. (1) Reloading the tool
schemas in Claude Desktop showed `concept` described as "Takma ad ... veya ham
US-GAAP etiketi (orn. NetIncomeLoss)" — 59 tests green. (2) Widening the
surface to response schemas found nothing new, but the injection harness proved
the widened blacklist still could not see `"Ticker bulunamadi"`. (3) That string
was live in `client.py` and reached the model on every unknown ticker. The
fixture list in `test_dil_kontrolu_bilinen_ornekleri_ayirt_ediyor` starts with
the two real strings.

---

<a id="p-18"></a>
### P-18 · A long-running client keeps an old server process

**Symptom.** A tool answers without the fields a recent change added. The
source is current, the test suite is green, the client's answer is not.

**Root cause.** An MCP client spawns the stdio server as a subprocess when it
starts and keeps that process for the whole session. Editing the source has no
effect until the client is fully quit and relaunched — closing the window is
not enough while the app stays in the tray or menu bar.

**Detection.** Before treating anything a live client returns as evidence about
the code, call one tool and look for a field that only exists in the current
version — `total_periods` after the pagination change. If it is missing, the
client is stale and its output says nothing about the repository.

**Incident.** 13 Aug 2026. Immediately before building the evaluation set,
`sec_edgar_get_concept_series` returned no `total_periods`/`returned`/
`has_more`. Without that check the evaluation set would have been written
against — and declared verified against — a version that no longer existed.

**Guard: none.** The staleness lives in another process on another machine;
nothing inside the repository can observe it. It is a step in the procedure:
check a version-bearing field first, restart the client, then measure.

---

## G. Upstream endpoints

<a id="p-19"></a>
### P-19 · A 200 response can be well-formed and still contain nothing

**Symptom.** A tool returns a successful, schema-valid, empty result. The model
reads it as "this company does not report that" and answers confidently. A
different tool on the same server, reading a different endpoint, says the data
is there.

**Root cause.** SEC's `companyconcept` endpoint served an object with `units.USD`
present but carrying no rows — 346 bytes, correct `label`, HTTP 200 — for one
company, while `companyfacts` carried 144 rows for the same tag. The raw body
reads `"units":{"USD":{}}`: an empty **object** where an array belongs, which
points at the producer rather than at a cache — a stale cache would serve the
whole previous object, not a differently-typed empty one. The emptiness
was upstream and location-dependent: five request variants from one network
(base, repeat, cache-busting query string, different `User-Agent`, no
compression) were all empty, and the same URL fetched from another network
returned the full document. No response header explained it; the responses
carried no `age`, `x-cache` or `etag` at all.

**Detection.** Count rows, do not trust the status code. Filter the unusable
shape in exactly one place: the first version checked `isinstance` at two call
sites and missed a third, which crashed with `'str' object has no attribute
'get'` — iterating an empty-object body yields its keys, not rows. If a 200 carries none,
read the second endpoint that holds the same facts before concluding anything,
and report which endpoint answered (`source_endpoint`) so the caller is never
guessing. If both are empty, raise an actionable error — an empty success is
indistinguishable from a real "no data" answer, and that is the whole problem.
The fallback stays behind the zero-row check: `companyfacts` is several MB and
must not be fetched on every call.

**Incident.** 13 Aug 2026. `sec_edgar_get_concept_series` returned
`total_periods: 0` for Coca-Cola under every concept, while
`sec_edgar_list_available_concepts` reported 144 data points for `Assets` on the
same server. Isolated with `arac/tani.py --matris`, which requests the same data
under varied conditions and names the variable that changed the outcome.

---

<a id="p-20"></a>
### P-20 · A documented deployment path that was never executed

**Symptom.** The README shows `docker build` and `docker run -p 8000:8000`. The
image builds, the container starts, the log says the server is running — and
nothing outside the container can reach it.

**Root cause.** The SDK's `run_streamable_http_async` defaults to
`host="127.0.0.1"`. Inside a container that binds the loopback interface only,
so the published port has nothing behind it. The `CMD` had never been executed
in any environment, so the default was never observed. Nothing in the test
suite touched the HTTP transport either: the tests exercise the tool functions
directly, which is a different code path from the one the README advertises.

**Detection.** Run the documented path, do not read it. A test starts the HTTP
transport on a free port and asks for `tools/list` over real HTTP with no
handshake, which also proves the stateless behaviour the 2026-07-28 spec
requires. A CI job builds the image and queries the running container from
outside it. A third test pins the SDK default itself, so if upstream ever
changes it, the explicit host in the `Dockerfile` is re-examined rather than
cargo-culted. The stdio path — the one Claude Desktop actually uses — is
covered the same way, through the SDK's own client rather than a hand-built
JSON-RPC frame: a hand-built frame omits the `params`/`_meta` the 2026-07-28
wire requires, so it fails the test rather than the server.

**Incident.** 13 Aug 2026. Found while auditing what in this repository is
claimed but unverified — not by a failure, because nobody had ever run it. The
`Dockerfile` now passes `host='0.0.0.0', stateless_http=True` explicitly.

---

<a id="p-21"></a>
### P-21 · A broken injection looks exactly like a missing guard

**Symptom.** The fault-injection harness reports a protection as **KORUMASIZ**
(unguarded) and names two unrelated tests as the ones that turned red.

**Root cause.** The injected replacement text was malformed - it left an
unbalanced bracket. The module no longer parsed, so importing it failed and
every test that touches the server failed with it, while the test that was
supposed to catch the injection never got the chance to run. The harness only
asks "did the expected test turn red", so "there is no guard here" and "my
injection is broken" produce the same output.

**Detection.** Parse the mutated source before running the suite. If it does
not compile, report it as a broken injection, not as a missing guard - the two
call for opposite actions: one means write a test, the other means fix the
injection string. Non-Python targets (the `Dockerfile`) are exempt.

**Incident.** 14 Aug 2026, while adding the revision-history tool. The
injection meant to strip a period's older values replaced
`gruplar.setdefault(...).append(` with a line that opened a bracket it never
closed. The harness said the new tool had no guard; it had two, and neither had
run.

---

<a id="p-22"></a>
### P-22 · A tool that rewrites the working tree must refuse to run twice

**Symptom.** Two protections reported as unguarded, with unrelated tests named
as the ones that failed - a `Dockerfile` test and a concept test failing while
a text-parsing guard was being checked. Afterwards the test suite stayed red:
nine tests failed against a working tree that looked clean in the editor.

**Root cause.** Two copies of the fault-injection harness were started by
mistake. Each one breaks a file, runs the suite, and restores the file. Run
them together and one is holding a file broken while the other runs the suite,
so the second one measures the first one's damage. Worse, when one was killed
mid-injection its restore never completed, and an injected line survived in
`src/` - every later test ran against sabotaged code.

**Detection.** The harness takes an exclusive lock file at startup and refuses
to start if one exists, naming the file so a stale lock can be removed. The
existing crash-safe restore covers the case where a run dies; the lock covers
the case where a run never should have started.

**Incident.** 14 Aug 2026. Recovered by scanning every injection's replacement
string against the working tree, which found one still applied - the alias map
had been left emptied. That scan is worth remembering as the recovery
procedure: for each injection, if the target string is missing and the
replacement string is present, the file is still sabotaged.


<a id="p-23"></a>
### P-23 · The primary document can be a cover page, and the largest file can be machine-generated

**Symptom.** Reading an 8-K returned the form's cover — state of incorporation,
address, four unchecked boxes, "the press release attached hereto as Exhibit
99.1 is incorporated herein by reference" — and none of the numbers the filing
was published to report. No error: a well-formed filing, read successfully,
carrying nothing the reader came for.

**Root cause.** EDGAR names exactly one `primaryDocument` per filing in the
submissions feed. On an 8-K that document is the cover; the substance sits in
an exhibit that appears only in the filing directory's `index.json`. Two things
make the directory harder to read than it looks. The `type` field is not a
document type — it is the name of the icon EDGAR draws in its own file listing,
`"text.gif"` for every entry, so nothing in the JSON says which file is the
exhibit. And the directory contains `R1.htm` … `Rn.htm`, renderings generated
by SEC's XBRL viewer rather than anything the filer wrote; on this filing
`R1.htm` was the largest `.htm` present.

**Detection.** Every readable file in the directory is listed on every call, so
an apparently empty filing shows where its content is. Navigation pages and
viewer output are dropped by name, and the file SEC calls primary is flagged
`is_primary`, which is the signal the model actually needs — size is not.
Guard: `test_8k_govdesi_ekte_oldugunda_ek_okunabiliyor`, whose fixture copies
the real directory listing, sizes included.

**Incident.** 14 Aug 2026, TSLA 8-K `0001628280-26-046717`, the Q2 2026
delivery release. Primary document `tsla-20260702.htm`, 26,572 bytes, cover
only. `exhibit99111111.htm`, 13,243 bytes, holds 451,758 produced / 480,126
delivered / 13.5 GWh. `R1.htm`, 38,047 bytes, generated. The first
implementation ranked files largest-first, on the assumption that the exhibit
would be the biggest readable file; the mock had been written to match that
assumption, so the test agreed with it. Measuring the actual filing refuted it
twice — the cover outweighs the exhibit because inline-XBRL markup is bulky,
and the generated rendering outweighs both.

---

<a id="p-24"></a>
### P-24 · A probe applied by hand is an injection with no restore

**Symptom.** Two tests red at the start of a session, in code that had been
green when the previous session ended and that nobody had edited since.

**Root cause.** While hunting for a fault-injection target, a candidate edit
(`toplam += 1` → `toplam += 0`, disabling a search counter) was applied to the
working tree by hand to see which tests it would turn red. The session ended
before it was undone. The harness writes a backup to disk, restores in a
`finally` block, restores again at exit, and holds a lock while it runs; an
edit made by hand has none of that. The harness's own safety net does not cover
edits the harness did not make.

**Detection.** Probe candidates with a script that writes the file, runs the
target tests and restores in a `finally` block — the same discipline as the
harness, never a bare edit to the tree. Independently, `arac/enjeksiyon.py`
refuses to start while any test is red, so leftover sabotage stops the next run
instead of being measured as a missing guard. Guard: `arac/enjeksiyon.py`
clean-state check; the leftover itself is caught by whichever test it breaks,
which is why the suite is run before anything is believed.

**Incident.** 14 Aug 2026, this repository, one probe left behind out of eleven
tried. Cost: two red tests carried into the next session, and a packaged
release that would have shipped a disabled counter had the suite not been run
first.


<a id="p-25"></a>
### P-25 · A verifier that cannot recognise its own success reports failure

**Symptom.** The fault-injection harness reported a protection as **KORUMASIZ**
— unguarded — while printing, in the same row, the very tests that had turned
red. The output contradicted itself and the contradiction was easy to read past,
because "unguarded" is exactly what a real gap looks like.

**Root cause.** The harness matched the expected test name by equality against
the names pytest prints. pytest prints a parametrized test as
`test_cerceve_donem_yazimi_serbest` followed by `[2025Q1]`, one line per case. No parametrized test could ever
match, so any guard proven by one was reported as missing. Six red tests, all of
them the right ones, and the verdict was still "no guard".

**Detection.** Matching accepts the exact name or the name followed by `[`,
which is the only form pytest adds. A test pins both directions, including that
the prefix match does not stretch to a longer name that merely starts the same way.
Guard: `test_enjeksiyon_parametreli_testi_de_taniyor`.

**Incident.** 14 Aug 2026, on the first parametrized target ever added to the
harness — a period-syntax guard covering six spellings. This is the same failure
class as P-21: the tool for distinguishing "guard missing" from "measurement
broken" was itself broken, and it fails toward the more alarming reading.


<a id="p-26"></a>
### P-26 · A breakdown and its total are two claims, not one equation

**Symptom.** A segment breakdown that looks complete and sums to something
other than the reported total — or sums to exactly the total by accident,
because a figure qualified by two axes at once was counted as if it were one
segment's share.

**Root cause.** Three assumptions that all feel obviously true and are not.
"A fact with no dimension is the total" — filings exist with no such fact at
all, and filings exist where the total is itself dimensional, tagged on a
parent member, which is the structure XBRL US actually recommends to prevent
double counting. "The members sum to the total" — XBRL US's Data Quality
Committee publishes rule DQC_0150 specifically to catch filings where they do
not, which means real filings do not. "A dimensional fact belongs to its
segment" — a fact carrying both a segment axis and a geography axis is the
intersection of the two, and adding it to a segment sum counts part of the
business twice. A fourth, smaller one: a total tagged `xsi:nil` is not zero.

**Detection.** Nothing is summed silently and no total is chosen. When one axis
is requested, the response carries the member sum and the entity-wide total
side by side with their difference, and multi-axis facts are excluded from the
sum. A nil total comes back as absent, not as `0`. When no numeric member
remains to add, no reconciliation row is produced at all — reporting `0` would
assert that zeros were summed. Guards:
`test_tutmayan_toplam_gizlenmiyor`, `test_cok_boyutlu_fact_toplamaya_girmiyor`,
`test_raporlanmayan_toplam_sifir_sanilmiyor`.

**Incident.** 14 Aug 2026, during design rather than after a failure: research
into DQC_0150 and into two bugs in another XBRL library's changelog — one where
a concept with only dimensional facts returned nothing, one where dimensional
rows overwrote the total — surfaced the failure class before any of it was
written. Recorded here because the assumption is the natural one to make, and
the arithmetic looks right often enough to be trusted.


<a id="p-27"></a>
### P-27 · A limit meant for display leaked into the arithmetic

**Symptom.** A segment breakdown that ties to the cent reported as off by
20.7 billion dollars. Same filing, same tool, same day — the only thing that
changed was `limit`.

**Root cause.** The reconciliation summed the facts that were about to be
*returned*, after truncation to the page size, while the entity-wide total came
from the whole filing. Two numbers from two different populations, subtracted.
The default page of 40 is smaller than a real segment query on a 10-K — three
comparative years across segments and product members — so the fabricated
discrepancy was not an edge case, it was the normal path. `has_more: true` was
present in the response, and nothing connected it to the reconciliation.

**Detection.** Anything computed is computed over the full matched set; the
page bound applies only to what is displayed. A test asks the same question at
`limit=1` and `limit=40` and requires the sums to be identical, which is the
property that actually matters and is cheap to assert anywhere a page bound
meets an aggregate. Guard: `test_mutabakat_sayfalama_sinirindan_etkilenmiyor`.

**Incident.** 15 Aug 2026, found by an adversarial review of code written hours
earlier — the same session that added P-26 to stop a tool from inventing a
discrepancy between a breakdown and its total. The tool then invented one
itself, by a different route. Worth remembering: the guard and the bug were
written by the same person in the same afternoon, so knowing the failure class
is not the same as being immune to it.


<a id="p-28"></a>
### P-28 · A set has no order, so anything that iterates one is not deterministic

**Symptom.** The same filing, read by the same code, produced different text in
different server processes. In one process a financial table came back with its
numbers; in another the whole table was gone and the section vanished from
`available_sections`. Nothing in the input, the code or the environment
differed — only the process.

**Root cause.** The HTML extractor's implied-end-tag table mapped a tag to a
**set** of tags it closes, and the loop stopped at the first match. CPython
randomises string hashing per process, so the iteration order of a small set of
short strings changes from run to run. When `<tr>` arrived while both a `<td>`
and its enclosing `<tr>` were open — the ordinary state in EDGAR HTML, which
omits closing tags — the code closed whichever the set happened to yield first.
Half the time that was `td`, leaving a hidden `<tr>` on the stack forever and
swallowing the rest of the table. Measured: content present under
`PYTHONHASHSEED` 0 and 2, absent under 1 and 3.

A second bug hid the first. Start tags emitted their `|` and newline separators
without checking whether they were inside a hidden block, so a swallowed table
still produced a full skeleton of empty cells. The output stayed long, and the
"the filter swallowed the document" safety net — which compares output length
against input length — never fired.

**Detection.** Ordered containers wherever order is part of the behaviour, and
close every applicable tag rather than the first. A test runs the extractor in
five subprocesses with different `PYTHONHASHSEED` values and requires the five
outputs to be identical, which is the only way this class of bug is visible at
all from inside one process. Guards:
`test_metin_cikarimi_surecten_surece_ayni_sonucu_veriyor`,
`test_gizli_blok_icinde_ayirici_uretilmiyor`.

**Incident.** 15 Aug 2026, in code written the previous night to fix P-19 — the
fix reintroduced the very failure it was written to remove, through a path
nobody thought to look at, and with a coin flip attached. The server's own
description says "deterministic tool calls"; for one process in four it was not
true. Worth generalising: a set literal is a claim that order does not matter.
If order does matter, the container is wrong, not the loop.

---

<a id="p-29"></a>
### P-29 · A filter compares a string the caller typed, and a miss is indistinguishable from an empty answer

**Symptom.** `sec_edgar_list_filings(ticker="AAPL", form_type="10-k")` returned
`filings: [], total_matching: 0, has_more: false` — a well-formed, confident,
empty answer. The same call with `10-K` returned the annual reports. Nothing in
the response said the filter had matched nothing rather than the company having
filed nothing.

**Root cause.** The form filter compared the caller's string to SEC's with `!=`.
SEC writes form types in upper case, so any other casing matched no row. The
failure is worse than a wrong result because the shape of the response is the
same as a true negative: a model reading it concludes "this company has no 10-K".

**Detection.** Comparison is now case-insensitive on both sides, in one helper
used by every place that filters by form. Amendments stay excluded — `10-K/A`
is not `10-K`, and that is a different filing, not a casing difference. A fault
injection restores the case-sensitive comparison and the test turns red. The
general rule: whenever a filter can silently produce nothing, the empty result
must be either impossible by construction or explained in the response. Guard:
`test_form_filtresi_buyuk_kucuk_harf_duyarsiz`.

**Incident.** 15 Aug 2026, found while extending the same function to read
SEC's older filing feeds. The comparison had been in place since the first
version of the tool and no test had ever passed it anything but `10-K` — the
suite only ever repeated the author's own spelling.

---

<a id="p-30"></a>
### P-30 · An optional dependency makes the loader optional too

**Symptom.** `arac/tani.py` stopped with `SEC_USER_AGENT environment variable is
required`. The `.env` file holding that variable was present, correctly spelled
and in the right directory. The error named the variable, so it read as a
configuration problem on the user's side rather than as a file that was never
opened.

**Root cause.** The loader imported `python-dotenv` and returned on
`ImportError`. The dependency is genuinely optional — the MCP server takes its
environment from whatever launches it — but the *loading* was made optional
along with it. Two unrelated situations reached that same silent path: running
the script with an interpreter outside the virtual environment, where the
package is absent, and a `.env` written by PowerShell's `Out-File -Encoding
utf8`, which prepends a byte-order mark so the first key parses as
`﻿SEC_USER_AGENT` and never matches.

**Detection.** The loader now carries its own dependency-free parser, decodes
with `utf-8-sig` so a BOM is consumed, and uses `setdefault` so a variable
already exported in the shell is never overwritten by a stale file. BOM
handling lives in exactly one place: an earlier version also stripped the mark
inside the line parser, and fault injection reported the encoding guard as
`KORUMASIZ` — two mechanisms for one property mean neither is tested. Guards:
`test_env_yukleyici_bagimlilik_olmadan_da_yukluyor`,
`test_env_yukleyici_bom_lu_dosyayi_okuyor`,
`test_env_yukleyici_mevcut_degiskeni_ezmiyor`.

**Incident.** 15 Aug 2026, after an update copied with `robocopy /MIR` deleted
the `.env` file — `/MIR` removes anything the source does not have, and the
command excluded directories but not files. Recreating the file did not fix the
error, which is what exposed the loader. Both halves are the same lesson: a step
that can quietly do nothing will eventually do nothing quietly at the worst
moment.

---

<a id="p-31"></a>
### P-31 · Cleanup that only runs if the process gets to run it

**Symptom.** A fault-injection sweep stopped producing output. The process was
gone; the log's last line was `[32/163]`, written 43 minutes earlier. Nothing
announced a failure — there was no traceback, no non-zero exit, no message at
all. The working tree looked normal and the test suite was green, because the
injection that happened to be applied (`belge.py`, the longest-match rule for
duplicate section headings) only turns one test red, and that test was not the
one being run in the moment the process died.

**Root cause.** Every restoration path in the harness was built on the process
surviving long enough to execute it: a `finally` block, an `atexit` handler, and
handlers for `SIGINT` and `SIGTERM`. A hard kill — `SIGKILL`, an out-of-memory
reaper, a container being reclaimed — runs none of them. The repository's own
decision record (KK-6) called the harness "crash resilient", and that claim was
true for exceptions and for signals a process can catch. It was never true for
the case where the process is not asked to stop but simply ceases.

The harness did restore leftovers, but only at the start of *its next run*. That
made the recovery invisible to every other step: running the tests, packaging a
release, or committing does not invoke the harness. A sweep could die at 32/163
and the next thing to touch the repository would see an injected source file
with no indication that anything had gone wrong.

**Detection.** Three changes, each addressing a different part of the failure:

- `enjeksiyon.py --kontrol` reports whether a previous run left anything behind
  and exits 2 if so. It deliberately does **not** repair: detection and repair
  are separate, because a check that silently fixes the state hides exactly the
  event worth seeing. CI runs it after the sweep, which also turns the
  harness's own cleanup claim into something that is verified rather than
  asserted.
- The name of the applied injection is written to disk *before* the file is
  broken and removed after it is restored, so a leftover identifies itself
  instead of having to be reconstructed by diffing against the backups.
- `--parca k/n` splits the sweep into contiguous shards. The full run is 163
  injections and each one runs the entire suite; how long that takes depends
  heavily on the machine's load — a single suite run measured 14 s on an idle
  container, around 40 minutes for the sweep, while the run that died was
  averaging some 80 s per injection, which projects past three hours. That
  spread is itself the argument: the longer a process lives, the likelier it is
  to be killed. Four shards keep each process short and make a lost shard cheap
  to repeat. The split is checked for completeness by a test —
  a sharding bug that dropped injections would quietly verify less than the
  harness claims, which is a worse failure than the one being fixed.

A per-run timeout was added at the same time, reported as its own outcome
rather than as an absent guard: a measurement that could not be taken is not
the same as a guard that does not exist (the same distinction as KK-10's
`ENJEKSIYON SOZDIZIMI BOZDU`).

**Incident.** 16 Aug 2026, during the v38 sweep. Recovery was manual: the files
were diffed against `.enjeksiyon_yedek/`, `belge.py` was found to differ by one
line, and it was restored by hand. That recovery worked only because the
backups were still on disk and someone thought to look. Nothing in the
repository would have raised the question.

---

<a id="p-32"></a>
### P-32 · "The latest filing" has a hidden argument: as of when

**Symptom.** A question written in 2025 asking about "the last three years" or
"the most recent 10-K" gets a different answer when it is run in 2026. Nothing
errors. The tool finds a real filing, quotes it accurately, and cites its
accession number — it is simply a filing that did not exist when the question
was written. The answer is well-sourced and off by a year.

A second, quieter version of the same thing: a figure for a period that has
already closed can still change, because the company restates it in a later
filing. Read today, FY2023 revenue is whatever the most recent filing says it
is. Read as it stood in January 2024, it is the original number. Both are
correct; they answer different questions, and nothing in the data marks which
one was asked.

**Root cause.** Every "most recent" in a filing tool carries an implicit *as of
now*. Once that assumption is written down it is obviously wrong for any
historical question — evaluating a benchmark authored a year ago, reproducing
an analysis, testing a strategy against what was knowable at the time. In
finance the general name for the failure is **look-ahead bias**: using
information that was not available at the moment being described.

The trap inside the fix is choosing the wrong date to cut on. A restated FY2023
figure has the same period end as the original — the two are separated only by
when they were **filed**. A filter that cuts on the period end therefore lets
every restatement through while looking like it is doing the right thing.

**Detection.** An `as_of` cutoff, and it cuts on the filing date:

- Every tool that selects by recency takes it, and every response repeats the
  cutoff that was applied. A cutoff that quietly did nothing would be
  indistinguishable from no cutoff at all — the same rule as P-19.
- A record whose filing date is unknown counts as *after* the cutoff. Letting it
  through would fill a promise about what was known on a date with a record
  whose date is not known.
- A filing named explicitly by accession number is still refused if it postdates
  the cutoff, with an error that says both dates. One exception would leave the
  caller holding a guarantee that is not true.
- `SEC_AS_OF` sets the cutoff for a whole process. Where a call and the
  environment disagree, the **earlier** wins: taking the later one would let a
  single call break a promise made for the session.
- One tool cannot honour it. SEC's frame endpoint reports no filing date per
  row, so `sec_edgar_compare_companies` refuses the call under a cutoff and
  names the tool that does honour it, rather than returning rows it cannot
  vouch for.

**Incident.** 16 Aug 2026, in this repository's own benchmark run. Five of fifty
answers were graded not-correct for exactly this reason: the dataset was
published on 16 May 2025 (Zenodo record 15428639), the run happened fifteen
months later, and phrases like "the last three years" had moved on. The tool arm
had found the right document by the wrong clock. Counting those five as correct
would have put the run at 92% rather than 82%; the lower number was published
and the cause was fixed in the tools rather than in the grading.

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
