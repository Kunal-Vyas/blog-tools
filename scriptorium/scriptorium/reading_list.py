"""Prepares the reading list: a folder of Gutenberg .txt files becomes a table of passages.

    reading-list/passages/   Parquet: passage_id, book, n, text      (the input to every build)
    reading-list/books/      Parquet: book, title, encoding
    reading-list/_manifest.json  how many passages were written, written last

Usage: python -m scriptorium.reading_list <books-dir> <lake> [--assume-utf8]

--assume-utf8 reproduces the old pipeline's bug: spark.read.text decodes every file as
UTF-8, and bytes that aren't valid UTF-8 silently become U+FFFD.
"""
import json
import sys
from pathlib import Path

from pyspark.sql import functions as F
from pyspark.sql import types as T

from scriptorium import passages
from scriptorium.spark import session

FILES = 7   # the reading list is written as this many Parquet files

BOOK = T.StructType([
    T.StructField("title", T.StringType()),
    T.StructField("encoding", T.StringType()),
    T.StructField("passages", T.ArrayType(T.StringType())),
])


def decode(content: bytes) -> tuple[str, str]:
    """Strict UTF-8 first; ISO-8859-1 only for files UTF-8 rejects.

    Every byte sequence is valid ISO-8859-1, so it never fails. That's exactly why it
    has to be the fallback: tried first, it would garble real UTF-8 without a word.
    """
    try:
        return content.decode("utf-8", errors="strict"), "utf-8"
    except UnicodeDecodeError:
        return content.decode("iso-8859-1"), "iso-8859-1"


@F.udf(BOOK)
def read_book(content, book):
    text, encoding = decode(bytes(content))
    return passages.title(text, book), encoding, passages.split(text)


@F.udf(BOOK)
def read_text_as_given(text, book):
    return passages.title(text, book), "assumed utf-8", passages.split(text)


def main(src: str, lake: str, assume_utf8: bool = False) -> None:
    spark = session("scriptorium-reading-list")
    out = Path(lake) / "reading-list"

    if assume_utf8:
        raw = (spark.read.option("pathGlobFilter", "*.txt").text(src, wholetext=True)
               .select(F.col("value").alias("text"), F.col("_metadata.file_path").alias("path")))
        book = F.regexp_extract("path", r"([^/]+)\.txt$", 1)
        books = raw.select(book.alias("book"), read_text_as_given("text", book).alias("b"))
    else:
        raw = spark.read.format("binaryFile").option("pathGlobFilter", "*.txt").load(src)
        book = F.regexp_extract("path", r"([^/]+)\.txt$", 1)
        books = raw.select(book.alias("book"), read_book("content", book).alias("b"))
    books = books.cache()

    rows = (books.select("book", F.posexplode("b.passages").alias("i", "text"))
            .select(F.concat_ws(":", "book", (F.col("i") + 1).cast("string")).alias("passage_id"),
                    "book", (F.col("i") + 1).alias("n"), "text"))
    (rows.repartitionByRange(FILES, "book", "n")           # seven files, in reading order
         .write.mode("overwrite").parquet(str(out / "passages")))
    books.select("book", "b.title", "b.encoding").write.mode("overwrite").parquet(str(out / "books"))

    # The manifest is written last, and counts what was written: the build checks against it.
    written = spark.read.parquet(str(out / "passages")).count()
    (out / "_manifest.json").write_text(json.dumps({"passages": written}) + "\n")

    enc = {r["encoding"]: r["count"] for r in books.groupBy("b.encoding").count().collect()}
    print(f"{books.count()} books {dict(sorted(enc.items()))}, {written:,} passages")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], "--assume-utf8" in sys.argv[3:])
