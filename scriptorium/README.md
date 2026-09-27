# scriptorium

A small search engine over Project Gutenberg, built with Apache Spark the way the
Oxford English Dictionary was built: readers write slips, slips are sorted into
pigeonholes, editors turn each pile into an entry, and nothing is published until it
has been checked.

Companion code for *The Dictionary Guide to Spark: Read, Sort, Define*.

## What's here

| Module | Job |
| --- | --- |
| `scriptorium.reading_list` | Spark: books as bytes → passages (Parquet, 7 files) and a manifest, written last |
| `scriptorium.analyzer` | The one rule for what counts as the same word, shared by the build and search |
| `scriptorium.build` | Spark: passages → index shards, corpus-wide stats, corpus totals |
| `scriptorium.publish` | Audits a build, then points `CURRENT` at it in one step |
| `scriptorium.search` | Scatter-gather BM25 search across the shards of the published build |
| `scriptorium.demo.lose_a_file` | Reproduces reading a folder before its writer has finished |

## Status

Tested end to end in Spark local mode (PySpark 4.2.0, JDK 21, Python 3.12) on the
18-book Project Gutenberg sample that ships with NLTK. Every number in the blog post
comes from that run. Not yet run on a cluster; the scripts use nothing local-only, so
`spark-submit` with object-storage paths should need no code changes.

## Run it locally

Needs Python 3.10+ and Java 17+.

```bash
pip install -e .

# The 18-book Gutenberg sample from NLTK
curl -LO https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/gutenberg.zip
unzip gutenberg.zip

# Reading list, build, audit and publish, search
python -m scriptorium.reading_list gutenberg lake
python -m scriptorium.build lake 2026-09-24
python -m scriptorium.publish lake 2026-09-24 canaries.tsv
python -m scriptorium.search lake white whale
python -m scriptorium.search lake --local-idf white whale

# The OED's way of dividing the work, to compare shard sizes
python -m scriptorium.build lake by-letter --by-letter
```

## Reproduce Thursday's broken builds

```bash
# A reading list read before its writer had finished
python -m scriptorium.demo.lose_a_file lake lost-lake bible-kjv:2636
python -m scriptorium.build lost-lake 2026-09-25-lost
python -m scriptorium.publish lost-lake 2026-09-25-lost canaries.tsv     # blocks

# Every book read with spark.read.text, which assumes UTF-8
python -m scriptorium.reading_list gutenberg raw-lake --assume-utf8
python -m scriptorium.build raw-lake 2026-09-25-raw
python -m scriptorium.publish raw-lake 2026-09-25-raw canaries.tsv       # blocks
```
