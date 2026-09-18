"""Silver and gold: run the dbt project in shack/ against the warehouse."""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .config import DATA, MANIFEST, PARSERS, SHACK, WAREHOUSE


def dbt_executable() -> str:
    beside = Path(sys.executable).parent / ("dbt.exe" if os.name == "nt" else "dbt")
    found = str(beside) if beside.exists() else shutil.which("dbt")
    if not found:
        raise SystemExit("dbt is not installed in this environment. Run: pip install -e .")
    return found


def boil(as_of: datetime, replay: bool = False, verbose: bool = False) -> dict:
    if not MANIFEST.exists():
        raise SystemExit("Nothing in bronze yet. Run `sugarshack tap` first.")
    WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
    target = DATA / "dbt"
    env = {
        **os.environ,
        "SUGAR_LAKE": str(MANIFEST.parent.parent),
        "SUGAR_WAREHOUSE": str(WAREHOUSE),
        "SUGAR_AS_OF": as_of.isoformat(),
        "SUGAR_PARSERS": PARSERS,
        "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
    }
    cmd = [dbt_executable(), "build",
           "--project-dir", str(SHACK), "--profiles-dir", str(SHACK),
           "--target-path", str(target / "target"), "--log-path", str(target / "logs")]
    if replay:
        cmd.append("--full-refresh")          # rebuild silver and gold from every bronze row
    results_file = target / "target" / "run_results.json"
    results_file.unlink(missing_ok=True)
    proc = subprocess.run(cmd, env=env, capture_output=not verbose, text=True)

    if not results_file.exists():
        errors = [l for l in (proc.stdout or "").splitlines() if "Error" in l]
        raise SystemExit("dbt could not start: " + (errors[-1].strip() if errors else "run with --verbose to see why"))
    results = json.loads(results_file.read_text())["results"]
    summary = {"ok": proc.returncode == 0, "models": 0, "tests": 0, "warnings": [], "failures": []}
    for r in results:
        name = r["unique_id"].split(".")[2]
        kind = r["unique_id"].split(".")[0]
        summary["models" if kind == "model" else "tests"] += 1
        if r["status"] == "warn":
            summary["warnings"].append(f"{name}: {r.get('failures')} rows")
        elif r["status"] in ("error", "fail", "skipped"):
            summary["failures"].append(f"{r['status']:<7} {name}: {(r.get('message') or '').splitlines()[0][:120]}")
    if not summary["ok"] and not verbose and not summary["failures"]:
        sys.stderr.write(proc.stdout)
    return summary
