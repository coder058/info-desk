"""Manual local-model profiling on captured evidence; never a live-source claim."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter
from urllib.parse import urlsplit

from .live_service import model_answer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    # GUESS: UNCALIBRATED GUESS — short exploratory run, not statistical confidence.
    parser.add_argument('--repeats', type=int, default=2)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error('repeats must be positive')
    url = urlsplit(os.environ.get('OLLAMA_URL', ''))
    if url.scheme != 'http' or url.hostname not in {'127.0.0.1', 'localhost', '::1'} or url.username:
        parser.error('This profiling tool only sends captured evidence to a configured loopback Ollama instance')
    raw = args.capture.read_bytes()
    job = json.loads(raw)
    question, passages = job['request']['question'], job['result']['passages']
    if not question.strip() or not passages:
        parser.error('The capture needs a question and retrieved evidence')
    report = {'scope': 'Repeated local generation on a captured question and evidence; no fresh source fetch or general accuracy claim.',
              'capture_sha256': hashlib.sha256(raw).hexdigest(), 'model': os.environ.get('OLLAMA_MODEL'),
              'evidence_sha256': hashlib.sha256(json.dumps({'question':question,'passages':passages}, sort_keys=True).encode()).hexdigest(),
              'implementation_sha256': hashlib.sha256(Path(__file__).with_name('live_service.py').read_bytes()).hexdigest(),
              'question': question, 'runs': []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(args.repeats):
        start = perf_counter()
        try:
            answer = model_answer(question, passages)
            row = {'status': 'validated', 'answer': answer}
        except Exception as exc:
            row = {'status': 'failed', 'error': f'{type(exc).__name__}: {exc}'}
        # SOURCE: measured wall-clock seconds converted to milliseconds.
        row['wall_ms'] = (perf_counter() - start) * 1000
        report['runs'].append(row)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
        print(json.dumps(row), flush=True)


if __name__ == '__main__':
    main()
