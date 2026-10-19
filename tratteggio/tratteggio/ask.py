"""Find, match, fill: the whole studio in one function."""
from dataclasses import dataclass, field
from pathlib import Path

from . import archive, chunker, easel, provenance
from .catalogue import Catalogue, Hit
from .tratteggio import REFUSAL, gate

ARCHIVE = Path(__file__).parent.parent / "archive"
THRESHOLD = 3.0


@dataclass
class Answer:
    text: str
    refused: bool
    reason: str
    sources: list[Hit] = field(default_factory=list)


def studio(folder: Path = ARCHIVE) -> Catalogue:
    return Catalogue(chunker.by_heading(archive.load(folder)))


def answer(question: str, cat: Catalogue, model, chapel: str = "lanaioli",
           threshold: float = THRESHOLD) -> Answer:
    hits = cat.search(question, k=3, chapel=chapel, current=True, thesaurus=True)
    if not gate(hits, threshold):
        return Answer(REFUSAL, True, f"weak retrieval (best score {hits[0].score:.2f} < {threshold})" if hits else "no cards", hits)
    draft = model.chat(easel.build(question, hits))
    if "NOT_IN_SOURCES" in draft:
        return Answer(REFUSAL, True, "model found no answer in the sources", hits)
    report = provenance.check(draft, hits)
    if not report.ok:
        return Answer(REFUSAL, True, "provenance failed: " + "; ".join(report.problems), hits)
    return Answer(draft, False, "ok", hits)
