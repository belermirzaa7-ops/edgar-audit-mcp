# Publishing

Three channels, none of them required to use this server — a clone and
`uv sync` works — but each changes how easily someone else can reach it.

Everything below was measured on 16 Aug 2026 against the registries' own
endpoints and documentation. Where something could **not** be checked from the
build environment, it says so instead of implying it was.

---

## 0. The name — decided 19 Aug 2026

This server is published as **`edgar-audit-mcp`**. It was called
`sec-edgar-mcp` until 19 August 2026, and that name could not be kept.

**Why it had to change.** `sec-edgar-mcp` is taken on PyPI. Measured 16 Aug 2026:

```
$ pip index versions sec-edgar-mcp
sec-edgar-mcp (1.0.8)
Available versions: 1.0.8, 1.0.7, 1.0.6, 1.0.5, 1.0.4, 1.0.3, 1.0.2, 1.0.1, 0.1.0
```

It belongs to `stefanoamorelli/sec-edgar-mcp`, a different SEC EDGAR MCP server,
AGPL-3.0, and the most visible project in this niche — 350 GitHub stars when
re-checked on 19 Aug 2026, up from 310 three days earlier. The collision was not
with an abandoned placeholder, and it was not going to age out.

**This project was written without reading that one.** The collision is on the
name only. Every design decision here is recorded in `CLAUDE.md` with the live
measurement that produced it, and the competitor scan that first surfaced the
overlap was run on 16 Aug 2026 — after most of this architecture already existed.

**Why this name.** The tools are not the differentiator; every server in this
niche reads EDGAR. What is different is that each figure carries the filing, the
tag and the filing date it came from, and that the traps which return a
plausible wrong number are handled rather than passed through. `audit` says that
in one word, and it is the word this server's buyers already use.

**Checked free before adopting** (19 Aug 2026):

| Registry | `edgar-audit-mcp` |
|---|---|
| PyPI | free — `/pypi/edgar-audit-mcp/json` returns 404 |
| npm | free — `registry.npmjs.org` returns 404 |
| GitHub repository name | free — `in:name` search returns 0 repositories |
| MCP registry | free by construction — namespaced under the GitHub account |

**What did NOT change, and why.** The tool names keep the `sec_edgar_` prefix
(`sec_edgar_get_concept_series`, …). That prefix names the *data source*, not
the product, and it is what stops a model from calling another server's
`get_company_profile` when several are loaded at once (KK-5). Renaming it would
break every client for no gain in accuracy — these tools really do read SEC
EDGAR.

The Python import package stays `edgar_mcp`. Distribution name and import name
are allowed to differ, the import name is invisible from outside, and 199 fault
injections are keyed to paths under `src/edgar_mcp/`. Churning those paths for a
cosmetic symmetry would put the measurement machinery at risk to change
something no user ever sees.

**Four names, and they are independent** — worth keeping straight, because only
one of them was a hard block:

| What | Collided? | Cost of changing |
|---|---|---|
| PyPI distribution name (`pyproject.toml` → `name`) | **Yes, hard block** | One line, nothing published yet |
| Console script name (`[project.scripts]`) | Yes, soft: two packages installing the same command means whichever was installed last wins, silently | One line + README/Docker references |
| Registry server name (`io.github.belermirzaa7-ops/...`) | **No** — namespaced by GitHub account | — |
| GitHub repository name | No technical collision; a discovery and perception problem | GitHub redirects old URLs, but every link already sent out changes meaning |

One test enforces consistency of the *registry* identity across the three files
that carry it (`test_kayit_defteri_kimligi_uc_dosyada_da_ayni`), and one fault
injection proves that test fails when the identity drifts.

---

## 1. PyPI

The package builds today. Measured, not assumed:

```
$ python -m build
Successfully built edgar_audit_mcp-0.1.0.tar.gz and edgar_audit_mcp-0.1.0-py3-none-any.whl
$ python -m twine check dist/*
Checking dist/edgar_audit_mcp-0.1.0-py3-none-any.whl: PASSED
Checking dist/edgar_audit_mcp-0.1.0.tar.gz: PASSED
```

