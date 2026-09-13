"""Replay branches with known problems through the reviewer and score it.

Each case runs several times: local calls are free, and models are not deterministic.
Usage: python evals/run_evals.py /path/to/fixture-repo
"""
import statistics
import subprocess
import sys
import time

import ollama

from sumbisori.agent import MODEL, review
from sumbisori.scan import scan_diff
from sumbisori.tools import RepoTools

REPO = sys.argv[1] if len(sys.argv) > 1 else "."
RUNS = 3
CASES = {                                   # branch -> file that must be flagged (None: must not block)
    "case/scd2-join": "jobs/daily_revenue.py",
    "case/delete-without-where": "sql/cleanup.sql",
    "case/limit-left-in": "jobs/daily_revenue.py",
    "case/clean-refactor": None,
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", REPO, *args], text=True).strip()


client = ollama.Client(timeout=600)
caught = missed = false_blocks = 0
latencies = []

for branch, expected in CASES.items():
    head = git("rev-parse", branch)
    _, diff = scan_diff(git("diff", f"main...{branch}"))
    for _ in range(RUNS):
        started = time.perf_counter()
        findings = review(diff, RepoTools(REPO, head), client).findings
        latencies.append(time.perf_counter() - started)
        if expected is None:
            false_blocks += any(f.severity == "block" for f in findings)
        elif any(f.path == expected for f in findings):
            caught += 1
        else:
            missed += 1
            print(f"missed  {branch}")

clean_runs = RUNS * sum(e is None for e in CASES.values())
print(f"model         {MODEL}")
print(f"caught        {caught}/{caught + missed}")
print(f"false blocks  {false_blocks}/{clean_runs}")
print(f"latency       p50 {statistics.median(latencies):.1f}s   "
      f"p95 {statistics.quantiles(latencies, n=20)[-1]:.1f}s")
