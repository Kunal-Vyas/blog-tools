"""The card catalogue: BM25 keyword search, optional vector search, fused by rank."""
import math
import re
from collections import Counter
from dataclasses import dataclass

from .chunker import Chunk
from .thesaurus import expand

STOP = set("""a an and are as at be by can do does for from has have how i if in is it
its my of on or our so that the their this to was we what when where which will with
you your me after before get any did should there his he were""".split())


def tokens(text: str) -> list[str]:
    out = []
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        if word in STOP:
            continue
        for suffix in ("ing", "ed", "es", "s"):
            if len(word) > 4 and word.endswith(suffix):
                word = word[: -len(suffix)]
                break
        out.append(word)
    return out


@dataclass
class Hit:
    chunk: Chunk
    score: float      # BM25 score of this chunk (the gate reads this)
    rank: int


class Catalogue:
    def __init__(self, chunks: list[Chunk], k1: float = 1.2, b: float = 0.75, embedder=None):
        self.chunks = chunks
        self.k1, self.b = k1, b
        self.docs = [Counter(tokens(c.card)) for c in chunks]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.lengths) / len(self.lengths)
        df = Counter(t for d in self.docs for t in d)
        n = len(chunks)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.embedder = embedder
        self.vectors = embedder.embed([c.card for c in chunks]) if embedder else None

    def bm25(self, query: str) -> list[float]:
        q = tokens(query)
        scores = []
        for doc, length in zip(self.docs, self.lengths):
            s = 0.0
            for t in q:
                tf = doc.get(t, 0)
                if tf:
                    s += self.idf[t] * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * length / self.avg))
            scores.append(s)
        return scores

    def search(self, query: str, k: int = 3, chapel: str | None = None,
               current: bool = False, thesaurus: bool = False) -> list[Hit]:
        if thesaurus:
            query = expand(query)
        keep = [i for i, c in enumerate(self.chunks)
                if (chapel is None or c.page.chapel in (chapel, "studio"))
                and (not current or c.page.current)]
        kw = self.bm25(query)
        order = sorted(keep, key=lambda i: -kw[i])
        if self.vectors is not None:
            order = self._fuse(query, keep, order)
        return [Hit(self.chunks[i], kw[i], r + 1) for r, i in enumerate(order[:k])]

    def _fuse(self, query: str, keep: list[int], kw_order: list[int], c: int = 60) -> list[int]:
        """Reciprocal rank fusion of keyword and vector rankings."""
        qv = self.embedder.embed([query])[0]
        cos = {i: sum(a * b for a, b in zip(qv, self.vectors[i])) for i in keep}
        vec_order = sorted(keep, key=lambda i: -cos[i])
        rrf = Counter()
        for ranking in (kw_order, vec_order):
            for r, i in enumerate(ranking):
                rrf[i] += 1 / (c + r + 1)
        return [i for i, _ in rrf.most_common()]
