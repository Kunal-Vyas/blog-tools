"""The only things the model is allowed to do: read the commit being pushed."""
import subprocess

from .scan import redact

MAX_LINES = 200       # per read_file call
MAX_MATCHES = 40      # per search_repo call
MAX_CHARS = 8_000     # hard cap on anything we put back into the context

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read lines from a file as it exists in the commit being pushed. "
                           "Use it to see code around a change.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Repo-relative path, e.g. 'jobs/daily_revenue.py'"},
                    "start_line": {"type": "integer", "description": "First line, 1-based. Default 1."},
                    "end_line": {"type": "integer", "description": f"Last line, inclusive. At most {MAX_LINES} lines per call."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_repo",
            "description": "Find every line in the repository containing an exact string. "
                           "Use it to check how a table, column or function is used elsewhere.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Exact text to search for, e.g. 'customers_scd'"},
                },
                "required": ["text"],
            },
        },
    },
]


def _git(root: str, *args: str) -> subprocess.CompletedProcess:
    # argv list, never shell=True: nothing the model says is ever interpreted by a shell.
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, timeout=10)


def _cap(text: str) -> str:
    text = redact(text)     # tool output is context too: don't hand back the key we just redacted
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + "\n[...truncated]"


class RepoTools:
    """Reads from git's object database at a fixed commit, not from the filesystem.
    There is no path to escape to, and uncommitted edits can't leak into the review."""

    def __init__(self, root: str, commit: str):
        self.root, self.commit = root, commit

    def read_file(self, path: str, start_line: int = 1, end_line: int | None = None) -> str:
        path = path.strip().lstrip("/")
        if path.startswith("-") or ".." in path.split("/"):
            return f"Error: '{path}' is not a valid repo-relative path."
        proc = _git(self.root, "show", f"{self.commit}:{path}")
        if proc.returncode != 0:
            return f"Error: '{path}' does not exist in the commit being pushed."
        lines = proc.stdout.splitlines()
        start = max(1, int(start_line))
        end = min(len(lines), int(end_line) if end_line else start + MAX_LINES - 1, start + MAX_LINES - 1)
        numbered = [f"{n:>5}  {lines[n - 1]}" for n in range(start, end + 1)]
        return _cap(f"{path} (lines {start}-{end} of {len(lines)})\n" + "\n".join(numbered))

    def search_repo(self, text: str) -> str:
        if not text.strip():
            return "Error: search text is empty."
        proc = _git(self.root, "grep", "-n", "-I", "-F", "-e", text, self.commit, "--")
        if proc.returncode == 1:
            return f"No matches for '{text}'."
        if proc.returncode != 0:
            return f"Error: search failed: {proc.stderr.strip()[:200]}"
        prefix = f"{self.commit}:"
        matches = [m.removeprefix(prefix) for m in proc.stdout.splitlines()]
        shown = matches[:MAX_MATCHES]
        more = f"\n[{len(matches) - len(shown)} more matches not shown]" if len(matches) > len(shown) else ""
        return _cap("\n".join(shown) + more)

    def call(self, name: str, arguments: dict) -> str:
        """Dispatch a tool call. Mistakes come back as text so the model can correct itself."""
        handler = {"read_file": self.read_file, "search_repo": self.search_repo}.get(name)
        if handler is None:
            return f"Error: unknown tool '{name}'. Available tools: read_file, search_repo."
        try:
            return handler(**arguments)
        except (TypeError, ValueError) as err:
            return f"Error: bad arguments for {name}: {err}"
        except subprocess.TimeoutExpired:
            return f"Error: {name} timed out."
