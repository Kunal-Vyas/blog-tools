"""The sugarbush: synthetic sources for Saltbox Market, a (fictional) Halifax marketplace.

Writes a whole season of landing files up front: orders placed in August and September
2026, and everything that follows from them until mid-October. Every file name carries the time it
"arrived", and `tap --through` only picks up files that have arrived by then, so you can
replay August 2026 one day at a time.

Four sources, each with the kind of mess real ones have:

  orders       CDC from the shop's Postgres (Debezium-style envelopes). About 2% of
               changes arrive hours or days late, so files are not in commit order. Test
               orders are created and then deleted.
  payments     Webhooks from the payment processor. Delivered at least once, so about 2.5%
               arrive twice. Saltbox sells in USD through a separate US account, and on
               2026-08-17 that account moves to API version 2026-08-01, which reshapes
               the payload. The CAD account stays on 2025-11-01. A receiver crash writes a few truncated lines,
               which the processor then retries successfully.
  fx_rates     A daily USD/CAD file on business days. One day is republished with a
               correction.
  settlements  The processor's daily settlement report, in minor units, by UTC day.
               This is the independent scale the gold layer is weighed against.

On top of that, the landing job re-sends a handful of files byte for byte.
"""
import csv
import hashlib
import io
import json
import math
import random
import shutil
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from .config import LANDING

UTC = timezone.utc
MONTH_START = datetime(2026, 8, 1, tzinfo=UTC)
ORDERS_END = datetime(2026, 10, 1, tzinfo=UTC)        # orders are placed through September
SEASON_END = datetime(2026, 10, 16, tzinfo=UTC)      # nothing arrives after this
DRIFT_AT = datetime(2026, 8, 17, tzinfo=UTC)          # the US account moves to the new API
V1, V2 = "2025-11-01", "2026-08-01"

REGIONS = {"NS": 24, "ON": 22, "QC": 12, "BC": 11, "AB": 9, "NB": 8, "PE": 4, "NL": 4, "MB": 3, "SK": 3}
HOURLY = [2, 1, 1, 1, 1, 2, 3, 4, 5, 6, 7, 7, 8, 7, 7, 7, 8, 9, 10, 10, 9, 7, 5, 3]  # local hour weights


