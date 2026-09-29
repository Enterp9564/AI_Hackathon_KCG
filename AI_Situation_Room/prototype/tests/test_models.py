import io
import json
import unittest
from unittest.mock import patch
from prototype.models import ResponsesModel, ModelError


class ModelContractTests(unittest.TestCase):
    def test_actual_request_uses_role_effort_and_session_input(self):
        sent=[]
        def transport(request,timeout):
            sent.append(json.loads(request.data))
            return io.BytesIO(json.dumps({'id':'response-test','status':'completed','model':'gpt-6-luna',
                'usage':{'input_tokens':12,'output_tokens':5},'output':[{'type':'message','content':[
                    {'type':'output_text','text':'{"summary":"현재 세션 검토"}'}]}]}).encode())
        with patch('prototype.models.urllib.request.urlopen',transport):
            model=ResponsesModel(key='test-key')
            result,meta=model.respond('commander','plan',{'session':{'id':'A'}})
            model.respond('intel','report',{'session':{'id':'B'}})
        self.assertEqual(result['summary'],'현재 세션 검토')
        self.assertEqual(meta['usage']['input_tokens'],12)
        self.assertEqual(sent[0]['reasoning'],{'effort':'medium'})
        self.assertEqual(sent[1]['reasoning'],{'effort':'medium'})
        self.assertEqual(sent[0]['model'],'gpt-6-luna')
        self.assertIn('json', sent[0]['input'].lower())
        self.assertEqual(json.loads(sent[1]['input'])['context'],{'session':{'id':'B'}})
        self.assertFalse(sent[0]['store'])
        self.assertIn('현장 계측 장비의 실측값', sent[0]['instructions'])
        self.assertIn('조언을 먼저', sent[1]['instructions'])

    def test_incomplete_or_refusal_response_is_not_report(self):
        for payload in [{'status':'incomplete','output':[]},
                        {'status':'completed','output':[{'type':'message','content':[{'type':'refusal','refusal':'no'}]}]}]:
            with self.subTest(payload=payload),patch('prototype.models.urllib.request.urlopen',return_value=io.BytesIO(json.dumps(payload).encode())):
                with self.assertRaises(ModelError):ResponsesModel(key='test-key').respond('commander','final',{})
