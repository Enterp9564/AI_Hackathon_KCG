import json
from pathlib import Path
import tempfile
import unittest
import importlib.util
from unittest.mock import patch
from prototype.manual_rag.corpus import Corpus, DEFAULT_SOURCE
from prototype.manual_rag.embedding import LocalEmbedder
from prototype.manual_rag.index import build_index, LocalIndex


class FakeEmbedder:
    fingerprint = 'test-encoder-v1'
    model_dir = Path('/unused-test-model')
    def encode_passages(self, texts):
        return [[1., float(i+1), .5] for i, _ in enumerate(texts)]
    def encode_queries(self, texts): return [[1., 1., .5] for _ in texts]


@unittest.skipUnless(importlib.util.find_spec('qdrant_client'), 'optional RAG dependencies required')
class ManualIndexTests(unittest.TestCase):
    def test_missing_model_is_not_downloaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError): LocalEmbedder(Path(tmp)/'absent')

    def test_persistent_index_restart_and_wrong_generation(self):
        corpus = Corpus()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'generation'
            manifest = build_index(corpus, FakeEmbedder(), root)
            self.assertEqual(manifest['count'], 14)
            first = LocalIndex(root, corpus, embedder=FakeEmbedder())
            result = first.search('수색')
            first.close()
            second = LocalIndex(root, corpus, embedder=FakeEmbedder())
            self.assertEqual(result, second.search('수색'))
            second.close()
            corpus.generation = 'changed'
            with self.assertRaises(ValueError): LocalIndex(root, corpus, embedder=FakeEmbedder())

    def test_model_mismatch_and_corrupt_database_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus = Corpus(); root = Path(tmp)/'index'
            build_index(corpus, FakeEmbedder(), root)
            changed = FakeEmbedder(); changed.fingerprint = 'another-model'
            with self.assertRaises(ValueError): LocalIndex(root, corpus, embedder=changed)
            manifest = json.loads((root/'manifest.json').read_text())
            manifest['count'] += 1
            (root/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError): LocalIndex(root, corpus, embedder=FakeEmbedder())

    def test_build_does_not_overwrite_existing_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'index'; root.mkdir(); (root/'keep').write_text('existing')
            with self.assertRaises(FileExistsError): build_index(Corpus(), FakeEmbedder(), root)
            self.assertEqual((root/'keep').read_text(), 'existing')


if __name__ == '__main__': unittest.main()
