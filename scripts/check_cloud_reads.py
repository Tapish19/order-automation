"""Verify the deployed API handles the concurrent read pattern used by the UI."""
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

base=sys.argv[1] if len(sys.argv)>1 else 'https://naturax-order-automation.vercel.app'
paths=['/api/employees','/api/rules','/api/dashboard','/api/dashboard?date_from=2099-01-01&category=dispatch_delay&employee=Meera%20Iyer&priority=urgent']

async def main():
    async with httpx.AsyncClient(base_url=base,timeout=90) as client:
        async def check(path):
            started=time.monotonic()
            response=await client.get(path)
            result={'path':path,'status':response.status_code,'seconds':round(time.monotonic()-started,3)}
            print(json.dumps(result),flush=True)
            response.raise_for_status()
            response.json()
            return result
        # Three waves mirror parallel page loads without issuing mutations.
        results=[]
        for _ in range(3):
            results.extend(await asyncio.gather(*(check(path) for path in paths)))
    target=Path(__file__).resolve().parents[1]/'artifacts'/'vercel-concurrent-reads.json'
    target.write_text(json.dumps({'url':base,'checks':results,'all_passed':True},indent=2),encoding='utf-8')

asyncio.run(main())
