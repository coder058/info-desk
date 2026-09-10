"""SYNTHETIC timing envelopes test units, not model performance."""
import pytest
import json
import httpx
from infodesk import live_service
from infodesk.live_service import provider_metrics, citation_options, expand_references, validate_answer


def test_SYNTHETIC_nanoseconds_are_converted_without_inventing_missing_fields():
    # SOURCE: 1 millisecond = 1,000,000 nanoseconds.
    assert provider_metrics({'load_duration': 1_000_000, 'eval_count': 2}) == {'load_ms': 1, 'eval_count': 2}
    assert provider_metrics({}) == {}


def test_SYNTHETIC_invalid_timings_and_token_counts_are_omitted():
    assert provider_metrics({'load_duration': -1, 'eval_duration': float('nan'),
                             'total_duration': True, 'eval_count': -1,
                             'prompt_eval_count': 1.5}) == {}


def test_SYNTHETIC_compact_references_resolve_only_to_supplied_exact_quotes():
    passage = {'chunk_id': 'SYNTHETIC:1', 'source_id': 'SYNTHETIC', 'title': 'SYNTHETIC report',
               'coverage': 'SYNTHETIC test fixture', 'body': 'SYNTHETIC output reached 12 units.'}
    context, refs = citation_options([passage])
    key = context[0]['quotes'][0]['id']
    raw = {'statements': [{'text': 'Output reached 12 units.', 'citations': [key]}], 'insufficient_evidence': False}
    result = validate_answer(expand_references(raw, refs), [passage])
    assert result['statements'][0]['citations'][0]['quote'] == passage['body']
    raw['statements'][0]['text'] = 'Output reached 99 units.'
    with pytest.raises(ValueError, match='numeric'):
        validate_answer(expand_references(raw, refs), [passage])
    raw['statements'][0]['citations'] = ['SYNTHETIC:invented']
    with pytest.raises(ValueError, match='unknown evidence'):
        expand_references(raw, refs)


def test_SYNTHETIC_quote_splitting_preserves_original_spacing_and_character_bound():
    # SOURCE: text intentionally exceeds the existing 300-character citation bound.
    body = ('SYNTHETIC   repeated words.\n' * 30) + ('x' * 350)
    passage = {'chunk_id': 'SYNTHETIC:2', 'source_id': 'SYNTHETIC', 'title': 'SYNTHETIC long text',
               'coverage': 'SYNTHETIC test fixture', 'body': body}
    context, refs = citation_options([passage])
    assert len(context[0]['quotes']) > 1
    assert len(refs) == len(context[0]['quotes'])
    assert all(0 < len(item['quote']) <= 300 and item['quote'] in body for item in refs.values())


def test_SYNTHETIC_long_excerpt_prefers_complete_sentences():
    first = 'SYNTHETIC output reached 12 units.'
    body = first + ' ' + ('More SYNTHETIC detail ' * 20)
    context, _ = citation_options([{'chunk_id':'SYNTHETIC:3','source_id':'SYNTHETIC',
        'title':'SYNTHETIC report','coverage':'SYNTHETIC fixture','body':body}])
    assert context[0]['quotes'][0]['text'] == first


def test_SYNTHETIC_country_initials_are_not_a_sentence_boundary():
    first = 'SYNTHETIC output reached 12 units.'
    body = first + ' The U.S. ' + ('SYNTHETIC future detail ' * 20)
    context, _ = citation_options([{'chunk_id':'SYNTHETIC:us','source_id':'SYNTHETIC',
        'title':'SYNTHETIC report','coverage':'SYNTHETIC fixture','body':body}])
    assert context[0]['quotes'][0]['text'] == first


def test_SYNTHETIC_real_model_request_contract_expands_ids_and_checks_numbers(monkeypatch):
    monkeypatch.setenv('OLLAMA_URL', 'http://127.0.0.1:11434/api/generate')
    monkeypatch.setenv('OLLAMA_MODEL', 'SYNTHETIC-test-model')
    passage = {'chunk_id':'SYNTHETIC:4','source_id':'SYNTHETIC','title':'SYNTHETIC report',
               'coverage':'SYNTHETIC fixture','body':'SYNTHETIC output reached 12 units.'}
    wrong_number = False
    def respond(request):
        payload = json.loads(request.content)
        assert payload['stream'] is False and payload['think'] is False
        assert payload['format']['$defs']['ReferenceStatement']['properties']['citations']['items']['type'] == 'string'
        answer = {'statements':[{'text':f'Output reached {99 if wrong_number else 12} units.',
                                'citations':['SYNTHETIC:4/q0']}], 'insufficient_evidence':False}
        # SOURCE: synthetic envelope uses Ollama's documented response shape.
        return httpx.Response(200, json={'done':True,'response':json.dumps(answer),'eval_count':12,'eval_duration':1_000_000})
    original = httpx.Client
    monkeypatch.setattr(live_service.httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs))
    answer = live_service.model_answer('SYNTHETIC question', [passage])
    assert answer['statements'][0]['citations'][0]['quote'] == passage['body']
    assert answer['provider_metrics']['eval_ms'] == 1
    wrong_number = True
    with pytest.raises(ValueError, match='numeric'):
        live_service.model_answer('SYNTHETIC question', [passage])
