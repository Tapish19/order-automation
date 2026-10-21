# Executed verification results

Final verification: **21 October 2026, Asia/Kolkata**. Environment: Windows, Python 3.13.14, Node.js 24.18.0, locally installed Microsoft Edge in headless mode. The actual installed Python versions are pinned in `requirements.lock.txt`; frontend versions in `frontend/package-lock.json`.

| Check | Actual result | Evidence |
|---|---|---|
| Backend rules/imports/lifecycle/reporting/scheduler/hosted mode | **70 passed**, 0 failed (15.68s) | `artifacts/pytest-results.xml`; `backend/tests/` |
| TypeScript compilation and Vite production build | **Passed**; compiled JS/CSS and index emitted | `frontend/dist/`; `npm run build` |
| Local browser acceptance flows against real backend/SQLite | **5 passed**, 0 failed, 0 skipped (13.5s) | `artifacts/browser-results.json`; HTML report at `artifacts/browser-report/index.html` |
| Public Vercel browser acceptance, real Turso storage | **5 passed**, 0 failed, 0 skipped (19.0s), including A–E | `artifacts/vercel-browser-results.json`; `artifacts/vercel-browser-report/index.html` |
| Public HTTPS runtime | **Passed**: frontend, both built assets, health, API docs, daily CSV; database reported Turso | `artifacts/live-smoke.json`; https://naturax-order-automation.vercel.app |
| Concurrent hosted read pattern | **12/12 HTTP 200** in three waves of four parallel reads, including combined future-date/type/employee/priority filters | `artifacts/vercel-concurrent-reads.json` |
| Protected hosted cron | Triggered through Vercel; an authenticated `Vercel daily cron` audit was persisted at **2026-10-21T03:11:34.644085+00:00** | `artifacts/vercel-persistence-before.json` → `cron_audit` |
| Single-server runtime on port 8000 | **Passed**: homepage 200, both built assets 200, API/health 200, API docs 200, daily CSV 200 | `artifacts/live-smoke.json`; `scripts/smoke_live.py` |
| Desktop/mobile visual capture | Captured; mobile 390×844 has no document-width overflow; no page errors in the combined final browser flow | `artifacts/dashboard-desktop.png`, `dashboard-mobile.png`, `data-corrections.png`, `reassignment-audit.png` |

## Interview challenges: observed evidence

The following reference numbers were retained from the original local interview run at **01:31 IST** on this date, summarized read-only in **`artifacts/interview-evidence.json`**. They are observed demonstration results, not projected business impact. The later local and hosted runs above also passed; live age-dependent counts naturally change as the sample records age.

| Challenge | Observed result |
|---|---|
| **A — invalid input** | `interview_invalid.csv`: **3 rows**, **1 inserted**, **2 rejected**. Browser showed filename, source row and phone explanation, corrected the phone through the UI, and verified the accepted record persisted. Invalid-date information remained an issue. |
| **B — dispatch 24h → 12h** | Saved rules through the UI. Dispatch exceptions increased **18 → 37**, **19 additional**. Browser verified changed API counts and actual dashboard filters. |
| **C — repeated uploads** | Three 147-row uploads: new unique orders **136 / 0 / 0**, unchanged rows **0 / 136 / 136**, task count **103 / 103 / 103**. Browser compared complete task ID sets for equality. Uploaded source rows reached **441** with **136 unique orders**. |
| **D — overdue reassignment** | Task **#88**, order **NX-1117**, changed from **Aarav Shah → Priya Nair**, status **in_progress**. Both persisted after reupload and page reload. A separate backend test opened a completely new app/engine against the same on-disk database and verified persistence after restart. |
| **E — audit trail** | Reassignment recorded responsible user **Live Interview Manager**, UTC timestamp **2026-10-20T20:01:49.523666+00:00** (**21 Oct 2026, 01:31:49 IST**), old/new owners, overdue=true, order/task IDs and handover note. Browser opened and filtered the audit screen to confirm the record. |

## Backend coverage

- Strict 2-hour boundary: 7,199 / 7,200 / 7,201 seconds.
- Dispatch boundary: 86,399 / 86,400 / 86,401 seconds; documented order-time fallback and real confirmation-time override.
- High-value boundary: ₹4,999.99 / ₹5,000 / ₹5,000.01.
- Full expected-delivery timestamp: just before / exactly / just after.
- Date-only expected delivery: 23:59:59 IST excluded, following midnight included.
- Naive timestamps consistently interpreted in IST and normalized to UTC.
- Failed attempt without optional attempt timestamp: urgent priority and immediate deadline.
- Delivered/cancelled/returned orders excluded from undelivered rules.
- Exact ten-column CSV and XLSX, blank dispatch on unshipped orders, Excel date-only precision.
- Missing/invalid ID, phone, status, value, date, employee, payment and required shipment dates; partial valid-row acceptance.
- Unreadable formats/encoding/CSV widths and duplicate header rejection.
- In-file identical/conflicting duplicates; identity collision versus legitimate update.
- Valid corrections, invalid correction rejection, missing-ID correction and source issue resolution.
- Invalid newer snapshots pause new exception creation while preserving the last accepted order/tasks.
- Repeated and concurrent reuploads retain one active task per category, fixed detection times/deadlines and persistent ownership.
- Manual closure, automatic resolution, history retention and a new task on a later recurrence.
- Date/type/employee/priority API filters, pending union filter and immediate-priority ordering.
- Daily report includes selected-date new detections, prior-date unresolved tasks, selected-date resolved detections, overdue/high-priority work and employee sections.
- Employee/task/rule/responsible-user validation.
- Periodic scheduler detects a newly aged order **without an upload or manual evaluation**. Test uses a controllable clock and shortened scheduler interval; the live default is 60 seconds.
- Hosted request evaluation, daily cron authentication, consistent sample files across app instances, rejection of ephemeral SQLite on Vercel, and remote transaction policy tested using independent engines.

