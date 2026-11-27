import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from factory.engine import Engine, Demo, Ollama, FactoryError, validate_task, validate_output, assess, read_json

TASK={'goal':'Create a checklist','context':'No actual deployment','criteria':['Backup','Tests'],'language':'en'}

class Reject(Demo):
    def call(self, role, payload):
        result=super().call(role,payload)
        if role=='reviewer': result['critical']=['Blocking issue']
        return result

class Flaky(Demo):
    def __init__(self): self.fail=True
    def call(self, role, payload):
        if role=='writer' and self.fail:
            self.fail=False
            raise TimeoutError()
        return super().call(role,payload)

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
    def test_demo(self):
        engine=Engine(self.root,Demo()); rid=engine.create(TASK); r=engine.execute(rid)
        self.assertEqual(r['status'],'REVIEWED_DRAFT'); self.assertEqual(r['calls'],3)
        self.assertTrue(r['human_review_required']); self.assertEqual(r['evaluation'],'fixture only')
        self.assertEqual(engine.execute(rid),r)
        self.assertEqual(read_json(self.root/rid/'draft.json')['status'],'UNAPPROVED_DRAFT')
    def test_critical_and_revision_limit(self):
        engine=Engine(self.root,Reject()); rid=engine.create(TASK); r=engine.execute(rid)
        self.assertEqual((r['status'],r['calls'],r['score']),('BLOCKED',7,100))
        self.assertFalse((self.root/rid/'draft.json').exists())
    def test_resume(self):
        engine=Engine(self.root,Flaky()); rid=engine.create(TASK)
        self.assertEqual(engine.execute(rid)['status'],'FAILED')
        self.assertEqual(engine.execute(rid)['calls'],4)
        state=read_json(self.root/rid/'state.json')
        self.assertEqual([h['role'] for h in state['history']],['planner','writer','reviewer'])
    def test_budget(self):
        engine=Engine(self.root,Flaky()); rid=engine.create(TASK,0)
        engine.execute(rid); self.assertEqual(engine.execute(rid)['status'],'BLOCKED')
    def test_bad_input(self):
        for change in [{'criteria':[]},{'criteria':['A','A']},{'language':[]},{'goal':''}]:
            with self.subTest(change=change), self.assertRaises(FactoryError): validate_task(TASK|change)
    def test_bad_review(self):
        bad={'checks':[{'id':0,'passed':True,'reason':'x'},{'id':0,'passed':True,'reason':'x'}],'critical':[],'feedback':'x'}
        with self.assertRaises(FactoryError): validate_output('reviewer',bad,2)
        bad['checks'][1]['id']=1; bad['checks'][1]['passed']='true'
        with self.assertRaises(FactoryError): validate_output('reviewer',bad,2)
    def test_all_criteria_mandatory(self):
        self.assertEqual(assess({'checks':[{'passed':True},{'passed':False}],'critical':[]}), (50,False))
    def test_traversal_and_lock(self):
        engine=Engine(self.root,Demo())
        with self.assertRaises(FactoryError): engine.folder('../outside')
        rid=engine.create(TASK); (self.root/rid/'.lock').mkdir()
        with self.assertRaises(FactoryError): engine.execute(rid)
    def test_backend_mismatch(self):
        rid=Engine(self.root,Demo()).create(TASK)
        with self.assertRaises(FactoryError): Engine(self.root,Ollama('local')).execute(rid)
    def test_ollama_protocol_mock(self):
        with patch('factory.engine.http.client.HTTPConnection') as factory:
            conn=factory.return_value; response=conn.getresponse.return_value
            response.status=200; response.read.return_value=json.dumps({'done':True,'message':{'content':'{"steps":["one"]}'}}).encode()
            self.assertEqual(Ollama('local').call('planner',{'task':TASK}),{'steps':['one']})
            factory.assert_called_once_with('127.0.0.1',11434,timeout=120)
            method,path,body,headers=conn.request.call_args.args
            self.assertEqual((method,path),('POST','/api/chat')); self.assertFalse(json.loads(body)['stream']); self.assertNotIn('tools',json.loads(body))
            conn.close.assert_called_once()
    def test_ollama_rejects_redirect_or_tool_calls(self):
        with patch('factory.engine.http.client.HTTPConnection') as factory:
            response=factory.return_value.getresponse.return_value; response.status=302
            with self.assertRaises(FactoryError): Ollama('local').call('planner',{'task':TASK})
            response.status=200; response.read.return_value=json.dumps({'done':True,'message':{'tool_calls':[{}],'content':'{}'}}).encode()
            with self.assertRaises(FactoryError): Ollama('local').call('planner',{'task':TASK})
    def test_arabic(self):
        engine=Engine(self.root,Demo()); rid=engine.create(TASK|{'goal':'قائمة','criteria':['اختبار'],'language':'ar'})
        engine.execute(rid); self.assertIn('اختبار',read_json(self.root/rid/'draft.json')['draft'])

if __name__=='__main__': unittest.main()
