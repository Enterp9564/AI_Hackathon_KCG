import io
import json
import unittest
from unittest.mock import patch
from prototype.models import ResponsesModel


class ManualModelTests(unittest.TestCase):
    def test_manual_rules_only_in_opt_in_context(self):
        sent=[]
        def transport(request,timeout):
            sent.append(json.loads(request.data))
            return io.BytesIO(json.dumps({'id':'test','status':'completed','model':'gpt-6-luna',
                'output':[{'type':'message','content':[{'type':'output_text','text':'{"summary":"test"}'}]}]}).encode())
        with patch('prototype.models.urllib.request.urlopen',transport):
            model=ResponsesModel(key='test')
            model.respond('sar','report',{'evidence':[]})
            model.respond('sar','report',{'evidence':[],'manual_search':{'status':'no_match'}})
        self.assertNotIn('sar: ID',sent[0]['instructions'])
        self.assertIn('sar: ID',sent[1]['instructions'])
        self.assertIn('no_match',sent[1]['instructions'])
