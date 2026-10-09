#!/usr/bin/env python3
"""Offline adapter for one saved OpenClaw TaskRecord; never connects or dispatches."""
import argparse,datetime,hashlib,json,re
from pathlib import Path
from cairn_receipts import artifact,load,validate,Refusal
UPSTREAM='StephenLReed/openclaw-a2a-server@5df556381e813be0e5786108f65720f1fbd53aee'
STATES={'accepted':'submitted','queued':'submitted','running':'working','succeeded':'completed','failed':'failed','canceled':'canceled','expired':'unknown'}
def adapt(snapshot,*,relative_path,instance,observed_at,actor):
 if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}',instance):raise Refusal('Stable non-secret instance namespace required')
 clock=datetime.datetime.fromisoformat(observed_at.replace('Z','+00:00'))
 if clock.tzinfo is None:raise Refusal('Observation clock requires timezone')
 if not isinstance(snapshot,dict) or not isinstance(snapshot.get('taskId'),str) or not 1<=len(snapshot['taskId'])<=512:raise Refusal('TaskRecord taskId required')
 items=snapshot.get('events')
 if not isinstance(items,list) or not 1<=len(items)<=1000:raise Refusal('1..1000 saved task events required')
 task=snapshot['taskId'];prefix=hashlib.sha256((instance+'\0'+task).encode()).hexdigest();events=[];previous=0
 for item in items:
  if not isinstance(item,dict) or type(item.get('id')) is not int or item['id']<=previous:raise Refusal('Event IDs must strictly increase')
  previous=item['id'];state=item.get('state')
  if state not in STATES:raise Refusal('Unknown upstream state; version review required')
  event={'event_id':f'openclaw:{prefix}:{previous}','kind':'task_state','task_id':f'openclaw:{prefix}','occurred_at':observed_at,'who':actor,'what':'Saved OpenClaw task event '+str(previous),'where':'Declared instance '+instance,'when':'Host observation time; upstream per-event timestamp unavailable','why':'Preserve a reviewable observation outside the in-memory task store','how':f'Offline adapter; source={UPSTREAM}; source_state={state}; mapped_state={STATES[state]}; expired maps to unknown, not success; raw snapshot retained','artifacts':[relative_path],'state':STATES[state]}
  validate(event);events.append(event)
 return events

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',required=True);p.add_argument('--snapshot',required=True);p.add_argument('--instance',required=True);p.add_argument('--observed-at',required=True);p.add_argument('--actor',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 try:
  pin=artifact(a.workspace,a.snapshot);snapshot=load(Path(a.workspace)/a.snapshot)
  events=adapt(snapshot,relative_path=a.snapshot,instance=a.instance,observed_at=a.observed_at,actor=a.actor)
  if artifact(a.workspace,a.snapshot)!=pin:raise Refusal('Snapshot changed during adaptation')
  # Fresh directory only: no overwrite of previously prepared observations.
  a.out.mkdir(parents=True,exist_ok=False)
  for i,e in enumerate(events,1):(a.out/f'event-{i:04}.json').write_text(json.dumps(e,indent=2)+'\n')
  print(json.dumps({'prepared':len(events),'output':str(a.out),'execution':'NONE','source':UPSTREAM,'clock_basis':'HOST_OBSERVATION','snapshot_pin_at_preparation':pin}));return 0
 except (OSError,ValueError,KeyError,TypeError) as exc:print(json.dumps({'status':'REFUSED','reason':str(exc)}));return 2
if __name__=='__main__':raise SystemExit(main())
