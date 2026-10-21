"""Back up and reset demonstration data; never delete the database resource.

Inspection/backup is the default. --apply requires explicit user authorization.
Use Vercel env run for cloud credentials, or --local PATH for offline rehearsal.
Backups are SQLite files under ignored data/backups, including original audits.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.rules import DEFAULT_RULES
from backend.app.sample_data import generate_samples
from backend.app.timeutils import iso, utcnow

TABLES = ('employees', 'orders', 'imports', 'data_issues', 'tasks', 'audit',
          'rule_config', 'runtime_state', 'sample_assets')
EMPLOYEES = ('Aarav Shah', 'Meera Iyer', 'Rohan Verma', 'Priya Nair')


class Local:
    def __init__(self, path):
        self.connection = sqlite3.connect(path, isolation_level=None)
        self.connection.execute('PRAGMA foreign_keys=ON')

    def query(self, sql, values=()):
        cursor = self.connection.execute(sql, values)
        return ([c[0] for c in cursor.description] if cursor.description else [], cursor.fetchall())

    def close(self):
        self.connection.close()

    def queries(self, statements):
        return [self.query(sql, values) for sql, values in statements]


class Remote:
    def __init__(self):
        url, token = os.getenv('TURSO_DATABASE_URL'), os.getenv('TURSO_AUTH_TOKEN')
        if not url or not token:
            raise RuntimeError('Database environment variables are unavailable; nothing changed.')
        self.url = url.replace('libsql://', 'https://', 1).rstrip('/') + '/v2/pipeline'
        self.client = httpx.Client(timeout=30, headers={'Authorization': 'Bearer ' + token})
        self.baton = None

    def query(self, sql, values=()):
        return self.queries([(sql, values)])[0]

    def queries(self, statements):
        requests = [{'type': 'execute', 'stmt': {'sql': sql, 'args': [
            {'type': 'integer' if isinstance(v, int) else 'text', 'value': str(v)} for v in values]}}
            for sql, values in statements]
        response = self.client.post(self.url, json={'baton': self.baton, 'requests': requests})
        if response.status_code != 200:
            raise RuntimeError('Database request failed; response withheld to protect credentials.')
        payload = response.json()
        self.baton = payload.get('baton')
        def decode(cell):
            kind = cell['type']
            if kind == 'null':
                return None
            if kind == 'integer':
                return int(cell['value'])
            if kind == 'float':
                return float(cell['value'])
            if kind == 'blob':
                return base64.b64decode(cell['base64'])
            return cell['value']
        results = []
        for item in payload['results']:
            if item['type'] != 'ok':
                raise RuntimeError('Database statement failed; reset will roll back.')
            result = item['response']['result']
            results.append(([c['name'] for c in result['cols']],
                            [[decode(v) for v in row] for row in result['rows']]))
        return results

    def close(self):
        if self.baton:
            self.client.post(self.url, json={'baton': self.baton, 'requests': [{'type': 'close'}]})
        self.client.close()


def reset(db, apply=False):
    now = utcnow().replace(microsecond=0)
    # Prepare files before acquiring the cloud write lock.
    with tempfile.TemporaryDirectory(prefix='naturax-reset-') as directory:
        generate_samples(now, directory)
        assets = [(p.name, base64.b64encode(p.read_bytes()).decode('ascii'))
                  for p in Path(directory).iterdir()]
    db.query('BEGIN IMMEDIATE' if apply else 'BEGIN')
    try:
        _, schema = db.query("SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'")
        table_names = {name for kind, name, sql in schema if kind == 'table'}
        if table_names != set(TABLES):
            raise RuntimeError('Unexpected database schema; reset refused.')
        snapshot = dict(zip(TABLES, db.queries([(f'SELECT * FROM "{table}"', ()) for table in TABLES])))
        counts = {table: len(data[1]) for table, data in snapshot.items()}
        backup_dir = ROOT / 'data' / 'backups'
        backup_dir.mkdir(parents=True, exist_ok=True)
        path = backup_dir / ('before-demo-reset-' + now.strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8] + '.db')
        # Exclusive creation prevents replacing any previous backup.
        with path.open('xb'):
            pass
        with sqlite3.connect(path) as backup:
            for kind, name, sql in schema:
                if kind == 'table':
                    backup.execute(sql)
            for table, (columns, rows) in snapshot.items():
                placeholders = ','.join('?' for _ in columns)
                backup.executemany(f'INSERT INTO "{table}" VALUES ({placeholders})', rows)
            for kind, name, sql in schema:
                if kind == 'index':
                    backup.execute(sql)
            if backup.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Backup integrity check failed; reset refused.')
            if backup.execute('PRAGMA foreign_key_check').fetchall():
                raise RuntimeError('Backup foreign key check failed; reset refused.')
        print(json.dumps({'backup': str(path), 'original_counts': counts}))
        if not apply:
            db.query('ROLLBACK')
            return path
        # Foreign-key dependants first; all changes remain in one transaction.
        statements = [(f'DELETE FROM "{table}"', ()) for table in (
            'audit', 'tasks', 'data_issues', 'imports', 'orders',
            'employees', 'rule_config', 'runtime_state', 'sample_assets')]
        for employee_id, name in enumerate(EMPLOYEES, 1):
            statements.append(('INSERT INTO employees (id, name) VALUES (?, ?)', (employee_id, name)))
        statements.append(('INSERT INTO rule_config (id, settings) VALUES (1, ?)', (json.dumps(DEFAULT_RULES),)))
        statements.append(('INSERT INTO runtime_state (key, value) VALUES (?, ?)', ('last_evaluation', iso(now))))
        for filename, content in assets:
            statements.append(('INSERT INTO sample_assets (filename, content) VALUES (?, ?)', (filename, content)))
        statements.append(('INSERT INTO audit (responsible_user, action, timestamp, details) VALUES (?, ?, ?, ?)',
                 ('Demo maintenance', 'demo_reset', iso(now), json.dumps({
                     'reason': 'User requested a fresh starting state for the video',
                     'previous_record_counts': counts, 'backup_saved': True,
                     'restored_rules': DEFAULT_RULES, 'sample_reference_time_utc': iso(now)}))))
        db.queries(statements)
        for _, rows in db.queries([(f'SELECT count(*) FROM "{table}"', ())
                                   for table in ('orders', 'tasks', 'imports', 'data_issues')]):
            if rows[0][0] != 0:
                raise RuntimeError('Fresh-state verification failed; reset will roll back.')
        db.query('COMMIT')
        print('Fresh state committed: no orders/tasks/uploads/issues; default rules and employees; refreshed samples.')
        return path
    except Exception:
        db.query('ROLLBACK')
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--local', type=Path)
    args = parser.parse_args()
    db = Local(args.local) if args.local else Remote()
    try:
        reset(db, apply=args.apply)
    finally:
        db.close()


if __name__ == '__main__':
    main()
