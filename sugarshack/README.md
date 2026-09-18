# sugarshack

A medallion lakehouse small enough to read in one sitting, and messy enough to be worth
reading.

It generates two months of orders and payments for Saltbox Market, a made-up Halifax
marketplace, with the problems real sources have: payment notifications delivered twice,
database changes arriving out of order, a payment API that changes shape mid-month,
refunds that turn up weeks later, and a landing job that re-sends files. Then it builds
the lake three ways:

1. **Bronze.** Every line, exactly as it arrived, stored once, with a commit log.
2. **Silver.** Parsed, typed, deduplicated and folded into current state, with anything
   unusable quarantined and labelled instead of dropped.
3. **Gold.** Business tables, built into a staging schema, audited, and only then
   published. The cash table is checked against the payment processor's settlement
   report to the cent.

It also ships the naive pipeline the business had before (the "bucket brigade"), and a
command that walks from its wrong number to the right one, one mistake at a time.

Companion code for the post
[The Maple Syrup Guide to Data Lakes](https://kunalvyas.info/blog/maple-syrup-guide-to-data-lakes.html).

**What this is not.** A production platform. It runs on DuckDB and dbt on one machine, so
you can see every moving part in a couple of minutes. The post explains how each piece
maps onto Spark, Delta Lake or Iceberg, and Databricks.

---

## Before you start

| You need | Notes |
|---|---|
| Python 3.11 or newer | `python3 --version` |
| ~200 MB of free disk | The generated season is about 100 MB; the lake and warehouse add about 30 MB |
| Nothing else | No Java, no Docker, no cloud account. DuckDB and dbt install with pip. |

Everything below assumes a terminal in the folder that contains this README.

---

## Step 1. Install

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .
```

That installs `duckdb`, `dbt-core` and `dbt-duckdb`, plus the `sugarshack` command.

```bash
sugarshack --help
```

---

## Step 2. Grow the sugarbush

```bash
sugarshack sugarbush
```

This writes every source file for August and September 2026, and the refunds and
settlements that trail into October, to `data/landing/`. It takes a few seconds and prints:

```
wrote .../data/landing
  order changes    165,471
  payment events   56,743
  hourly files     3,403
  resent files     7
  truncated lines  41
```

With the default seed, everything is deterministic: you will see the same numbers as the
post. `--seed` gives you a different season.

Every file name carries the time it "arrived". The other commands take a `--through`
time and only see files that had arrived by then, which is how you replay the season one
day at a time.

---

## Step 3. Build the lake

```bash
sugarshack run --through 2026-08-16
```

`run` is three steps, each also available on its own:

| Step | Command | What it does |
|---|---|---|
| tap | `sugarshack tap --through ...` | Copies newly arrived files into bronze Parquet, once each |
| boil | `sugarshack boil --through ...` | Runs the dbt project: silver, then gold into `gold_build`, with tests |
| grade | `sugarshack grade --through ...` | Audits `gold_build`; publishes it to `gold` only if nothing blocks |

A `--through` with only a date means the end of that day, UTC. With a time, it means
exactly then: `--through 2026-09-08T12:00`.

Output:

```
as of 2026-08-16 23:59 UTC
  tapped   orders       batch   1   384 files   43,035 rows
  tapped   payments     batch   2   384 files   15,382 rows
  tapped   fx_rates     batch   3    12 files       12 rows
  tapped   settlements  batch   4    15 files       30 rows
  skipped  3 file(s) with the same bytes as one already in bronze
  boiled   15 models, 17 tests
  PASS   quarantine rate  orders 0.00% of 43,035; payments 0.02% of 15,382 (mostly unparseable_json)
  PASS   conservation     15,006 events, same count and same net in silver and gold
  PASS   fx coverage      every USD event has a rate; the oldest used is 2 days old
  PASS   reconciliation   30 settlement lines match to the cent

Published gold as of 2026-08-16 23:59 UTC.
```

Run it again with the same `--through` and tap reports `nothing new has arrived`.

---

## Step 4. Replay the post

The post walks through a few moments of the season. To see them yourself, start from an
empty lake (`rm -rf data/lake`) and run these in order.

**The payment API changes shape (August 17).** Pretend the pipeline only knows the old
version:

```bash
SUGAR_PARSERS=2025-11-01 sugarshack run --through 2026-08-16
SUGAR_PARSERS=2025-11-01 sugarshack run --through 2026-08-17T12:00
```

The second run blocks: about 20% of the new payment rows have an API version no parser
understands. They sit in `silver.quarantine`, and `gold` still shows August 16.

**Add the parser, replay from bronze.** The parser for the new version is already in
`sugarshack/shack/macros/parsers.sql`; without `SUGAR_PARSERS` both versions are enabled.

```bash
sugarshack run --through 2026-08-17T12:00 --replay
```

`--replay` rebuilds silver and gold from every row in bronze. The quarantine drains and
the build publishes.

**The Tuesday after Labour Day.** Catch up, then compare the two pipelines:

```bash
sugarshack run     --through 2026-09-08T12:00
sugarshack bucket  --through 2026-09-08T12:00
sugarshack compare --through 2026-09-08T12:00
```

```
2026-08 net revenue, as of 2026-09-08 12:00 UTC

  bucket brigade dashboard                           C$2,864,598.75
  re-sent files counted twice       -   16,287.17    C$2,848,311.58
  webhook retries counted twice     -   72,401.70    C$2,775,909.88
  v2 amounts read as null           +  319,482.85    C$3,095,392.73
  refunds never subtracted          -  149,038.45    C$2,946,354.28
  USD added as if it were CAD       +  248,650.25    C$3,195,004.53

  gold.mart_daily_cash C$3,195,004.53 (matches)

  awaiting shipment          all   over 72h
  bucket brigade           1,505         54
  gold                     1,481          4
```

Catching up in one jump gives the same gold tables as running every day in between. The
test suite checks that.

**Late refunds.** Keep going and watch August move in one table and stay put in the other:

```bash
sugarshack run --through 2026-10-15
sugarshack query "select sum(net_cad) from gold.mart_order_revenue where order_date between '2026-08-01' and '2026-08-31'"
sugarshack query "select sum(net_cad) from gold.mart_daily_cash where processor_date between '2026-08-01' and '2026-08-31'"
```

---

## Reading the grades

| Line | Meaning |
|---|---|
| `PASS` | Fine. |
| `WARN` | Worth a look; the build still publishes. |
| `BLOCK` | The build is not published. `gold` keeps the last graded build. |
| `warn  relationships_...` | A dbt test at warning level. Usually a payment whose order hasn't arrived through CDC yet. |

| Audit | Blocks when |
|---|---|
| quarantine rate | More than 2% of rows that arrived since the last publish are unusable, and at least 10 rows |
| conservation | Silver and gold disagree on the number of payment events or their net |
| fx coverage | A USD event has no exchange rate on or before its date |
| reconciliation | A day's cash differs from the settlement report and the day closed more than 48 hours ago. Younger gaps are warnings: webhooks for that day may still be arriving. |

Exit code 1 means the build was not published, or dbt failed.

---

## Configuration

Environment variables:

| Variable | Default | What it does |
|---|---|---|
| `SUGAR_DATA` | `./data` | Where landing files, the lake and the warehouse live |
| `SUGAR_PARSERS` | `2025-11-01,2026-08-01` | Payment API versions silver will parse |

Decisions you make once are constants in the source:

| Constant | Where | Default |
|---|---|---|
| `QUARANTINE_WARN`, `QUARANTINE_BLOCK` | `sugarshack/config.py` | 0.5%, 2% |
| `QUARANTINE_MIN_ROWS` | `sugarshack/config.py` | 10 |
| `SETTLING_HOURS` | `sugarshack/config.py` | 48 |
| `payment_parsers()` | `sugarshack/shack/macros/parsers.sql` | One entry per API version |
| `business_tz` | `sugarshack/shack/dbt_project.yml` | `America/Halifax` |

---

## Looking around

```bash
sugarshack status                                   # what gold shows, and as of when
sugarshack query "select * from silver.quarantine limit 5"
sugarshack query "show all tables"
```

`query` opens the warehouse read-only. Schemas:

| Schema | Tables |
|---|---|
| `bronze` | Views over the committed Parquet files, one per source |
| `silver` | `stg_*` parsing views, `silver_payments`, `silver_orders`, `silver_fx_rates`, `silver_settlements`, `quarantine` |
| `gold_build` | The latest build, graded or not |
| `gold` | The latest build that passed grading, plus `_published`, the history |

If you prefer the DuckDB CLI or a notebook, open `data/lake/warehouse.duckdb`, but close it
before the next `run` (see Troubleshooting).

---

## How it works

```
sugarshack/sugarbush.py   Generates the sources and their mess. Read the docstring for the list.
sugarshack/tap.py         Bronze. Content-hashed files, one Parquet file per batch, a manifest
                          written last, orphan files from a crash swept on the next run.
sugarshack/shack/         The dbt project.
  macros/bronze.sql         Bronze views list the manifest, not the folder.
  macros/parsers.sql        One parser per payment API version.
  models/silver/            Parse, quarantine, dedupe by event id, fold orders by LSN.
  models/gold/              Signed payments with FX, daily cash, revenue by order date
                            (rebuilt only for dates new data touches), fulfilment queue.
sugarshack/grade.py       Audits gold_build, then publishes to gold in one transaction.
sugarshack/bucket.py      The old pipeline, reading landing files directly.
sugarshack/compare.py     Fixes the old pipeline one mistake at a time.
tests/                    End-to-end tests of the claims in the post.
```

---

## Tests

```bash
pip install -e ".[test]"
pytest -q
```

About a minute and a half. They check that tapping twice changes nothing, that a crashed
batch is invisible and then swept, that the API change blocks until replayed, that daily
builds equal a single replay, that orders fold by LSN, and that the comparison lands on
gold.

---

## Troubleshooting

**`IO Error: Could not set lock on file ".../warehouse.duckdb"`**
Another process has the warehouse open: a DuckDB CLI session, a notebook, or a second
`sugarshack` command. DuckDB allows one writer at a time. Close the other process and run
again.

**`dbt could not start: ...`**
dbt failed before building anything. The message after the colon is dbt's own error.
Run the same command with `--verbose` to see all of dbt's output.

**`Nothing in bronze yet. Run sugarshack tap first.`**
`boil` and `grade` need at least one tapped batch. Use `run`, or `tap` first.

**`data/landing already exists`**
`sugarbush` won't overwrite your season. Use `sugarshack sugarbush --force`, which deletes
and regenerates it. It does not touch `data/lake`; delete that too if you want a clean start.

**A run blocks on reconciliation you don't expect**
A day older than 48 hours doesn't match its settlement report. Look at both sides:
`sugarshack query "select * from silver.silver_settlements where settlement_date = 'YYYY-MM-DD'"`
and the same day in `gold_build.mart_daily_cash`. If you changed a model, `--replay`.

**Numbers differ from the post**
Check you ran `sugarbush` without `--seed`, and replayed the same `--through` times.
`rm -rf data/lake` and start Step 4 again.

**Windows**
This has been tested on Linux. It is all Python, so it should run
in PowerShell, where variables are set with `$env:SUGAR_PARSERS = "2025-11-01"` and
cleared with `Remove-Item Env:SUGAR_PARSERS`. If it doesn't, please open an issue.

---

## Uninstall

```bash
rm -rf data .venv
```

---

## Known limits

- Bronze uses a JSON-lines manifest as its commit log. That is the idea behind Delta
  Lake and Iceberg, without their guarantees: no concurrent writers, no time travel, no
  compaction. Use a real table format in production.
- Silver rebuilds from bronze with `--replay` in seconds because the data is small. At
  lake scale, replays are planned events, and you would replay a date range, not
  everything.
- The quarantine is only drained by replaying. There is no tooling to inspect, fix and
  re-inject individual rows.
- One machine, one writer. No orchestration, retries or alerting; `run` is what a
  scheduler would call.
- The sources are synthetic. The mess is modelled on real systems, but it is still a
  model.
