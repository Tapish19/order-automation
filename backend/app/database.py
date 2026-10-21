from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.engine import make_url

from .models import Base, Employee, RuleConfig
from .rules import DEFAULT_RULES

ROOT = Path(__file__).resolve().parents[2]


def create_database(url=None):
    if url is None:
        (ROOT / "data").mkdir(exist_ok=True)
        url = "sqlite:///" + (ROOT / "data" / "naturax.db").as_posix()
    parsed = make_url(url)
    if parsed.database and parsed.database != ":memory:":
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
    options = {"connect_args": {"check_same_thread": False, "timeout": 30}}
    if url in {"sqlite://", "sqlite:///:memory:"}:
        options["poolclass"] = StaticPool
    engine = create_engine(url, **options)

    @event.listens_for(engine, "connect")
    def pragmas(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")

    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as db:
        if not db.get(RuleConfig, 1):
            db.add(RuleConfig(id=1, settings=DEFAULT_RULES.copy()))
        if not db.query(Employee).first():
            db.add_all([Employee(name=name) for name in ["Aarav Shah", "Meera Iyer", "Rohan Verma", "Priya Nair"]])
    return engine, factory
