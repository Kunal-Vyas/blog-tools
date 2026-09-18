# blog-tools

Working code from the posts on [kunalvyas.info/blog](https://kunalvyas.info/blog/).

When a post describes something I built, the real thing lives here: not a snippet pulled
out of context, but the package, its README, and whatever it takes to run it yourself.

Each tool is a self-contained folder. Nothing at the root imports anything from a tool, and
no tool imports from another. Clone the repository, go into the folder you care about, and
follow its README.

---

## What's here

| Tool | What it does | Post |
|---|---|---|
| [`sumbisori`](sumbisori/) | A code reviewer that runs on a local open-weight model every time you `git push`. Scans for secrets, reviews the diff, blocks the push when it finds something that would hurt production. | [The Haenyeo Guide to AI](https://kunalvyas.info/blog/haenyeo-guide-to-ai.html) |
| [`sugarshack`](sugarshack/) | A laptop-sized medallion lakehouse on DuckDB and dbt. Generates messy sources, builds bronze, silver and gold, audits gold against the payment processor's settlement report, and only publishes what passes. | [The Maple Syrup Guide to Data Lakes](https://kunalvyas.info/blog/maple-syrup-guide-to-data-lakes.html) |

---

## Getting started

```bash
git clone https://github.com/Kunal-Vyas/blog-tools.git
cd blog-tools/sumbisori      # or blog-tools/sugarshack
```

Then read that folder's README. Each tool lists its own prerequisites and sets up its own
virtual environment, so you never install one tool's dependencies to run another.

---

## What to expect from this code

**It runs.** Every tool here has been executed, not just written. If a README tells you to
type something, that command has been typed.

**It is built to be read.** These are companions to posts that explain the reasoning, so
they favour clarity over cleverness and over completeness. Where a real deployment would
reach for a mature library, the code often shows the small version of the idea and says so
in a comment. The READMEs are explicit about those trade-offs under "Known limits".

**It is not a product.** No release process, no semantic versioning, no promise that a tool
keeps working as the models and libraries underneath it move. Fork it, take the parts you
want, change whatever you like.

**Models are not deterministic.** Anything here that calls an LLM can behave differently on
identical input. Where that matters, the tool ships an eval harness so you can measure the
behaviour on your own hardware rather than trusting a number in a blog post.

---

## Layout

```
blog-tools/
├── README.md           this file
├── .gitignore
└── <tool>/             one folder per tool, self-contained
    ├── README.md       what it does, how to run it, how to troubleshoot it
    ├── pyproject.toml  dependencies and entry points
    ├── <package>/      the code
    └── evals/          how to measure whether it works, where that applies
```

Conventions I try to hold to, so that each folder feels the same:

- A README that gets a reader from an empty machine to a working tool, with a
  troubleshooting section built from failures I actually hit.
- A way to try the tool that changes nothing, before any step that changes something.
- Configuration through environment variables where it is per-run, and named constants in
  the source where it is a decision you make once.
- No network calls except to services the README names.

---

## Questions and corrections

Open an issue, or email me at kunalhvyas@gmail.com. Corrections are welcome, especially
where a README sends you down a path that doesn't work on your setup. Pull requests are
fine too, though these are companions to published writing, so anything that changes what
a post describes may take a while to land.

---

## Licence and attribution

MIT, see [LICENSE](LICENSE). Use it however you like.

The ideas, arguments and technical judgments in these tools and the posts they accompany
are my own. I used AI assistance while building and writing them, and I reviewed and tested
everything published here.

— Kunal Vyas, Halifax, Nova Scotia
