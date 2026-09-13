"""Build a small git repository whose branches contain known problems.

    python evals/make_fixture.py /tmp/sumbisori-fixture
    python evals/run_evals.py   /tmp/sumbisori-fixture

Each branch matches one case in run_evals.py. Add your own by copying a block:
a branch, a change, and an entry in CASES with the file that must be flagged.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/sumbisori-fixture")

BASE = {
    "jobs/daily_revenue.py": '''from pyspark.sql import SparkSession, functions as F


def run(spark: SparkSession, run_date: str) -> None:
    orders = spark.read.table("sales.orders").where(F.col("order_date") == run_date)
    customers = spark.read.table("sales.customers")
    enriched = orders.join(customers, on="customer_id", how="left")
    (enriched.groupBy("order_date", "region")
        .agg(F.sum("amount").alias("revenue"))
        .write.mode("overwrite")
        .option("replaceWhere", f"order_date = '{run_date}'")
        .saveAsTable("reporting.daily_revenue"))
''',
    "jobs/customer_ltv.py": '''from pyspark.sql import SparkSession, functions as F


def run(spark: SparkSession) -> None:
    customers = (spark.read.table("sales.customers_scd")
                 .where(F.col("is_current")))          # SCD2: one row per customer version
    orders = spark.read.table("sales.orders")
    ltv = orders.join(customers, "customer_id").groupBy("customer_id").agg(F.sum("amount"))
    ltv.write.mode("overwrite").saveAsTable("reporting.customer_ltv")
''',
    "sql/cleanup.sql": "DELETE FROM staging.orders WHERE loaded_at < CURRENT_DATE - 7;\n",
}

CASES = {
    # branch: {path: new content}
    "case/scd2-join": {"jobs/daily_revenue.py": BASE["jobs/daily_revenue.py"].replace(
        'spark.read.table("sales.customers")',
        'spark.read.table("sales.customers_scd")   # has the new region column')},
    "case/limit-left-in": {"jobs/daily_revenue.py": BASE["jobs/daily_revenue.py"].replace(
        '.where(F.col("order_date") == run_date)',
        '.where(F.col("order_date") == run_date).limit(1000)')},
    "case/delete-without-where": {"sql/cleanup.sql": "DELETE FROM staging.orders;\n"},
    "case/clean-refactor": {"jobs/customer_ltv.py": BASE["jobs/customer_ltv.py"].replace(
        'ltv = orders.join(customers, "customer_id").groupBy("customer_id").agg(F.sum("amount"))',
        'joined = orders.join(customers, "customer_id")\n'
        '    ltv = joined.groupBy("customer_id").agg(F.sum("amount"))')},
}


def git(*args: str) -> None:
    subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True)


def write(files: dict) -> None:
    for path, content in files.items():
        target = ROOT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)


if ROOT.exists():
    sys.exit(f"{ROOT} already exists. Delete it or pass another path.")

ROOT.mkdir(parents=True)
subprocess.run(["git", "init", "-q", "-b", "main", str(ROOT)], check=True)
git("config", "user.email", "fixture@example.com")
git("config", "user.name", "Fixture")
write(BASE)
git("add", "-A")
git("commit", "-qm", "baseline")

for branch, files in CASES.items():
    git("checkout", "-q", "main")
    git("checkout", "-qb", branch)
    write(files)
    git("commit", "-qam", branch.split("/")[-1])

git("checkout", "-q", "main")
print(f"Fixture repository ready at {ROOT}")
print("Branches:", ", ".join(CASES))
print(f"\nNow run:  python evals/run_evals.py {ROOT}")
