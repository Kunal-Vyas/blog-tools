"""Deterministic checks that run before any model sees the diff."""
import re
from dataclasses import dataclass

# Patterns with near-zero false positives. For production, reach for
# gitleaks or detect-secrets; this is the 40-line version of the idea.
PATTERNS = {
    "AWS access key ID": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    "Private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "Hardcoded credential": re.compile(
        r"""(?i)\b\w*(?:password|passwd|secret|token|api_?key)\w*\s*[:=]\s*['"]([^'"\s]{8,})['"]"""
    ),
}
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def redact(text: str) -> str:
    for kind, pattern in PATTERNS.items():
        text = pattern.sub(f"[REDACTED {kind}]", text)
    return text


@dataclass
class SecretHit:
    path: str
    line: int
    kind: str


def scan_diff(diff: str) -> tuple[list[SecretHit], str]:
    """Find secrets on added lines. Return the hits and a redacted copy of the diff."""
    hits, out = [], []
    path, line_no = "?", 0
    for raw in diff.splitlines():
        line = raw
        if raw.startswith("+++ "):
            path = raw[6:] if raw.startswith("+++ b/") else raw[4:]
        elif m := HUNK.match(raw):
            line_no = int(m.group(1))
        elif raw.startswith("+"):
            hits += [SecretHit(path, line_no, kind) for kind, p in PATTERNS.items() if p.search(raw)]
            line = redact(raw)
            line_no += 1
        elif raw.startswith(" "):
            line_no += 1
        out.append(line)
    return hits, "\n".join(out)
