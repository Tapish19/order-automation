"""Package complete source, samples and verification evidence without dependencies/runtime DBs."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root=Path(__file__).resolve().parents[1]
output=root/'artifacts'/'naturax-order-automation-source.zip'
files=[]
for folder in ['backend/app','backend/tests','frontend/src','frontend/e2e','scripts','samples']:
    files.extend(p for p in (root/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
files.extend(p for p in root.iterdir() if p.is_file() and (p.suffix in {'.md','.txt','.ini','.ps1','.sh'} or p.name=='.gitignore'))
files.extend(root/'frontend'/name for name in ['package.json','package-lock.json','tsconfig.json','vite.config.ts','playwright.config.ts','index.html'])
files.extend(root/'artifacts'/name for name in ['pytest-results.xml','browser-results.json','daily-report.csv','dashboard-desktop.png','dashboard-mobile.png','data-corrections.png','reassignment-audit.png','live-smoke.json','interview-evidence.json'])
with ZipFile(output,'w',ZIP_DEFLATED) as archive:
    for file in sorted(set(files)):
        if file.exists():
            archive.write(file,Path('naturax-order-automation')/file.relative_to(root))
print(f'{output}: {output.stat().st_size:,} bytes')
