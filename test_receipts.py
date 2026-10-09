import copy,json,tempfile,unittest
from pathlib import Path
from cairn_receipts import record,verify,compare,replay,scan,Refusal

def event(ident='one',state='working'):
 return dict(event_id=ident,kind='task_state',task_id='synthetic-task',occurred_at='2026-10-09T18:00:00Z',who='Synthetic contributor',what='Review fixture',where='Local fixture',when='Synthetic timestamp',why='Test receipts',how='No inference or remote call',artifacts=['result.txt'],state=state)
def bench(ident='bench',metric='prompt_eval',value=10):
 e=event(ident);e.pop('state');e.update(kind='benchmark',benchmark=dict(hardware='SYNTHETIC-HOST',model='fixture-model',model_sha256='0'*64,workload='pp128',metric=metric,unit='tokens/second',value=value,variant=ident));return e
class ReceiptTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();(self.root/'result.txt').write_text('synthetic result\n');self.ledger=self.root/'ledger.jsonl'
 def tearDown(self):self.temp.cleanup()
 def test_record_verify(self):record(self.ledger,self.root,event());self.assertEqual(verify(self.ledger,self.root)['artifact_match'],'PASS')
 def test_idempotent_and_collision(self):record(self.ledger,self.root,event());self.assertTrue(record(self.ledger,self.root,event())['duplicate']);e=event();e['why']='changed';self.assertRaises(Refusal,record,self.ledger,self.root,e)
 def test_drift_distinct_from_chain(self):record(self.ledger,self.root,event());(self.root/'result.txt').write_text('changed');v=verify(self.ledger,self.root);self.assertEqual((v['chain'],v['artifact_match']),('PASS','DRIFT'))
 def test_tamper(self):record(self.ledger,self.root,event());r=json.loads(self.ledger.read_text());r['payload']['event']['who']='impostor';self.ledger.write_text(json.dumps(r)+'\n');self.assertRaises(Refusal,scan,self.ledger)
 def test_incomplete_tail(self):record(self.ledger,self.root,event());self.ledger.write_bytes(self.ledger.read_bytes()[:-1]);self.assertRaises(Refusal,scan,self.ledger)
 def test_traversal_and_symlink(self):e=event();e['artifacts']=['../secret'];self.assertRaises(Refusal,record,self.ledger,self.root,e);(self.root/'alias').symlink_to(self.root/'result.txt');e['artifacts']=['alias'];self.assertRaises(Refusal,record,self.ledger,self.root,e)
 def test_compare_scope(self):self.assertEqual(compare(bench(),bench('candidate',value=15))['ratio'],1.5);self.assertRaises(Refusal,compare,bench(),bench('decode',metric='decode'))
 def test_replay_event_time(self):record(self.ledger,self.root,event());done=event('done','completed');done['occurred_at']='2026-10-09T19:00:00Z';record(self.ledger,self.root,done);older=event('late-import','submitted');older['occurred_at']='2026-10-09T17:00:00Z';record(self.ledger,self.root,older);self.assertEqual(replay(self.ledger)['tasks'][0]['state'],'completed')
 def test_nonfinite(self):e=bench();e['benchmark']['value']=float('nan');self.assertRaises(Refusal,record,self.ledger,self.root,e)
if __name__=='__main__':unittest.main()
