# Info Desk

Live energy and sanctions research: collect official updates, preserve document versions, retrieve evidence and generate short cited AI answers for human review.

Two workspaces, never mixed. **Live research** uses actual EIA RSS, Federal Register API and OFAC HTTP responses; it needs the Python backend, so it is the default only when the page is served from localhost. **Recorded case & regression tests** replays dated captures and is the default on GitHub Pages, because that host cannot fetch, persist or run a model. `?mode=live` and `?mode=recorded` override the choice. Recorded output is never presented as live.

## Live workflow

1. Start the local app (setup below). Source checks run on opening the live workspace, then while the tab is visible and auto-check is enabled. The polling floor is 60 seconds, with longer provider Cache-Control/Retry-After respected. These are publication feeds, not tick streams.
2. Inspect source status, capture times and publication dates. First-seen documents are labelled new to this installation, not newly published. Errors preserve old evidence with a stale-source warning.
3. Filter the inbox or select documents. Ask a focused question using **Evidence retrieval only** or **AI brief with citations**. Retrieval uses SQLite FTS5/BM25 over the latest captured document versions.
4. Inspect the returned passages, exact citations and version diffs. AI output is a draft interpretation, not verified truth. No model call occurs on background source refresh.
5. Export the complete job/evidence JSON. Jobs persist their stages, result and errors; cancellation suppresses acceptance of in-flight results. Restarted unfinished jobs become `interrupted`, never falsely `completed`.

