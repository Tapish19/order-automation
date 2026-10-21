"""Summarize the most recent real browser-test SQLite database, read-only."""
import json
import sqlite3
from pathlib import Path

root=Path(__file__).resolve().parents[1]
database=max((root/'artifacts').glob('browser-*.db'),key=lambda path:path.stat().st_mtime)
with sqlite3.connect(f'file:{database.as_posix()}?mode=ro',uri=True) as connection:
    connection.row_factory=sqlite3.Row
    imports=[dict(row) for row in connection.execute('SELECT * FROM imports ORDER BY id')]
    audits=[dict(row) for row in connection.execute('SELECT * FROM audit ORDER BY id')]
    for record in audits:
        record['details']=json.loads(record['details'])
    assignments=[a for a in audits if a['action']=='task_assigned']
    rule_changes=[a for a in audits if a['action']=='rules_changed']
    change=next(a for a in rule_changes if a['details']['settings']['dispatch_hours']==12)
    dispatch_before=sum(a['details']['category']=='dispatch_delay' and a['timestamp']<change['timestamp'] for a in assignments)
    dispatch_after=sum(a['details']['category']=='dispatch_delay' for a in assignments)
    handovers=[a for a in audits if a['action']=='task_reassigned']
    reassigned=handovers[-1]
    persistent=dict(connection.execute('SELECT * FROM tasks WHERE id=?',(reassigned['task_id'],)).fetchone())
    proof={
        'source':'Real Playwright browser acceptance run against FastAPI and on-disk SQLite',
        'database':database.name,
        'A_invalid_file':next(b for b in imports if b['filename']=='interview_invalid.csv'),
        'B_dispatch_threshold':{'old_hours':24,'new_hours':12,'exceptions_before':dispatch_before,'exceptions_after':dispatch_after,'additional_exceptions':dispatch_after-dispatch_before},
        'C_first_three_uploads':[{'batch_id':b['id'],'rows':b['total_rows'],'inserted':b['inserted'],'updated':b['updated'],'unchanged':b['unchanged']} for b in imports[:3]],
        'C_task_counts_after_first_three_uploads':[sum(a['timestamp']<(imports[i+1]['created_at'] if i+1<len(imports) else '9999') for a in assignments) for i in range(3)],
        'D_persisted_task':{key:persistent[key] for key in ['id','order_id','assigned_employee','status','first_detected_at','deadline']},
        'E_reassignment_audit':reassigned,
    }
target=root/'artifacts'/'interview-evidence.json'
target.write_text(json.dumps(proof,indent=2),encoding='utf-8')
print(json.dumps(proof,indent=2))
