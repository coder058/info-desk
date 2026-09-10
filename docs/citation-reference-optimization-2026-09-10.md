# Selecting citations instead of generating them

## Problem and decision

The local model spent output tokens copying quotations that Python already had. The previous implementation then checked those copies against the retrieved passages. The new model-only schema asks for short statements and reference IDs; Python resolves each ID to an exact excerpt and runs the same citation and numeric validation on the expanded answer.

The public answer format is unchanged: every citation contains its original `chunk_id` and quotation. Unknown IDs fail. A selected quotation cannot be changed by the model. This reduces copying; it does **not** prove that a generated statement correctly interprets that quotation.

Excerpts respect the existing citation length limit and prefer punctuation boundaries, avoiding initials such as `U.S.` as sentence endings. Long sentences may still need a bounded fragment. Every fragment remains a contiguous substring of the original passage. The original captured text is not rewritten.

## Observations, not a general benchmark

One captured EIA LNG question was used for exploratory before/after measurements with the already-installed `qwen3:4b` model. These were local runs on this machine, not a controlled hardware benchmark, held-out question set or public API latency measurement.

| Observed configuration | Client wall times | Generated tokens |
|---|---|---|
| Previous full-quotation schema, two runs | 41.7 s; 30.6 s | 236; 236 |
| Initial reference-ID schema, two runs | 21.6 s; 10.4 s | 131; 119 |
| Final sentence-boundary implementation, real browser workflow | 15.2 s | 132 |

Loading and cache state differ. In the first previous-schema run, Ollama reported about 6.3 seconds loading, 11.2 processing the prompt and 23.7 generating tokens. The following run reused most of the prompt but still spent about 29.9 seconds generating tokens. The final browser run reported about 2.1 seconds processing the prompt and 12.7 generating tokens. These provider stages need not sum exactly to client wall time.

Every listed run passed citation/numeric validation. That is a structural/provenance result, not an independent semantic-quality score. No “N times faster” or p95 service claim is inferred from these samples. Prompt tokens did not decrease; the intended reduction is generated quotation text.

## Verification

- 73 Python tests passed on 10 September 2026, including reference expansion, unknown IDs, incorrect numbers, exact substring preservation, bounded excerpts and initials at sentence boundaries.
- Eight synthetic/recorded browser workflow groups passed. They check UI and failure behavior, not live model accuracy.
- A separate real browser run fetched/checked EIA, Federal Register and OFAC, generated the answer, opened its citations and verified mobile layout. EIA returned 304 on the final check; the other connectors returned 200. No source records were fabricated.
- Local raw observations remain in ignored `test-results/model-profile-*.json` and `test-results/live-real-job.json`. The manual profiler saves available provider stages separately from wall time and records hashes for future comparisons. No local paths or internal application answers are exported to the portfolio manifest.

To reproduce on an installed, configured local model:

```sh
python -m infodesk.profile_model --capture test-results/live-real-job.json --output test-results/model-profile.json --repeats 2
```

The capture must exist from a real manual run; the command does not invent one, fetch fresh news or download a model. Its loopback-only check prevents this profiling command from sending captured evidence to an external model endpoint.

## Remaining limits

Public GitHub Pages still serves the recorded case, not this Python/model runtime. Live sources cover summaries, abstracts and license titles. Retrieval still has the cross-language misses documented in `evals/README.md`. Citation matching does not prove semantic entailment, and lower token count does not establish equal answer quality across other questions.

Provider metric definitions: [Ollama Generate API](https://docs.ollama.com/api/generate).
