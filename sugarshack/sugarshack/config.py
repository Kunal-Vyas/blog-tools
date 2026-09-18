"""Where things live, and the few decisions you make once."""
import os
from pathlib import Path

DATA = Path(os.environ.get("SUGAR_DATA", "data")).resolve()
LANDING = DATA / "landing"                 # what the sources drop: never modified by the pipeline
BRONZE = DATA / "lake" / "bronze"          # append-only Parquet, one folder per source
MANIFEST = BRONZE / "_manifest.jsonl"      # the commit log: a batch exists only once it is listed here
WAREHOUSE = DATA / "lake" / "warehouse.duckdb"   # silver, gold_build and gold schemas
SHACK = Path(__file__).parent / "shack"    # the dbt project

SOURCES = ("orders", "payments", "fx_rates", "settlements")

# Payment API versions the silver parser understands. Anything else is quarantined, not guessed at.
PARSERS = os.environ.get("SUGAR_PARSERS", "2025-11-01,2026-08-01")

# Grading thresholds (see grade.py)
QUARANTINE_WARN = 0.005        # 0.5% of a day's arrivals quarantined: publish, but say so
QUARANTINE_BLOCK = 0.02        # 2%: something upstream changed, do not publish
QUARANTINE_MIN_ROWS = 10       # ...but one bad line in a quiet hour is not a trend
SETTLING_HOURS = 48            # reconciliation gaps younger than this are warnings, not blocks

BUSINESS_TZ = "America/Halifax"
