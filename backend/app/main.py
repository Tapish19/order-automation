import asyncio
import base64
import csv
import io
import logging
import os
import secrets
import tempfile
import threading
from collections import Counter
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .database import ROOT, create_database
from .models import Audit, DataIssue, Employee, ImportBatch, Order, RuleConfig, RuntimeState, SampleAsset, Task
from .rules import CATEGORIES
from .sample_data import generate_samples
from .services import OPEN_STATUSES, audit, import_records, reconcile, serialize, task_dict
from .timeutils import IST, day_bounds, iso, local_day, timestamp, utcnow
from .validation import FileError, HEADERS, read_file, validate


class Filters(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    category: str | None = None
    employee: str | None = None
    priority: Literal["urgent", "high", "medium", "low"] | None = None
    status: Literal["all", "pending", "open", "in_progress", "resolved"] = "all"
    overdue: bool = False
    search: str = ""


class TaskChange(BaseModel):
    assigned_employee: str | None = Field(default=None, min_length=1, max_length=100)
    status: Literal["open", "in_progress", "resolved"] | None = None
    note: str = Field(default="", max_length=1000)


class ConfigChange(BaseModel):
    unconfirmed_hours: float = Field(gt=0, le=168, allow_inf_nan=False)
    dispatch_hours: float = Field(gt=0, le=720, allow_inf_nan=False)
    high_value_rupees: float = Field(ge=0, le=1000000000, allow_inf_nan=False, multiple_of=0.01)
    follow_up_hours: float = Field(gt=0, le=168, allow_inf_nan=False)


class EmployeeCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)


class Correction(BaseModel):
    record: dict[str, str]


def responsible_user(x_user: str = Header(default="Interview Manager")):
    if not x_user.strip() or len(x_user) > 100:
        raise HTTPException(422, "Responsible user must contain 1–100 characters.")
    return x_user.strip()


def select_records(db, now, filters):
    if filters.date_from and filters.date_to and filters.date_from > filters.date_to:
        raise HTTPException(422, "Start date must precede end date.")
    if filters.category and filters.category not in CATEGORIES:
        raise HTTPException(422, "Unknown exception category.")
    orders = {o.id: o for o in db.scalars(select(Order)).all()}
    selected_orders = {}
    for oid, order in orders.items():
        day = local_day(order.order_date)
        if filters.date_from and day < filters.date_from.isoformat():
            continue
        if filters.date_to and day > filters.date_to.isoformat():
            continue
        if filters.search and filters.search.casefold() not in f"{oid} {order.customer_name} {order.phone}".casefold():
            continue
        selected_orders[oid] = order
    tasks = []
    for task in db.scalars(select(Task).order_by(Task.first_detected_at.desc(), Task.id.desc())).all():
        if task.order_id not in selected_orders:
            continue
        if filters.category and task.category != filters.category:
            continue
        if filters.employee and task.assigned_employee != filters.employee:
            continue
        if filters.priority and task.priority != filters.priority:
            continue
        if filters.status == "pending" and task.status not in OPEN_STATUSES:
            continue
        if filters.status not in {"all", "pending"} and task.status != filters.status:
            continue
        item = task_dict(task, orders[task.order_id], now)
        if filters.overdue and not item["overdue"]:
            continue
        tasks.append(item)
    if filters.category or filters.priority or filters.employee or filters.status != "all" or filters.overdue:
        task_ids = {t["order_id"] for t in tasks}
        selected_orders = {oid:o for oid,o in selected_orders.items() if oid in task_ids or (
            filters.employee and not (filters.category or filters.priority or filters.overdue or filters.status != "all") and o.assigned_employee == filters.employee)}
    return selected_orders, tasks


