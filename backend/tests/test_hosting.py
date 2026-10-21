from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine as real_create_engine

from backend.app.database import create_database
from backend.app.main import create_app
from conftest import tasks, upload


def hosted_app(monkeypatch, tmp_path, clock):
    monkeypatch.setenv('NATURAX_SERVERLESS','1')
    return create_app('sqlite:///' + (tmp_path/'hosted.db').as_posix(), clock=lambda:clock[0],scheduler=False)


def test_hosted_request_evaluates_aged_order_and_reports_real_schedule(monkeypatch,tmp_path,clock,order):
    app=hosted_app(monkeypatch,tmp_path,clock)
    order['order_date']=(clock[0]-timedelta(hours=1)).isoformat()
    with TestClient(app) as client:
        upload(client,[order]);assert tasks(client)==[]
        clock[0]+=timedelta(hours=2)
        assert len(tasks(client))==1  # GET triggers the due evaluation, no timer.
        health=client.get('/api/health').json()
        assert health['scheduler_seconds'] is None
        assert health['evaluation_mode']=='request_and_daily_cron'
        assert client.get('/api/dashboard').json()['open_tasks']==1


def test_cron_requires_secret_and_audits_authenticated_evaluation(monkeypatch,tmp_path,clock,order):
    app=hosted_app(monkeypatch,tmp_path,clock)
    with TestClient(app) as client:
        assert client.get('/api/cron/evaluate').status_code==503
        monkeypatch.setenv('CRON_SECRET','test-only-secret')
        assert client.get('/api/cron/evaluate').status_code==401
        assert client.get('/api/cron/evaluate',headers={'Authorization':'Bearer wrong'}).status_code==401
        upload(client,[order])
        response=client.get('/api/cron/evaluate',headers={'Authorization':'Bearer test-only-secret'})
        assert response.status_code==200
        assert any(a['responsible_user']=='Vercel daily cron' for a in client.get('/api/audit').json())


def test_hosted_sample_files_persist_across_app_instances(monkeypatch,tmp_path,clock):
    app=hosted_app(monkeypatch,tmp_path,clock)
    with TestClient(app) as client:
        first=client.get('/api/samples/naturax_orders.csv')
        assert first.status_code==200 and len(first.content.splitlines())==148
        assert client.get('/api/samples/naturax_orders.xlsx').content.startswith(b'PK')
    clock[0]+=timedelta(hours=3)
    restarted=hosted_app(monkeypatch,tmp_path,clock)
    with TestClient(restarted) as client:
        assert client.get('/api/samples/naturax_orders.csv').content==first.content
        assert client.post('/api/demo/generate').json()['rows']==147
        assert client.get('/api/samples/naturax_orders.csv').content!=first.content


def test_vercel_never_uses_ephemeral_sqlite(monkeypatch):
    monkeypatch.setenv('VERCEL','1')
    monkeypatch.delenv('TURSO_DATABASE_URL',raising=False)
    with pytest.raises(RuntimeError,match='ephemeral local SQLite is not permitted'):
        create_database()


def test_remote_adapter_transaction_lock_across_independent_app_instances(monkeypatch,tmp_path,clock,order):
    monkeypatch.setenv('TURSO_DATABASE_URL','libsql://test.turso.io')
    monkeypatch.setenv('TURSO_AUTH_TOKEN','test-only-token')
    monkeypatch.setenv('NATURAX_SERVERLESS','1')
    captured=[]
    def emulate_remote_engine(url,**options):
        captured.append((url,options['connect_args'].copy()))
        # Exercise the exact remote engine transaction policy on actual SQLite.
        # Live Turso transport is verified separately after deployment.
        options['connect_args'].pop('auth_token')
        return real_create_engine('sqlite:///'+(tmp_path/'shared.db').as_posix(),**options)
    monkeypatch.setattr('backend.app.database.create_engine',emulate_remote_engine)
    app1=create_app(clock=lambda:clock[0],scheduler=False)
    app2=create_app(clock=lambda:clock[0],scheduler=False)
    with TestClient(app1) as first, TestClient(app2) as second:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda client:upload(client,[order]),[first,second]))
        assert sum(result['inserted'] for result in results)==1
        assert len(tasks(first))==1 and len(tasks(second))==1
    assert all(url=='sqlite+libsql://test.turso.io?secure=true' for url,_ in captured)
    assert all(options['isolation_level'] is None for _,options in captured)
    assert all('timeout' not in options for _,options in captured)
