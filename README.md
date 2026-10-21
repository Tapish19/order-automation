# NaturaX D2C Order Follow-up Automation

A complete local application: React + Vite + TypeScript + Tailwind CSS, Recharts, Python + FastAPI, Pandas, SQLAlchemy and SQLite. The browser reads and changes the real backend database. No Shopify account, WhatsApp connection, courier API, API keys, or production NaturaX data is needed. The initial database is empty; sample orders are imported explicitly.

## Hosted application on Vercel

Live URL: **https://naturax-order-automation.vercel.app**. See `DEPLOYMENT.md` for hosting configuration and verification evidence. The hosted database uses **Turso's SQLite-compatible service**; the local setup below continues using the local SQLite file. Hosted sample files are generated once and persisted in the database so repeat uploads use the same reference times across function instances. The hosted demo contains assessment records imported through the actual API during verification, not NaturaX production data.

Vercel Hobby functions do not run a permanent 60-second process. Hosted rules evaluate after uploads/corrections/rule changes/manual evaluation, on API activity when 60 seconds have elapsed since the last evaluation, and via an authenticated **daily** cron at `02:30 UTC` (08:00 IST, subject to Hobby scheduling precision). The browser's minute refresh creates API activity while open. **When the application is closed, Hobby only provides daily scheduled detection, not minute-level detection.** Local `start.ps1` retains the continuous 60-second scheduler while its server runs. A more frequent hosted unattended schedule requires a suitable scheduler/plan; no paid plan was enabled.

Hosted uploads are limited to **4 MB**, below Vercel's function payload ceiling. Local uploads retain the **10 MB** limit. The frontend reads the actual limit from `/api/meta`. The same 50,000-row validation cap applies. The production site is an interview demonstration with a self-declared audit user; do not treat it as authenticated production order operations.

## Setup on Windows (PowerShell)

Prerequisites: Python **3.12–3.13**, Node.js **22.12+ or 24**, npm. Tested here with Python 3.13.14 and Node 24.18.0. The tested NumPy lockfile requires Python 3.12+. Internet access is needed once to install packages; the application runs locally afterward.

```powershell
cd C:\Users\Abhishek\Downloads\naturax-order-automation
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
cd frontend
npm ci
npm run build
cd ..
.\start.ps1
```

Open **http://127.0.0.1:8000**. API documentation: **http://127.0.0.1:8000/docs**. The backend serves the built frontend, so the interview needs just one server. Stop it with Ctrl+C. If PowerShell execution policy blocks the launcher, run:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Start with **Upload orders → Import sample orders**, or choose the supplied CSV or Excel file. Review **Data corrections** for rejected rows. All metrics begin at zero until a real upload is performed. Identify yourself using the **Responsible user** field before changing tasks or settings; this value is sent as `X-User` and stored in the audit trail.

For Linux/macOS, replace `.venv\Scripts\python.exe` with `.venv/bin/python`, create the environment with `python3 -m venv .venv`, and use `bash start.sh`. The npm commands are the same. Lockfile pins record the versions installed and tested here; `requirements.txt` also specifies supported dependency ranges.

## Development

In terminal 1, from the project root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

In terminal 2:

```powershell
cd frontend
npm run dev
```

Open http://127.0.0.1:5173. Vite proxies `/api` to port 8000. Optional `VITE_API_PROXY` changes this target. Rebuild the frontend to update the single-server version. Use **one Uvicorn worker** for this SQLite interview application; the process serializes mutations with a lock and a database partial unique index enforces one active exception episode per order/category.

## Exact ten-column format

Both `samples/naturax_orders.csv` and `samples/naturax_orders.xlsx` contain **only** these ten headers:

1. Order ID
2. Order date
3. Customer name
4. Phone number
5. Order value
6. Payment type (Prepaid or COD)
7. Order status
8. Dispatch date
9. Expected delivery date
10. Assigned employee