## Hosted verification

The final real browser run used **https://naturax-order-automation.vercel.app**, Vercel Python 3.12 functions in Mumbai and the provisioned **Turso Starter** database. It used server-generated CSV/Excel files persisted in that database. The final five flows passed in 19.0 seconds without test retries or skipped flows; read-only transport requests allow a bounded retry for connection resets.

The hosted checks imported/corrected assessment records, changed the dispatch threshold through the UI, compared persistent task IDs across repeated uploads, reassigned an overdue task, opened its audit record with user/timestamp, downloaded the report, uploaded Excel and a delivered-order update, and checked the mobile layout.

Afterward, the rules were restored to the assessment defaults **2h / 24h / ₹5,000 / 4h follow-up**. The live database held **138 unique assessment orders**. Task **#88 / NX-1117** remained assigned to **Priya Nair**, **in_progress**, with its original detection/deadline **2026-10-21T02:53:24.373905+00:00**. Its reassignment by **Live Interview Manager** was recorded at **2026-10-21T03:09:59.182234+00:00**. `scripts/check_hosted_state.py` captures this state and verifies it after a subsequent production deployment; evidence files are named `artifacts/vercel-persistence-before.json` and `artifacts/vercel-persistence-after.json`.

Runtime fixes included removing unsupported libSQL timeout/PRAGMA options, storing generated workbook bytes as base64 text instead of unsupported DB-API binary bindings, preloading reconciliation/import lookups, and separating normal read transactions from mutation locks. These issues were found and corrected before the final clean live test run.

## Browser flows

1. Real CSV upload, all five categories, three uploads with stable task IDs and real dashboard counts.
2. Deliberately invalid file, partial acceptance, correction screen/source evidence, correction persisted through the backend.
3. 24→12-hour rule save, changed exceptions, filtered API/dashboard results.
4. Overdue task ownership/status change, repeat import, reload, filtered audit record with user/time/details.
5. Real Excel upload, no duplicate tasks, employee creation, actual daily CSV download, delivered-order update with exception resolution, order register, mobile layout and no page errors.

The sample downloaded report is `artifacts/daily-report.csv`. Initial browser harness failures (Windows launch path, accessible-name badge selection and an asynchronous audit-filter selector) were corrected; the final JSON report above records a clean run without retries or skipped flows.

## Nonblocking warnings and verification limits

- The installed Starlette TestClient emits one deprecation warning about its `httpx` transport. All 70 tests complete successfully; this is a test tooling warning.
- Vite reports a JS chunk above its 500 kB advisory threshold (approximately 633 kB, 189 kB gzip, including React/Recharts). The build succeeds and browser flows pass. This local interview application has not been load-tested or performance-benchmarked.
- Playwright's runner emits an environment color-output warning. It does not affect assertions.
- No Shopify, WhatsApp, courier or production NaturaX integration was built or tested; none is needed for the assessment. Production authentication/RBAC, multi-server deployment, independent tamper-resistant audit storage, historic pending-state reconstruction and actual financial/time-saving outcomes are outside this local demonstration.
- The illustrative 305-minute/day administrative saving in README is explicitly assumption-based, not a measured result.
- Local test servers were stopped after verification. The Vercel site remains live. Local execution uses `start.ps1`; the default `data/naturax.db` is preserved and begins with no imported orders. Local browser tests use separate databases; hosted checks use persisted assessment records on the new demonstration site.
- Vercel Hobby provides **daily unattended cron**, not minute-level unattended execution. Hosted rule evaluation also runs on uploads/updates/manual actions and API activity when due. This limitation is explicit in README and DEPLOYMENT.md; no paid plan was activated.

## Reproduce

```powershell
# Project root
.\.venv\Scripts\python.exe -m pytest -q --junitxml=artifacts/pytest-results.xml
cd frontend
npm run build
npm run test:e2e
cd ..
.\.venv\Scripts\python.exe scripts/collect_interview_evidence.py
```

To repeat the single-server smoke check, run `start.ps1` in one terminal and `.\.venv\Scripts\python.exe scripts/smoke_live.py` in another. Each browser run creates a fresh SQLite database and stops its own server afterward. The source submission ZIP can be reproduced with `.\.venv\Scripts\python.exe scripts/package_submission.py`.
