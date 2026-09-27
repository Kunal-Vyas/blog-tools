"""Answers queries the way an OpenSearch cluster does: send the query to every shard,
let each score its own passages, and merge the best.

Usage: python -m scriptorium.search <lake> [--local-idf] <query words...>
"""
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pyarrow.parquet as pq

from scriptorium import analyzer

K1 = 1.2    # how quickly repeating a word stops adding to the score
B = 0.75    # how much a long passage is marked down for being long
TOP = 5


class Shard:
    def __init__(self, path: Path):
        self.postings = {}
        self.length = {}                        # passage length = the sum of its word counts
        for row in pq.read_table(path, columns=["word", "postings"]).to_pylist():
            self.postings[row["word"]] = [(p["passage_id"], p["tf"]) for p in row["postings"]]
            for pid, tf in self.postings[row["word"]]:
                self.length[pid] = self.length.get(pid, 0) + tf
        self.tokens = sum(self.length.values())

    def search(self, query: list[str], scale: dict | None) -> list[tuple[float, str]]:
        """Score this shard's passages. scale=None means: judge rarity from this shard alone."""
        n = scale["passages"] if scale else len(self.length)
        avgdl = scale["tokens"] / scale["passages"] if scale else self.tokens / max(1, n)
        scores = {}
        for word in query:
            postings = self.postings.get(word, [])
            if not postings:
                continue
            df = scale["df"][word] if scale else len(postings)
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))           # Lucene's BM25 idf
            for pid, tf in postings:
                dl = self.length[pid]
                s = idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * dl / avgdl))
                scores[pid] = scores.get(pid, 0.0) + s
        # Each shard sends back only its own best: that's all the merge needs.
        return sorted(((s, pid) for pid, s in scores.items()), reverse=True)[:TOP]


def main(argv: list[str]) -> None:
    lake = Path(argv[0])
    local = "--local-idf" in argv
    query = [t for w in argv[1:] if w != "--local-idf" for t in analyzer.tokens(w)]  # same rule as the index

    build = lake / (lake / "CURRENT").read_text().strip()
    shards = [Shard(p) for p in sorted((build / "index").glob("shard=*"))]
    scale = None
    if not local:
        corpus = json.loads((build / "corpus.json").read_text())
        stats = pq.read_table(build / "stats", filters=[("word", "in", query)]).to_pylist()
        scale = {**corpus, "df": {r["word"]: r["df"] for r in stats}}

    # Scatter: every shard searches at once. Gather: merge their top results.
    started = time.perf_counter()
    with ThreadPoolExecutor(len(shards)) as pool:
        answers = pool.map(lambda s: s.search(query, scale), shards)
    hits = sorted((h for a in answers for h in a), key=lambda h: (-h[0], h[1]))[:TOP]
    ms = (time.perf_counter() - started) * 1000

    ids = [pid for _, pid in hits]
    text = {r["passage_id"]: r["text"] for r in pq.read_table(
        lake / "reading-list" / "passages", filters=[("passage_id", "in", ids or [""])]).to_pylist()}
    titles = {r["book"]: r["title"] for r in pq.read_table(lake / "reading-list" / "books").to_pylist()}
    for i, (score, pid) in enumerate(hits, 1):
        t = text[pid]
        print(f"{i}. {score:5.2f}  {pid:<24} {titles[pid.split(':')[0]]}")
        print(f"   {t if len(t) <= 110 else t[:107] + '...'}")
    if not hits:
        print("No passages found.")
    print(f"({len(shards)} shards, {'per-shard' if local else 'global'} idf, {ms:.1f} ms)")


if __name__ == "__main__":
    main(sys.argv[1:])
