# Retrieval evaluation

Run from the repository root:

```sh
python -m infodesk.evaluate_retrieval --output test-results/retrieval-evaluation.json
```

This exercises the actual SQLite FTS5/BM25 retriever using an isolated in-memory database. It makes no network requests or model calls and never modifies the live database. CI saves the full result as an artifact.

## Dataset and scoring

The development set contains 17 human-authored questions: 13 answerable and 4 unanswerable **from the supplied excerpts**. Three answerable questions are Spanish or French formulations over English documents. The corpus reuses the project's dated `PUBLIC_RECORDING` excerpts, excluding editorial annotations through `load_sources()`. These are not newly collected news or independently verified claims.

Each positive annotation identifies both a source and an exact evidence quotation. The runner rejects missing annotations, invalid source scopes and duplicate case IDs. It records corpus/dataset hashes, returned passages, runtime versions and every timing sample.

- Evidence recall: fraction of annotated evidence units returned, averaged across answerable questions.
- Top-one hit rate and reciprocal rank: whether and where the first annotated quote appears.
- Unanswerable with retrieved context: a diagnostic, **not** model hallucination or abstention accuracy. Relevant words can occur without an answer.
- Timing: nearest-rank p50/p95 of local retrieval calls. Excludes ingestion, network, disk persistence and model generation. The repeated queries use warm in-memory state.

## Observed baseline — 10 September 2026

`retrieval-baseline-2026-09-10.json` records the actual run. Ten of thirteen answerable questions return their expected evidence at rank one; the three cross-language questions miss. Three of four unanswerable questions still return passages, exposing why non-empty retrieval cannot establish answerability. Do not advertise this as “77% AI accuracy”.

The 20 repetitions per question are an uncalibrated timing sample size, not a statistical-power calculation. The corpus is tiny and the questions are a development set, not held out. Improving against these cases alone risks overfitting. Live-feed retrieval, fresh questions and generated-answer quality still require separate evaluation.
