"""The bucket brigade: the pipeline Saltbox had before the sugar shack.

It reads the landing folder directly, the way a lot of first pipelines do, and it looks
reasonable. It is also wrong in five ways at once. `sugarshack compare` takes it apart.
"""
import json
from datetime import datetime

import duckdb

from .config import LANDING
from .tap import arrived_at


def landed(source: str, through: datetime) -> list[str]:
    return sorted(str(p) for p in (LANDING / source).glob("*/*.jsonl") if arrived_at(p) <= through)


def naive_revenue(through: datetime, month: str) -> float:
    """'Revenue' as the dashboard computed it: every charge in the month, from the files."""
    with duckdb.connect() as con:
        con.execute("set TimeZone = 'UTC'")
        return con.execute("""
            select sum(try_cast(json->>'$.data.object.amount' as bigint)) / 100.0
            from read_json_objects(?, format = 'newline_delimited', ignore_errors = true)
            where json->>'$.type' = 'charge.succeeded'
              and strftime(to_timestamp((json->>'$.created')::bigint), '%Y-%m') = ?
        """, [landed("payments", through), month]).fetchone()[0] or 0.0


def naive_queue(through: datetime) -> tuple[int, int]:
    """Orders 'awaiting shipment': the last change we received for each order says 'paid'.
    Returns (waiting, waiting for more than 72 hours)."""
    latest = {}
    for path in landed("orders", through):         # files in arrival order...
        for line in open(path):
            change = json.loads(line)
            if change["after"]:                     # ...deletes have no 'after', so skip them
                latest[change["after"]["order_id"]] = change["after"]
    waiting = [row for row in latest.values() if row["status"] == "paid"]
    stuck = sum(1 for row in waiting
                if (through - datetime.fromisoformat(row["updated_at"])).total_seconds() >= 72 * 3600)
    return len(waiting), stuck
