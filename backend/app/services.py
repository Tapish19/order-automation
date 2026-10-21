import json
from collections import Counter, defaultdict

from sqlalchemy import select

from .models import Audit, DataIssue, Employee, ImportBatch, Order, RuleConfig, Task
from .rules import detect
from .timeutils import iso
from .validation import clean, validate

OPEN_STATUSES = {"open", "in_progress"}
ORDER_FIELDS = ["order_date", "customer_name", "phone", "value_paise", "payment_type", "status",
                "dispatch_date", "expected_delivery_date", "assigned_employee", "confirmed_at", "delivery_attempt_at"]


def audit(db, actor, action, now, order_id=None, task_id=None, **details):
    db.add(Audit(order_id=order_id, task_id=task_id, responsible_user=actor,
                 action=action, timestamp=iso(now), details=details))


def ensure_employee(db, name):
    if not db.scalar(select(Employee).where(Employee.name == name)):
        db.add(Employee(name=name))
        db.flush()


def add_issue(db, batch, row_number, raw, error, now, severity="error"):
    db.add(DataIssue(batch_id=batch.id if batch else None, filename=batch.filename if batch else "evaluation",
                     row_number=row_number, order_id=raw.get("id") or None, raw_record=raw,
                     severity=severity, created_at=iso(now), **error))


def reconcile(db, now, actor="System scheduler"):
    config = db.get(RuleConfig, 1).settings
    open_issues = db.scalars(select(DataIssue).where(DataIssue.status == "open")).all()
    blocked_ids = {i.order_id for i in open_issues if i.severity == "error" and i.batch_id is not None}
    evaluation_issues = defaultdict(list)
    active_by_order = defaultdict(dict)
    for issue in open_issues:
        if issue.batch_id is None:
            evaluation_issues[issue.order_id].append(issue)
    for task in db.scalars(select(Task).where(Task.condition_active.is_(True))):
        active_by_order[task.order_id][task.category] = task
    created = resolved = 0
    for order in db.scalars(select(Order)).all():
        # A rejected newer snapshot leaves the previous record intact, but it must
        # not create new exceptions from a now-uncertain order status or value.
        if order.id in blocked_ids:
            continue
        # A configuration change may make previously optional data necessary.
        raw = {k: getattr(order, k) for k in ORDER_FIELDS if k != "value_paise"}
        raw.update(id=order.id, order_value=f"{order.value_paise / 100:.2f}")
        _, errors = validate(raw, config, now)
        issue_fields = {issue.field for issue in evaluation_issues[order.id]}
        for error in errors:
            if error["field"] not in issue_fields:
                db.add(DataIssue(batch_id=None, filename=order.source_filename, row_number=order.source_row,
                                 order_id=order.id, raw_record=raw, severity="error", created_at=iso(now), **error))
                issue_fields.add(error["field"])
        active = active_by_order[order.id]
        if errors:
            # Indeterminate data is not evidence that a previous exception was resolved.
            continue
        for issue in evaluation_issues[order.id]:
            issue.status, issue.resolved_at = "resolved", iso(now)
        detected = detect(order, config, now)
        for category, info in detected.items():
            if category in active:
                active[category].reason = info["reason"]
                continue
            task = Task(order_id=order.id, category=category, assigned_employee=order.assigned_employee,
                        first_detected_at=iso(now), deadline=iso(info["deadline"]), status="open", condition_active=True,
                        **{k: v for k, v in info.items() if k != "deadline"})
            db.add(task)
            db.flush()
            audit(db, actor, "task_assigned", now, order.id, task.id, assigned_employee=task.assigned_employee,
                  status="open", category=category, deadline=task.deadline)
            created += 1
        for category, task in active.items():
            if category not in detected:
                previous = task.status
                task.condition_active = False
                task.resolved_at = iso(now)
                task.status = "resolved"
                audit(db, actor, "exception_resolved", now, order.id, task.id,
                      previous_status=previous, status="resolved", reason="Business condition no longer applies")
                resolved += 1
    return {"created_tasks": created, "resolved_tasks": resolved}


