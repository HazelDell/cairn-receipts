import unittest
from openclaw_snapshot import adapt,Refusal
class AdapterTests(unittest.TestCase):
 def run_adapter(self,items):return adapt({'taskId':'task-synthetic','events':items},relative_path='snapshot.json',instance='synthetic-instance',observed_at='2026-10-09T18:00:00Z',actor='Synthetic reviewer')
 def test_seven_states(self):
  events=self.run_adapter([{'id':i+1,'state':s} for i,s in enumerate(('accepted','queued','running','succeeded','failed','canceled','expired'))]);self.assertEqual([e['state'] for e in events],['submitted','submitted','working','completed','failed','canceled','unknown']);self.assertIn('source_state=expired',events[-1]['how'])
 def test_unknown_refused(self):self.assertRaises(Refusal,self.run_adapter,[{'id':1,'state':'surprise'}])
 def test_duplicate_refused(self):self.assertRaises(Refusal,self.run_adapter,[{'id':1,'state':'accepted'},{'id':1,'state':'running'}])
 def test_retry_identity_stable(self):items=[{'id':1,'state':'accepted'}];self.assertEqual(self.run_adapter(items),self.run_adapter(items))
 def test_host_clock_explicit(self):e=self.run_adapter([{'id':1,'state':'accepted'}])[0];self.assertIn('upstream per-event timestamp unavailable',e['when'])
if __name__=='__main__':unittest.main()
