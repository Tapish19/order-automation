import os
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, StaticPool
from sqlalchemy.engine import make_url

from .models import Base, Employee, RuleConfig
from .rules import DEFAULT_RULES

ROOT = Path(__file__).resolve().parents[2]


def create_database(url=None):
    remote = url is None and bool(os.getenv("TURSO_DATABASE_URL"))
    if remote:
        token = os.getenv("TURSO_AUTH_TOKEN")
        if not token:
            raise RuntimeError("TURSO_AUTH_TOKEN is required with TURSO_DATABASE_URL.")
        host = os.environ["TURSO_DATABASE_URL"].removeprefix("libsql://").removeprefix("https://").rstrip("/")
        if not host or "/" in host or "?" in host:
            raise RuntimeError("TURSO_DATABASE_URL must identify a libSQL database host.")
        url = f"sqlite+libsql://{host}?secure=true"
    if url is None:
        if os.getenv("VERCEL") == "1":
            raise RuntimeError("Vercel needs TURSO_DATABASE_URL and TURSO_AUTH_TOKEN; ephemeral local SQLite is not permitted.")
        (ROOT / "data").mkdir(exist_ok=True)
        url = "sqlite:///" + (ROOT / "data" / "naturax.db").as_posix()
    parsed = make_url(url)
    if not remote and parsed.database and parsed.database != ":memory:":
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
    options = {"connect_args": {"check_same_thread": False, "timeout": 30}}
    if remote:
        options["connect_args"] = {"auth_token": token, "isolation_level": None, "check_same_thread": False}
        options["poolclass"] = NullPool
    if url in {"sqlite://", "sqlite:///:memory:"}:
        options["poolclass"] = StaticPool
    engine = create_engine(url, hide_parameters=True, **options)

    @event.listens_for(engine, "connect")
    def pragmas(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
        if not remote:
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("PRAGMA journal_mode=WAL")

    if remote:
        @event.listens_for(engine, "begin")
        def begin_remote_transaction(conn):
            # A DB-level lock covers the read/decide/write sequence across Vercel
            # instances, including seeding and idempotent task reconciliation.
            conn.exec_driver_sql("BEGIN IMMEDIATE" if conn.get_execution_options().get("naturax_write") else "BEGIN")

    if remote:
        with engine.connect().execution_options(naturax_write=True) as connection:
            with connection.begin():
                Base.metadata.create_all(connection)
    else:
        Base.metadata.create_all(engine)

    class SessionFactory(sessionmaker):
        @contextmanager
        def begin(self):
            with super().begin() as session:
                if remote:
                    session.connection(execution_options={"naturax_write": True})
                yield session

    factory = SessionFactory(engine, expire_on_commit=False)
    with factory.begin() as db:
        if not db.get(RuleConfig, 1):
            db.add(RuleConfig(id=1, settings=DEFAULT_RULES.copy()))
        if not db.query(Employee).first():
            db.add_all([Employee(name=name) for name in ["Aarav Shah", "Meera Iyer", "Rohan Verma", "Priya Nair"]])
    return engine, factory
