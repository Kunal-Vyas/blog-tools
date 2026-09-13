# sumbisori

A code reviewer that runs on your own machine, every time you `git push`.

It does three things to the commits you are about to push:

1. **Scans for secrets** with plain regex. A hit stops the push. This never calls a model.
2. **Reviews the diff** with an open-weight model running locally through Ollama. The model
   can read files and search the repository, so it can catch problems that are not visible
   in the diff itself.
3. **Reports** findings as `BLOCK` or `WARN`, and exits non-zero if anything blocks.

Nothing leaves your machine. That is the point: the code, and any credential that slipped
into it, stays on the laptop.

Companion code for the post
[The Haenyeo Guide to AI](https://kunalvyas.info/blog/haenyeo-guide-to-ai.html).

**What this is not.** It does not replace secret scanning in CI, or human review of the
pull request. It is the check that happens before either of those, while the mistake is
still cheap to fix.

---

## Before you start

| You need | Notes |
|---|---|
| Python 3.11 or newer | `python3 --version` |
| git | Any recent version |
| [Ollama](https://ollama.com/download) | The local model server |
| ~20 GB of free disk | For the model weights |
| 24 GB of GPU memory, or a Mac with 32 GB unified memory | Less is fine with a smaller model — see [Choosing a model](#choosing-a-model) |

Everything below assumes a terminal in the folder that contains this README.

---

## Step 1. Start Ollama and pull a model

```bash
ollama pull qwen3-coder:30b
```

That is about a 19 GB download, so start it before you make coffee.

Then make sure the server is running. The simplest way, and the one this README assumes:

```bash
OLLAMA_CONTEXT_LENGTH=32768 OLLAMA_KEEP_ALIVE=30m ollama serve
```

Leave that running in its own terminal window. If Ollama is already running as a
background app or service, either quit it first so the command above can take the port, or
set the same two variables the way your platform sets them for services (on macOS,
`launchctl setenv`; on Linux with systemd, `systemctl edit ollama`) and restart it. Check
Ollama's own documentation if you go that route.

Neither variable is strictly required — the reviewer asks for its own context length on
every call, and the defaults still work. They just make things faster.
`OLLAMA_CONTEXT_LENGTH` stops Ollama reloading the model because the requested context
differs from the loaded one, and `OLLAMA_KEEP_ALIVE` keeps the model warm so your second
push of the day doesn't pay for a cold load.

Check the server is up:

```bash
ollama ps
```

---

## Step 2. Install sumbisori

A virtual environment keeps this out of your system Python:

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .
```

Check it landed, and note the path — you will need it in step 4:

```bash
which sumbisori-pre-push         # Windows: where sumbisori-pre-push
```

---

## Step 3. Try it on a branch, without pushing anything

Do this first. It prints exactly what the hook would print, but it changes nothing and
pushes nothing.

```bash
cd /path/to/some/repo
python -m sumbisori.dryrun                  # origin/main..HEAD
python -m sumbisori.dryrun my-branch        # origin/main..my-branch
python -m sumbisori.dryrun main..my-branch  # any range you like
```

On a branch with problems, you get something like:

```
reviewing 370ab743..fix-region  (273f588 fix region mapping)
model qwen3-coder:30b, context 32768

  BLOCK  jobs/daily_revenue.py:3  AWS access key ID
  BLOCK  jobs/daily_revenue.py:11  Join to customers_scd without an is_current filter
         customer_ltv.py filters customers_scd on is_current; this join matches every customer version
  WARN   jobs/daily_revenue.py:9  .limit(1000) left in a production read
         The limit truncates the day's orders before aggregation

This push would be stopped.
```

The first run on a cold model takes a while: it has to load 19 GB into memory before it
reads a single line. Later runs are much quicker.

If you have no suitable branch to hand, make one:

```bash
python evals/make_fixture.py /tmp/sumbisori-fixture
cd /tmp/sumbisori-fixture
python -m sumbisori.dryrun main..case/scd2-join
```

---

## Step 4. Install the hook in a repository

Hooks live inside each repository's `.git` folder, so this is per repository.

```bash
cp hooks/pre-push /path/to/your/repo/.git/hooks/pre-push
chmod +x /path/to/your/repo/.git/hooks/pre-push
```

**One gotcha worth reading.** git runs the hook with whatever environment your shell had
when you typed `git push`. If your virtual environment isn't active at that moment, the
hook fails with `sumbisori-pre-push: not found`. The reliable fix is to put the full path
from step 2 into the hook:

```sh
#!/bin/sh
# Review the commits being pushed. Bypass with: git push --no-verify
exec /full/path/to/.venv/bin/sumbisori-pre-push "$@"
```

Now push a branch. If something blocks, the push stops and nothing reaches the remote.

To use it in every repository you clone, point git at a shared hooks folder instead of
copying the file each time:

```bash
mkdir -p ~/.git-hooks
cp hooks/pre-push ~/.git-hooks/pre-push && chmod +x ~/.git-hooks/pre-push
git config --global core.hooksPath ~/.git-hooks
```

That replaces hook handling for all your repositories, so if you already use something
like pre-commit or Husky, check how they expect to be chained first.

---

## Reading the output

| Line | Meaning |
|---|---|
| `BLOCK` | Would break production, corrupt data, or leak a credential. Stops the push. |
| `WARN` | Worth a look, but the push continues. |
| `ok     nothing to flag` | The scan and the model both came up empty. |
| `skip   model review unavailable` | Ollama was unreachable, timed out, or errored. The secret scan still ran. |
| `skip   diff is N chars, too large` | Over `MAX_DIFF_CHARS`. The model review is skipped; the secret scan still ran. |

Exit code 1 means the push was stopped, 0 means it went through.

The two checks fail in deliberately different directions. The secret scan is
deterministic, so it **fails closed**: a hit always stops the push. The model is
probabilistic and its server might be off, so it **fails open**: if the review can't run,
you get a warning and your push goes through. A reviewer that blocks people whenever the
GPU is busy gets uninstalled by Tuesday.

To push anyway:

```bash
git push --no-verify
```

---

## Configuration

Environment variables, so you can change them per shell or per repository:

| Variable | Default | What it does |
|---|---|---|
| `SUMBI_MODEL` | `qwen3-coder:30b` | Which Ollama model to use |
| `SUMBI_NUM_CTX` | `32768` | Context length to request. Keep it equal to the server's. |
| `SUMBI_BASE` | `origin/main` | What a new branch is compared against |

```bash
SUMBI_MODEL=gpt-oss:20b python -m sumbisori.dryrun my-branch
```

A few knobs are constants in the source rather than variables, because changing them is a
decision you want to make once and be able to read later:

| Constant | Where | Default |
|---|---|---|
| `SYSTEM` | `sumbisori/agent.py` | The review prompt. The first thing to edit for your codebase. |
| `MAX_ROUNDS` | `sumbisori/agent.py` | 6 tool rounds before the model must report |
| `CONTEXT_BUDGET` | `sumbisori/agent.py` | Stop at 75% of the context window |
| `MAX_DIFF_CHARS` | `sumbisori/hook.py` | 40,000 characters |
| `TIMEOUT_SECONDS` | `sumbisori/hook.py` | 120 seconds per call |
| `PATTERNS` | `sumbisori/scan.py` | The secret regexes |

The prompt is tuned for a data engineering repository: Spark jobs, SQL, pipelines. If your
code looks nothing like that, rewrite `SYSTEM` before judging the results.

---

## Choosing a model

The model must support tool calling, or it will never call `read_file` or `search_repo`
and you will get thin reviews with no evidence. On
[ollama.com/library](https://ollama.com/library), a model's page lists `tools` among its
capabilities if it does.

| If you have | Try | Why |
|---|---|---|
| 24 GB GPU, or a 32 GB Mac | `qwen3-coder:30b` | Mixture-of-experts: only about 3.3B parameters are active per token, so it answers quickly for its size |
| 16 GB | `gpt-oss:20b` | Fits with room left for the context |
| A bigger GPU, and patience | Any larger dense coding model tagged `tools` | Better reasoning, slower on every push |

Two numbers decide whether a model works for you. **Total parameters** decide whether it
fits in memory. **Active parameters** decide how fast it generates. For something sitting
in your push path, speed matters more than the last few points of benchmark quality.

If memory is tight, `OLLAMA_KV_CACHE_TYPE=q8_0` roughly halves the context cache at a
small cost in quality.

---

## Measuring whether it is any good

Do this before you ask a team to install it. A reviewer that cries wolf gets
`--no-verify`'d into irrelevance within a week, and one that misses things is worse than
none, because people start trusting it.

```bash
python evals/make_fixture.py /tmp/sumbisori-fixture
python evals/run_evals.py /tmp/sumbisori-fixture
```

The output looks like this (the numbers are an illustration, not a result):

```
model         qwen3-coder:30b
caught        11/12
false blocks  0/3
latency       p50 34.1s   p95 61.8s
```

- **caught** — how many planted problems were flagged, across several runs of each case.
  Models are not deterministic, so a problem caught one run in three is not caught.
- **false blocks** — how often a clean branch was blocked. This is the number that decides
  whether people keep the hook installed.
- **latency** — watch p95, not the median. The slowest push is the one people remember.

Add your own cases as you go. Each one is a branch in the fixture repository plus a line in
`CASES` in `evals/run_evals.py` naming the file that must be flagged, or `None` for a
branch that must pass. Every time the reviewer misses something in real life, add it.

---

## How it works

```
sumbisori/scan.py     Regex secret scan. Runs first, redacts what it finds, blocks on a hit.
sumbisori/tools.py    The only two things the model can do: read_file and search_repo.
                      Both read from git at the pushed commit. No shell, no writes.
sumbisori/agent.py    The loop: call the model, run the tool it asks for, repeat within
                      budget, then take the tools away and ask for a JSON report that
                      Pydantic validates.
sumbisori/hook.py     Works out what is being pushed, runs the checks, sets the exit code.
sumbisori/dryrun.py   The same checks against a branch you name, without pushing.
hooks/pre-push        The three-line shell script git actually calls.
evals/                Fixture builder and scorer.
```

The model never touches your filesystem or a shell. It asks; `tools.py` decides.

---

## Troubleshooting

**`Failed to connect to Ollama`**
The server isn't running, or isn't where the client expects it. Start it (step 1) and check
with `ollama ps`. If Ollama runs on another host or port, set `OLLAMA_HOST`, for example
`OLLAMA_HOST=http://127.0.0.1:11434`.

**`sumbisori-pre-push: not found` when pushing**
The hook ran, but the command wasn't on `PATH` in that shell. Put the full path to the
executable in the hook, as shown in step 4.

**The hook doesn't run at all**
Check that it is executable (`ls -l .git/hooks/pre-push`) and named exactly `pre-push`,
with no `.sample` suffix. If `git config core.hooksPath` returns a path, git is looking in
that folder instead of `.git/hooks`.

**`model requires more system memory`, or everything is glacial**
The model didn't fit and spilled into system RAM. Use a smaller model, lower
`SUMBI_NUM_CTX`, or set `OLLAMA_KV_CACHE_TYPE=q8_0`. `ollama ps` shows whether a loaded
model is running entirely on the GPU.

**`skip   model review unavailable ... timed out`**
The review took longer than `TIMEOUT_SECONDS` in `sumbisori/hook.py`. Raise it, use a
faster model, or keep the model warm with `OLLAMA_KEEP_ALIVE`.

**Reviews come back empty, or with no evidence**
Most likely the model doesn't support tool calling. Check for `tools` on its Ollama library
page, and try `qwen3-coder:30b`.

**`skip   diff is N chars, too large`**
Expected on big branches. Push smaller changes, or raise `MAX_DIFF_CHARS` and accept slower
reviews.

**Nothing happens on a new branch**
The reviewer compares against `origin/main`. If your default branch has another name, set
`SUMBI_BASE`, for example `SUMBI_BASE=origin/develop`.

**Windows**
The hook is a shell script, so run your pushes from Git Bash. Use a Unix-style path in the
`exec` line, for example `/c/Users/you/project/.venv/Scripts/sumbisori-pre-push`.

---

## Uninstall

```bash
rm /path/to/your/repo/.git/hooks/pre-push
git config --global --unset core.hooksPath     # only if you set it
pip uninstall sumbisori
ollama rm qwen3-coder:30b                      # reclaims ~19 GB
```

---

## Known limits

- The secret scan covers a handful of common formats. For production, run
  [gitleaks](https://github.com/gitleaks/gitleaks) or
  [detect-secrets](https://github.com/Yelp/detect-secrets) alongside it.
- The model is not deterministic. The same diff can produce slightly different findings
  from one run to the next. That is what the evals are for.
- This ships with no accuracy numbers. They depend on your model, your hardware and your
  codebase. Run the evals and find out.
- The prompt assumes a data engineering repository.
