import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from prototype.store import Store
from prototype.inbox import Inbox
from prototype.mcp_server import make_mcp_server, PROTOCOL


class MCPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name)/'room.sqlite')
        self.inbox = Inbox(self.store)
        self.sid = self.store.create_session('A호')['id']
        self.inbox.link(self.sid, 'link-one', 'a')
        self.server = make_mcp_server(self.inbox, {'link-one': 'x'*40, 'resaid-ai': 'y'*40}, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/mcp'
        self.args = dict(report_id='r1', incident_id='a', incident_title='A호',
                         reported_at='2026-09-27T14:32:00+09:00', content='상태 변화')

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.tmp.cleanup()

    def request(self, method='initialize', params=None, headers=None, notification=False, verb='POST'):
        data = dict(jsonrpc='2.0', method=method, params=params or {})
        if not notification: data['id'] = 1
        h = {'Authorization':'Bearer '+'x'*40, 'Content-Type':'application/json',
             'Accept':'application/json, text/event-stream', 'MCP-Protocol-Version':PROTOCOL}
        h.update(headers or {})
        request = urllib.request.Request(self.url, data=json.dumps(data).encode() if verb=='POST' else None,
                                         headers=h, method=verb)
        try: response = urllib.request.urlopen(request, timeout=3)
        except urllib.error.HTTPError as error: response = error
        with response:
            body = response.read()
            return response.status, json.loads(body) if body else None

    def test_handshake_tools_and_idempotent_receipt(self):
        status, data = self.request(params={'protocolVersion':PROTOCOL, 'capabilities':{}, 'clientInfo':{'name':'test','version':'1'}})
        self.assertEqual(status, 200)
        self.assertEqual(data['result']['protocolVersion'], PROTOCOL)
        self.assertEqual(self.request('notifications/initialized', notification=True), (202,None))
        self.assertEqual(self.request('tools/list')[1]['result']['tools'][0]['name'], 'submit_field_report')
        params = {'name':'submit_field_report', 'arguments':self.args}
        a = self.request('tools/call', params)[1]['result']['structuredContent']
        b = self.request('tools/call', params)[1]['result']['structuredContent']
        self.assertEqual(a['receipt_id'], b['receipt_id'])
        self.assertEqual(self.store.snapshot(self.sid)['runs'], [])
        self.assertEqual(self.request(verb='GET')[0], 405)

    def test_auth_origin_host_and_protocol(self):
        for headers, status in [({'Authorization':''},401), ({'Origin':'https://evil.example'},403),
                                ({'Host':'evil.example'},403), ({'MCP-Protocol-Version':'bad'},400)]:
            self.assertEqual(self.request(headers=headers)[0], status)

    def test_project_identity_and_invalid_arguments(self):
        params = {'name':'submit_field_report', 'arguments':self.args}
        self.assertTrue(self.request('tools/call', params, headers={'Authorization':'Bearer '+'y'*40})[1]['result']['isError'])
        for args in [dict(self.args, content=''), dict(self.args, reported_at='14:32'),
                     dict(self.args, project='resaid-ai'), dict(self.args, incident_id='unknown')]:
            result = self.request('tools/call', {'name':'submit_field_report', 'arguments':args})[1]['result']
            self.assertTrue(result['isError'])
        self.assertEqual(self.inbox.list()['reports'], [])

    def test_notification_cannot_submit_and_conflict_preserves_original(self):
        params = {'name':'submit_field_report', 'arguments':self.args}
        self.assertEqual(self.request('tools/call', params, notification=True)[0], 400)
        self.request('tools/call', params)
        result = self.request('tools/call', dict(params, arguments=dict(self.args, content='changed')))[1]['result']
        self.assertTrue(result['isError'])
        self.assertEqual(self.inbox.list()['reports'][0]['original'], self.args)
