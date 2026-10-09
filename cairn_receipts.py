#!/usr/bin/env python3
"""Offline evidence receipts for benchmark and task-event review. Standard library only."""
import argparse,datetime,fcntl,hashlib,json,math,os
from pathlib import Path
SCHEMA='cairn.receipt.v1'
MAX_BYTES=8_000_000
MAX_ROWS=10_000
class Refusal(ValueError):pass

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def sha(value):return hashlib.sha256(value).hexdigest()
def load(path):
 if Path(path).stat().st_size>MAX_BYTES:raise Refusal('Input exceeds 8 MB')
 def unique(pairs):
  result={}
  for k,v in pairs:
   if k in result:raise Refusal('Duplicate JSON key')
   result[k]=v
  return result
 return json.loads(Path(path).read_text(),object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(Refusal('Nonfinite JSON value')))

def artifact(root,relative):
 root=Path(root).resolve()
 rel=Path(relative)
 if rel.is_absolute() or '..' in rel.parts or not rel.parts:raise Refusal('Artifact must be a relative workspace path')
 path=root/rel
 for p in (path,*path.parents):
  if p==root:break
  if p.is_symlink():raise Refusal('Artifact symlinks refused')
 if not path.resolve().is_relative_to(root):raise Refusal('Artifact outside workspace')
 fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0))
 try:
  import stat
  before=os.fstat(fd)
  if not stat.S_ISREG(before.st_mode) or before.st_size>MAX_BYTES or before.st_nlink!=1:raise Refusal('Artifact must be bounded, regular and single-link')
  with os.fdopen(fd,'rb',closefd=False) as stream:raw=stream.read(MAX_BYTES+1)
  after=os.fstat(fd)
  if len(raw)>MAX_BYTES or (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns):raise Refusal('Artifact changed during read')
  return {'path':rel.as_posix(),'bytes':len(raw),'sha256':sha(raw)}
 finally:os.close(fd)

def validate(event):
 required={'event_id','kind','task_id','occurred_at','who','what','where','when','why','how','artifacts'}
 allowed=required|{'state','benchmark'}
 if type(event)!=dict or not required<=event.keys() or event.keys()-allowed:raise Refusal('Event fields mismatch')
 for key in required-{'artifacts'}:
  if not isinstance(event[key],str) or not 1<=len(event[key])<=4096:raise Refusal('Missing/bounded text required: '+key)
 if event['kind'] not in ('task_state','benchmark'):raise Refusal('Unknown event kind')
 clock=datetime.datetime.fromisoformat(event['occurred_at'].replace('Z','+00:00'))
 if clock.tzinfo is None:raise Refusal('Event clock needs timezone')
 if type(event['artifacts'])!=list or len(event['artifacts'])>32 or not all(isinstance(v,str) for v in event['artifacts']):raise Refusal('Up to 32 artifact paths required')
 if len(set(event['artifacts']))!=len(event['artifacts']):raise Refusal('Duplicate artifact')
 if event['kind']=='task_state' and event.get('state') not in ('submitted','working','completed','failed','canceled','unknown'):raise Refusal('Unknown task state')
 if event['kind']=='benchmark':
  b=event.get('benchmark',{})
  if type(b)!=dict or set(b)!={'hardware','model','model_sha256','workload','metric','unit','value','variant'}:raise Refusal('Benchmark contract mismatch')
  if any(not isinstance(b[k],str) or not b[k] for k in set(b)-{'value'}):raise Refusal('Benchmark context required')
  if len(b['model_sha256'])!=64 or any(c not in '0123456789abcdef' for c in b['model_sha256']):raise Refusal('Exact model digest required')
  if type(b['value']) not in (int,float) or not math.isfinite(b['value']) or b['value']<0:raise Refusal('Finite nonnegative metric required')
 return event

def scan(ledger):
 path=Path(ledger)
 if not path.exists():return []
 if path.is_symlink() or not path.is_file() or path.stat().st_nlink!=1 or path.stat().st_size>MAX_BYTES:raise Refusal('Invalid/bounded ledger required')
 raw=path.read_bytes()
 if raw and not raw.endswith(b'\n'):raise Refusal('Incomplete tail; preserve history')
 rows=[];prev='';seen=set()
 for line in raw.splitlines():
  if len(rows)>=MAX_ROWS:raise Refusal('Ledger row bound exceeded')
  r=json.loads(line);body={k:v for k,v in r.items() if k!='row_sha256'}
  if set(r)!={'schema','seq','previous_row_sha256','payload','payload_sha256','row_sha256'} or r['schema']!=SCHEMA or r['seq']!=len(rows)+1 or r['previous_row_sha256']!=prev or sha(canonical(body))!=r['row_sha256'] or sha(canonical(r['payload']))!=r['payload_sha256']:raise Refusal('Broken ledger chain')
  event_id=r['payload']['event']['event_id']
  if event_id in seen:raise Refusal('Duplicate event in ledger')
  seen.add(event_id);rows.append(r);prev=r['row_sha256']
 return rows

