import unittest
from prototype.manual_rag.evaluate import summarize


class ManualEvaluationTests(unittest.TestCase):
    def test_recall_empty_queries_and_failures_are_separate(self):
        report=summarize([
            dict(expected=['a','b'],found=['a'],status='ok',latency_ms=2),
            dict(expected=[],found=['c'],status='ok',latency_ms=3),
            dict(expected=[],found=[],status='error',latency_ms=5)])
        self.assertEqual(report['recall'],.5)
        self.assertEqual(report['false_positive_queries'],1)
        self.assertEqual(report['failures'],1)
        self.assertFalse(report['passed'])
