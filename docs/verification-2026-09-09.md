# Info Desk — local verification, 9 September 2026

## Defects corrected

- FastAPI sync handlers previously used a SQLite connection created in a different thread. The store now serializes access; the app creates/closes it in lifespan and persists to a file by default.
- Approval is now a conditional SQL update and note/audit insertion in one transaction. Concurrent connections cannot both approve; rejection cannot overwrite approval. Deduplication includes case, action, headline, body hash and interpreter, not only body text.
- GET preview no longer writes to the user's ledger. Individual run artifacts are retained separately from current draft status.
- Original input files mixed capture/editorial notes with publisher excerpts. Originals were preserved, while analysed text excludes those notes. Absent claims are no longer presented as OFAC denials. The live OFAC page was inspected to check this distinction: https://ofac.treasury.gov/sanctions-programs-and-country-information/venezuela-related-sanctions . This was not a fresh capture replacing the old dataset.
- Model code formerly received a generic prompt without evidence and could propose arbitrary body/action fields. Its role is now limited to ranking cited findings, with complete-ID validation and deterministic fallback.
- The UI now exposes source selection, all source-subset results, claim filtering, source excerpts, verification queue, notes, exports, evaluation assertions and run traces.

## Executed checks

- Python 3.14.3; `python -m pytest`: **33 passed** at the initial full verification. Includes synthetic malformed model output, timeouts, concurrent approval, persistence across app restarts, invalid input and local API restrictions.
- `python -m ruff check src tests`: passed.
- `python -m infodesk.harness`: all **6 curated cases** passed. Synthetic injection/retry faults are labelled. This is a regression set, not an accuracy study.
- Chromium browser workflow passed at **1440×1000, 820×1000 and 390×844**. All seven source combinations, filters, source inspector, review exports, keyboard tabs and no document-level horizontal overflow were exercised.
- Additional browser checks passed: local API execution and durable rejection; a synthetic API 503 preserves the previous result and allows retry; a missing replay file produces a visible error.
- Desktop and mobile screenshots inspected visually. Browser results and screenshots are local under `test-results/`, ignored by Git.
- `npm install --ignore-scripts`: no reported vulnerabilities in the browser-test dependency tree at this check.

## Actual optional model check

The existing local Ollama installation had `qwen3:4b`; no model was installed or downloaded for this task.

- First full-source request reached the configured timeout. Measured analysis duration: **30081.37 ms**, `model_status=fallback`, interpreter `heuristic`, release action `verify_first`.
- After the model had loaded, the same source selection completed: **11247.66 ms**, **33 reported output tokens**, `model_status=completed`, interpreter `ollama-ranked / deterministic facts`, action still `verify_first`.
- These are individual local measurements, including analysis/model work, not browser response times, percentiles or speed guarantees. Model ranking quality was not scored against editorial ground truth. A warm success does not remove the observed cold-start risk.

## Not established

- No independent AI benchmark, unseen-document generalization, exhaustive security review or extraction accuracy score.
- No production multi-user deployment, authentication or external publishing.
- GitHub Actions execution and public publication are separate from the local checks above; local workflow edits alone do not establish a successful GitHub run.
- Local SQLite is appropriate for this bounded single-user demonstration, not a claim of distributed-system reliability.