def import_records(db, records, filename, now, actor, row_numbers=None):
    batch = ImportBatch(filename=filename, created_at=iso(now))
    db.add(batch)
    db.flush()
    config = db.get(RuleConfig, 1).settings
    counts = Counter()
    batch.total_rows = len(records)
    ids = defaultdict(list)
    for i, raw in enumerate(records):
        if clean(raw.get("id")):
            ids[clean(raw["id"])].append(i)
    existing_orders = {}
    previous_issues = defaultdict(list)
    identifiers = list(ids)
    # Keep bind counts portable even for the maximum-size local upload.
    for start in range(0, len(identifiers), 500):
        chunk = identifiers[start:start + 500]
        existing_orders.update({o.id: o for o in db.scalars(select(Order).where(Order.id.in_(chunk)))})
        for issue in db.scalars(select(DataIssue).where(DataIssue.order_id.in_(chunk), DataIssue.status == "open", DataIssue.severity == "error")):
            previous_issues[issue.order_id].append(issue)
    employee_names = set(db.scalars(select(Employee.name)))
    conflicts = set()
    repeats = set()
    for indices in ids.values():
        if len(indices) > 1:
            signatures = {json.dumps({k: clean(v) for k, v in records[i].items()}, sort_keys=True) for i in indices}
            if len(signatures) > 1:
                conflicts.update(indices)
            else:
                repeats.update(indices[1:])
    for i, raw in enumerate(records):
        row_number = row_numbers[i] if row_numbers else i + 2
        if i in conflicts:
            add_issue(db, batch, row_number, raw, {"field": "id", "explanation": "Conflicting duplicate ID inside this file. All conflicting copies were rejected.",
                "recommended_correction": "Keep one authoritative row per order ID, or correct the ID if these are different orders."}, now)
            counts["rejected"] += 1
            counts["duplicate_rows"] += 1
            continue
        if i in repeats:
            add_issue(db, batch, row_number, raw, {"field": "id", "explanation": "Identical duplicate row inside this file; safely skipped.",
                "recommended_correction": "Remove the repeated row from the source file."}, now, severity="warning")
            counts["duplicate_rows"] += 1
            continue
        row, errors = validate(raw, config, now)
        existing = existing_orders.get(row.get("id"))
        if existing and not errors:
            identity_diff = [k for k in ("customer_name", "phone", "order_date") if str(getattr(existing, k)).casefold() != str(row[k]).casefold()]
            if identity_diff:
                errors.append({"field": "id", "explanation": "Existing ID belongs to a different source identity (" + ", ".join(identity_diff) + ").",
                    "recommended_correction": "Verify the ID. Updates must keep the original customer, phone, and order date; use a distinct ID for a different order."})
        if errors:
            for error in errors:
                add_issue(db, batch, row_number, raw, error, now)
            counts["rejected"] += 1
            continue
        if row["assigned_employee"] not in employee_names:
            ensure_employee(db, row["assigned_employee"])
            employee_names.add(row["assigned_employee"])
        if existing:
            changes = {k: {"from": getattr(existing, k), "to": row[k]} for k in ORDER_FIELDS if getattr(existing, k) != row[k]}
            if changes:
                for k in ORDER_FIELDS:
                    setattr(existing, k, row[k])
                existing.updated_at, existing.source_filename, existing.source_row = iso(now), filename, row_number
                audit(db, actor, "order_updated", now, existing.id, changes=changes)
                if "assigned_employee" in changes:
                    audit(db, actor, "order_assignment_changed", now, existing.id, **changes["assigned_employee"])
                counts["updated"] += 1
            else:
                counts["unchanged"] += 1
        else:
            db.add(Order(id=row["id"], **{k: row[k] for k in ORDER_FIELDS}, source_filename=filename,
                         source_row=row_number, first_imported_at=iso(now), updated_at=iso(now)))
            audit(db, actor, "order_imported", now, row["id"], assigned_employee=row["assigned_employee"])
            counts["inserted"] += 1
        db.flush()
        # A valid later import resolves earlier errors for this ID, while retaining history.
        for issue in previous_issues[row["id"]]:
            if issue.batch_id != batch.id:
                issue.status, issue.resolved_at = "resolved", iso(now)
                audit(db, actor, "data_issue_resolved", now, row["id"], issue_id=issue.id, resolution="Valid order reimported")
    for field in ("inserted", "updated", "unchanged", "rejected", "duplicate_rows"):
        setattr(batch, field, counts[field])
    db.flush()
    result = reconcile(db, now, actor)
    audit(db, actor, "file_imported", now, filename=filename, batch_id=batch.id, total_rows=batch.total_rows,
          inserted=batch.inserted, updated=batch.updated, unchanged=batch.unchanged, rejected=batch.rejected)
    db.flush()
    return batch, result


def serialize(model):
    return {col.name: getattr(model, col.name) for col in model.__table__.columns}


def task_dict(task, order, now):
    return {**serialize(task), "customer_name": order.customer_name, "phone": order.phone,
            "order_value": order.value_paise / 100, "order_status": order.status, "order_date": order.order_date,
            "overdue": task.status in OPEN_STATUSES and task.deadline < iso(now)}