`confirmed_at` and `delivery_attempt_at` are optional extra columns. Human-readable `Confirmed at` / `Delivery attempt at`, and equivalent snake_case required columns, are accepted too. `Payment type` is also accepted. Upload UTF-8 CSV (BOM accepted), XLSX, or XLS. Excel reads the **first worksheet**; formulas must have cached values. Save phone numbers as text to retain country prefixes/leading digits. 10 MB and 50,000 source rows per upload are the practical limits.

Use ISO `YYYY-MM-DD` dates or `YYYY-MM-DD HH:MM[:SS]` / ISO `T` timestamps, optionally ending in `Z` or an explicit `+05:30` offset. Ambiguous dates like `03/04/26`, unformatted numeric Excel date serials, impossible dates, invalid status/value/payment/phone, future occurrence timestamps, and inconsistent event chronology produce correction issues.

Supported statuses: `unconfirmed`, `confirmed`, `dispatched`, `out_for_delivery`, `failed_delivery`, `delivered`, `cancelled`, `returned`. Spaces/hyphens normalize to underscores. Aliases: `pending`/`pending_confirmation` → unconfirmed; `shipped` → dispatched; `delivery_failed`/`failed_delivery_attempt` → failed_delivery. Payment must be `Prepaid` or `COD`.

### Status-dependent validation and time assumptions

- ID, order date, customer, phone, nonnegative INR value (up to two decimals), payment, recognized status, and assigned employee are required. New nonblank employee names in an upload enter the team directory.
- **Blank dispatch dates are valid for unconfirmed and confirmed orders.** Shipped, out-for-delivery and failed-delivery records require a dispatch date and expected delivery. Unshipped statuses with a dispatch date are contradictory and require correction. Terminal orders may lack shipment dates.
- Unconfirmed orders need a full order timestamp to measure hours. **Confirmed orders use `confirmed_at` if supplied. When it is absent, the documented assessment assumption is to measure dispatch delay from `order_date`, but only when `order_date` contains a time.** This can overstate a dispatch delay when confirmation occurred much later. It is a proxy, not evidence of the actual confirmation time. A date-only order date cannot support this hourly fallback and becomes a data-correction issue. No missing order/confirmation/attempt time is invented.
- A confirmed order with a valid `confirmed_at` may have a date-only order date. Valid timestamps are normalized to UTC for storage; naive timestamps mean **Asia/Kolkata**. Screens display IST, and calendar filters/report boundaries use IST, regardless of the computer timezone.
- **Date-only expected delivery includes the entire local calendar day.** `2026-10-21` becomes overdue at `2026-10-22 00:00:00 Asia/Kolkata` (18:30 UTC on October 21). For a full expected timestamp, the clock must be strictly after that instant. This delivery-day policy is explicit; the original date remains stored as a date.
- XLSX cell number formats preserve whether an Excel datetime was presented as a date or a time. For legacy XLS midnight datetimes without usable precision metadata, midnight is conservatively treated as date-only; use ISO text timestamps when precision matters.
- A high-value nonterminal order needs expected delivery even if not yet dispatched, because rule 5 does not require dispatch. Low-value unshipped orders can leave expected delivery blank. Every supplied date, including optional dates, must be valid.
- Invalid rows are quarantined, not written over the last valid order snapshot. An unresolved rejected update for an existing ID pauses new exception evaluation for that order; existing tasks and history remain intact. This avoids creating a new exception from an uncertain newer status/value. A valid correction or reimport resolves earlier errors for that ID and resumes evaluation. If a changed rule makes existing data insufficient, the engine creates an issue and leaves existing task episodes intact until the data can be evaluated safely; unknown does not mean resolved.

## Business rules and deadlines

| Rule | Exact default condition | Priority | Deadline/action |
|---|---|---|---|
| Unconfirmed | Status unconfirmed and age **>2 hours** | Medium | 4h from detection; call to confirm |
| Dispatch delay | Status confirmed, no dispatch, age **>=24 hours** from known confirmation or documented order-time fallback | High | 4h; unblock warehouse dispatch |
| Delivery delay | Shipped status, clock past expected delivery, not delivered | High | 4h; follow up with courier/customer |
| Failed delivery | Status failed_delivery; optional attempt time is not required | **Urgent** | **At detection, immediately**; arrange reattempt |
| High-value delay | Value **>₹5,000**, nonterminal, clock past expected delivery | Urgent | 4h; manager/customer escalation |

