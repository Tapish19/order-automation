from sqlalchemy import Boolean, ForeignKey, Index, Integer, JSON, String, Text, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    order_date: Mapped[str] = mapped_column(String(40))
    customer_name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str] = mapped_column(String(30))
    value_paise: Mapped[int] = mapped_column(Integer)
    payment_type: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(40))
    dispatch_date: Mapped[str | None] = mapped_column(String(40))
    expected_delivery_date: Mapped[str | None] = mapped_column(String(40))
    confirmed_at: Mapped[str | None] = mapped_column(String(40))
    delivery_attempt_at: Mapped[str | None] = mapped_column(String(40))
    assigned_employee: Mapped[str] = mapped_column(String(100))
    source_filename: Mapped[str] = mapped_column(String(255))
    source_row: Mapped[int] = mapped_column(Integer)
    first_imported_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class ImportBatch(Base):
    __tablename__ = "imports"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[str] = mapped_column(String(40))
    total_rows: Mapped[int] = mapped_column(default=0)
    inserted: Mapped[int] = mapped_column(default=0)
    updated: Mapped[int] = mapped_column(default=0)
    unchanged: Mapped[int] = mapped_column(default=0)
    rejected: Mapped[int] = mapped_column(default=0)
    duplicate_rows: Mapped[int] = mapped_column(default=0)


class DataIssue(Base):
    __tablename__ = "data_issues"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("imports.id"))
    filename: Mapped[str] = mapped_column(String(255))
    row_number: Mapped[int] = mapped_column(Integer)
    order_id: Mapped[str | None] = mapped_column(String(100), index=True)
    field: Mapped[str] = mapped_column(String(100))
    explanation: Mapped[str] = mapped_column(Text)
    recommended_correction: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(default="error")
    raw_record: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(default="open")
    created_at: Mapped[str] = mapped_column(String(40))
    resolved_at: Mapped[str | None] = mapped_column(String(40))


class Task(Base):
    """One task per exception episode; first_detected_at never changes."""
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    category: Mapped[str] = mapped_column(String(50))
    reason: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20))
    assigned_employee: Mapped[str] = mapped_column(String(100))
    recommended_action: Mapped[str] = mapped_column(Text)
    deadline: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(default="open")
    condition_active: Mapped[bool] = mapped_column(Boolean, default=True)
    first_detected_at: Mapped[str] = mapped_column(String(40), index=True)
    resolved_at: Mapped[str | None] = mapped_column(String(40))
    __table_args__ = (
        Index("uq_active_exception", "order_id", "category", unique=True,
              sqlite_where=text("condition_active = 1")),
    )


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str | None] = mapped_column(String(100), index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"))
    responsible_user: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(60))
    timestamp: Mapped[str] = mapped_column(String(40), index=True)
    details: Mapped[dict] = mapped_column(JSON)


class RuleConfig(Base):
    __tablename__ = "rule_config"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    settings: Mapped[dict] = mapped_column(JSON)


class RuntimeState(Base):
    __tablename__ = "runtime_state"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(100))


class SampleAsset(Base):
    """Keep generated interview files consistent across serverless instances."""
    __tablename__ = "sample_assets"
    filename: Mapped[str] = mapped_column(String(100), primary_key=True)
    # The remote DB-API does not implement sqlite3.Binary. Base64 text works
    # across both drivers and keeps XLSX bytes intact across function instances.
    content: Mapped[str] = mapped_column(Text)
