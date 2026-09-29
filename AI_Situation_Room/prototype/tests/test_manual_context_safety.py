import copy
import json
import unittest
from prototype.manual_rag.context import prepare_manual_context
from prototype.manual_rag.corpus import Corpus
from prototype.manual_rag.retrieval import ManualSearch


class ManualContextSafetyTests(unittest.TestCase):
    def setUp(self):
        self.search = ManualSearch(mode='lexical')
        self.addCleanup(self.search.close)
        self.assignment = dict(role='sar', instruction='현재 상황 검토')

    def result(self, session=None, assumptions='', evidence=None):
        return prepare_manual_context(dict(prompt='이 조건으로 검토해줘', assumptions=assumptions),
            session or {}, self.assignment, self.search, evidence=evidence)

    def assert_hazards(self, result):
        ids = {i['chunk_id'] for i in result['items']}
        self.assertIn('sar-draft:external-support:v1', ids)
        self.assertIn('sar-draft:water-recovery:v1', ids)

    def test_generic_followup_uses_current_facts_without_mutating_them(self):
        session = dict(facts=dict(notes='기관실 화재와 익수자 발생'))
        before = copy.deepcopy(session)
        self.assert_hazards(self.result(session))
        self.assertEqual(session, before)

    def test_simulation_assumptions_reach_both_search_methods(self):
        queries = []
        class Index:
            def search(self, query, limit): queries.append(query); return []
            def close(self): pass
        self.search._index = Index()
        self.assert_hazards(self.result(assumptions='기관실 화재와 익수자 발생'))
        self.assertTrue(any('기관실 화재' in q and '가정' in q for q in queries))

    def test_linkone_received_projection_is_searchable(self):
        evidence = [dict(id='linkone:one', content=json.dumps(dict(
            room=dict(incident_type='기관실 화재와 익수자 발생'), people=[], current={})))]
        self.assert_hazards(self.result(evidence=evidence))

    def test_oversized_context_is_reported_not_silently_cut(self):
        result = self.result(dict(facts=dict(notes='화재 없음. ' * 6000)))
        self.assertIn('context_omitted', result['warnings'])
        self.assertEqual(result['status'], 'partial')

    def test_pdf_hash_changes_evidence_identity(self):
        corpus = Corpus(); row = corpus.items[0]
        first = corpus.evidence(row)
        row['original_sha256'] = '0' * 64
        second = corpus.evidence(row)
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(second['original_sha256'], '0' * 64)