def create_app(database_url=None, clock=None, scheduler=True, evaluation_interval=60):
    engine, factory = create_database(database_url or os.getenv("NATURAX_DATABASE_URL"))
    write_lock = threading.RLock()
    get_now = clock or utcnow
    hosted = os.getenv("VERCEL") == "1" or os.getenv("NATURAX_SERVERLESS") == "1"
    scheduler_enabled = scheduler and not hosted
    request_check_at = None

    def mark_evaluated(db, now):
        state = db.get(RuntimeState, "last_evaluation")
        if state:
            state.value = iso(now)
        else:
            db.add(RuntimeState(key="last_evaluation", value=iso(now)))

    def evaluate_if_due():
        nonlocal request_check_at
        with write_lock:
            now = get_now()
            if request_check_at and (now - request_check_at).total_seconds() < evaluation_interval:
                return
            with factory.begin() as db:
                state = db.get(RuntimeState, "last_evaluation")
                if not state or (now - timestamp(state.value)).total_seconds() >= evaluation_interval:
                    reconcile(db, now, "System request evaluation")
                    mark_evaluated(db, now)
            request_check_at = now

    async def ticker():
        while True:
            await asyncio.sleep(evaluation_interval)
            def evaluate():
                with write_lock, factory.begin() as db:
                    reconcile(db, get_now())
            await asyncio.to_thread(evaluate)

    @asynccontextmanager
    async def lifespan(app):
        if hosted:
            await asyncio.to_thread(evaluate_if_due)
        else:
            with write_lock, factory.begin() as db:
                reconcile(db, get_now())
        background = asyncio.create_task(ticker()) if scheduler_enabled else None
        yield
        if background:
            background.cancel()
            try:
                await background
            except asyncio.CancelledError:
                pass
        engine.dispose()

    app = FastAPI(title="NaturaX Order Automation", version="1.0.0", lifespan=lifespan)
    @app.exception_handler(Exception)
    async def log_unhandled_error(request, exc):
        logging.getLogger("naturax").error("Unhandled %s on %s", type(exc).__name__, request.url.path, exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": "The request could not be completed. Check the server error log."})
    app.state.factory, app.state.engine = factory, engine
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["GET", "POST", "PATCH", "PUT"], allow_headers=["Content-Type", "X-User"])

    def session():
        if hosted:
            evaluate_if_due()
        with factory() as db:
            yield db

    @app.get("/api/health")
    def health(db=Depends(session)):
        db.execute(select(RuleConfig))
        return {"status": "ok", "timezone": "Asia/Kolkata", "server_time": iso(get_now()),
                "scheduler_seconds": evaluation_interval if scheduler_enabled else None,
                "evaluation_mode": "request_and_daily_cron" if hosted else "local_scheduler",
                "database": "turso" if engine.dialect.driver == "libsql" else "sqlite"}

    @app.get("/api/meta")
    def meta():
        return {"categories": CATEGORIES, "required_columns": list(HEADERS), "timezone": "Asia/Kolkata", "max_upload_mb": 4 if hosted else 10}

    @app.get("/api/employees")
    def employees(db=Depends(session)):
        return [serialize(e) for e in db.scalars(select(Employee).order_by(Employee.name))]

    @app.post("/api/employees", status_code=201)
    def add_employee(body: EmployeeCreate, actor=Depends(responsible_user)):
        name = body.name.strip()
        if len(name) < 2:
            raise HTTPException(422, "Provide the employee's name.")
        with write_lock, factory.begin() as db:
            if db.scalar(select(Employee).where(Employee.name == name)):
                raise HTTPException(409, "Employee already exists.")
            person = Employee(name=name)
            db.add(person)
            db.flush()
            audit(db, actor, "employee_added", get_now(), employee=name)
            return serialize(person)

    @app.post("/api/uploads")
    async def upload(file: UploadFile, actor=Depends(responsible_user)):
        max_upload_mb = 4 if hosted else 10
        content = await file.read(max_upload_mb * 1024 * 1024 + 1)
        if len(content) > max_upload_mb * 1024 * 1024:
            raise HTTPException(413, f"Maximum file size is {max_upload_mb} MB.")
        filename = Path((file.filename or "upload.csv").replace("\\", "/")).name[:255]
        try:
            records, missing = read_file(filename, content)
        except FileError as exc:
            raise HTTPException(422, str(exc))
        def ingest():
            with write_lock, factory.begin() as db:
                batch, result = import_records(db, records, filename, get_now(), actor)
                if hosted:
                    mark_evaluated(db, get_now())
                return {**serialize(batch), **result, "missing_columns": missing,
                        "issue_count": len(db.scalars(select(DataIssue).where(DataIssue.batch_id == batch.id)).all())}
        return await asyncio.to_thread(ingest)

    @app.get("/api/imports")
    def imports(db=Depends(session)):
        return [serialize(b) for b in db.scalars(select(ImportBatch).order_by(ImportBatch.id.desc()))]

    @app.get("/api/data-issues")
    def issues(status: Literal["all", "open", "resolved"] = "open", batch_id: int | None = None, db=Depends(session)):
        query = select(DataIssue).order_by(DataIssue.id.desc())
        if status != "all":
            query = query.where(DataIssue.status == status)
        if batch_id is not None:
            query = query.where(DataIssue.batch_id == batch_id)
        return [serialize(i) for i in db.scalars(query)]

    @app.post("/api/data-issues/{issue_id}/correct")
    def correct(issue_id: int, body: Correction, actor=Depends(responsible_user)):
        with write_lock, factory.begin() as db:
            issue = db.get(DataIssue, issue_id)
            if not issue:
                raise HTTPException(404, "Issue not found.")
            now = get_now()
            _, errors = validate(body.record, db.get(RuleConfig, 1).settings, now)
            if errors:
                raise HTTPException(422, {"message": "Correction is still invalid.", "errors": errors})
            batch, result = import_records(db, [body.record], issue.filename, now, actor, [issue.row_number])
            if hosted:
                mark_evaluated(db, now)
            if batch.rejected:
                raise HTTPException(409, "This ID conflicts with an existing order. Verify the customer identity or use the correct ID.")
            # Resolve all issues for the original source row, including missing IDs.
            for sibling in db.scalars(select(DataIssue).where(DataIssue.batch_id == issue.batch_id,
                                         DataIssue.row_number == issue.row_number, DataIssue.filename == issue.filename, DataIssue.status == "open")):
                sibling.status, sibling.resolved_at = "resolved", iso(now)
            audit(db, actor, "data_corrected", now, body.record.get("id"), issue_id=issue_id,
                  source_filename=issue.filename, source_row=issue.row_number, changes={k: {"from":issue.raw_record.get(k), "to":v} for k,v in body.record.items() if issue.raw_record.get(k) != v})
            return {"batch": serialize(batch), **result}

    @app.get("/api/orders")
    def orders(filters: Filters = Depends(), db=Depends(session)):
        selected, _ = select_records(db, get_now(), filters)
        return [{**serialize(o), "order_value": o.value_paise / 100} for o in selected.values()]

    @app.get("/api/tasks")
    def tasks(filters: Filters = Depends(), db=Depends(session)):
        return select_records(db, get_now(), filters)[1]

    @app.patch("/api/tasks/{task_id}")
    def update_task(task_id: int, body: TaskChange, actor=Depends(responsible_user)):
        with write_lock, factory.begin() as db:
            task = db.get(Task, task_id)
            if not task:
                raise HTTPException(404, "Task not found.")
            now = get_now()
            if body.assigned_employee is not None:
                name = body.assigned_employee.strip()
                if not db.scalar(select(Employee).where(Employee.name == name)):
                    raise HTTPException(422, "Choose an existing employee.")
                if task.assigned_employee != name:
                    previous, task.assigned_employee = task.assigned_employee, name
                    audit(db, actor, "task_reassigned", now, task.order_id, task.id,
                          previous_employee=previous, assigned_employee=name, was_overdue=task.status in OPEN_STATUSES and task.deadline < iso(now), note=body.note)
            if body.status is not None and task.status != body.status:
                if not task.condition_active and body.status != "resolved":
                    raise HTTPException(409, "The business condition has cleared. A later recurrence creates a new task.")
                previous, task.status = task.status, body.status
                task.resolved_at = iso(now) if task.status == "resolved" else None
                audit(db, actor, "task_status_changed", now, task.order_id, task.id,
                      previous_status=previous, status=body.status, note=body.note)
            return task_dict(task, db.get(Order, task.order_id), now)

    @app.post("/api/evaluate")
    def evaluate(actor=Depends(responsible_user)):
        with write_lock, factory.begin() as db:
            result = reconcile(db, get_now(), actor)
            if hosted:
                mark_evaluated(db, get_now())
            audit(db, actor, "rules_evaluated", get_now(), **result)
            return result

    @app.get("/api/cron/evaluate")
    def cron_evaluate(authorization: str | None = Header(default=None)):
        secret = os.getenv("CRON_SECRET")
        if not secret:
            raise HTTPException(503, "Cron authentication is not configured.")
        if not secrets.compare_digest(authorization or "", f"Bearer {secret}"):
            raise HTTPException(401, "Invalid cron authorization.")
        with write_lock, factory.begin() as db:
            now = get_now()
            result = reconcile(db, now, "Vercel daily cron")
            mark_evaluated(db, now)
            audit(db, "Vercel daily cron", "rules_evaluated", now, **result)
            return result

    @app.get("/api/rules")
    def rules(db=Depends(session)):
        return db.get(RuleConfig, 1).settings

    @app.put("/api/rules")
    def change_rules(body: ConfigChange, actor=Depends(responsible_user)):
        with write_lock, factory.begin() as db:
            config = db.get(RuleConfig, 1)
            old, config.settings = config.settings.copy(), body.model_dump()
            audit(db, actor, "rules_changed", get_now(), previous=old, settings=config.settings)
            result = reconcile(db, get_now(), actor)
            if hosted:
                mark_evaluated(db, get_now())
            return {"settings": config.settings, **result}

    @app.get("/api/dashboard")
    def dashboard(filters: Filters = Depends(), db=Depends(session)):
        now = get_now()
        selected, rows = select_records(db, now, filters)
        pending = [t for t in rows if t["status"] in OPEN_STATUSES]
        batches = db.scalars(select(ImportBatch)).all()
        category_counts = Counter(t["category"] for t in pending)
        employee_counts = Counter(t["assigned_employee"] for t in pending)
        trend = Counter(local_day(t["first_detected_at"]) for t in rows)
        return {"uploaded_rows": sum(b.total_rows for b in batches), "unique_orders_all_time": db.query(Order).count(),
                "unique_orders": len(selected), "orders_requiring_attention": len({t["order_id"] for t in pending}),
                "open_tasks": len(pending), "overdue_tasks": sum(t["overdue"] for t in pending),
                "data_issues": db.query(DataIssue).filter(DataIssue.status == "open", DataIssue.severity == "error").count(),
                "exceptions_by_category": [{"category": c, "name": CATEGORIES[c], "count": category_counts[c]} for c in CATEGORIES],
                "employee_pending": [{"name": k, "count": v} for k,v in sorted(employee_counts.items())],
                "daily_detections": [{"date": k, "count": v} for k,v in sorted(trend.items())],
                "immediate_cases": sorted([t for t in pending if t["priority"] in {"urgent", "high"}],
                                          key=lambda t: (0 if t["priority"] == "urgent" else 1, t["deadline"])), "as_of": iso(now)}

    @app.get("/api/audit")
    def audit_trail(order_id: str | None = None, action: str | None = None, db=Depends(session)):
        query = select(Audit).order_by(Audit.id.desc())
        if order_id:
            query = query.where(Audit.order_id == order_id)
        if action:
            query = query.where(Audit.action == action)
        return [serialize(a) for a in db.scalars(query)]

    @app.get("/api/reports/daily.csv")
    def report(report_date: date = Query(default_factory=lambda: get_now().astimezone(IST).date()), db=Depends(session)):
        now = get_now()
        start, end = day_bounds(report_date.isoformat())
        orders = {o.id: o for o in db.scalars(select(Order))}
        tasks = [task_dict(t, orders[t.order_id], now) for t in db.scalars(select(Task))]
        headers = ["section", "report_date", "snapshot_at_utc", "task_id", "order_id", "customer_name", "phone", "order_value_inr",
                   "category", "reason", "priority", "assigned_employee", "recommended_action", "deadline_utc", "task_status", "first_detected_at_utc", "pending_count"]
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        def safe(value):
            s = str(value)
            return "'" + s if s.lstrip().startswith(("=", "+", "-", "@")) else value
        def emit(section, t):
            row = {"section":section,"report_date":report_date.isoformat(),"snapshot_at_utc":iso(now),"task_id":t["id"],
                "order_value_inr":t["order_value"],"deadline_utc":t["deadline"],"task_status":t["status"],"first_detected_at_utc":t["first_detected_at"]}
            row.update({k:t[k] for k in ["order_id","customer_name","phone","category","reason","priority","assigned_employee","recommended_action"]})
            writer.writerow({k:safe(v) for k,v in row.items()})
        pending = [t for t in tasks if t["status"] in OPEN_STATUSES]
        sections = {"new_exceptions": [t for t in tasks if start <= t["first_detected_at"] < end],
                    "unresolved_exceptions": pending, "overdue_tasks": [t for t in pending if t["overdue"]],
                    "high_priority_cases": [t for t in pending if t["priority"] in {"urgent", "high"}],
                    "employee_pending_actions": sorted(pending, key=lambda t: t["assigned_employee"])}
        for section, items in sections.items():
            for task in items:
                emit(section, task)
        for name, count in sorted(Counter(t["assigned_employee"] for t in pending).items()):
            writer.writerow({"section":"employee_pending_summary", "report_date":report_date.isoformat(), "snapshot_at_utc":iso(now),
                             "assigned_employee":safe(name), "pending_count":count})
        return Response("\ufeff" + stream.getvalue(), media_type="text/csv", headers={"Content-Disposition":f'attachment; filename="naturax-daily-{report_date}.csv"'})

    def store_samples(db, now):
        with tempfile.TemporaryDirectory(prefix="naturax-samples-") as directory:
            result = generate_samples(now, directory)
            for path in Path(directory).iterdir():
                db.merge(SampleAsset(filename=path.name, content=base64.b64encode(path.read_bytes()).decode("ascii")))
            return result

    @app.post("/api/demo/generate")
    def generate(actor=Depends(responsible_user)):
        with write_lock:
            with factory.begin() as db:
                result = store_samples(db, get_now()) if hosted else generate_samples(get_now())
                audit(db, actor, "sample_files_generated", get_now(), **result)
            return result

    @app.get("/api/samples/{filename}")
    def sample(filename: Literal["naturax_orders.csv", "naturax_orders.xlsx", "interview_invalid.csv", "order_update_delivered.csv", "manifest.json"]):
        if hosted:
            with write_lock, factory.begin() as db:
                asset = db.get(SampleAsset, filename)
                if not asset:
                    store_samples(db, get_now())
                    db.flush()
                    asset = db.get(SampleAsset, filename)
                content = base64.b64decode(asset.content)
            media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if filename.endswith(".xlsx") else "application/json" if filename.endswith(".json") else "text/csv"
            return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
        path = ROOT / "samples" / filename
        if not path.exists():
            with write_lock:
                generate_samples(get_now())
        return FileResponse(path, filename=filename)

    dist = ROOT / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


app = create_app()
