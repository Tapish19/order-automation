import csv
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.sample_data import make_records
from conftest import tasks, upload


def test_interview_A_deliberately_invalid_file(client, order):
    result=upload(client,[dict(order,id='BAD',phone='wrong'),dict(order,id='GOOD')])
    assert result['inserted']==1 and result['rejected']==1
    assert client.get('/api/data-issues').json()[0]['order_id']=='BAD'


def test_interview_B_threshold_24_to_12(client, order, clock):
    order.update(status='confirmed',order_date=(clock[0]-timedelta(hours=18)).isoformat())
    upload(client,[order])
    assert tasks(client)==[]
    config=client.get('/api/rules').json();config['dispatch_hours']=12
    response=client.put('/api/rules',json=config,headers={'X-User':'Interview Manager'})
    assert response.json()['created_tasks']==1
    assert tasks(client)[0]['category']=='dispatch_delay'
    config['dispatch_hours']=24
    assert client.put('/api/rules',json=config).json()['resolved_tasks']==1


def test_interview_C_repeated_uploads_and_evaluations(client, order):
    upload(client,[order])
    first=tasks(client)[0]
    for _ in range(3):
        assert upload(client,[order])['created_tasks']==0
        assert client.post('/api/evaluate').json()['created_tasks']==0
    assert len(tasks(client))==1
    assert tasks(client)[0]['first_detected_at']==first['first_detected_at']
    assert tasks(client)[0]['deadline']==first['deadline']
    dashboard=client.get('/api/dashboard').json()
    assert dashboard['uploaded_rows']==4 and dashboard['unique_orders_all_time']==1


def test_interview_D_E_overdue_reassignment_persistence_and_audit(client, order, clock, app):
    upload(client,[order]);clock[0]+=timedelta(hours=5)
    task=tasks(client,overdue=True)[0]
    response=client.patch(f"/api/tasks/{task['id']}",json={'assigned_employee':'Priya Nair','status':'in_progress','note':'Shift handover'},headers={'X-User':'NaturaX Manager'})
    assert response.status_code==200
    upload(client,[order]);client.post('/api/evaluate')
    stored=tasks(client)[0]
    assert stored['assigned_employee']=='Priya Nair' and stored['status']=='in_progress'
    records=client.get('/api/audit',params={'order_id':order['id'],'action':'task_reassigned'}).json()
    assert len(records)==1
    record=records[0]
    assert record['responsible_user']=='NaturaX Manager'
    assert datetime.fromisoformat(record['timestamp'])==clock[0]
    assert record['details']['previous_employee']=='Meera Iyer' and record['details']['was_overdue'] is True
    assert record['details']['assigned_employee']=='Priya Nair'
    # A completely new app/engine reading the same on-disk database sees the assignment.
    restarted=create_app(str(app.state.engine.url),clock=lambda:clock[0],scheduler=False)
    with TestClient(restarted) as next_client:
        assert tasks(next_client)[0]['assigned_employee']=='Priya Nair'


def test_resolve_same_problem_no_reopen_then_new_episode(client, order, clock):
    upload(client,[order]);first=tasks(client)[0]
    assert client.patch(f"/api/tasks/{first['id']}",json={'status':'resolved'}).status_code==200
    upload(client,[order]);client.post('/api/evaluate')
    assert len(tasks(client))==1 and tasks(client)[0]['status']=='resolved'
    upload(client,[dict(order,status='delivered')])
    assert tasks(client)[0]['condition_active'] is False
    clock[0]+=timedelta(days=1)
    upload(client,[order])
    rows=tasks(client)
    assert len(rows)==2 and sum(t['status']=='open' for t in rows)==1
    assert rows[0]['first_detected_at']!=first['first_detected_at']


def test_business_resolution_preserves_history(client, order):
    upload(client,[order]);first=tasks(client)[0]
    upload(client,[dict(order,status='delivered')])
    assert tasks(client)[0]['status']=='resolved'
    assert tasks(client)[0]['id']==first['id']
    assert client.get('/api/dashboard').json()['open_tasks']==0
    assert any(a['action']=='exception_resolved' for a in client.get('/api/audit').json())
    assert client.patch(f"/api/tasks/{first['id']}",json={'status':'open'}).status_code==409


