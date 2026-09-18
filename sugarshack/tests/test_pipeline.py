"""End-to-end checks of the properties the post claims. Takes a few minutes."""
import json

GOLD_QUERIES = {
    "fct_payments": "select * exclude (_batch_seq, _ingested_at) from gold.fct_payments",
    "mart_daily_cash": "select * from gold.mart_daily_cash",
    "mart_order_revenue": "select * exclude (_built_through_seq) from gold.mart_order_revenue",
    "mart_fulfilment_queue": "select * from gold.mart_fulfilment_queue",
}


def test_tap_is_idempotent(shack):
    first = shack.run("tap", "--through", "2026-08-20").stdout
    assert "skipped" in first                        # the re-sent files are recognised by content
    again = shack.run("tap", "--through", "2026-08-20").stdout
    assert "nothing new has arrived" in again
    lines = (shack.data / "lake/bronze/_manifest.jsonl").read_text().splitlines()
    files = [json.loads(l)["file"] for l in lines]
    assert len(files) == len(set(files))


def test_uncommitted_batch_is_invisible_and_swept(shack):
    shack.run("run", "--through", "2026-08-05")
    before = shack.sql("select count(*) from silver.silver_payments")[0][0]
    orphan_dir = next((shack.data / "lake/bronze/payments").glob("ingest_date=*"))
    orphan = orphan_dir / "deadbeefdeadbeef.parquet"
    orphan.write_bytes(next(orphan_dir.glob("*.parquet")).read_bytes())    # a crash left this behind
    shack.run("boil", "--through", "2026-08-05", "--replay")
    assert shack.sql("select count(*) from silver.silver_payments")[0][0] == before
    assert "swept 1" in shack.run("tap", "--through", "2026-08-05").stdout
    assert not orphan.exists()


def test_schema_drift_blocks_publish_until_replayed(shack):
    shack.run("run", "--through", "2026-08-16", parsers="2025-11-01")
    blocked = shack.run("run", "--through", "2026-08-17T12:00", parsers="2025-11-01", ok=False).stdout
    assert "BLOCK  quarantine rate" in blocked and "unsupported_api_version" in blocked
    assert shack.sql("select max(as_of) from gold._published")[0][0].day == 16   # gold did not move
    fixed = shack.run("run", "--through", "2026-08-17T12:00", "--replay").stdout
    assert "Published" in fixed
    assert shack.sql("select count(*) from silver.quarantine where source = 'payments' "
                     "and quarantine_reason = 'unsupported_api_version'")[0][0] == 0


def test_daily_builds_match_a_single_replay(shack, make_shack):
    for day in ("2026-08-15", "2026-08-16", "2026-08-17", "2026-08-18T09:00", "2026-08-18", "2026-08-22"):
        shack.run("run", "--through", day)
    other = make_shack()
    other.run("run", "--through", "2026-08-22")
    for name, query in GOLD_QUERIES.items():
        daily, once = shack.sql(query), other.sql(query)
        assert sorted(map(repr, daily)) == sorted(map(repr, once)), name


def test_orders_fold_by_lsn_not_arrival(shack):
    shack.run("run", "--through", "2026-09-08T12:00")
    wrong = shack.sql("""
        with latest as (
            select order_id, arg_max(status, lsn) as status, arg_max(op = 'd', lsn) as deleted
            from silver.stg_order_changes group by order_id
        )
        select count(*) from latest join silver.silver_orders o using (order_id)
        where latest.status <> o.status or latest.deleted <> o.is_deleted
    """)[0][0]
    assert wrong == 0


def test_compare_walks_to_gold(shack):
    shack.run("run", "--through", "2026-09-08T12:00")
    out = shack.run("compare", "--through", "2026-09-08T12:00").stdout
    assert "(matches)" in out
