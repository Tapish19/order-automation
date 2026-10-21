"""Capture/verify durable live task state across deployments; never read credential files."""
import argparse
import json
import os
from pathlib import Path

import httpx

parser=argparse.ArgumentParser()
parser.add_argument('phase',choices=['capture','verify'])
parser.add_argument('--url',default='https://naturax-order-automation.vercel.app')
parser.add_argument('--restore-default-rules',action='store_true')
parser.add_argument('--check-cron',action='store_true')
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
before_path=root/'artifacts'/'vercel-persistence-before.json'
with httpx.Client(base_url=args.url,timeout=120,headers={'X-User':'Deployment verification'}) as client:
    health=client.get('/api/health');health.raise_for_status()
    assert health.json()['database']=='turso'
    if args.restore_default_rules:
        changed=client.put('/api/rules',json={'unconfirmed_hours':2,'dispatch_hours':24,'high_value_rupees':5000,'follow_up_hours':4})
        changed.raise_for_status()
    tasks=client.get('/api/tasks');tasks.raise_for_status()
    audits=client.get('/api/audit');audits.raise_for_status()
    orders=client.get('/api/orders');orders.raise_for_status()
    reassignment=next(a for a in audits.json() if a['action']=='task_reassigned' and a['responsible_user']=='Live Interview Manager')
    task=next(t for t in tasks.json() if t['id']==reassignment['task_id'])
    fields=['id','order_id','assigned_employee','status','first_detected_at','deadline']
    snapshot={'url':args.url,'database':health.json()['database'],'order_count':len(orders.json()),
              'tracked_task':{key:task[key] for key in fields},'reassignment_audit':reassignment,
              'cron_audit':next((a for a in audits.json() if a['responsible_user']=='Vercel daily cron' and a['action']=='rules_evaluated'),None),
              'audit_count':len(audits.json()),'checked_at':health.json()['server_time']}
    if args.check_cron:
        assert 'CRON_SECRET' in os.environ,'Run with the secret injected into the process environment.'
        assert client.get('/api/cron/evaluate').status_code==401
        cron=client.get('/api/cron/evaluate',headers={'Authorization':'Bearer '+os.environ['CRON_SECRET']})
        cron.raise_for_status()
        snapshot['authenticated_cron']=cron.json()
    if args.phase=='capture':
        before_path.write_text(json.dumps(snapshot,indent=2),encoding='utf-8')
    else:
        before=json.loads(before_path.read_text(encoding='utf-8'))
        assert snapshot['order_count']==before['order_count']
        assert snapshot['tracked_task']==before['tracked_task']
        assert snapshot['reassignment_audit']==before['reassignment_audit']
        assert snapshot['audit_count']>=before['audit_count']
        snapshot['preserved_after_redeployment']=True
        (root/'artifacts'/'vercel-persistence-after.json').write_text(json.dumps(snapshot,indent=2),encoding='utf-8')
print(json.dumps(snapshot,indent=2))
