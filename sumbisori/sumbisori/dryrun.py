"""Try the reviewer on a branch without pushing anything.

    python -m sumbisori.dryrun                 # origin/main..HEAD
    python -m sumbisori.dryrun my-branch       # origin/main..my-branch
    python -m sumbisori.dryrun main..my-branch # any range you like

Prints exactly what the pre-push hook would print, and exits 1 if it would
have stopped the push. Nothing is written, and nothing is pushed.
"""
import subprocess
import sys

import ollama

from .agent import MODEL, NUM_CTX
from .hook import BASE_BRANCH, TIMEOUT_SECONDS, check, git


def resolve(argument: str) -> tuple[str, str]:
    """Turn 'main..feature', 'feature' or '' into a (base, head) pair."""
    if ".." in argument:
        base, _, head = argument.partition("..")
        return base.strip("."), head
    head = argument or "HEAD"
    return git("merge-base", BASE_BRANCH, head), head


def main() -> int:
    try:
        root = git("rev-parse", "--show-toplevel")
        base, head = resolve(sys.argv[1] if len(sys.argv) > 1 else "")
        subject = git("log", "-1", "--format=%h %s", head)
    except subprocess.CalledProcessError as err:
        print(f"sumbisori: git failed: {err.stderr or err}".strip(), file=sys.stderr)
        print(f"Is {BASE_BRANCH} fetched? Set another base with SUMBI_BASE.", file=sys.stderr)
        return 2

    print(f"reviewing {base[:8]}..{head}  ({subject})")
    print(f"model {MODEL}, context {NUM_CTX}\n")
    blocked = check(root, base, head, ollama.Client(timeout=TIMEOUT_SECONDS))
    print("\nThis push would be stopped." if blocked else "\nThis push would go through.")
    return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
