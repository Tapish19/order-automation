import base64
import csv
import io
import json
import sqlite3

import pytest

from conftest import upload
from backend.app.rules import DEFAULT_RULES
from scripts.reset_live_demo import EMPLOYEES, Local, reset


def test_reset_backs_up_real_records_and_restores_fresh_state(app, client, order):
    upload(client, [order])
    client.post('/api/employees', json={'name': 'Recording Employee'})
    settings = dict(DEFAULT_RULES, dispatch_hours=12)
    client.put('/api/rules', json=settings)
    db = Local(app.state.engine.url.database)
    original_counts = {t: db.query(f'SELECT count(*) FROM {t}')[1][0][0]
                       for t in ('orders', 'tasks', 'audit', 'imports')}
    try:
        backup_path = reset(db, apply=True)
        with sqlite3.connect(backup_path) as backup:
            assert backup.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert backup.execute('PRAGMA foreign_key_check').fetchall() == []
            for table, count in original_counts.items():
                assert backup.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == count
            assert backup.execute('SELECT assigned_employee FROM orders').fetchone()[0] == order['assigned_employee']
        for table in ('orders', 'tasks', 'imports', 'data_issues'):
            assert db.query(f'SELECT count(*) FROM {table}')[1][0][0] == 0
        assert {row[0] for row in db.query('SELECT name FROM employees')[1]} == set(EMPLOYEES)
        assert json.loads(db.query('SELECT settings FROM rule_config')[1][0][0]) == DEFAULT_RULES
        assert db.query('SELECT action FROM audit')[1] == [('demo_reset',)]
        content = db.query("SELECT content FROM sample_assets WHERE filename='naturax_orders.csv'")[1][0][0]
        assert len(list(csv.DictReader(io.StringIO(base64.b64decode(content).decode('utf-8-sig'))))) == 147
    finally:
        db.close()


def test_reset_rolls_back_when_mutation_fails(app, client, order):
    upload(client, [order])
    db = Local(app.state.engine.url.database)
    original = db.queries([('SELECT * FROM orders', ()), ('SELECT * FROM tasks', ()), ('SELECT * FROM audit', ())])
    query = db.query
    def fail_insert(sql, values=()):
        if sql.startswith('INSERT INTO employees'):
            raise RuntimeError('Simulated insertion failure')
        return query(sql, values)
    db.query = fail_insert
    try:
        with pytest.raises(RuntimeError, match='Simulated insertion failure'):
            reset(db, apply=True)
        assert db.queries([('SELECT * FROM orders', ()), ('SELECT * FROM tasks', ()), ('SELECT * FROM audit', ())]) == original
    finally:
        db.close()
