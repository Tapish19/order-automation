# Vercel deployment

Application: **https://naturax-order-automation.vercel.app**

GitHub: **https://github.com/Tapish19/order-automation**

## What runs where

- React/Vite/TypeScript/Tailwind/Recharts build from `frontend/` and are served by the Vercel FastAPI deployment.
- FastAPI/Pandas/SQLAlchemy run as a Python **3.12** Vercel function in **bom1 (Mumbai)**.
- Durable records use the **Turso Starter ($0/month)** SQLite-compatible database, also in Mumbai. Orders, rules, tasks, audit records, validation issues, imports, runtime evaluation markers and generated sample files live there. No SQLite file in `/tmp` is used as persistent storage.
- Local execution remains file-backed SQLite. The Linux-only libSQL driver is declared in `pyproject.toml` for the hosted build; Windows local development uses the standard Python SQLite driver.

The Vercel project is `naturax-order-automation`, project ID `prj_whtdrhB1OheTLGZ87stNzjUmPJYG`, in `tapish19s-projects`. GitHub is connected for deployments. The user completed Vercel CLI login and the required Turso Marketplace terms in the browser.

## Deployment files

| File | Purpose |
|---|---|
| `vercel.json` | FastAPI framework, frontend build command, Mumbai region and daily cron |
| `pyproject.toml` | Python 3.12, deployment dependencies, custom FastAPI entrypoint and static asset handling |
| `.vercelignore` | Excludes dependencies, local databases, test artifacts, environment files and installed provider guidance from uploads |
| `backend/app/database.py` | Chooses local SQLite or remote libSQL; no filesystem fallback on Vercel; transaction locking across instances |
| `backend/app/main.py` | Serverless request evaluation, authenticated cron, actual hosted upload limit, database-backed sample download/generation |
| `backend/app/models.py` | `RuntimeState` and `SampleAsset` preserve evaluation timing and sample files across instances |

## Environment variables

Configure these **in Vercel**, never in source control or frontend variables:

- `TURSO_DATABASE_URL`: injected by the connected Turso resource.
- `TURSO_AUTH_TOKEN`: injected by the integration; backend only.
- `CRON_SECRET`: independently generated sensitive secret for the cron endpoint.

`VERCEL=1` is supplied by Vercel and selects hosted behavior. The adapter refuses to silently fall back to ephemeral local SQLite if cloud credentials are missing. `.env*` and `.vercel/` are ignored by Git and deployment source selection. No credentials are included in the submission.

To deploy from this linked project after running checks:

```powershell
npx vercel deploy --prod --scope tapish19s-projects
```

The Git repository is also connected. Changing the public source and pushing `main` can create a production build. Preview deployments need their own deliberately scoped database variables; the provisioned integration is connected to **Production**. A preview without credentials fails clearly rather than losing data into temporary storage.

## Persistence and concurrency

Remote mutation transactions use `BEGIN IMMEDIATE`, so read/decide/write operations are protected across function instances in addition to the active-exception unique index. Ordinary reads use a normal read transaction and do not take the exclusive write lock. Reconciliation preloads tasks/issues in sets, and imports preload order/employee identities, to avoid one network lookup per field or order. An instance caches its most recent evaluation check; the authoritative evaluation time remains in SQLite. Remote connections use `NullPool`; local connections retain normal SQLite configuration. Driver-specific local pragmas/timeout arguments are not sent to the remote service. Generated XLSX/CSV assets are stored as base64 text because this remote DB-API does not expose `sqlite3.Binary`; exact bytes are restored for downloads.

The cloud DB is separate from deployments. Redeploying the function does not regenerate orders, clear task assignments or reset audit history. `RuntimeState` persists the last evaluation time. Sample assets retain one generation reference until `POST /api/demo/generate` is explicitly requested. Regenerating samples does not delete orders; use a new dataset identity/fresh database if rebasing dates conflicts with an already imported ID.

## Scheduling limits

Local: evaluate every 60 seconds while the backend runs.

Hosted: evaluate after imports/corrections/configuration, on manual evaluation, and on API activity if the persisted last evaluation is at least 60 seconds old. A daily Vercel cron calls `/api/cron/evaluate` at `30 2 * * *` (08:00 IST). The endpoint rejects missing/incorrect `Authorization: Bearer <CRON_SECRET>`; Vercel sends its configured secret automatically.

**Vercel Hobby permits daily cron jobs only, with per-hour timing precision. When nobody is using the site, this deployment does not provide unattended one-minute detection.** No billing plan was upgraded. For a stricter unattended SLA, configure an appropriate external scheduler or compatible paid plan after deciding that requirement. This does not change the precise five rule conditions.

Official constraints: [Vercel SQLite storage](https://vercel.com/kb/guide/is-sqlite-supported-in-vercel), [Vercel cron plans](https://vercel.com/docs/cron-jobs/usage-and-pricing), [Turso SQLAlchemy](https://docs.turso.tech/sdk/python/orm/sqlalchemy).

## Verification

Backend tests include hosted request evaluation, persistent sample files, missing-cloud-credentials rejection, cron authentication and independent-instance transaction policy. Live transport and browser evidence is recorded separately from local tests in `TEST_RESULTS.md` and `artifacts/vercel-*.json`.

Live browser acceptance can run against this **new assessment dataset** using:

```powershell
.\.venv\Scripts\python.exe scripts/prepare_vercel_checks.py
$env:NATURAX_E2E_BASE_URL='https://naturax-order-automation.vercel.app'
$env:NATURAX_E2E_SAMPLES=(Join-Path (Get-Location) 'artifacts/hosting-samples')
cd frontend
npm run test:e2e
```

The full suite deliberately uploads assessment records and changes task/rule state. Counts use the starting upload total so the same persisted sample files can be checked again without clearing data. Rule challenge B explicitly restores 24 hours before checking the change to 12 hours. Read-only API checks permit up to two retries for connection resets, not for HTTP assertion failures. Do not run these mutating assessment checks against unrelated operational data. Normal local tests create isolated databases instead. Runtime health is public at `/api/health`; interactive API documentation is at `/docs`.
