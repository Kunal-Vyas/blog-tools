"""Cutting records into catalogue cards."""
from dataclasses import dataclass

from .archive import Record as Page


@dataclass
class Chunk:
    id: str
    page: Page
    heading: str
    text: str

    @property
    def card(self) -> str:
        """What the index sees: page title and heading travel with the text."""
        return f"{self.page.title} > {self.heading}\n{self.text}"


def fixed_size(pages: list[Page], size: int = 300, overlap: int = 0) -> list[Chunk]:
    """The naive cut: every `size` characters, wherever that lands."""
    chunks = []
    for page in pages:
        body = page.body
        step = size - overlap
        for n, start in enumerate(range(0, len(body), step)):
            chunks.append(Chunk(f"{page.id}#c{n}", page, "", body[start:start + size]))
    return chunks


def by_heading(records: list[Page]) -> list[Chunk]:
    """One card per `##` section, so a description never splits mid-sentence."""
    chunks = []
    for rec in records:
        heading, lines = None, []
        for line in rec.body.splitlines() + ["## "]:
            if line.startswith("## "):
                if heading and lines:
                    slug = heading.lower().replace(" ", "-")
                    chunks.append(Chunk(f"{rec.id}#{slug}", rec, heading, " ".join(lines).strip()))
                heading, lines = line[3:].strip(), []
            elif line.strip() and not line.startswith("# "):
                lines.append(line.strip())
    return chunks
