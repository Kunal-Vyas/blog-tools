"""Checks a finished build, and only then points readers at it.

Readers find the live index through one small file, CURRENT. Publishing replaces that
file in a single step, so nobody ever reads half of one build and half of another.

Usage: python -m scriptorium.publish <lake> <build> <canaries.tsv>
    canaries.tsv: word <tab> passage that must contain it
"""
import json
import os
import sys
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.parquet as pq

from scriptorium import analyzer


def audit(lake: Path, build: str, canaries: Path) -> list[str]:
    out = lake / "builds" / build
    failed = []

    def report(ok: bool, name: str, detail: str) -> None:
        print(f"  {'PASS ' if ok else 'BLOCK'}  {name:<13} {detail}")
        if not ok:
            failed.append(name)

    # 1. The job finished. Spark writes _SUCCESS only after every task has committed.
    if not (out / "index" / "_SUCCESS").exists() or not (out / "stats" / "_SUCCESS").exists():
        report(False, "finished", "no _SUCCESS marker: the build did not finish")
        return failed

    # 2. Every passage the reading list's writer wrote was read. Reading a folder while
    #    its writer is still at work succeeds, and quietly misses whatever isn't there yet.
    expected = json.loads((lake / "reading-list" / "_manifest.json").read_text())["passages"]
    corpus = json.loads((out / "corpus.json").read_text())
    report(corpus["passages"] == expected, "passages",
           f"{expected:,} in the manifest, {corpus['passages']:,} in the index")

    # 3. Every passage was decoded. Bytes that weren't valid UTF-8 become U+FFFD,
    #    and the words around them become unfindable.
    report(corpus["garbled"] == 0, "encoding",
           f"{corpus['garbled']:,} passages with undecodable bytes")

    # 4. The shards and the stats agree: for every word, the shards' counts add up to
    #    the corpus-wide count.
    index = pq.read_table(out / "index", columns=["word", "df"])
    by_word = index.group_by("word").aggregate([("df", "sum")])
    stats = pq.read_table(out / "stats")
    joined = by_word.join(stats, "word", join_type="full outer")
    disagree = pc.sum(pc.fill_null(pc.not_equal(joined["df_sum"], joined["df"]), True)).as_py()
    report(disagree == 0, "conservation",
           f"{by_word.num_rows:,} words in the shards, {stats.num_rows:,} in the stats, {disagree} disagree")

    # 5. Canaries: words we know are in known passages must be findable there.
    wanted = [line.split("\t") for line in canaries.read_text(encoding="utf-8").splitlines() if line]
    words = {analyzer.tokens(w)[0] for w, _ in wanted}
    table = pq.read_table(out / "index", columns=["word", "postings"],
                          filters=[("word", "in", sorted(words))]).to_pylist()
    found = {(r["word"], p["passage_id"]) for r in table for p in r["postings"]}
    dead = [f"{analyzer.tokens(w)[0]} in {pid}" for w, pid in wanted
            if (analyzer.tokens(w)[0], pid) not in found]
    report(not dead, "canaries",
           f"{len(wanted)} of {len(wanted)} found" if not dead else "not found: " + "; ".join(dead))
    return failed


def publish(lake: Path, build: str) -> None:
    """Write the new pointer beside the old one, then swap them in one step.

    os.replace is atomic on a local disk. On object storage, write CURRENT as a single
    small object: a reader gets the old version or the new one, never a mix.
    """
    tmp = lake / "CURRENT.tmp"
    tmp.write_text(f"builds/{build}\n")
    os.replace(tmp, lake / "CURRENT")


def main(lake: str, build: str, canaries: str) -> None:
    print(f"=== {build}")
    if audit(Path(lake), build, Path(canaries)):
        print("Not published. CURRENT still points at the last good build.")
        sys.exit(1)
    publish(Path(lake), build)
    print(f"Published builds/{build}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
