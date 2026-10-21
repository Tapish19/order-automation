import csv
import io
import json
from datetime import timedelta
from pathlib import Path

import pandas as pd

from .timeutils import IST, iso, utcnow
from .validation import HEADERS

ROOT = Path(__file__).resolve().parents[2]


def make_records(now):
    now = now.astimezone(IST)
    names = ["Ananya Sharma", "Vikram Patel", "Sana Khan", "Aditya Rao", "Kavya Menon", "Arjun Singh", "Diya Kapoor", "Ishaan Das"]
    employees = ["Aarav Shah", "Meera Iyer", "Rohan Verma", "Priya Nair"]

    def stamp(hours):
        return (now - timedelta(hours=hours)).isoformat(timespec="seconds")

    records = []
    for i in range(120):
        group = i % 8
        status = ["delivered", "unconfirmed", "confirmed", "dispatched", "failed_delivery", "dispatched", "confirmed", "cancelled"][group]
        row = {"id": f"NX-{1001+i}", "order_date": stamp(120 if group not in {1, 2, 6} else {1: 3, 2: 30, 6: 18}[group]),
               "customer_name": names[i % len(names)], "phone": f"91980000{i:04d}",
               "order_value": str(749 + (i * 137) % 4000), "payment_type": "COD" if i % 3 == 0 else "Prepaid",
               "status": status, "dispatch_date": stamp(72) if group in {0, 3, 4, 5} else "",
               "expected_delivery_date": stamp(6) if group in {3, 5} else stamp(-24) if group == 4 else "",
               "assigned_employee": employees[i % 4]}
        if group == 5:
            row["order_value"] = str(6000 + i * 11)
        records.append(row)
    base = dict(records[0], status="unconfirmed", dispatch_date="", expected_delivery_date="", order_value="2000")
    def special(identifier, **changes):
        return dict(base, id=identifier, **changes)
    records.extend([
        special("EDGE-2H-BELOW", order_date=stamp(2 - 1/3600)),
        special("EDGE-2H-EXACT", order_date=stamp(2)),
        special("EDGE-2H-ABOVE", order_date=stamp(2 + 1/3600)),
        special("EDGE-24H-BELOW", status="confirmed", order_date=stamp(24 - 1/3600)),
        special("EDGE-24H-EXACT", status="confirmed", order_date=stamp(24)),
        special("EDGE-24H-ABOVE", status="confirmed", order_date=stamp(24 + 1/3600)),
        special("EDGE-12H-BELOW", status="confirmed", order_date=stamp(12 - 1/3600)),
        special("EDGE-12H-EXACT", status="confirmed", order_date=stamp(12)),
        special("EDGE-12H-ABOVE", status="confirmed", order_date=stamp(12 + 1/3600)),
        special("EDGE-5000-BELOW", status="dispatched", order_date=stamp(120), dispatch_date=stamp(72), expected_delivery_date=stamp(6), order_value="4999.99"),
        special("EDGE-5000-EXACT", status="dispatched", order_date=stamp(120), dispatch_date=stamp(72), expected_delivery_date=stamp(6), order_value="5000"),
        special("EDGE-5000-ABOVE", status="dispatched", order_date=stamp(120), dispatch_date=stamp(72), expected_delivery_date=stamp(6), order_value="5000.01"),
        special("EDGE-EXPECTED-BEFORE", status="dispatched", order_date=stamp(120), dispatch_date=stamp(72), expected_delivery_date=stamp(-1/3600)),
        special("EDGE-EXPECTED-EXACT", status="dispatched", order_date=stamp(120), dispatch_date=stamp(72), expected_delivery_date=stamp(0)),
        special("EDGE-EXPECTED-AFTER", status="dispatched", order_date=stamp(120), dispatch_date=stamp(72), expected_delivery_date=stamp(1/3600)),
        special("DATE-ONLY-EXPECTED", status="dispatched", order_date=stamp(120), dispatch_date=stamp(72), expected_delivery_date=now.date().isoformat()),
        special("BAD-DATE", order_date="2026-02-30 10:00"),
        special("BAD-MISSING-PHONE", order_date=stamp(4), phone=""),
        special("BAD-MISSING-STATUS", order_date=stamp(4), status=""),
        special("BAD-MISSING-VALUE", order_date=stamp(4), order_value=""),
        special("BAD-UNKNOWN-STATUS", order_date=stamp(4), status="somewhere"),
        special("BAD-DATE-ONLY-HOURLY", order_date=now.date().isoformat()),
        special("BAD-MISSING-DISPATCH", status="dispatched", order_date=stamp(120), expected_delivery_date=stamp(6)),
        special("BAD-MISSING-EXPECTED", status="dispatched", order_date=stamp(120), dispatch_date=stamp(72)),
        special("BAD-CONFLICT", order_date=stamp(4)),
        special("BAD-CONFLICT", order_date=stamp(4), phone="919999999999"),
        dict(records[0]),  # Exact duplicate safely skipped.
    ])
    return records


def generate_samples(now=None, directory=None):
    now = (now or utcnow()).replace(microsecond=0)
    directory = Path(directory) if directory else ROOT / "samples"
    directory.mkdir(exist_ok=True, parents=True)
    rows = make_records(now)
    external = [{header: row[field] for header, field in HEADERS.items()} for row in rows]
    pd.DataFrame(external).to_csv(directory / "naturax_orders.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(external).to_excel(directory / "naturax_orders.xlsx", index=False)
    invalid = [dict(rows[0], id="INTERVIEW-INVALID-PHONE", phone="invalid"),
               dict(rows[0], id="INTERVIEW-INVALID-DATE", order_date="not-a-date"),
               dict(rows[6], id="INTERVIEW-VALID-18H")]
    pd.DataFrame([{h: r[k] for h,k in HEADERS.items()} for r in invalid]).to_csv(directory / "interview_invalid.csv", index=False)
    delivered = dict(rows[2], status="delivered")
    pd.DataFrame([{h: delivered[k] for h,k in HEADERS.items()}]).to_csv(directory / "order_update_delivered.csv", index=False)
    (directory / "manifest.json").write_text(json.dumps({"reference_time_utc": iso(now), "reference_time_ist": now.astimezone(IST).isoformat(),
        "rows": len(rows), "columns": list(HEADERS), "note": "Threshold records are exact only at this reference time. Tests freeze this clock; the live clock advances normally."}, indent=2), encoding="utf-8")
    return {"rows": len(rows), "reference_time": iso(now)}


if __name__ == "__main__":
    print(json.dumps(generate_samples(), indent=2))
