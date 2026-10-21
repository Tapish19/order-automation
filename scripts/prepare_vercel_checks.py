"""Wait for the live app and download its persistent sample files for real browser checks."""
import json
import sys
import time
from pathlib import Path

import httpx

base=sys.argv[1] if len(sys.argv)>1 else 'https://naturax-order-automation.vercel.app'
root=Path(__file__).resolve().parents[1]
target=root/'artifacts'/'hosting-samples'
target.mkdir(parents=True,exist_ok=True)
deadline=time.monotonic()+240
with httpx.Client(base_url=base,timeout=30) as client:
    while True:
        response=client.get('/api/health')
        if response.status_code==200:
            health=response.json()
            assert health['database']=='turso',health
            print('Public API is healthy; persistent Turso database connected.',flush=True)
            break
        if time.monotonic()>deadline:
            raise RuntimeError(f'Live API did not become healthy: HTTP {response.status_code}: {response.text[:200]}')
        time.sleep(5)
    for name in ['naturax_orders.csv','naturax_orders.xlsx','interview_invalid.csv','order_update_delivered.csv','manifest.json']:
        sample=client.get('/api/samples/'+name)
        sample.raise_for_status()
        (target/name).write_bytes(sample.content)
        print(f'Downloaded {name}: {len(sample.content)} bytes',flush=True)
    dashboard=client.get('/api/dashboard');dashboard.raise_for_status()
    result={'url':base,'health':health,'uploaded_rows_before_browser_checks':dashboard.json()['uploaded_rows'],
            'sample_reference':json.loads((target/'manifest.json').read_text(encoding='utf-8'))}
    (root/'artifacts'/'vercel-readiness.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
