import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from prototype.manual_rag.corpus import Corpus, CorpusError
from prototype.manual_rag.retrieval import ManualSearch

SOURCE = Path(__file__).parents[1] / 'manuals/library/international'


class ManualCorpusTests(unittest.TestCase):
    def test_14_curated_summaries_keep_source_pages_and_limits(self):
        corpus = Corpus(SOURCE)
        self.assertEqual(len(corpus.items), 14)
        self.assertEqual(len(corpus.sources), 6)
        self.assertTrue(all(x['limitations'] and x['pdf_pages'] for x in corpus.items))
        self.assertTrue(all(x['review_status'] == 'draft_needs_domain_review' for x in corpus.items))
        self.assertEqual(corpus.generation, Corpus(SOURCE).generation)

    def test_invalid_hash_page_duplicate_and_policy_are_rejected(self):
        for change in ('hash', 'page', 'duplicate', 'policy'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / 'corpus'
                shutil.copytree(SOURCE, target)
                rows = [json.loads(x) for x in (target/'chunks.jsonl').read_text().splitlines()]
                if change == 'hash': rows[0]['content'] += 'modified'
                if change == 'page': rows[0]['pdf_pages'] = [9999]
                if change == 'duplicate': rows.append(rows[0])
                if change == 'policy': rows[0]['scope'] = 'internal'
                (target/'chunks.jsonl').write_text('\n'.join(json.dumps(x) for x in rows))
                with self.assertRaises(CorpusError): Corpus(target)

    def test_input_mutation_does_not_change_loaded_corpus(self):
        corpus = Corpus(SOURCE)
        items = corpus.items
        items[0]['content'] = 'changed'
        self.assertNotEqual(corpus.items[0]['content'], 'changed')


class ManualSearchTests(unittest.TestCase):
    def setUp(self):
        self.search = ManualSearch(SOURCE, mode='lexical')
        self.addCleanup(self.search.close)

    def query(self, text, **kwargs):
        return self.search.retrieve(text, role='sar', **kwargs)

    def test_korean_paraphrase_and_compound_incident(self):
        result = self.query('기관실 불길이 번지고 사람이 바다에 빠졌다')
        ids = [x['chunk_id'] for x in result['items']]
        self.assertIn('sar-draft:external-support:v1', ids)
        self.assertIn('sar-draft:water-recovery:v1', ids)
        self.assertEqual(result['status'], 'ok')

    def test_no_match_does_not_fill_with_unrelated_items(self):
        result = self.query('케이크 만드는 방법')
        self.assertEqual(result['status'], 'no_match')
        self.assertEqual(result['items'], [])

    def test_negation_is_not_rewritten_as_active_hazard(self):
        result = self.query('불은 꺼졌고 방제 지원이 종료됐다')
        self.assertNotIn('update', result)
        self.assertNotIn('dispatch_orders', result)

    def test_budget_never_truncates_conditions_and_source(self):
        result = self.query('수색 표류 datum', budget_bytes=1)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['items'], [])
        self.assertTrue(result['omitted_ids'])
        full = self.query('수색 표류 datum')
        for item in full['items']:
            original = next(x for x in self.search.corpus.items if x['chunk_id'] == item['chunk_id'])
            self.assertEqual(item['content'], original['content'])
            self.assertEqual(item['limitations'], original['limitations'])

    def test_missing_hybrid_index_is_explicit_lexical_degradation(self):
        with tempfile.TemporaryDirectory() as tmp:
            search = ManualSearch(SOURCE, mode='hybrid', index_dir=Path(tmp))
            self.addCleanup(search.close)
            result = search.retrieve('화재 침수', role='sar')
            self.assertEqual(result['method'], 'lexical')
            self.assertIn('degraded', result['warnings'])
            self.assertFalse(search.ready_vector)

    def test_corrupt_corpus_never_uses_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(CorpusError): ManualSearch(Path(tmp), mode='hybrid')

    def test_bad_query_does_not_disable_vector_search_for_other_queries(self):
        class Index:
            def search(self, text, limit):
                if text=='long':raise ValueError('query too long')
                return [(0,.95)]
            def close(self):pass
        self.search.mode='hybrid';self.search._index=Index()
        bad=self.query('long')
        self.assertIn('degraded',bad['warnings'])
        good=self.query('조난 접수')
        self.assertEqual(good['method'],'hybrid')
        self.assertEqual(good['warnings'],[])

    def test_generation_and_ids_stable_across_restart(self):
        result = self.query('환자 의료 인계')
        other = ManualSearch(SOURCE, mode='lexical')
        self.addCleanup(other.close)
        again = other.retrieve('환자 의료 인계', role='sar')
        self.assertEqual(result['generation'], again['generation'])
        self.assertEqual([x['id'] for x in result['items']], [x['id'] for x in again['items']])

    def test_result_is_json_serializable_and_detached(self):
        result = self.query('화재')
        json.dumps(result, allow_nan=False)
        result['items'][0]['limitations'].clear()
        self.assertTrue(self.query('화재')['items'][0]['limitations'])


if __name__ == '__main__': unittest.main()