```bash
# 0) is the name free? "No matching distribution found" means yes.
pip index versions <candidate-name>

# 1) clean build
rm -rf dist build
python -m pip install --upgrade build twine
python -m build

# 2) check the metadata renders (this is what shows on the project page)
python -m twine check dist/*

# 3) TestPyPI first: upload, install from it, run the server once
python -m twine upload --repository testpypi dist/*
pipx run --index-url https://test.pypi.org/simple/ --spec <name> <script-name>

# 4) the real thing
python -m twine upload dist/*
```

Notes worth having before step 4:

- **A version can never be reused on PyPI.** Bump `version` in `pyproject.toml`
  for every upload; a failed upload still burns the number.
- **`SEC_USER_AGENT` is required at startup**, so a smoke test of the installed
  command must set it:
  `SEC_USER_AGENT="Your Name you@example.com" <script-name>` should start and
  wait on stdio rather than exit.
- Use an API token (`__token__` as the username), scoped to this project once it
  exists.
- The registry's ownership check reads the **README**, which becomes the PyPI
  description — see below. It is already in place; do not remove it.

## 2. MCP registry

The registry stores metadata only, not artifacts: a package has to exist on
PyPI, npm, or a container registry *before* the server can be published. Steps
below are quoted from the registry's own quickstart and package-type pages as
they stood on 16 Aug 2026.

**Ownership verification.** The registry checks that the artifact really belongs
to whoever is publishing, and the check differs per package type. Both markers
this repository needs are already in the tree:

- **PyPI** — the string `mcp-name: <server name>` must appear in the package
  README (an HTML comment is accepted). It is the first line of `README.md`.
- **OCI** — the image must carry
  `LABEL io.modelcontextprotocol.server.name="<server name>"`. It is in the
  `Dockerfile`.

Both must equal the `name` field in `server.json`. A test pins all three
together, because a rename that updates two of the three fails at publish time,
which is the most expensive place to find out.

```bash
# 1) install the publisher CLI (macOS/Linux)
curl -L "https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_$(uname -s | tr '[:upper:]' '[:lower:]')_$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/').tar.gz" | tar xz mcp-publisher && sudo mv mcp-publisher /usr/local/bin/
mcp-publisher --help

# 2) authenticate. GitHub device flow; the namespace must match the account.
mcp-publisher login github

# 3) publish the file in this repository
mcp-publisher publish

# 4) confirm it is listed
curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.belermirzaa7-ops/edgar-audit-mcp"
```

`server.json` in the repository root declares the OCI package, because that name
is namespaced by the GitHub account and therefore does not collide. **A `pypi`
entry has to be added once `edgar-audit-mcp` is actually uploaded** — the name
is settled, but an entry pointing at a distribution that does not exist yet
would be worse than having no entry at all.

**Not verified here, and it matters:** `server.json` was written against the
documented required fields and the published example, but it was **not**
machine-validated against the schema — the build environment's proxy refuses
`static.modelcontextprotocol.io` (`Tunnel connection failed: 403 Forbidden`), so
`check-jsonschema` could not fetch it. Run this once from a normal network
before publishing:

```bash
pipx run check-jsonschema --schemafile \
  https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json \
  server.json
```

`mcp-publisher publish` also validates server-side, so a bad file is rejected
rather than accepted wrongly — but a local check costs one command and gives a
readable error instead of a rejection.

The registry is in **preview** and its own documentation warns of breaking
changes and data resets before general availability. The schema URL is dated
(`2025-12-11`); when it moves, `server.json` moves with it.

## 3. Container image

`Dockerfile` builds a working image and CI already queries a running container
from outside, so publishing is a tag and a push. GHCR is the natural target: it
shares the GitHub account that already namespaces the registry entry, and it is
one of the registries the MCP registry accepts.

```bash
docker build -t ghcr.io/belermirzaa7-ops/edgar-audit-mcp:0.1.0 .
docker run --env-file .env -p 8000:8000 ghcr.io/belermirzaa7-ops/edgar-audit-mcp:0.1.0
docker push ghcr.io/belermirzaa7-ops/edgar-audit-mcp:0.1.0
```

The image tag in `server.json` must match what was actually pushed, including
the version.

## Order

1. **Name decision** — blocks everything else, costs a minute now and grows.
2. **Container image** — the only artifact that can be published under a name
   nobody else holds, and it satisfies the registry's package requirement.
3. **Registry** — discovery, and the reason the two ownership markers exist.
4. **PyPI** — largest reach, but only after the name is settled; then add the
   `pypi` entry to `server.json` and publish a new version of the registry
   entry.
