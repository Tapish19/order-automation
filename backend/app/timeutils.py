import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc
DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def utcnow():
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="microseconds")


def timestamp(value: str) -> datetime:
    if DATE_ONLY.fullmatch(value):
        raise ValueError("A date alone does not supply the time required for an hourly rule")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def normalize_date(value: str, require_time=False) -> str:
    """Keep date-only input as a date. Never manufacture an order timestamp."""
    value = value.strip()
    if DATE_ONLY.fullmatch(value):
        date.fromisoformat(value)
        if require_time:
            raise ValueError("Time is required; supply YYYY-MM-DD HH:MM[:SS] with optional UTC offset")
        return value
    if not re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?$", value):
        raise ValueError("Use ISO YYYY-MM-DD or YYYY-MM-DD HH:MM[:SS], optionally with UTC offset")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return iso(dt)


def expected_boundary(value: str) -> tuple[datetime, bool]:
    if DATE_ONLY.fullmatch(value):
        # A promised delivery date includes the whole local calendar day.
        following = date.fromisoformat(value) + timedelta(days=1)
        return datetime.combine(following, time.min, IST).astimezone(UTC), True
    return timestamp(value), False


def past_expected(value: str, now: datetime) -> bool:
    boundary, date_only = expected_boundary(value)
    return now >= boundary if date_only else now > boundary


def local_day(value: str) -> str:
    return value if DATE_ONLY.fullmatch(value) else timestamp(value).astimezone(IST).date().isoformat()


def day_bounds(value: str):
    start = datetime.combine(date.fromisoformat(value), time.min, IST)
    return iso(start), iso(start + timedelta(days=1))
