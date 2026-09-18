"""Bronze: land every line exactly as it arrived, once, with enough metadata to replay it.

Three rules, and the code below is mostly about keeping them under failure:

1. Never parse. Each line is stored as a string. A payload the parser can't read today is
   still here tomorrow, when the parser can.
2. Never ingest the same file twice. Files are identified by content hash, not name, so a
   re-sent file is a no-op.
3. A batch exists only once the manifest says so. Parquet is written first, the manifest
   line last. Readers (see models/bronze) trust the manifest, not the folder listing.

In production, Delta Lake or Iceberg gives you rule 3 for free: the transaction log is the
manifest. This is the small version of the idea, so you can see what the log is doing.
"""
import csv
import hashlib
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from .config import BRONZE, LANDING, MANIFEST, SOURCES

UTC = timezone.utc


def arrived_at(path: Path) -> datetime:
    """Landing files carry their arrival time in the name: <source>-YYYYMMDDTHH00[-resend].ext"""
    stamp = path.stem.split("-")[1]
    return datetime.strptime(stamp, "%Y%m%dT%H00").replace(tzinfo=UTC)


def read_manifest() -> list[dict]:
    if not MANIFEST.exists():
        return []
    return [json.loads(line) for line in MANIFEST.read_text().splitlines() if line.strip()]


def lines_of(path: Path) -> list[str]:
    """JSON lines stay as they are. CSV rows become JSON objects, so every bronze table has one shape."""
    text = path.read_text()
    if path.suffix == ".csv":
        return [json.dumps(row, separators=(",", ":")) for row in csv.DictReader(io.StringIO(text))]
    return [line for line in text.splitlines() if line.strip()]


def sweep_orphans(committed: set[str]) -> int:
    """Delete batch files a crashed run wrote but never committed."""
    removed = 0
    for f in BRONZE.glob("*/ingest_date=*/*"):
        if f.name.endswith(".tmp") or f.stem not in committed:
            f.unlink()
            removed += 1
    return removed


def tap(through: datetime) -> dict:
    BRONZE.mkdir(parents=True, exist_ok=True)
    manifest = read_manifest()
    seen = {m["sha256"] for m in manifest}
    tapped = {m["file"] for m in manifest}
    committed = {m["batch_id"] for m in manifest if m["batch_id"]}
    next_seq = max((m["batch_seq"] for m in manifest if m["batch_seq"]), default=0) + 1
    report = {"orphans_removed": sweep_orphans(committed), "batches": []}
    ingested_at = datetime.now(UTC)
    duplicates = []

    for source in SOURCES:
        new, rows = [], []
        for path in sorted((LANDING / source).glob("*/*.*")):
            name = str(path.relative_to(LANDING))
            when = arrived_at(path)
            if when > through or name in tapped:
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest in seen:                      # same bytes as a file we already have
                duplicates.append({"source": source, "batch_id": None, "batch_seq": None,
                                   "parquet": None, "ingested_at": ingested_at.isoformat(),
                                   "file": name, "sha256": digest})
                continue
            seen.add(digest)
            new.append({"file": name, "sha256": digest})
            for n, line in enumerate(lines_of(path), start=1):
                rows.append({"_raw": line, "_landing_file": name,
                             "_line": n, "_file_sha256": digest, "_arrived_at": when.isoformat()})
        if not new:
            continue

        # Batch id from content: the same set of files always gets the same name.
        hashes = "".join(sorted(n["sha256"] for n in new))
        batch_id = hashlib.sha256(hashes.encode()).hexdigest()[:16]
        folder = BRONZE / source / f"ingest_date={ingested_at:%Y-%m-%d}"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{batch_id}.parquet"
        _write_parquet(rows, target, batch_id, next_seq, ingested_at)

        # Commit: one manifest line per landing file, appended and flushed to disk.
        with MANIFEST.open("a") as log:
            for n in new:
                log.write(json.dumps({"source": source, "batch_id": batch_id,
                                      "batch_seq": next_seq,
                                      "parquet": str(target.relative_to(BRONZE.parent)),
                                      "ingested_at": ingested_at.isoformat(), **n}) + "\n")
            log.flush()
            os.fsync(log.fileno())
        report["batches"].append({"source": source, "batch_seq": next_seq,
                                  "files": len(new), "rows": len(rows)})
        next_seq += 1

    if duplicates:                      # remember them, so they are not re-hashed every run
        with MANIFEST.open("a") as log:
            log.writelines(json.dumps(d) + "\n" for d in duplicates)
    report["skipped_duplicates"] = len(duplicates)
    return report


def _write_parquet(rows, target: Path, batch_id: str, batch_seq: int, ingested_at: datetime):
    staged = target.with_suffix(".jsonl.tmp")
    tmp = target.with_suffix(".parquet.tmp")
    staged.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows))
    con = duckdb.connect()
    con.execute(f"""
        COPY (SELECT _raw, _landing_file, _line, _file_sha256, _arrived_at,
                     '{batch_id}' AS _batch_id, {batch_seq} AS _batch_seq,
                     TIMESTAMPTZ '{ingested_at.isoformat()}' AS _ingested_at
              FROM read_json('{staged}', format = 'newline_delimited', columns = {{
                     _raw: 'VARCHAR', _landing_file: 'VARCHAR', _line: 'INTEGER',
                     _file_sha256: 'VARCHAR', _arrived_at: 'TIMESTAMPTZ'}})
              ORDER BY _arrived_at, _landing_file, _line)
        TO '{tmp}' (FORMAT parquet, COMPRESSION zstd)""")
    con.close()
    staged.unlink()
    os.replace(tmp, target)       # atomic on the same filesystem: readers never see half a file
