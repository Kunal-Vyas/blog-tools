"""sugarshack: tap, boil, grade.

    sugarshack sugarbush                       write a season of source files to data/landing
    sugarshack run --through 2026-08-31        tap -> boil -> grade (and publish if it passes)
    sugarshack bucket --through ...            what the old pipeline would have said
    sugarshack compare --through ...           why the two disagree
    sugarshack query "select ..."              look at any table, read-only
    sugarshack status                          what is published, and when
"""
import argparse
import sys
from datetime import datetime, time, timezone

import duckdb

from . import config

UTC = timezone.utc


def when(text: str) -> datetime:
    """'2026-08-31' means the end of that day (UTC); '2026-09-08T12:00' means exactly then."""
    if "T" in text:
        value = datetime.fromisoformat(text)
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.combine(datetime.fromisoformat(text).date(), time(23, 59, 59), UTC)


def money(x: float) -> str:
    return f"C${x:,.2f}" if x >= 0 else f"-C${-x:,.2f}"


def cmd_sugarbush(args):
    from .sugarbush import generate
    stats = generate(seed=args.seed, force=args.force)
    print(f"wrote {config.LANDING}")
    for k, v in stats.items():
        print(f"  {k.replace('_', ' '):<16} {v:,}")


def cmd_tap(args):
    from .tap import tap
    report = tap(args.through)
    if report["orphans_removed"]:
        print(f"  swept {report['orphans_removed']} uncommitted batch file(s) from a previous crash")
    for b in report["batches"]:
        print(f"  tapped   {b['source']:<12} batch {b['batch_seq']:>3}  {b['files']:>4} files  {b['rows']:>7,} rows")
    if report["skipped_duplicates"]:
        print(f"  skipped  {report['skipped_duplicates']} file(s) with the same bytes as one already in bronze")
    if not report["batches"]:
        print("  nothing new has arrived")
    return report


def cmd_boil(args):
    from .boil import boil
    s = boil(args.through, replay=args.replay, verbose=args.verbose)
    verb = "replayed" if args.replay else "boiled"
    print(f"  {verb:<8} {s['models']} models, {s['tests']} tests" + ("" if s["ok"] else "  FAILED"))
    for w in s["warnings"]:
        print(f"  warn     {w}")
    for f in s["failures"]:
        print(f"  {f}")
    return s["ok"]


def cmd_grade(args):
    from .grade import grade, publish
    results, previous = grade(args.through)
    for r in results:
        print(f"  {r.status:<6} {r.name:<16} {r.detail}")
    if any(r.status == "BLOCK" for r in results):
        stale = f"the build as of {previous['as_of']:%Y-%m-%d %H:%M} UTC" if previous else "nothing yet"
        print(f"\nNot published. gold still shows {stale}.")
        return False
    publish(args.through, results)
    print(f"\nPublished gold as of {args.through:%Y-%m-%d %H:%M} UTC.")
    return True


def cmd_run(args):
    print(f"as of {args.through:%Y-%m-%d %H:%M} UTC")
    cmd_tap(args)
    if not cmd_boil(args):
        print("\nNot graded: dbt failed, so gold_build is incomplete.")
        return False
    return cmd_grade(args)


def cmd_bucket(args):
    from .bucket import naive_queue, naive_revenue
    print(f"bucket brigade, as of {args.through:%Y-%m-%d %H:%M} UTC")
    print(f"  {args.month} revenue       {money(naive_revenue(args.through, args.month))}")
    waiting, stuck = naive_queue(args.through)
    print(f"  awaiting shipment    {waiting:,} orders ({stuck:,} for more than 72h)")


def cmd_compare(args):
    from .compare import compare
    r = compare(args.through, args.month)
    print(f"{args.month} net revenue, as of {args.through:%Y-%m-%d %H:%M} UTC\n")
    for label, total, delta in r["steps"]:
        change = "" if delta is None else f"{'+' if delta >= 0 else '-'}{money(abs(delta))[2:]:>12}"
        print(f"  {label:<32} {change:>14}   {money(total):>15}")
    match = "matches" if abs(r["steps"][-1][1] - r["gold"]) < 0.005 else "DOES NOT MATCH"
    print(f"\n  gold.mart_daily_cash {money(r['gold'])} ({match})")
    print("\n  awaiting shipment          all   over 72h")
    print(f"  bucket brigade        {r['queue_naive']:>8,} {r['stuck_naive']:>10,}")
    print(f"  gold                  {r['queue_gold']:>8,} {r['stuck_gold']:>10,}")


def cmd_status(args):
    if not config.WAREHOUSE.exists():
        print("Nothing built yet.")
        return
    with duckdb.connect(str(config.WAREHOUSE), read_only=True) as con:
        con.execute("set TimeZone = 'UTC'")
        from .grade import last_published
        last = last_published(con)
        if not last:
            print("Nothing published yet.")
            return
        print(f"gold as of {last['as_of']:%Y-%m-%d %H:%M} UTC, bronze batches up to {last['through_seq']}")
        print(con.sql("select * from gold.mart_daily_cash order by processor_date desc, currency limit 6"))


def cmd_query(args):
    with duckdb.connect(str(config.WAREHOUSE), read_only=True) as con:
        con.execute("set TimeZone = 'UTC'")
        con.sql(args.sql).show(max_rows=args.rows, max_width=160)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="sugarshack", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("sugarbush", help="generate the landing files")
    p.add_argument("--seed", type=int, default=22)
    p.add_argument("--force", action="store_true", help="delete and regenerate data/landing")
    p.set_defaults(fn=cmd_sugarbush)

    def through(p, month=False):
        p.add_argument("--through", type=when, required=True,
                       help="pretend it is this moment (UTC): 2026-08-31 or 2026-09-08T12:00")
        if month:
            p.add_argument("--month", default="2026-08")

    for name, fn, text in [("tap", cmd_tap, "land new files in bronze"),
                           ("boil", cmd_boil, "build silver and gold_build with dbt"),
                           ("grade", cmd_grade, "audit gold_build and publish it to gold"),
                           ("run", cmd_run, "tap, boil and grade")]:
        p = sub.add_parser(name, help=text)
        through(p)
        if name in ("boil", "run"):
            p.add_argument("--replay", action="store_true", help="rebuild silver and gold from all of bronze")
            p.add_argument("--verbose", action="store_true", help="show dbt's own output")
        p.set_defaults(fn=fn)

    p = sub.add_parser("bucket", help="the old pipeline's numbers")
    through(p, month=True)
    p.set_defaults(fn=cmd_bucket)
    p = sub.add_parser("compare", help="walk from the old number to the gold one")
    through(p, month=True)
    p.set_defaults(fn=cmd_compare)
    p = sub.add_parser("query", help="run read-only SQL against the warehouse")
    p.add_argument("sql")
    p.add_argument("--rows", type=int, default=40)
    p.set_defaults(fn=cmd_query)
    p = sub.add_parser("status", help="what gold currently shows")
    p.set_defaults(fn=cmd_status)

    args = parser.parse_args(argv)
    try:
        outcome = args.fn(args)
    except BrokenPipeError:              # e.g. `sugarshack query ... | head`
        sys.stderr.close()
        return 0
    return 1 if outcome is False else 0


if __name__ == "__main__":
    sys.exit(main())