class Season:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.order_changes = []      # (ts, payload-without-lsn)
        self.payment_events = []     # dicts with a "created" datetime
        self.n = 0

    def uid(self, prefix: str, width: int = 12) -> str:
        self.n += 1
        return f"{prefix}_{hashlib.sha1(f'{prefix}{self.n}'.encode()).hexdigest()[:width]}"

    # -- orders and their lifecycle -------------------------------------------------------
    def build_orders(self):
        rng = self.rng
        day = MONTH_START
        while day < ORDERS_END:
            weekend = day.weekday() >= 5
            count = int(rng.gauss(1000 if weekend else 880, 60))
            for _ in range(count):
                local_hour = rng.choices(range(24), HOURLY)[0]
                utc_hour = (local_hour + 3) % 24               # Halifax is UTC-3 in August
                t0 = day + timedelta(hours=utc_hour, seconds=rng.randrange(3600))
                if t0 >= ORDERS_END:
                    t0 = ORDERS_END - timedelta(seconds=rng.randrange(1, 3600))
                self.order_lifecycle(t0)
            day += timedelta(days=1)

    def order_lifecycle(self, t0: datetime):
        rng = self.rng
        usd = rng.random() < 0.22
        row = {
            "order_id": self.uid("ord", 10),
            "customer_id": f"cus_{rng.randrange(1, 60000):05d}",
            "status": "placed",
            "currency": "usd" if usd else "cad",
            "total_minor": int(min(90000, max(1500, rng.lognormvariate(math.log(9800), 0.55)))),
            "ship_region": "US" if usd else rng.choices(list(REGIONS), list(REGIONS.values()))[0],
            "created_at": t0.isoformat(),
            "updated_at": t0.isoformat(),
        }
        if rng.random() < 0.003:                                   # QA test order: created, then deleted
            row["customer_id"] = f"cus_qa_{rng.randrange(100):02d}"
            self.change("c", t0, None, row)
            self.change("d", t0 + timedelta(hours=rng.uniform(1, 6)), row, None)
            return
        self.change("c", t0, None, row)

        if rng.random() < 0.04:                                    # abandoned before payment
            self.update(row, t0 + timedelta(hours=rng.uniform(1, 48)), status="cancelled")
            return

        paid = t0 + timedelta(seconds=rng.uniform(30, 300))
        charge = self.uid("ch")
        self.update(row, paid, status="paid")
        self.payment("charge.succeeded", paid, row, charge, row["total_minor"])

        if rng.random() < 0.015:                                   # address fixed before shipping
            regions = [r for r in REGIONS if r != row["ship_region"]] if row["currency"] == "cad" else ["US"]
            self.update(row, paid + timedelta(minutes=rng.uniform(10, 360)), ship_region=rng.choice(regions))

        if rng.random() < 0.03:                                    # cancelled after payment: full refund
            at = paid + timedelta(hours=rng.uniform(2, 30))
            self.update(row, at, status="cancelled")
            self.payment("charge.refunded", at, row, charge, row["total_minor"])
            return

        self.update(row, paid + timedelta(hours=rng.uniform(18, 72)), status="shipped")

        if rng.random() < 0.05:                                    # returned weeks later
            at = paid + timedelta(days=rng.lognormvariate(math.log(14), 0.6))
            full = rng.random() < 0.6
            amount = row["total_minor"] if full else int(row["total_minor"] * rng.uniform(0.2, 0.6))
            self.payment("charge.refunded", at, row, charge, amount)
            if full:
                self.update(row, at, status="returned")

    def update(self, row: dict, ts: datetime, **changes):
        before = dict(row)
        row.update(changes, updated_at=ts.isoformat())
        self.change("u", ts, before, dict(row))

    def change(self, op, ts, before, after):
        if ts < SEASON_END:
            self.order_changes.append((ts, {"op": op, "ts_ms": int(ts.timestamp() * 1000),
                                            "before": before, "after": after and dict(after)}))

    # -- payments -------------------------------------------------------------------------
    def payment(self, kind: str, ts: datetime, order: dict, charge: str, amount: int):
        if ts >= SEASON_END:
            return
        self.payment_events.append({
            "id": self.uid("evt", 16), "type": kind, "created": ts, "charge": charge,
            "refund": self.uid("re") if kind == "charge.refunded" else None,
            "order_id": order["order_id"], "amount": amount, "currency": order["currency"],
            "charge_amount": order["total_minor"],
        })


def render_payment(e: dict) -> str:
    """The same event, as the processor would have sent it on that day."""
    if e["created"] < DRIFT_AT or e["currency"] == "cad":
        obj = {"id": e["charge"], "object": "charge", "order_id": e["order_id"],
               "amount": e["charge_amount"], "currency": e["currency"]}
        if e["refund"]:
            obj["refund"] = {"id": e["refund"], "amount": e["amount"]}
        version = V1
    else:
        # 2026-08-01: amounts become objects, currency moves inside them and is upper-cased,
        # order_id moves under metadata, and refunds become their own object.
        money = {"value": e["amount"], "currency": e["currency"].upper()}
        if e["refund"]:
            obj = {"id": e["refund"], "object": "refund", "charge": e["charge"], "amount": money,
                   "metadata": {"order_id": e["order_id"]}}
        else:
            obj = {"id": e["charge"], "object": "charge", "amount": money,
                   "metadata": {"order_id": e["order_id"]}}
        version = V2
    return json.dumps({"id": e["id"], "type": e["type"], "api_version": version,
                       "created": int(e["created"].timestamp()), "data": {"object": obj}},
                      separators=(",", ":"))


def hour_file(source: str, arrived: datetime) -> str:
    return f"{source}/{arrived:%Y-%m-%d}/{source}-{arrived:%Y%m%dT%H00}.jsonl"


def write(path: str, text: str):
    target = LANDING / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