def test_filters_change_backend_results(client, order, clock):
    older=dict(order,id='OLDER',order_date=(clock[0]-timedelta(days=2)).isoformat(),status='confirmed',assigned_employee='Aarav Shah')
    upload(client,[order,older])
    assert len(tasks(client))==2
    assert len(tasks(client,employee='Meera Iyer'))==1
    assert tasks(client,priority='urgent')==[]
    assert len(tasks(client,category='dispatch_delay'))==1
    assert len(tasks(client,date_from='2026-10-21',date_to='2026-10-21'))==1
    dash=client.get('/api/dashboard',params={'category':'dispatch_delay','employee':'Aarav Shah','priority':'high','date_to':'2026-10-20'}).json()
    assert dash['open_tasks']==1 and dash['orders_requiring_attention']==1
    assert dash['employee_pending']==[{'name':'Aarav Shah','count':1}]
    assert client.get('/api/dashboard',params={'date_from':'2026-10-22','date_to':'2026-10-20'}).status_code==422


def test_report_all_sections_and_new_definition_ist(client, order, clock):
    # First order was detected on the prior IST date; next on selected date.
    clock[0]=datetime(2026,10,20,18,29,0,tzinfo=timezone.utc)
    order.update(order_date='2026-10-19T09:00:00+05:30')
    upload(client,[order])
    clock[0]=datetime(2026,10,21,6,30,0,tzinfo=timezone.utc)
    second=dict(order,id='SECOND',status='confirmed')
    upload(client,[second])
    third=dict(order,id='THIRD')
    upload(client,[third])
    third_task=tasks(client,search='THIRD')[0]
    client.patch(f"/api/tasks/{third_task['id']}",json={'status':'resolved'})
    response=client.get('/api/reports/daily.csv',params={'report_date':'2026-10-21'})
    assert response.status_code==200
    rows=list(csv.DictReader(io.StringIO(response.text.lstrip('\ufeff'))))
    sections={r['section'] for r in rows}
    assert {'new_exceptions','unresolved_exceptions','overdue_tasks','high_priority_cases','employee_pending_actions','employee_pending_summary'} <= sections
    new={r['order_id'] for r in rows if r['section']=='new_exceptions'}
    assert new=={'SECOND','THIRD'}
    unresolved={r['order_id'] for r in rows if r['section']=='unresolved_exceptions'}
    assert unresolved=={order['id'],'SECOND'}
    assert all(r['first_detected_at_utc'] for r in rows if r['task_id'])


def test_sample_has_100_plus_all_rules_and_bad_rows(client, clock):
    records=make_records(clock[0]);assert len(records)>=100
    result=upload(client,records)
    assert result['inserted']>=100 and result['rejected']>=8 and result['duplicate_rows']>=3
    categories={t['category'] for t in tasks(client)}
    assert categories=={'unconfirmed','dispatch_delay','delivery_delay','failed_delivery','high_value_delay'}


def test_concurrent_reuploads_remain_idempotent(client, order):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:upload(client,[order]),range(4)))
    assert sum(r['inserted'] for r in results)==1
    assert len(tasks(client))==1


def test_employee_and_task_assignment_validation(client, order):
    upload(client,[order]);task=tasks(client)[0]
    assert client.patch(f"/api/tasks/{task['id']}",json={'assigned_employee':'Unknown'}).status_code==422
    assert client.post('/api/employees',json={'name':'New Employee'}).status_code==201
    assert client.patch(f"/api/tasks/{task['id']}",json={'assigned_employee':'New Employee'}).status_code==200
    assert client.post('/api/employees',json={'name':'New Employee'}).status_code==409


def test_invalid_rule_and_actor_validation(client):
    config=client.get('/api/rules').json();config['dispatch_hours']=0
    assert client.put('/api/rules',json=config).status_code==422
    assert client.post('/api/evaluate',headers={'X-User':' '}).status_code==422


def test_pending_filter_includes_in_progress_and_excludes_resolved(client, order):
    upload(client,[order,dict(order,id='SECOND'),dict(order,id='THIRD')])
    rows=tasks(client)
    client.patch(f"/api/tasks/{rows[0]['id']}",json={'status':'in_progress'})
    client.patch(f"/api/tasks/{rows[1]['id']}",json={'status':'resolved'})
    pending=tasks(client,status='pending')
    assert len(pending)==2
    assert {t['status'] for t in pending}=={'open','in_progress'}


def test_priority_desk_places_immediate_failures_first(client, clock):
    upload(client,make_records(clock[0]))
    cases=client.get('/api/dashboard').json()['immediate_cases']
    assert cases[0]['category']=='failed_delivery'
