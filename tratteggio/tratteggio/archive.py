"""The basement: load archive records and their front matter."""
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Record:
    id: str
    title: str
    chapel: str          # which work the record belongs to ("studio" = applies to all)
    kind: str            # contract, drawing, photograph, condition, ...
    dated: int
    superseded_by: str | None
    body: str
    meta: dict = field(default_factory=dict)

    @property
    def current(self) -> bool:
        return self.superseded_by is None


def _parse(text: str) -> tuple[dict, str]:
    _, front, body = text.split("---", 2)
    meta = {}
    for line in front.strip().splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta, body.strip()


def load(folder: Path) -> list[Record]:
    out = []
    for path in sorted(Path(folder).glob("*.md")):
        m, body = _parse(path.read_text(encoding="utf-8"))
        out.append(Record(m["id"], m["title"], m["chapel"], m["kind"], int(m["dated"]),
                          m.get("superseded_by"), body, m))
    return out
