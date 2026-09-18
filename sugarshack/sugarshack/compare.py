"""Take the bucket brigade's number apart, one mistake at a time, until it matches gold."""
from datetime import datetime

import duckdb

from .bucket import landed, naive_queue
from .config import WAREHOUSE

# Each step fixes one thing, on top of the steps before it.
STEPS = [
    ("re-sent files counted twice",       "not resend"),
    ("webhook retries counted twice",     "first_delivery"),
    ("v2 amounts read as null",           "v2_amounts"),
    ("refunds never subtracted",          "refunds"),
    ("USD added as if it were CAD",       "fx"),
]


def compare(through: datetime, month: str) -> dict:
    files = landed("payments", through)
    with duckdb.connect(str(WAREHOUSE), read_only=True) as con:
        con.execute("set TimeZone = 'UTC'")
        con.execute("""
            create temp table events as
            select filename like '%-resend.jsonl' as resend,
                   json->>'$.id' as event_id,
                   json->>'$.type' as type,
                   json->>'$.api_version' as version,
                   to_timestamp((json->>'$.created')::bigint) as created_at,
                   try_cast(json->>'$.data.object.amount' as bigint) as naive_amount,
                   coalesce(try_cast(json->>'$.data.object.refund.amount' as bigint),
                            try_cast(json->>'$.data.object.amount.value' as bigint),
                            try_cast(json->>'$.data.object.amount' as bigint)) as amount,
                   lower(coalesce(json->>'$.data.object.currency',
                                  json->>'$.data.object.amount.currency')) as currency,
                   row_number() over (partition by json->>'$.id' order by filename) = 1 as first_delivery
            from read_json_objects(?, format = 'newline_delimited', ignore_errors = true, filename = true)
        """, [files])
        con.execute("delete from events where strftime(created_at, '%Y-%m') <> ?", [month])

        def total(fixes: set) -> float:
            amount = "amount" if "v2_amounts" in fixes else "naive_amount"
            sign = "case type when 'charge.succeeded' then 1 else -1 end" if "refunds" in fixes else "1"
            types = "('charge.succeeded', 'charge.refunded')" if "refunds" in fixes else "('charge.succeeded')"
            rate = "case currency when 'usd' then fx.rate else 1 end" if "fx" in fixes else "1"
            where = ["type in " + types]
            if "not resend" in fixes:
                where.append("not resend")
            if "first_delivery" in fixes:
                where.append("first_delivery")
            return con.execute(f"""
                select coalesce(sum(round({sign} * {amount} / 100.0 * {rate}, 2)), 0)
                from events e
                asof left join (select rate_date, rate from silver.silver_fx_rates) fx
                     on (e.created_at at time zone 'UTC')::date >= fx.rate_date
                where {' and '.join(where)}
            """).fetchone()[0]

        applied = set()
        rows = [("bucket brigade dashboard", float(total(applied)), None)]
        for label, fix in STEPS:
            before = total(applied)
            applied.add(fix)
            after = total(applied)
            rows.append((label, float(after), float(after - before)))

        gold = con.execute("""select sum(net_cad) from gold.mart_daily_cash
                              where strftime(processor_date, '%Y-%m') = ?""", [month]).fetchone()[0]
        queue = con.execute("select coalesce(sum(orders), 0) from gold.mart_fulfilment_queue").fetchone()[0]
        stuck = con.execute("""select coalesce(sum(orders), 0) from gold.mart_fulfilment_queue
                               where waiting = '4. over 72h'""").fetchone()[0]
    naive_waiting, naive_stuck = naive_queue(through)
    return {"steps": rows, "gold": float(gold or 0), "queue_gold": int(queue), "stuck_gold": int(stuck),
            "queue_naive": naive_waiting, "stuck_naive": naive_stuck}