An order exactly two hours old does not trigger rule 1. An order worth exactly ₹5,000 does not trigger rule 5. At exactly 24 hours a confirmed order has exhausted its dispatch window and triggers rule 2. Delivered, cancelled, and returned orders are excluded from all five active exception rules. A shipment can meet multiple categories; each category gets a distinct task. The **Business rules** screen configures hour/value thresholds and the default follow-up window. Failed delivery remains immediate regardless of this window. Changes are audited and run evaluation in the same transaction.

Evaluation runs on startup, after each import/correction, after saving rules, on **Evaluate rules**, and every 60 seconds while the backend is running. Existing deadlines and first-detection times never move forward on reuploads or reevaluation. The process must remain running for unattended detection; overdue status is computed from the current clock.

## Validation and duplicate workflow

The **Data corrections** screen shows filename, physical source row (header is row 1), order ID if known, field, explanation, recommended correction, severity, status, and the editable original record. **Correct row** resubmits the full record to server-side validation and imports it only if valid; related errors for that original row are resolved and the correction is audited.

- Identical duplicate rows **within a file**: import one; skip repeated copies with a visible warning.
- Conflicting repeated IDs **within a file**: reject all conflicting copies, with an issue on each row. No arbitrary last-row-wins behavior.
- ID already in SQLite, same customer name (case-insensitive), normalized phone and normalized order date: a legitimate update to status, amount, payment, shipment dates or employee; identical records count as unchanged.
- ID already present with different customer/phone/order date: reject as an identity collision. Verify the ID/source rather than silently attaching one customer's data to another. This conservative version does not provide a separate identity-override workflow; correct the incoming identity or use the proper order ID.
- Invalid rows do not prevent independent valid rows importing. Completely unreadable/unsupported files, malformed CSV row widths, ambiguous duplicate headers, and files beyond limits return a clear error with no import transaction. Missing columns become missing per-row values subject to status-dependent validation; the upload response also lists missing headers. Empty readable files contain zero imports.

**Uploaded rows** is the sum of all readable imported batch source rows, including rejected rows, repeated files, duplicate rows, and correction submissions. **Unique orders** counts distinct accepted order IDs, so repeated uploads can increase uploaded rows without increasing orders/tasks. Import history separates new, updated, unchanged, rejected and duplicate rows. For an identical in-file duplicate, `duplicate_rows` accounts for the skipped row; for conflicting duplicates, those rows count both as rejected and duplicate, so duplicate count is a diagnostic subset, not an extra additive bucket.

## Task and exception lifecycle

`tasks` stores both the exception episode and its follow-up task: category, reason, priority, owner, next action, deadline, status, **first_detected_at**, condition_active and resolution time. Customer details join to the latest accepted order, and the API exposes them with every task. The database partial unique index on `(order_id, category) WHERE condition_active=1` is the idempotency guarantee. Uploads and evaluations are transactional and serialized within the single local server.

1. A newly true rule creates a persistent open task and an assignment audit record.
2. Reimporting/updating an order preserves existing task IDs, owner/reassignments, deadlines, status, first detection and history. Changing an order's default employee only affects future tasks; it never steals an existing task assignment.
3. A manager may set open → in progress → resolved, reopen a manually closed task while its condition remains active, or reassign any task, including overdue work. A manual resolution is a manager disposition of that episode and is not automatically undone merely because the imported condition is unchanged.
4. When a validated order/rule change makes a condition false, its existing episode becomes inactive/resolved. History remains. A condition-cleared episode cannot be reopened manually.
5. If that condition later becomes true again, create a **new episode/task with a new first-detection time**. Do not erase the old resolution, reassignment or status history.

Every task assignment, reassignment and status change stores order ID, task ID, responsible user, action, UTC timestamp and change details. Reassignment includes former/new owners, overdue-at-change and optional note. Order default assignment changes, imports, corrections and rule changes are audited as well. Audit records have no update/delete endpoint.

