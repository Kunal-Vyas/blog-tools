"""The review board: score retrieval before anyone looks at a generated answer."""
from pathlib import Path

from . import archive, chunker
from .catalogue import Catalogue
from .questions import ANSWERABLE, UNANSWERABLE

CHAPEL = "lanaioli"


def is_trap(hit):
    """A card from the wrong chapel, or a record a newer one replaced."""
    return hit.chunk.page.chapel not in (CHAPEL, "studio") or not hit.chunk.page.current


def evaluate(cat: Catalogue, k: int = 3, filters: bool = False, thesaurus: bool = False) -> dict:
    kw = dict(chapel=CHAPEL, current=True) if filters else {}
    found, rr, traps, misses = 0, 0.0, 0, []
    for q, evidence in ANSWERABLE:
        hits = cat.search(q, k=k, thesaurus=thesaurus, **kw)
        rank = next((h.rank for h in hits if evidence in h.chunk.text), None)
        found += rank is not None
        rr += 1 / rank if rank else 0
        traps += any(is_trap(h) for h in hits)
        if rank is None:
            misses.append(q)
    n = len(ANSWERABLE)
    return {"recall": found / n, "mrr": rr / n, "trap_rate": traps / n, "misses": misses}


def gate_table(cat: Catalogue, thresholds):
    kw = dict(chapel=CHAPEL, current=True, thesaurus=True)
    good = [cat.search(q, k=1, **kw)[0].score for q, _ in ANSWERABLE]
    bad = [cat.search(q, k=1, **kw)[0].score for q in UNANSWERABLE]
    return good, bad, [(t, sum(s >= t for s in good), sum(s < t for s in bad)) for t in thresholds]


def main():
    records = archive.load(Path(__file__).parent.parent / "archive")
    fixed = Catalogue(chunker.fixed_size(records, size=300))
    heads = Catalogue(chunker.by_heading(records))
    print(f"records={len(records)} fixed_chunks={len(fixed.chunks)} heading_chunks={len(heads.chunks)}")
    for name, cat, f, t in [("A fixed-size, no filters", fixed, False, False),
                            ("B by heading, no filters", heads, False, False),
                            ("C by heading + filters", heads, True, False),
                            ("D C + thesaurus", heads, True, True)]:
        r = evaluate(cat, filters=f, thesaurus=t)
        print(f"{name:28s} recall@3={r['recall']:.2f} mrr={r['mrr']:.2f} trap_rate={r['trap_rate']:.2f} misses={len(r['misses'])}")
        for m in r["misses"]:
            print("    miss:", m)
    good, bad, rows = gate_table(heads, [2, 3, 4, 5, 6, 7])
    print("unanswerable top scores:", [(q[:30], round(s, 2)) for q, s in zip(UNANSWERABLE, bad)])
    print(f"{len(ANSWERABLE)} answerable, {len(UNANSWERABLE)} unanswerable")
    for t, ok, refused in rows:
        print(f"  threshold {t}: answered {ok}/{len(good)}, refused {refused}/{len(bad)}")


if __name__ == "__main__":
    main()
