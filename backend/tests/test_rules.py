from datetime import datetime, timedelta, timezone

import pytest

from conftest import tasks, upload


@pytest.mark.parametrize("seconds,expected", [(7199,False),(7200,False),(7201,True)])
def test_unconfirmed_strict_boundary(client, order, clock, seconds, expected):
    order["order_date"]=(clock[0]-timedelta(seconds=seconds)).isoformat()
    assert upload(client,[order])["inserted"]==1
    assert bool(tasks(client,category="unconfirmed")) is expected


@pytest.mark.parametrize("seconds,expected", [(86399,False),(86400,True),(86401,True)])
def test_dispatch_boundary_and_fallback(client, order, clock, seconds, expected):
    order.update(status="confirmed",order_date=(clock[0]-timedelta(seconds=seconds)).isoformat())
    assert upload(client,[order])["inserted"]==1
    found=tasks(client,category="dispatch_delay")
    assert bool(found) is expected
    if found:
        assert "order timestamp" in found[0]["reason"]


@pytest.mark.parametrize("value,expected", [("4999.99",False),("5000",False),("5000.01",True)])
def test_high_value_strict_boundary(client, order, clock, value, expected):
    order.update(status="dispatched", order_date=(clock[0]-timedelta(days=4)).isoformat(),
                 dispatch_date=(clock[0]-timedelta(days=2)).isoformat(), expected_delivery_date=(clock[0]-timedelta(seconds=1)).isoformat(),order_value=value)
    upload(client,[order])
    assert bool(tasks(client,category="high_value_delay")) is expected
    assert len(tasks(client,category="delivery_delay"))==1


@pytest.mark.parametrize("seconds,expected", [(-1,False),(0,False),(1,True)])
def test_expected_timestamp_strict_boundary(client, order, clock, seconds, expected):
    order.update(status="dispatched",order_date=(clock[0]-timedelta(days=4)).isoformat(),
                 dispatch_date=(clock[0]-timedelta(days=2)).isoformat(),expected_delivery_date=(clock[0]-timedelta(seconds=seconds)).isoformat())
    upload(client,[order])
    assert bool(tasks(client,category="delivery_delay")) is expected


def test_failed_delivery_optional_attempt_is_immediate(client, order, clock):
    order.update(status="failed_delivery", order_date=(clock[0]-timedelta(days=3)).isoformat(),
                 dispatch_date=(clock[0]-timedelta(days=1)).isoformat(),expected_delivery_date=(clock[0]+timedelta(days=1)).isoformat())
    assert upload(client,[order])["inserted"]==1
    task=tasks(client)[0]
    assert task["category"]=="failed_delivery" and task["priority"]=="urgent"
    assert datetime.fromisoformat(task["deadline"])==clock[0]
    assert task["customer_name"] and task["phone"] and task["recommended_action"] and task["assigned_employee"]
    clock[0]+=timedelta(microseconds=1)
    assert tasks(client)[0]["overdue"]


@pytest.mark.parametrize("status",["delivered","cancelled","returned"])
def test_terminal_orders_do_not_trigger_undelivered_rules(client, order, clock, status):
    order.update(status=status, order_date=(clock[0]-timedelta(days=10)).isoformat(),order_value="9000",
                 dispatch_date=(clock[0]-timedelta(days=8)).isoformat(),expected_delivery_date=(clock[0]-timedelta(days=5)).isoformat())
    assert upload(client,[order])["inserted"]==1
    assert tasks(client)==[]


def test_confirmation_timestamp_overrides_old_order_date(client, order, clock):
    order.update(status="confirmed",order_date=(clock[0]-timedelta(days=4)).isoformat(),confirmed_at=(clock[0]-timedelta(hours=1)).isoformat())
    upload(client,[order],optional=True)
    assert tasks(client)==[]


def test_date_only_expected_end_of_ist_day(client, order, clock):
    clock[0]=datetime(2026,10,21,18,29,59,tzinfo=timezone.utc)  # 23:59:59 IST
    order.update(status="dispatched",order_date="2026-10-18",dispatch_date="2026-10-19",expected_delivery_date="2026-10-21")
    assert upload(client,[order])["inserted"]==1
    assert tasks(client)==[]
    clock[0]+=timedelta(seconds=1)
    assert client.post('/api/evaluate').json()["created_tasks"]==1
    assert tasks(client)[0]["category"]=="delivery_delay"


def test_naive_timestamps_are_ist_and_offset_times_agree(client, order, clock):
    # Frozen time is 12:00 IST. 09:59:59 IST is >2h ago.
    order.update(order_date="2026-10-21 09:59:59")
    upload(client,[order])
    stored=client.get('/api/orders').json()[0]
    assert stored["order_date"].startswith("2026-10-21T04:29:59")
    assert len(tasks(client))==1


def test_rule_change_may_require_missing_expected_date(client, order):
    order.update(status="confirmed",order_value="4500")
    upload(client,[order])
    rules=client.get('/api/rules').json()
    rules['high_value_rupees']=4000
    response=client.put('/api/rules',json=rules)
    assert response.status_code==200
    assert tasks(client)==[]
    assert any(i['field']=='expected_delivery_date' for i in client.get('/api/data-issues').json())