## Dashboard, filters and report precision

**Dashboard** shows uploaded source rows, unique orders, orders with unresolved tasks, open/in-progress tasks, overdue tasks, category counts, employee pending workload, and a high/urgent priority desk. Chart bars and team counts come from SQLite-backed API responses. Metric cards navigate to working screens; tasks can be managed directly from the priority desk.

The shared filters call `/api/dashboard`, `/api/tasks`, and `/api/orders` with `date_from`, `date_to`, `category`, `employee`, and `priority`; filtering happens in the backend, not just visually. Dates select the order's IST calendar date, inclusively. Task owner filters use the current task assignment; the orders register may also show an order whose default owner matches. Unresolved counts use open + in_progress, whereas task/history filters can include resolved episodes. Upload totals, all-time unique count, and correction count are explicitly lifetime figures, independent of task filters. Search, status, and overdue-only filters are also available in the task register. Tables paginate results locally after the API has filtered them.

**Daily reports** downloads a real CSV from `/api/reports/daily.csv?report_date=YYYY-MM-DD`. Sections:

- `new_exceptions`: first detected in `[selected IST midnight, following IST midnight)`, including those now resolved.
- `unresolved_exceptions`: all currently open/in-progress tasks, across all dates.
- `overdue_tasks`: current unresolved tasks past their deadlines.
- `high_priority_cases`: current unresolved high and urgent tasks.
- `employee_pending_actions`: all pending task details sorted by owner.
- `employee_pending_summary`: pending counts per employee.

New is based on the persisted first detection, **not order date or reupload date**. A task can occur in multiple sections on purpose; do not sum CSV rows to infer unique tasks. Reports contain customer details, category/reason, action, owner, value, priority, deadline, task status, first detection, selected date and snapshot time. Empty sections produce no data rows. UTF-8 BOM supports Excel; formula-leading text is escaped. This is a current snapshot with selected-date new detections, **not a historical reconstruction of pending status at that date**.

## Sample dataset

`samples/` includes a **147-row CSV and matching XLSX**, an invalid interview file, a delivered-order update and a generation manifest. The main dataset has 120 realistic base orders plus threshold, data-error and duplicate cases: clean delivered/cancelled orders, all five exception categories, missing phone/status/value/dates, invalid dates/status, identical and conflicting duplicates. With default rules at the manifest reference time, **136 distinct orders** import, **10 rows reject**, and **1 identical duplicate row skips**.

`EDGE-*` rows cover one second below/exactly/above 2h, 12h, 24h and expected timestamp, plus ₹4,999.99 / ₹5,000 / ₹5,000.01. A date-only expected delivery case demonstrates end-of-day IST behavior. Tests freeze the evaluation clock to verify exact boundaries; the live clock advances, so an exactly-two-hour fixture will naturally become older than two hours after generation.

Refresh date-sensitive fixtures **before using a fresh demo database**:

```powershell
.\.venv\Scripts\python.exe scripts/generate_samples.py
```

Keep the generated files unchanged for repeated-upload challenge C. Regenerating their dates against existing identical IDs triggers the deliberate identity-collision protection; it does not erase database history. To use a fresh isolated demo, point to a **new** SQLite filename before launching, without deleting existing data:

```powershell
$env:NATURAX_DATABASE_URL='sqlite:///data/interview-fresh.db'
.\start.ps1
```

`NATURAX_DATABASE_URL` is optional. The default is the absolute project path `data/naturax.db`. `data/` is created automatically and survives server restarts. Back up the SQLite database with the application stopped; keep the database and any SQLite WAL/SHM files together if copying while running.

## Automated checks

