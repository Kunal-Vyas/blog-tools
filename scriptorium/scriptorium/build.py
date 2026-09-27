"""Builds the index: every word, and every passage it appears in.

One Spark job, three outputs, all under builds/<build>/:

    index/shard=0..3/   word, df, postings [(passage_id, tf), ...]   one folder per shard
    stats/              word, df                                     for the whole corpus
    corpus.json         passages, tokens, garbled

Usage: python -m scriptorium.build <lake> <build> [--shards 4] [--by-letter]
"""
import argparse
import json
from pathlib import Path

from pyspark.sql import functions as F
from pyspark.sql import types as T

from scriptorium import analyzer
from scriptorium.spark import session

tokens = F.udf(lambda text: analyzer.tokens(text), T.ArrayType(T.StringType()))


def by_passage(shards: int):
    """OpenSearch's way: a passage and all its words live on one shard."""
    return F.pmod(F.hash("passage_id"), F.lit(shards))


def by_letter(shards: int):
    """The OED's way: words are split among editors by their first letter."""
    first = F.ascii(F.col("word")) - F.ascii(F.lit("a"))           # a=0 ... z=25
    return (F.when((first >= 0) & (first < 26), F.floor(first * shards / 26))
             .otherwise(0).cast("int"))                           # a-g, h-m, n-t, u-z for 4


def main(lake: str, build: str, shards: int = 4, letter: bool = False) -> None:
    spark = session("scriptorium-build")
    root = Path(lake)
    reading_list = root / "reading-list"
    if not (reading_list / "_manifest.json").exists():
        raise SystemExit("The reading list has no manifest: its writer hasn't finished.")
    out = root / "builds" / build

    passages = spark.read.parquet(str(reading_list / "passages"))

    # The readers: one slip per word per passage, carrying its count. Spark counts
    # inside each task before the shuffle, so "the" nine times becomes one row, not nine.
    slips = (passages
             .select("passage_id", F.explode(tokens("text")).alias("word"))
             .groupBy("passage_id", "word").agg(F.count("*").alias("tf"))
             .cache())

    # The pigeonholes and the editors: pick a shard for every slip, then gather each
    # word's slips on each shard into one sorted postings list.
    shard = by_letter(shards) if letter else by_passage(shards)
    index = (slips.withColumn("shard", shard)
             .groupBy("shard", "word")
             .agg(F.sort_array(F.collect_list(F.struct("passage_id", "tf"))).alias("postings"))
             .withColumn("df", F.size("postings")))
    index.write.mode("overwrite").partitionBy("shard").parquet(str(out / "index"))

    # One scale for everyone: how many passages in the whole corpus contain each word.
    stats = slips.groupBy("word").agg(F.count("*").alias("df"))
    stats.write.mode("overwrite").parquet(str(out / "stats"))

    corpus = passages.agg(
        F.count("*").alias("passages"),
        F.sum(F.instr("text", "\ufffd").cast("boolean").cast("int")).alias("garbled"),
    ).first().asDict()
    corpus["tokens"] = slips.agg(F.sum("tf")).first()[0]
    (out / "corpus.json").write_text(json.dumps(corpus) + "\n")
    print(f"built {build}: {corpus['passages']:,} passages, {corpus['tokens']:,} words")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("lake")
    p.add_argument("build")
    p.add_argument("--shards", type=int, default=4)
    p.add_argument("--by-letter", action="store_true")
    a = p.parse_args()
    main(a.lake, a.build, a.shards, a.by_letter)
