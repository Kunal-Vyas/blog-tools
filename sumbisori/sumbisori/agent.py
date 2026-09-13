"""The harness: a bounded loop around a local model."""
import os
from typing import Literal

import ollama
from pydantic import BaseModel, Field, ValidationError

from .tools import TOOL_SCHEMAS, RepoTools

MODEL = os.environ.get("SUMBI_MODEL", "qwen3-coder:30b")
NUM_CTX = int(os.environ.get("SUMBI_NUM_CTX", "32768"))
MAX_ROUNDS = 6          # the breath: tool rounds before we force the model to surface
CONTEXT_BUDGET = 0.75   # ...or sooner, if the conversation fills 75% of the window

SYSTEM = """You review code changes to a data engineering repository before they are pushed.

Look for problems that would hurt production:
- debugging leftovers: .limit(), .sample(), .show(), hardcoded dates, local file paths
- joins or filters that silently change row counts
- destructive SQL: DROP, TRUNCATE, DELETE or UPDATE without a WHERE clause
- errors that are swallowed, and writes that are not idempotent on re-run

Rules:
- Only report problems introduced by lines this diff adds or changes.
- Verify before you claim. If a finding depends on how a table, column or function is
  used elsewhere, check with search_repo or read_file first.
- Secrets are already handled and appear as [REDACTED ...]. Do not report them.
- Skip style and naming. If nothing is wrong, say so."""


class Finding(BaseModel):
    severity: Literal["block", "warn"] = Field(description="block = would break production or corrupt data")
    path: str
    line: int | None = None
    title: str = Field(description="One line, under 80 characters")
    evidence: str = Field(description="What you checked that confirms the problem")


class Review(BaseModel):
    findings: list[Finding]


def _approx_tokens(messages: list) -> int:
    # ~3 characters per token is a deliberately pessimistic estimate for code.
    return sum(len(str(m["content"] or "")) + len(str(m.get("tool_calls") or "")) for m in messages) // 3


def review(diff: str, tools: RepoTools, client: ollama.Client) -> Review:
    messages: list = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Review this diff:\n\n{diff}"},
    ]
    options = {"num_ctx": NUM_CTX, "temperature": 0.1}

    for _ in range(MAX_ROUNDS):
        response = client.chat(model=MODEL, messages=messages, tools=TOOL_SCHEMAS,
                               options=options, keep_alive="30m")
        messages.append(response.message)
        if not response.message.tool_calls:
            break                                   # the model has seen enough
        for call in response.message.tool_calls:
            result = tools.call(call.function.name, call.function.arguments)
            messages.append({"role": "tool", "tool_name": call.function.name, "content": result})
        if _approx_tokens(messages) > CONTEXT_BUDGET * NUM_CTX:
            break                                   # running out of breath: surface now

    return _surface(messages, client, options)


def _surface(messages: list, client: ollama.Client, options: dict) -> Review:
    """Turn the investigation into a validated, machine-readable report."""
    messages = messages + [{
        "role": "user",
        "content": "Stop investigating. Report only the problems you verified, as JSON.",
    }]
    for _ in range(2):
        response = client.chat(model=MODEL, messages=messages, format=Review.model_json_schema(),
                               options={**options, "temperature": 0}, keep_alive="30m")
        try:
            return Review.model_validate_json(response.message.content)
        except ValidationError as err:
            messages += [response.message,
                         {"role": "user", "content": f"That JSON was invalid:\n{err}\nReturn corrected JSON only."}]
    raise RuntimeError("the model could not produce a valid report")
