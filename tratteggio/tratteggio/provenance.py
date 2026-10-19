"""The restoration report: every sentence cited, every number found in its source."""
import re
from dataclasses import dataclass

from .catalogue import Hit

NUM = re.compile(r"\d+(?:\.\d+)?")


@dataclass
class Report:
    ok: bool
    problems: list[str]


def check(answer: str, hits: list[Hit]) -> Report:
    problems = []
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", answer.strip()) if s.strip()]
    for s in sentences:
        cited = [int(n) for n in re.findall(r"\[S(\d+)\]", s)]
        if not cited:
            problems.append(f"uncited: {s!r}")
            continue
        if any(n < 1 or n > len(hits) for n in cited):
            problems.append(f"cites a source that was not given: {s!r}")
            continue
        text = " ".join(hits[n - 1].chunk.text for n in cited)
        for num in NUM.findall(re.sub(r"\[S\d+\]", "", s)):
            if num not in text:
                problems.append(f"{num} is not in {['S%d' % n for n in cited]}: {s!r}")
    return Report(not problems, problems)
