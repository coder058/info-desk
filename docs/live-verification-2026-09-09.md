# Live desk — verification and limits

## Implemented flow

Live official HTTP sources → contract validation → document versions → SQLite FTS5/BM25 retrieval → optional structured model answer → citation/numeric checks → human review/export.

The old fixed-source case remains a separate regression lab, loaded only when opened. It is not a fallback for live failures.

## Observed source checks

On 9 September 2026, a real integration run fetched:

- EIA Today in Energy RSS: HTTP 200, **14 documents**.
- Federal Register OFAC notice API: HTTP 200, **10 documents**.
- OFAC Venezuela license page: HTTP 200, **1 versioned license-list document**.

These are **25 captured source records**, not 25 independently verified news stories. Coverage is RSS summaries, notice abstracts/metadata and license titles, not complete articles or full legal analysis. Publication time and fetch time are distinct. No prices, news records or results were invented for the live test.

## Automated checks

- `python -m pytest`: **59 passed** after adding the live pipeline and the same-version year-context regression.
- `python -m ruff check src tests`: passed.
- Browser regression suite covers the recorded workflow at desktop/tablet/mobile, real local recorded-case execution, and synthetic live UI workflows at desktop/mobile. Live UI fixtures are explicitly SYNTHETIC, with no external model calls in CI.
- Live backend tests cover append-only revisions (including reverting to previous text), latest-version retrieval, document/source scoping, query-operator handling, allowlisted URLs, malformed RSS/entity rejection, Retry-After/cooldown, ETag/304, source failure visibility, invalid model citations/numbers, abstention without a model call, failed inference retaining evidence, backpressure, cancellation, restart interruption and document diffs.

## Actual model testing

An initial real Qwen3 4B answer over six retrieved passages completed in **75323.19 ms** with **408 reported output tokens**. It passed quote/numeric checks but was too verbose for the intended demo. This is a single local measurement, not a benchmark or guarantee.

The response contract was then bounded to two short statements, with bounded quotes, and the question can be scoped to a selected document. The optional manual check `node e2e/live-real.cjs` exercises current source ingestion, a real model answer, citation navigation and mobile layout. Its actual result is saved to `test-results/live-real-job.json`, with screenshots alongside it. These outputs are ignored by Git; they are not synthetic fixture results or an automated general-accuracy score.

The first bounded live answer failed validation: a statement said “2026” while its paragraph citation said “the year”; the year was in a separate title passage. The validator was not disabled. It can now attach the exact retrieved title as an additional citation, only for a missing four-digit year and only from the **same document and captured version**. The UI and exported answer disclose that addition. Missing quantities and cross-version evidence still fail validation. A synthetic regression checks this boundary.

The final real-browser run completed successfully: live source checks (EIA HTTP 304, Federal Register and OFAC HTTP 200), a two-statement AI answer over two passages, opening its citations, and mobile layout. Model duration was **79520.69 ms**, with **236 reported output tokens**. The required same-version title citation was attached and disclosed. This did **not** establish a latency improvement; local CPU inference remains too slow for a polished public demo. The model job is asynchronous and the interface remains usable while it runs.

Final browser regression run: **8 workflow groups passed** (three recorded responsive sizes, local rejection, two failure paths, and two synthetic live responsive workflows). The manual real-source/model browser run also passed. Raw final job evidence is in `test-results/live-real-job.json`.

## Remaining limits

- Local CPU inference can be slow or time out. Model generation is an asynchronous job, not an instant response; progress remains visible. Cancellation stops acceptance of the answer, not necessarily an already-running provider request.
- Matching a quote and its numbers establishes provenance, not semantic entailment or completeness. The model can still misinterpret a source. Every answer remains a reviewable draft.
- Lexical retrieval can miss synonyms, cross-language matches or relevant older material. No embedding model, universal web search or evaluation of retrieval recall is claimed.
- Sources are polled, not pushed. A polling floor and provider cache/retry headers bound requests; there is no zero-latency news claim. Background checks run while the browser tab is open, not as a separately deployed always-on scheduler.
- Only known official connectors are fetched. There is no arbitrary URL tool, social posting, broker action or automatic news publication.
- Jobs and evidence persist locally in SQLite. Multi-user authentication, access quotas, a hosted backend and remote inference are still required for a publicly usable FDE demo. GitHub Pages alone cannot provide that runtime.
- Local tests do not establish a successful GitHub Actions run or public deployment. Neither is claimed here.
