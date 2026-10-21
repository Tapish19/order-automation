import io
from datetime import timedelta

import pandas as pd
import pytest

from backend.app.validation import HEADERS
from conftest import csv_bytes, tasks, upload


def test_exact_ten_headers_csv_and_blank_dispatch(client, order):
    assert len(HEADERS)==10
    result=upload(client,[order])
    assert result['inserted']==1 and result['rejected']==0
    assert client.get('/api/orders').json()[0]['dispatch_date'] is None


def test_exact_ten_headers_excel(client, order):
    stream=io.BytesIO()
    pd.DataFrame([{h:order[k] for h,k in HEADERS.items()}]).to_excel(stream,index=False)
    response=client.post('/api/uploads',files={'file':('orders.xlsx',stream.getvalue())})
    assert response.status_code==200,response.text
    assert response.json()['inserted']==1
    assert len(tasks(client))==1


@pytest.mark.parametrize('changes,field',[
    ({'phone':''},'phone'),({'status':''},'status'),({'status':'unknown'},'status'),
    ({'order_value':''},'order_value'),({'order_value':'NaN'},'order_value'),({'order_value':'inf'},'order_value'),
    ({'order_value':'-1'},'order_value'),({'order_value':'5000.001'},'order_value'),
    ({'order_date':'2026-02-30 10:00'},'order_date'),({'order_date':'2026-10-20'},'order_date'),
    ({'payment_type':'UPI'},'payment_type'),({'id':''},'id'),({'assigned_employee':''},'assigned_employee'),
    ({'status':'dispatched','expected_delivery_date':'2026-10-20'},'dispatch_date'),
])
def test_invalid_rows_become_corrections_not_exceptions(client, order, changes, field):
    bad=dict(order,**changes)
    good=dict(order,id='GOOD',status='delivered')
    result=upload(client,[bad,good])
    assert result['inserted']==1 and result['rejected']==1
    issues=client.get('/api/data-issues').json()
    assert any(i['field']==field for i in issues)
    assert all(i['filename']=='orders.csv' and i['row_number']==2 and i['recommended_correction'] for i in issues)
    assert tasks(client)==[]


def test_identical_and_conflicting_duplicates_in_one_file(client, order):
    same=dict(order,id='IDENTICAL')
    conflict=dict(order,id='CONFLICT')
    result=upload(client,[same,same,conflict,dict(conflict,phone='919999999999')])
    assert result['inserted']==1 and result['duplicate_rows']==3 and result['rejected']==2
    assert len(client.get('/api/orders').json())==1
    assert any(i['severity']=='warning' for i in client.get('/api/data-issues').json())


def test_existing_identity_collision_rejected_but_status_update_allowed(client, order):
    upload(client,[order])
    assert upload(client,[dict(order,customer_name='Other Customer')])['rejected']==1
    assert upload(client,[dict(order,status='confirmed')])['updated']==1
    assert client.get('/api/orders').json()[0]['customer_name']==order['customer_name']


def test_correction_screen_api_imports_and_resolves_source_row(client, order):
    upload(client,[dict(order,phone='')])
    issue=client.get('/api/data-issues').json()[0]
    response=client.post(f"/api/data-issues/{issue['id']}/correct",json={'record':order},headers={'X-User':'Correction Manager'})
    assert response.status_code==200,response.text
    assert client.get('/api/data-issues').json()==[]
    assert len(tasks(client))==1
    assert any(a['action']=='data_corrected' and a['responsible_user']=='Correction Manager' for a in client.get('/api/audit').json())


def test_missing_id_can_be_corrected(client, order):
    upload(client,[dict(order,id='')])
    issue=client.get('/api/data-issues').json()[0]
    assert issue['order_id'] is None
    assert client.post(f"/api/data-issues/{issue['id']}/correct",json={'record':order}).status_code==200
    assert client.get('/api/data-issues').json()==[]


def test_invalid_correction_is_rejected(client, order):
    upload(client,[dict(order,phone='')])
    issue=client.get('/api/data-issues').json()[0]
    response=client.post(f"/api/data-issues/{issue['id']}/correct",json={'record':dict(order,phone='bad')})
    assert response.status_code==422
    assert client.get('/api/orders').json()==[]


@pytest.mark.parametrize('filename,content', [('bad.xlsx',b'garbage'),('bad.csv',b'\xff\xfe'),('bad.txt',b'a,b'),('bad.csv',b'a,b\n1,2,3\n')])
def test_unreadable_files_fail_without_importing(client, filename, content):
    assert client.post('/api/uploads',files={'file':(filename,content)}).status_code==422
    assert client.get('/api/imports').json()==[]


def test_valid_reimport_resolves_earlier_errors(client, order):
    upload(client,[dict(order,order_value='bad')])
    upload(client,[order])
    assert client.get('/api/data-issues').json()==[]


def test_date_only_excel_style_not_invented_as_midnight(client, order):
    from datetime import datetime
    from openpyxl import Workbook
    book=Workbook();sheet=book.active
    sheet.append(list(HEADERS))
    values=[order[k] for k in HEADERS.values()]
    values[1]=datetime(2026,10,20)
    sheet.append(values)
    sheet['B2'].number_format='yyyy-mm-dd'
    stream=io.BytesIO();book.save(stream)
    response=client.post('/api/uploads',files={'file':('date-only.xlsx',stream.getvalue())})
    assert response.json()['rejected']==1
    assert any(i['field']=='order_date' for i in client.get('/api/data-issues').json())


def test_duplicate_headers_are_rejected_before_pandas_mangles_them(client, order):
    content=csv_bytes([order]).decode().replace('Order ID,','Order ID,Order ID,',1).replace('TEST-001,','TEST-001,OTHER,',1)
    response=client.post('/api/uploads',files={'file':('duplicate.csv',content.encode())})
    assert response.status_code==422
    assert 'Duplicate column' in response.json()['detail']


def test_expected_delivery_cannot_precede_unshipped_order(client, order):
    order.update(order_value='6000',expected_delivery_date='2026-10-10')
    assert upload(client,[order])['rejected']==1
    assert tasks(client)==[]


def test_rejected_update_pauses_new_exceptions_until_source_is_corrected(client, order, clock):
    order['order_date']=(clock[0]-timedelta(hours=1)).isoformat()
    upload(client,[order])
    assert tasks(client)==[]
    clock[0]+=timedelta(hours=3)
    assert upload(client,[dict(order,status='UNKNOWN')])['rejected']==1
    client.post('/api/evaluate')
    assert tasks(client)==[]
    assert client.get('/api/orders').json()[0]['status']=='unconfirmed'
    assert upload(client,[dict(order,status='delivered')])['updated']==1
    assert tasks(client)==[]
    assert client.get('/api/data-issues').json()==[]
