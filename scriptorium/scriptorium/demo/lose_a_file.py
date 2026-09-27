"""Reproduces Thursday's missing passages on a laptop.

Copies a lake's reading list without the Parquet file that holds one passage. That is
what the index job saw when it listed the folder before the writer had finished: six
files instead of seven. The manifest still records what the writer meant to write.

Usage: python -m scriptorium.demo.lose_a_file <lake> <new-lake> <passage-id>
"""
import shutil
import sys
from pathlib import Path

import pyarrow.parquet as pq


def main(lake: str, new_lake: str, passage_id: str) -> None:
    src, dst = Path(lake) / "reading-list", Path(new_lake) / "reading-list"
    shutil.copytree(src, dst, dirs_exist_ok=True)
    for f in sorted((dst / "passages").glob("*.parquet")):
        ids = pq.read_table(f, columns=["passage_id"]).column(0).to_pylist()
        if passage_id in ids:
            f.unlink()
            print(f"removed {f.name}: {len(ids):,} passages")
            return
    raise SystemExit(f"{passage_id} not found")


if __name__ == "__main__":
    main(*sys.argv[1:4])
