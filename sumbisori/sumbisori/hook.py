"""git pre-push hook: review what is about to leave your machine."""
import os
import subprocess
import sys

import httpx
import ollama

from .agent import MODEL, review
from .scan import scan_diff
from .tools import RepoTools

BASE_BRANCH = os.environ.get("SUMBI_BASE", "origin/main")
MAX_DIFF_CHARS = 40_000
TIMEOUT_SECONDS = 120


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


def is_zero(sha: str) -> bool:
    return set(sha) == {"0"}        # works for SHA-1 and SHA-256 repositories


def ranges(stdin_lines):
    """git feeds pre-push one line per ref: <local ref> <local sha> <remote ref> <remote sha>"""
    for line in stdin_lines:
        if not line.strip():
            continue
        _, local_sha, _, remote_sha = line.split()
        if is_zero(local_sha):
            continue                                        # deleting a remote branch
        known = not is_zero(remote_sha) and subprocess.run(
            ["git", "cat-file", "-e", remote_sha], capture_output=True).returncode == 0
        if known:
            yield remote_sha, local_sha
            continue
        try:                                                # new branch, or remote moved
            yield git("merge-base", BASE_BRANCH, local_sha), local_sha
        except subprocess.CalledProcessError:
            print(f"sumbisori: can't find a base for {local_sha[:8]}; skipping.", file=sys.stderr)


def check(root: str, base: str, head: str, client: ollama.Client) -> bool:
    """Review one range. Returns True if the push should be stopped."""
    diff = git("diff", "--no-color", "--unified=5", f"{base}..{head}")
    if not diff:
        return False

    hits, redacted = scan_diff(diff)
    for hit in hits:
        print(f"  BLOCK  {hit.path}:{hit.line}  {hit.kind}")
    blocked = bool(hits)                                    # deterministic checks fail closed

    if len(redacted) > MAX_DIFF_CHARS:
        print(f"  skip   diff is {len(redacted):,} chars, too large for a local review")
        return blocked
    try:
        report = review(redacted, RepoTools(root, head), client)
    except (ConnectionError, httpx.TimeoutException, ollama.ResponseError, RuntimeError) as err:
        print(f"  skip   model review unavailable ({MODEL}): {err}")       # the model fails open
        return blocked

    for f in report.findings:
        where = f"{f.path}:{f.line}" if f.line else f.path
        print(f"  {f.severity.upper():<5}  {where}  {f.title}\n         {f.evidence}")
    if not hits and not report.findings:
        print("  ok     nothing to flag")
    return blocked or any(f.severity == "block" for f in report.findings)


def main() -> int:
    root = git("rev-parse", "--show-toplevel")
    client = ollama.Client(timeout=TIMEOUT_SECONDS)          # the default timeout is None: forever
    blocked = False

    for base, head in ranges(sys.stdin):
        blocked |= check(root, base, head, client)

    if blocked:
        print("\nPush stopped. Fix the issues above, or push anyway with: git push --no-verify")
    return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
