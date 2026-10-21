"""Read-only verification of a running built app. Run after start.ps1."""
import json
import re
import sys
from pathlib import Path

import httpx

base=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8000'
with httpx.Client(base_url=base, timeout=15) as client:
    health=client.get('/api/health'); health.raise_for_status()
    homepage=client.get('/'); homepage.raise_for_status()
    assert 'NaturaX' in homepage.text
    assets=re.findall(r'(?:src|href)="(/assets/[^\"]+)"',homepage.text)
    assert len(assets)>=2
    for asset in assets:
        client.get(asset).raise_for_status()
    client.get('/docs').raise_for_status()
    rules=client.get('/api/rules'); rules.raise_for_status()
    dashboard=client.get('/api/dashboard'); dashboard.raise_for_status()
    report=client.get('/api/reports/daily.csv'); report.raise_for_status()
    assert 'first_detected_at_utc' in report.text
result={'base_url':base,'health':health.json(),'homepage_status':homepage.status_code,'asset_count':len(assets),
        'api_docs_status':200,'report_status':report.status_code,'rules':rules.json(),'unique_orders':dashboard.json()['unique_orders_all_time']}
target=Path(__file__).resolve().parents[1]/'artifacts'/'live-smoke.json'
target.write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
