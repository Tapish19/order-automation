import csv
import io
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.validation import HEADERS


@pytest.fixture
def clock():
    return [datetime(2026, 10, 21, 6, 30, tzinfo=timezone.utc)]


@pytest.fixture
def app(tmp_path, clock):
    return create_app("sqlite:///" + (tmp_path / "test.db").as_posix(), clock=lambda: clock[0], scheduler=False)


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def order(clock):
    return {"id":"TEST-001", "order_date":(clock[0]-timedelta(hours=3)).isoformat(),
        "customer_name":"Kavya Menon", "phone":"919876543210", "order_value":"2400",
        "payment_type":"Prepaid", "status":"unconfirmed", "dispatch_date":"", "expected_delivery_date":"",
        "assigned_employee":"Meera Iyer"}


def csv_bytes(rows, optional=False):
    headers = dict(HEADERS)
    if optional:
        headers.update({"confirmed_at":"confirmed_at", "delivery_attempt_at":"delivery_attempt_at"})
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(headers))
    writer.writeheader()
    for row in rows:
        writer.writerow({h:row.get(k, "") for h,k in headers.items()})
    return stream.getvalue().encode("utf-8")


def upload(client, rows, optional=False, filename="orders.csv"):
    response = client.post("/api/uploads", files={"file":(filename,csv_bytes(rows,optional),"text/csv")}, headers={"X-User":"Test Manager"})
    assert response.status_code == 200, response.text
    return response.json()


def tasks(client, **params):
    response = client.get("/api/tasks", params=params)
    assert response.status_code == 200, response.text
    return response.json()
