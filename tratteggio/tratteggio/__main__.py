"""python -m tratteggio "question" [--dry-run] [--model llama3.2] [--chapel lanaioli]"""
import argparse

from . import easel
from .ask import THRESHOLD, answer, studio
from .brush import Ollama


def main():
    p = argparse.ArgumentParser(prog="tratteggio")
    p.add_argument("question")
    p.add_argument("--model", default="llama3.2")
    p.add_argument("--chapel", default="lanaioli")
    p.add_argument("--dry-run", action="store_true", help="show retrieval and prompt, call no model")
    a = p.parse_args()
    cat = studio()
    if a.dry_run:
        hits = cat.search(a.question, k=3, chapel=a.chapel, current=True, thesaurus=True)
        for h in hits:
            print(f"#{h.rank}  {h.score:5.2f}  {h.chunk.id}")
        print(f"gate: {'open' if hits and hits[0].score >= THRESHOLD else 'closed'} (threshold {THRESHOLD})\n")
        for m in easel.build(a.question, hits):
            print(f"--- {m['role']} ---\n{m['content']}\n")
        return
    result = answer(a.question, cat, Ollama(a.model), chapel=a.chapel)
    print(result.text)
    print(f"\n[{result.reason}]")
    for n, h in enumerate(result.sources, 1):
        print(f"  S{n}  {h.chunk.page.title} > {h.chunk.heading}")


if __name__ == "__main__":
    main()
