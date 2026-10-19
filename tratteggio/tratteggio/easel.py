"""Taping the sketch to the easel: build the prompt with numbered sources."""
from .catalogue import Hit

SYSTEM = """You are the studio archivist for the Lanaioli Chapel fresco.
Answer ONLY from the numbered sources below. Do not use outside knowledge.
After every sentence, cite the source it came from, like [S1].
If the sources do not answer the question, reply exactly: NOT_IN_SOURCES
Keep the answer under 80 words.
If sources disagree, prefer the most recent record and say so."""


def build(question: str, hits: list[Hit]) -> list[dict]:
    sources = "\n\n".join(
        f"[S{n}] {h.chunk.page.title} > {h.chunk.heading}\n{h.chunk.text}"
        for n, h in enumerate(hits, 1))
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Sources:\n{sources}\n\nQuestion: {question}"},
    ]
