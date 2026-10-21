"""Remove only the known, unassigned browser-test employee; retain an audit record.

Run using Vercel env run so credentials stay in the process environment.
Defaults to inspection; pass --apply to commit the guarded cleanup.
"""
import argparse
import json
import os
from datetime import datetime, timezone

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    name = 'Interview Specialist 1792552204893'
    employee_id = 5
    url = os.environ.get('TURSO_DATABASE_URL', '')
    token = os.environ.get('TURSO_AUTH_TOKEN', '')
    if not url or not token:
        raise SystemExit('Database environment variables are unavailable; nothing changed.')
    url = url.replace('libsql://', 'https://', 1).rstrip('/') + '/v2/pipeline'
    baton = None
    with httpx.Client(timeout=30, headers={'Authorization': 'Bearer ' + token}) as client:
        def execute(sql, values=()):
            nonlocal baton
            response = client.post(url, json={
                'baton': baton,
                'requests': [{'type': 'execute', 'stmt': {'sql': sql, 'args': [
                    {'type': 'integer' if isinstance(v, int) else 'text', 'value': str(v)}
                    for v in values]}}],
            })
            if response.status_code != 200:
                raise RuntimeError('Database request failed; credentials and response withheld.')
            payload = response.json()
            baton = payload.get('baton')
            result = payload['results'][0]
            if result['type'] != 'ok':
                raise RuntimeError('Database statement failed; transaction will roll back.')
            return result['response']['result']

        try:
            execute('BEGIN IMMEDIATE' if args.apply else 'BEGIN')
            result = execute('''SELECT e.id, e.name,
                (SELECT count(*) FROM orders WHERE assigned_employee=e.name),
                (SELECT count(*) FROM tasks WHERE assigned_employee=e.name)
                FROM employees e WHERE e.id=? AND e.name=?''', (employee_id, name))
            rows = result['rows']
            if not rows:
                print('Known test employee is already absent; nothing changed.')
            else:
                row = [cell.get('value') for cell in rows[0]]
                print(json.dumps({'employee_id': row[0], 'name': row[1],
                                  'assigned_orders': int(row[2]), 'assigned_tasks': int(row[3])}))
                if int(row[2]) or int(row[3]):
                    raise RuntimeError('Employee has assignments; cleanup refused.')
                if args.apply:
                    deleted = execute('DELETE FROM employees WHERE id=? AND name=?', (employee_id, name))
                    if deleted['affected_row_count'] != 1:
                        raise RuntimeError('Employee changed; cleanup refused.')
                    execute('''INSERT INTO audit (responsible_user, action, timestamp, details)
                        VALUES (?, ?, ?, ?)''', ('Demo maintenance', 'employee_removed',
                        datetime.now(timezone.utc).isoformat(), json.dumps({
                            'employee_id': employee_id, 'employee': name,
                            'reason': 'Remove unassigned employee left by hosted browser acceptance test',
                            'assigned_orders': 0, 'assigned_tasks': 0})))
                    print('Removed the test employee and recorded the cleanup in the audit trail.')
            execute('COMMIT' if args.apply else 'ROLLBACK')
        except Exception:
            if baton:
                execute('ROLLBACK')
            raise
        finally:
            if baton:
                client.post(url, json={'baton': baton, 'requests': [{'type': 'close'}]})


if __name__ == '__main__':
    main()
