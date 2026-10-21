import time
from datetime import timedelta

from fastapi.testclient import TestClient

from backend.app.main import create_app
from conftest import tasks, upload


def test_periodic_evaluation_detects_newly_aged_order_without_user_action(tmp_path, order, clock):
    app=create_app('sqlite:///' + (tmp_path / 'nested' / 'scheduled.db').as_posix(),
                   clock=lambda:clock[0], scheduler=True, evaluation_interval=0.05)
    order['order_date']=(clock[0]-timedelta(hours=2)).isoformat()
    with TestClient(app) as client:
        upload(client,[order])
        assert tasks(client)==[]
        clock[0]+=timedelta(seconds=1)
        cutoff=time.monotonic()+3
        while time.monotonic()<cutoff and not tasks(client):
            time.sleep(0.02)
        found=tasks(client)
        assert len(found)==1 and found[0]['category']=='unconfirmed'
        audit=client.get('/api/audit',params={'action':'task_assigned'}).json()[0]
        assert audit['responsible_user']=='System scheduler'