| Live connector | Coverage | Source contract |
|---|---|---|
| EIA Today in Energy | Publisher RSS summaries, not full articles | [Official RSS directory](https://www.eia.gov/tools/rssfeeds/) |
| Federal Register / OFAC | Recent notice metadata and available abstracts | [Official API](https://www.federalregister.gov/developers/documentation/api/v1) |
| OFAC Venezuela | Current general-license titles, not full license conditions | [Official program page](https://ofac.treasury.gov/sanctions-programs-and-country-information/venezuela-related-sanctions) |

The model receives retrieved text and a structured output schema. Unknown citations, quotes absent from the retrieved passage and numbers not found in the cited quotation reject the answer. No retrieved evidence means no model call. These checks establish traceability, **not semantic entailment or legal correctness**. Generation failures stay visible; they do not silently become heuristic answers.

If a statement names a year found only in the retrieved title of the same document version, the validator can attach that exact title as a second citation. The added reference is disclosed; a missing quantity or unrelated document cannot be used this way.

The live API is local and single-user. **GitHub Pages cannot host this backend or Ollama.** A recruiter-accessible live deployment still requires a hosted backend, authentication/access limits, persistent storage and a configured inference service. No public deployment or production readiness is claimed.

### Live API

- `GET /api/live/status`: connector health, collected documents and durable job history.
- `POST /api/live/sync`: queue source checks for `source_ids`.
- `POST /api/live/ask`: queue a question with `source_ids`, optional `document_ids` and `use_model`.
- `GET /api/live/jobs/{id}`: state, checkpoints, result and explicit error.
- `POST /api/live/jobs/{id}/cancel`: cancel acceptance of a running result; an in-flight HTTP request may finish.
- `GET /api/live/documents/{id}`: captured versions, hashes and the latest diff.

Requests accept only allowlisted source IDs, not arbitrary fetch URLs. One worker prevents uncontrolled concurrent model calls; excess jobs receive HTTP 409. Live captures are persisted separately from the recorded demo's draft/approval tables.

See [live verification](docs/live-verification-2026-09-09.md) for actual checks and remaining deployment limits.

## Recorded regression workflow

1. Start with OFAC, White House and AP selected. The initial result is a **recorded preview**.
2. Choose **Compare selected sources**. Remove OFAC to inspect the differing ranking scopes; choose White House alone to inspect single-source figures.
3. Search for a claim such as royalties. Select its row to see the exact matching excerpt, publisher link, capture date and analysed-text hash.
4. Open **Review & export**. Mark findings as read, add personal notes and download a cited Markdown memo or the evidence JSON. Reading a finding does not resolve it.
5. Open **Evaluations & trace**, or choose the injection/retry examples. Each case exposes its checks and SQLite snapshot. Test faults are explicitly SYNTHETIC.

**Recorded-case modes (separate from the live workspace above)**

| Mode | What actually happens | What does not happen |
|---|---|---|
| Static site / GitHub Pages | Selects among Python-generated results for all seven non-empty source combinations; filters claims, opens citations, exports a memo | No Python execution, live model call, database approval or fresh source fetch |
| Local FastAPI app | Runs the same Python analysis on selected recordings; persists runs and draft decisions in SQLite | No news publishing, arbitrary URL scraping or multi-user authentication |
| Optional local Ollama | Prioritises already-extracted, cited findings using a validated JSON permutation | Cannot generate new facts, remove findings, change release policy or write notes |

## Run locally

Python 3.10+ is required. Node is needed only for browser tests, not to serve the app.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m infodesk.harness
python -m infodesk.app
```

Open **http://127.0.0.1:8000/**. The local database defaults to `data/desk.sqlite3` and survives restarts. Override its path with `INFODESK_DB`. There is no automatic `.env` loader; set variables in your shell.

To preview only the public replay:

```powershell
python -m http.server 8000 --bind 127.0.0.1 --directory public
```

### Optional model assistance

Use an Ollama instance and a model you already have installed. No model is downloaded by this application. For example, if `qwen3:4b` is present:

```powershell
$env:OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
$env:OLLAMA_MODEL = "qwen3:4b"
python -m infodesk.app
```

In **Live research**, choose **AI brief with citations**. Live failures stay failed and retain retrieved passages. The CPU-model output is bounded to two short statements; the request deadline is an uncalibrated resource budget, not a speed guarantee.

In the separate **Recorded case**, select **Model-assisted finding order**, then compare. That older workflow only reorders findings and reports its own deterministic fallback explicitly.

The default model request timeout is an uncalibrated resource budget, not a latency target. A successful local call and a cold-start timeout are recorded in [verification](docs/verification-2026-09-09.md). Neither establishes model quality. The output contract follows [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs).

## Engineering decisions

| Component | Depends on | Produces / enforces |
|---|---|---|
| `sources.py`, `tools.py` | Allowlisted stored excerpts | Capture metadata and controlled reads; editorial additions excluded from evidence |
| `extract.py`, `claims.py` | Curated claim rules + analysed source text | Claim cells, named quantities and attribution; absence is not denial |
| `interpret.py` | Evidence-backed findings; optional Ollama | Deterministic memo and bounded finding ordering |
| `validate.py`, `policy.py` | Quantities, licenses, configured instruction-pattern checks | Release guard; no model-controlled database write |
| `store.py` | SQLite transactions and conditional status updates | Persistent run snapshots, deduplication by complete draft identity, atomic approval and note insertion |
| `workbench.py` | The same analysis service | Shared payload for local API and generated replay |
| `public/` | Replay JSON or local API | Responsive source selector, claim inspector, review queue, exports and visible evaluations |

**Why this scope:** the live workspace demonstrates retrieval-augmented generation with lexical search, versioned evidence and bounded model output. The recorded workspace remains a fixed-rule comparison, not RAG or a general extraction benchmark. Neither independently verifies the publisher's claims.

The local API binds to loopback, rejects unexpected Host headers and cross-origin writes, and accepts only registered source IDs. It is **single-user**. Do not expose it publicly without authentication, per-user authorization, request limits and a production storage design.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Local API and configured-model availability |
| `POST /api/analyses` | `{"source_ids":["ofac","white-house","ap"],"use_model":false}` |
| `GET /api/runs` | Persisted run index |
| `GET /api/runs/{id}` | Original run snapshot, not silently rewritten after a decision |
| `POST /api/drafts/{id}/decide` | `{"decision":"approve"}` or `{"decision":"reject"}` |
| `GET /api/db` | Current local ledger state |
| `GET /api/harness` | Isolated regression evaluation, not mutations to your ledger |

All supplied public-source cases currently produce `hold` or `verify_first`; the UI correctly prevents approval. Positive approval, rejection, replay and concurrency paths are exercised with clearly labelled SYNTHETIC tests. Exporting a memo never approves a note.

## Tests and evidence

```powershell
python -m pytest
python -m infodesk.harness
npm ci
npx playwright install chromium
npm run test:browser
```

The browser suite starts its own local API with an isolated temporary SQLite database, and a static server under `/info-desk/` to check GitHub Pages relative paths. It exercises every source combination, search/filtering, excerpt navigation, review/export, mobile layout, keyboard tabs, local rejection and outage handling. Screenshots go to `test-results/`.

The harness generates `public/case.json`, `public/harness.json` and `public/workbench.json`. Both CI and the Pages workflow run Python and browser checks before success/deployment. Models are not used by these workflows.

**Evaluation limit:** `baseline_action` calls the same rule implementation. Matching it is a regression consistency check, **not an independent baseline** and not evidence that an LLM is more accurate. The six curated harness cases do not measure unseen-news accuracy or comprehensive injection resistance.

## Source integrity and limits

- Inputs are the existing 8 September 2026 excerpts under `recordings/`. They are not a new live fetch or a complete archive of the publisher pages.
- The original OFAC and White House files included final editorial paragraphs. The originals remain unchanged for audit; `sources.py` removes those paragraphs and capture headers before analysis. The UI no longer displays editorial absence notes as publisher denials.
- SHA-256 identifies the exact analysed text. It does not authenticate a publisher or prove a factual claim.
- AP coverage is selected excerpts, not the full article. Missing information may exist elsewhere in the original reporting. Repetition or attribution to the same announcement is not independent corroboration.
- The two NABEP ranking phrases use different comparison groups. They require scope review, not an automatic assertion that one is false.
- License titles alone cannot establish legal authorization. This is not sanctions screening or legal advice.
- The instruction-pattern detector is intentionally limited. It is not a complete prompt-injection defence. The stronger boundary is that model output cannot change facts, policy, SQL or approval.
- Live ingestion is limited to the three documented official connectors. No Telegram/X publishing, arbitrary uploads, agent-controlled writes, trained classifier, production authentication or Docker deployment is claimed.

See [verification and remaining risks](docs/verification-2026-09-09.md).