From the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --junitxml=artifacts/pytest-results.xml
cd frontend
npm run build
npm run test:e2e
```

Backend tests use separate on-disk temporary databases and a controllable clock. Browser tests use a new uniquely named database in `artifacts/`, launch the built application on port **8011**, and exercise actual uploads, corrections, filters, task changes, reports and audit screens. Run `npm run build` before browser tests so the backend serves the latest bundle. Microsoft Edge is selected automatically on Windows when installed. Else install Chromium with `npx playwright install chromium`; optionally set `PLAYWRIGHT_CHANNEL=chrome` or `msedge` for another installed browser. Browser screenshots, traces on failure, JSON/HTML results and an example downloaded CSV go in `artifacts/`.

See **TEST_RESULTS.md** for the actual executed results and **DEMO_SCRIPT.md** for the timed five-minute interview. **REQUIREMENTS_CHECKLIST.md** maps every requirement to implementation files/endpoints/screens and acceptance evidence.

## Business impact: the five assessment questions

1. **How manual work is reduced:** one batch upload replaces checking each row, calculating ages, comparing delivery/value conditions and writing follow-up lists. The engine validates rows, evaluates five rules, assigns owners, maintains task state and builds the daily handover. Staff still make the customer/courier decisions and calls.
2. **How orders avoid being forgotten:** unresolved tasks remain in SQLite across uploads/restarts, have an owner and fixed deadline, appear in employee queues/overdue counters, and stay in daily reports until disposition. Periodic evaluation catches conditions that become true after import. Repeated uploads do not bury older work under duplicate tasks.
3. **KPIs:** orders requiring attention / unique accepted orders; unresolved and overdue task counts; pending tasks per employee; share of urgent cases past deadline; median detection-to-resolution time from persisted timestamps; time to first status change from audit records; recurrence rate by category; percentage of source rows rejected; eventual dispatch/delivery delay rate after corrected updates. Current dashboard exposes counts/category/workload; duration and outcome KPIs can be derived from persisted task/audit/order history and are not presented as already measured improvements.
4. **Daily time-saving estimate:** assume **200 orders/day**, manual triage **90 seconds/order**, and **20 exceptions/day** requiring **2 minutes each** to record/assign. Baseline administration = 200×90÷60 + 20×2 = **340 minutes/day**. Assume automation still needs **15 minutes** for upload/corrections and **20 minutes** reviewing/reassigning tasks/report = **35 minutes/day**, an illustrative **305 minutes (5h 5m, about 90%) of administrative time saved**. These are explicit assumptions, not observed results. Customer conversations, courier responses and implementation/maintenance time are excluded from both estimates. Validate by timing representative staff sessions before/after and recording volumes/errors.
5. **Limitations:** source freshness determines accuracy; hourly rules cannot infer missing times; order-time fallback may overestimate confirmation delay; Excel source precision matters; manual status dispositions require judgment; no actual courier/customer messages are sent; background detection requires the server running; a local single-process SQLite app has a modest scale ceiling. This interview version uses a self-declared responsible user and loopback binding, not production authentication/RBAC or independently tamper-proof audit storage. Reports do not reconstruct historical pending state. Identity collisions require source verification; there is no override. Real shipping outcomes, sales recovery and measured time savings are not claimed.

## Source layout

```text
backend/app/main.py          FastAPI endpoints, scheduler, server-side filters/reports
backend/app/models.py        SQLite/SQLAlchemy orders, tasks, issues, batches, audit, rules
backend/app/database.py      SQLite initialization, WAL, employee/rule defaults
backend/app/validation.py    Pandas CSV/Excel parsing and status-dependent validation
backend/app/timeutils.py     IST boundaries, UTC normalization, date precision
backend/app/rules.py         Five business rules and deadline policy
backend/app/services.py      Imports, identity checks, task episode reconciliation, audits
backend/app/sample_data.py   Real fixture generation (CSV/XLSX + interview files)
backend/tests/              Backend rule, import, lifecycle and interview tests
frontend/src/App.tsx         All eight working screens, task/correction dialogs
frontend/src/api.ts          Real API calls and IST formatting
frontend/src/styles.css      Tailwind and responsive application styling
frontend/e2e/               Browser acceptance tests against a real isolated backend
samples/                    Submission datasets and generation reference time
artifacts/                  Executed check results, screenshots and sample report
```
