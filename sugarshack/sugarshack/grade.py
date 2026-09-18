"""Grade the build, then publish it, or don't.

dbt tests ask whether each row is syrup. Grading asks whether the batch is: is the
share of unusable rows normal, does every cent in silver reach gold, and does the gold
cash table weigh the same as the processor's own settlement report?

This is write-audit-publish. dbt writes gold into `gold_build`. The audits below read it.
Only if none of them blocks does `publish` copy it into `gold`, in one transaction, so
dashboards see either the previous graded build or this one, never something in between.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

import duckdb

from .config import QUARANTINE_BLOCK, QUARANTINE_MIN_ROWS, QUARANTINE_WARN, SETTLING_HOURS, WAREHOUSE

GOLD_TABLES = ("fct_payments", "mart_daily_cash", "mart_order_revenue", "mart_fulfilment_queue")


@dataclass
class Result:
    name: str
    status: str          # PASS, WARN or BLOCK
    detail: str


def last_published(con) -> dict | None:
    exists = con.execute("""select count(*) from information_schema.tables
                            where table_schema = 'gold' and table_name = '_published'""").fetchone()[0]
    if not exists:
        return None
    row = con.execute("""select as_of, through_seq, published_at from gold._published
                         order by published_at desc limit 1""").fetchone()
    return row and {"as_of": row[0], "through_seq": row[1], "published_at": row[2]}


def audit_quarantine(con, since_seq: int) -> Result:
    """Of the rows that arrived since the last publish, how many could no parser use?"""
    rows = con.execute(f"""
        with arrived as (
            select 'payments' as source, count(*) as n from silver.stg_payment_events where _batch_seq > {since_seq}
            union all
            select 'orders', count(*) from silver.stg_order_changes where _batch_seq > {since_seq}
        ),
        held as (
            select source, count(*) as n, mode(quarantine_reason) as top_reason
            from silver.quarantine where _batch_seq > {since_seq}
            group by source
        )
        select a.source, a.n, coalesce(h.n, 0), h.top_reason
        from arrived a left join held h using (source)
        order by a.source
    """).fetchall()
    worst, parts = "PASS", []
    for source, arrived, held, reason in rows:
        rate = held / arrived if arrived else 0.0
        if rate > QUARANTINE_BLOCK and held >= QUARANTINE_MIN_ROWS:
            worst = "BLOCK"
        elif rate > QUARANTINE_WARN and worst == "PASS":
            worst = "WARN"
        note = f" (mostly {reason})" if held else ""
        parts.append(f"{source} {rate:.2%} of {arrived:,}{note}")
    return Result("quarantine rate", worst, "; ".join(parts))


def audit_conservation(con) -> Result:
    """Every event in silver reaches gold exactly once, and the money adds up."""
    s_n, s_sum = con.execute("""select count(*), sum(case event_type when 'capture' then amount_minor
                                                             else -amount_minor end)
                                from silver.silver_payments""").fetchone()
    g_n, g_sum = con.execute("select count(*), sum(amount_minor) from gold_build.fct_payments").fetchone()
    if (s_n, s_sum) != (g_n, g_sum):
        return Result("conservation", "BLOCK",
                      f"silver has {s_n:,} events netting {s_sum:,}; gold has {g_n:,} netting {g_sum:,}")
    return Result("conservation", "PASS", f"{g_n:,} events, same count and same net in silver and gold")


def audit_fx(con) -> Result:
    missing = con.execute("select count(*) from gold_build.fct_payments where fx_rate is null").fetchone()[0]
    if missing:
        return Result("fx coverage", "BLOCK", f"{missing:,} USD events have no rate on or before their date")
    stale = con.execute("""select max(processor_date - fx_rate_date) from gold_build.fct_payments
                           where currency = 'usd'""").fetchone()[0] or 0
    status = "WARN" if stale > 4 else "PASS"
    return Result("fx coverage", status, f"every USD event has a rate; the oldest used is {stale} days old")


def audit_reconciliation(con, as_of: datetime) -> Result:
    """Weigh the barrels: gold cash per day and currency against the processor's settlement."""
    rows = con.execute("""
        select s.settlement_date, s.currency,
               s.gross_minor, s.refunds_minor, s.net_minor,
               coalesce(c.captured_minor, 0), coalesce(c.refunded_minor, 0),
               coalesce(c.net_minor, 0)
        from silver.silver_settlements s
        left join gold_build.mart_daily_cash c
               on c.processor_date = s.settlement_date and c.currency = s.currency
        order by 1, 2
    """).fetchall()
    settling, broken = [], []
    for day, cur, sg, sr, sn, gg, gr, gn in rows:
        if (sg, sr, sn) == (gg, gr, gn):
            continue
        closed_at = datetime.combine(day + timedelta(days=1), datetime.min.time(), as_of.tzinfo)
        gap = f"{day} {cur.upper()} net off by {(gn - sn) / 100:+,.2f}"
        (settling if as_of - closed_at < timedelta(hours=SETTLING_HOURS) else broken).append(gap)
    if broken:
        more = " ..." if len(broken) > 3 else ""
        return Result("reconciliation", "BLOCK", "; ".join(broken[:3]) + more)
    if settling:
        return Result("reconciliation", "WARN", "still settling: " + "; ".join(settling[:3]))
    return Result("reconciliation", "PASS", f"{len(rows)} settlement lines match to the cent")


def grade(as_of: datetime) -> tuple[list[Result], dict | None]:
    with duckdb.connect(str(WAREHOUSE)) as con:
        previous = last_published(con)
        since = previous["through_seq"] if previous else 0
        results = [
            audit_quarantine(con, since),
            audit_conservation(con),
            audit_fx(con),
            audit_reconciliation(con, as_of),
        ]
    return results, previous


def publish(as_of: datetime, results: list[Result]) -> None:
    summary = "; ".join(f"{r.name}: {r.status}" for r in results)
    with duckdb.connect(str(WAREHOUSE)) as con:
        through_seq = con.execute("""select greatest(
                (select coalesce(max(_batch_seq), 0) from silver.stg_payment_events),
                (select coalesce(max(_batch_seq), 0) from silver.stg_order_changes))
            """).fetchone()[0]
        con.execute("begin transaction")
        try:
            con.execute("create schema if not exists gold")
            for table in GOLD_TABLES:
                con.execute(f"create or replace table gold.{table} as "
                            f"select * from gold_build.{table}")
            con.execute("""create table if not exists gold._published (
                               as_of timestamptz, through_seq bigint,
                               published_at timestamptz, audits varchar)""")
            con.execute("insert into gold._published values (?, ?, now(), ?)",
                        [as_of, through_seq, summary])
            con.execute("commit")
        except Exception:
            con.execute("rollback")
            raise