def record(ledger,workspace,event):
 validate(event)
 payload={'event':event,'artifact_pins':[artifact(workspace,p) for p in event['artifacts']],'attribution':'DECLARED_NOT_AUTHENTICATED','scope':'Evidence bytes and declared event; not completeness, truth or authorization'}
 path=Path(ledger)
 if not path.parent.is_dir():raise Refusal('Create ledger directory explicitly')
 lock=os.open(str(path)+'.lock',os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
 try:
  import stat
  st=os.fstat(lock)
  if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1:raise Refusal('Invalid lock file')
  fcntl.flock(lock,fcntl.LOCK_EX);rows=scan(path);pin=sha(canonical(payload))
  for row in rows:
   if row['payload']['event']['event_id']==event['event_id']:
    if row['payload_sha256']!=pin:raise Refusal('Event ID reused with changed payload')
    return {'duplicate':True,'receipt':row}
  body={'schema':SCHEMA,'seq':len(rows)+1,'previous_row_sha256':rows[-1]['row_sha256'] if rows else '', 'payload':payload,'payload_sha256':pin};body['row_sha256']=sha(canonical(body));data=canonical(body)+b'\n'
  if len(rows)>=MAX_ROWS or (path.stat().st_size if path.exists() else 0)+len(data)>MAX_BYTES:raise Refusal('Ledger capacity reached; archive explicitly')
  fd=os.open(path,os.O_CREAT|os.O_APPEND|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0),0o600)
  try:
   st=os.fstat(fd)
   if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1:raise Refusal('Invalid ledger file')
   view=memoryview(data)
   while view:view=view[os.write(fd,view):]
   os.fsync(fd)
  finally:os.close(fd)
  directory=os.open(path.parent,os.O_RDONLY)
  try:os.fsync(directory)
  finally:os.close(directory)
  return {'duplicate':False,'receipt':body}
 finally:fcntl.flock(lock,fcntl.LOCK_UN);os.close(lock)

def verify(ledger,workspace):
 rows=scan(ledger);drift=[]
 for row in rows:
  for pin in row['payload']['artifact_pins']:
   try:matches=artifact(workspace,pin['path'])==pin
   except (OSError,ValueError):matches=False
   if not matches:drift.append({'event_id':row['payload']['event']['event_id'],'path':pin['path']})
 return {'chain':'PASS','rows':len(rows),'artifact_match':'PASS' if not drift else 'DRIFT','drift':drift,'scope':'Byte identity only; shared-ledger hashes are not independent signatures'}

def compare(a,b):
 validate(a);validate(b)
 if a['kind']!='benchmark' or b['kind']!='benchmark':raise Refusal('Two benchmark events required')
 x=a['benchmark'];y=b['benchmark'];keys=set(x)-{'value','variant'}
 mismatch=sorted(k for k in keys if x[k]!=y[k])
 if mismatch:raise Refusal('Incomparable context fields: '+','.join(mismatch))
 return {'metric':x['metric'],'unit':x['unit'],'baseline':x['value'],'candidate':y['value'],'ratio':y['value']/x['value'] if x['value'] else None,'scope':'Declared matching context; not a reproduced performance claim'}

def replay(ledger):
 latest={}
 for row in scan(ledger):
  e=row['payload']['event']
  if e['kind']!='task_state':continue
  rank=(datetime.datetime.fromisoformat(e['occurred_at'].replace('Z','+00:00')),row['seq'])
  if e['task_id'] not in latest or rank>latest[e['task_id']][0]:latest[e['task_id']]=(rank,{'task_id':e['task_id'],'state':e['state'],'event_id':e['event_id'],'row_sha256':row['row_sha256']})
 return {'tasks':[v[1] for k,v in sorted(latest.items())],'execution':'NONE','scope':'Recorded state projection, not live worker health; no A2A protocol conformance claimed'}

def main():
 p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
 for name in ('record','verify'):
  q=sub.add_parser(name);q.add_argument('--ledger',required=True);q.add_argument('--workspace',required=True)
  if name=='record':q.add_argument('--event',required=True)
 q=sub.add_parser('compare');q.add_argument('baseline');q.add_argument('candidate');q=sub.add_parser('replay');q.add_argument('--ledger',required=True);a=p.parse_args()
 try:
  result=record(a.ledger,a.workspace,load(a.event)) if a.command=='record' else verify(a.ledger,a.workspace) if a.command=='verify' else compare(load(a.baseline),load(a.candidate)) if a.command=='compare' else replay(a.ledger)
  print(json.dumps(result,indent=2));return 1 if result.get('artifact_match')=='DRIFT' else 0
 except (ValueError,OSError,KeyError,TypeError) as e:print(json.dumps({'status':'REFUSED','reason':str(e)}));return 2
if __name__=='__main__':raise SystemExit(main())
