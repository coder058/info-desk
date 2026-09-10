"""Reproducible retrieval evaluation over dated excerpts; no network/model calls."""
import argparse
import hashlib
import json
import platform
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from .live_store import LiveStore
from .sources import ROOT, load_sources


def score_passages(passages, expected):
    """Evidence units are (source, exact quote), not mere document ID matches."""
    hits = [[i for i, passage in enumerate(passages)
             if passage['source_id'] == unit['source'] and unit['quote'] in passage['body']]
            for unit in expected]
    # SOURCE: recall is found evidence units / annotated units; reciprocal rank is 1 / rank.
    ranks = [i + 1 for indices in hits for i in indices]
    return {
        'evidence_recall': sum(bool(indices) for indices in hits) / len(expected) if expected else None,
        'first_relevant_rank': min(ranks) if ranks else None,
        'reciprocal_rank': 1 / min(ranks) if ranks else 0,
        'top1_relevant': 1 in ranks if expected else None,
    }


def evaluate(dataset_path, repeats):
    if repeats < 1:
        raise ValueError('repeats must be positive')
    raw = dataset_path.read_bytes()
    dataset = json.loads(raw)
    sources = load_sources()
    store = LiveStore()
    rows = []
    try:
        for source_id, source in sources.items():
            store.ingest(source_id, {'url': source['url'], 'title': source['title'],
                'body': source['body'], 'coverage': source['capture_note'], 'published_at': None})
        seen = set()
        for case in dataset['cases']:
            if case['id'] in seen:
                raise ValueError('Duplicate evaluation case ID')
            seen.add(case['id'])
            if not case['sources'] or set(case['sources']) - sources.keys():
                raise ValueError(f"Unknown or empty source selection: {case['id']}")
            for unit in case['expected']:
                if (not unit['quote'] or unit['source'] not in case['sources']
                        or unit['quote'] not in sources[unit['source']]['body']):
                    raise ValueError(f"Annotation is not present in selected evidence: {case['id']}")
            if not case['expected'] and not case.get('reason'):
                raise ValueError('Unanswerable cases require an annotation rationale')
            samples = []
            for _ in range(repeats):
                start = perf_counter()
                passages = store.retrieve(case['question'], case['sources'])
                # SOURCE: milliseconds converted from perf_counter seconds.
                samples.append((perf_counter() - start) * 1000)
            rows.append({**case, **score_passages(passages, case['expected']),
                'retrieved_count': len(passages), 'retrieval_ms_samples': samples,
                'retrieved': [{'source': p['source_id'], 'chunk_id': p['chunk_id'], 'body': p['body']}
                              for p in passages]})
    finally:
        store.close()
    answerable = [r for r in rows if r['expected']]
    negative = [r for r in rows if not r['expected']]
    mean = lambda values: sum(values) / len(values) if values else None
    # SOURCE: nearest-rank empirical quantile. These are local retrieval timings, not end-to-end AI latency.
    import math
    times = sorted(t for r in rows for t in r['retrieval_ms_samples'])
    quantile = lambda p: times[max(0, math.ceil(p * len(times)) - 1)] if times else None
    return {
        'scope': dataset['description'], 'evaluated_at': datetime.now(timezone.utc).isoformat(),
        'dataset_sha256': hashlib.sha256(raw).hexdigest(),
        'corpus_sha256': {sid: hashlib.sha256(s['body'].encode()).hexdigest() for sid, s in sources.items()},
        'runtime': {'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version,
                    'platform': platform.platform()},
        'summary': {'cases': len(rows), 'answerable': len(answerable), 'unanswerable': len(negative),
            'mean_evidence_recall_at_returned_limit': mean([r['evidence_recall'] for r in answerable]),
            'top1_hit_rate': mean([r['top1_relevant'] for r in answerable]),
            'mean_reciprocal_rank': mean([r['reciprocal_rank'] for r in answerable]),
            'unanswerable_with_retrieved_context': sum(bool(r['retrieved_count']) for r in negative),
            'retrieval_ms_p50': quantile(.5), 'retrieval_ms_p95': quantile(.95),
            'repetitions_per_case': repeats},
        'limits': ['Development set, not held out; questions are human-authored, not independent user traffic.',
            'Corpus is the supplied dated excerpts, not current live connector coverage or independently verified facts.',
            'No answer generation or semantic correctness is scored. Context returned for an unanswerable question is not necessarily a wrong answer.',
            'No retrieval confidence or safe abstention can be inferred from non-empty search results.',
            'Local in-memory retrieval timing excludes network, persistence I/O and model inference.'],
        'cases': rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'evals/retrieval-cases.json')
    # GUESS: UNCALIBRATED GUESS — repeat count for a cheap local timing sample, not statistical power.
    parser.add_argument('--repeats', type=int, default=20)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = evaluate(args.dataset, args.repeats)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(result['summary'], indent=2))


if __name__ == '__main__':
    main()