def generate(seed: int = 22, force: bool = False) -> dict:
    if LANDING.exists():
        if not force:
            raise SystemExit(f"{LANDING} already exists. Use --force to regenerate it.")
        shutil.rmtree(LANDING)
    s = Season(seed)
    rng = s.rng
    s.build_orders()

    # -- orders: commit order defines the LSN; arrival order is what the files see -------
    s.order_changes.sort(key=lambda c: c[0])
    files = defaultdict(list)
    for lsn, (ts, change) in enumerate(s.order_changes, start=10_000_000):
        change["source"] = {"db": "saltbox", "table": "orders", "lsn": lsn}
        roll, delay = rng.random(), rng.uniform(1, 20)
        if roll < 0.015:
            delay += rng.uniform(3600, 4 * 3600)             # connector rebalance
        elif roll < 0.02:
            delay += rng.uniform(6 * 3600, 60 * 3600)        # a partition stuck behind a bad consumer
        arrived = ts + timedelta(seconds=delay)
        files[hour_file("orders", arrived)].append((arrived, json.dumps(change, separators=(",", ":"))))

    # -- payments: at-least-once delivery, a truncated line or two ------------------------
    truncated = 0
    for e in s.payment_events:
        line = render_payment(e)
        delay = rng.lognormvariate(math.log(2), 0.8)
        if rng.random() < 0.005:
            delay += rng.uniform(3600, 36 * 3600)                    # processor-side outage
        first = e["created"] + timedelta(seconds=delay)
        if rng.random() < 0.0008:                                    # receiver crashed mid-write
            files[hour_file("payments", first)].append((first, line[: rng.randrange(20, len(line) - 5)]))
            first += timedelta(minutes=rng.uniform(5, 60))              # ...so the processor retried
            truncated += 1
        files[hour_file("payments", first)].append((first, line))
        if rng.random() < 0.025:                                     # retried although we answered 200
            again = first + timedelta(minutes=rng.uniform(5, 360))
            files[hour_file("payments", again)].append((again, line))

    written = 0
    for path, lines in files.items():
        if lines[0][0] >= SEASON_END:
            continue
        lines.sort(key=lambda x: x[0])
        write(path, "\n".join(text for _, text in lines) + "\n")
        written += 1

    # -- the landing job re-sends a few files byte for byte -------------------------------
    candidates = sorted(p for p in files if p.startswith(("orders/2026-08", "payments/2026-08")))
    resent = rng.sample(candidates, 7)
    for path in resent:
        stamp = path.rsplit("-", 1)[1].split(".")[0]                 # e.g. 20260812T1400
        arrived = datetime.strptime(stamp, "%Y%m%dT%H00").replace(tzinfo=UTC) + timedelta(hours=1)
        source = path.split("/")[0]
        copy = f"{source}/{arrived:%Y-%m-%d}/{source}-{arrived:%Y%m%dT%H00}-resend.jsonl"
        write(copy, (LANDING / path).read_text())

    # -- fx: business days, published 16:30 Halifax (19:30 UTC), one correction ----------
    rate, d = 1.3725, date(2026, 7, 31)
    while d < SEASON_END.date():
        if d.weekday() < 5:
            rate = round(rate + rng.gauss(0, 0.0035), 4)
            published = datetime(d.year, d.month, d.day, 19, 30, tzinfo=UTC)
            write(f"fx_rates/{d}/fx_rates-{published:%Y%m%dT%H00}.csv",
                  f"rate_date,base,quote,rate\n{d},USD,CAD,{rate}\n")
            if d == date(2026, 8, 12):
                fixed = published + timedelta(hours=14)
                write(f"fx_rates/{fixed.date()}/fx_rates-{fixed:%Y%m%dT%H00}.csv",
                      f"rate_date,base,quote,rate\n{d},USD,CAD,{round(rate + 0.0041, 4)}\n")
        d += timedelta(days=1)

    # -- settlements: the processor's truth, by UTC day, next morning ---------------------
    totals = defaultdict(lambda: [0, 0, 0, 0])
    for e in s.payment_events:
        t = totals[(e["created"].date(), e["currency"])]
        if e["type"] == "charge.succeeded":
            t[0] += e["amount"]; t[2] += 1
        else:
            t[1] += e["amount"]; t[3] += 1
    d = MONTH_START.date()
    while d < SEASON_END.date() - timedelta(days=1):
        buf = io.StringIO()
        out = csv.writer(buf, lineterminator="\n")
        out.writerow(["settlement_date", "currency", "gross_minor", "refunds_minor",
                      "net_minor", "charge_count", "refund_count"])
        for cur in ("cad", "usd"):
            g, r, nc, nr = totals.get((d, cur), [0, 0, 0, 0])
            out.writerow([d, cur, g, r, g - r, nc, nr])
        arrived = datetime(d.year, d.month, d.day, 6, tzinfo=UTC) + timedelta(days=1)
        write(f"settlements/{arrived.date()}/settlements-{arrived:%Y%m%dT%H00}.csv", buf.getvalue())
        d += timedelta(days=1)

    return {"order_changes": len(s.order_changes), "payment_events": len(s.payment_events),
            "hourly_files": written, "resent_files": len(resent), "truncated_lines": truncated}
