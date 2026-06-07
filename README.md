# Claude Code Skills — QuantumBFS

A small marketplace of [Claude Code](https://code.claude.com) plugins, each shipping one skill.

## Install

In Claude Code, add this repo as a marketplace, then install whichever plugin(s) you want:

```text
/plugin marketplace add QuantumBFS/claude-code-skills
/plugin install download-papers@quantum-bfs
/plugin install submit-slurm-job@quantum-bfs
/plugin install verify-references@quantum-bfs
/plugin install paper-review-checklist@quantum-bfs
/plugin install distill-feedback-from-history@quantum-bfs
/plugin install digitize-plots@quantum-bfs
/plugin install claude-log-restore@quantum-bfs
```

The `@quantum-bfs` suffix matches the `name` field in `.claude-plugin/marketplace.json`.

To update later:

```text
/plugin marketplace update quantum-bfs
```

## Plugins

### `download-papers`

Download an academic paper as a PDF given a URL, DOI, paper title, or arXiv ID. Resolves in order: open web (author homepage, repositories) → Sci-Hub mirrors → arXiv.

Triggers on phrases like *"download paper"*, *"get me the PDF"*, *"fetch this DOI"*. No configuration required.

### `submit-slurm-job`

Generate and submit `sbatch` scripts for GPU compute jobs on a Slurm cluster. Handles partition selection, explicit GPU model in `--gres`, full Python path, and log file management.

**Required configuration** — add to your project's `CLAUDE.md`:

```markdown
## Slurm Configuration

- PYTHON_PATH: `/path/to/miniconda3/envs/myenv/bin/python3`
- PROJECT_DIR: `/home/your_user/private/homefile`   # scripts/logs must live here
- PARTITION: `home`                                 # compute partition
```

Invoke with `/submit-slurm-job` (or just describe the job — Claude will pick up the skill).

### `verify-references`

Verify a BibTeX bibliography against CrossRef metadata. The skill:

1. Scans your `.tex` files to flag uncited entries.
2. Queries CrossRef for every entry with a DOI and writes a side-by-side `.bib`.
3. Compares the two and produces a Markdown report listing field-level discrepancies (title, author, journal, volume, pages, year), sorted by similarity.

Useful before submission to catch hallucinated or stale BibTeX. Invoke by asking to *"verify references"* / *"check the bib file"*. Requires Python 3 and an internet connection (for the CrossRef API).

### `paper-review-checklist`

Review a LaTeX research-paper draft against a fixed checklist (notation, figures, citations, structure, equations, style, reproducibility) and insert inline author-comment reminders at the locations that fail each check.

The skill reads the entire `.tex`, runs programmatic checks (broken `\ref`/`\cite`, unreferenced equation labels, symbol-synonym pairs, one-use acronyms), then walks the checklist category by category and inserts short `\lw{...}` notes (or `\todo{...}` — whichever author-comment macro the project's preamble defines). Ends with a per-category summary and the top three most impactful issues.

Invoke by asking to *"review my paper"* / *"apply the paper-review checklist to file X"*.

### `distill-feedback-from-history`

Mine your own local Claude Code session history (`~/.claude/projects/`) for **recurring behavioral feedback** — corrections, format/voice edicts, error catches, domain-knowledge injections — and distill each pattern into the right kind of artifact:

- **CLAUDE.md addition** (default) — the natural home for discipline rules and preferences.
- **Auto-memory feedback entry** — alternative for the same content if you prefer the harness memory system.
- **SKILL.md draft** — only when the pattern describes a parameterizable multi-step workflow. Rare; behavioral patterns are not workflows.

The pipeline runs in eight phases: extract → tag (regex) → domain-injection (LLM) + filter → cluster → classify into a bucket → distill (autonomous or A/B/C/D/E gate) → render → hand back. Default scope is all projects, last 30 days.

Invoke by asking to *"distill recurring feedback from my sessions"* / *"what should I add to CLAUDE.md?"* / *"find behavioral patterns I should write down"*. Single-user, local-only; reads JSONLs and writes drafts to `./distilled/`, no network calls, no auto-install.

**Note:** This plugin replaces the earlier `extract-skills-from-history`, which mis-rendered behavioral rules as standalone `SKILL.md` files. The new name and bucketed output reflect that most patterns mined this way are memories, not skills.

### `digitize-plots`

Extract numeric `(x, y)` data from a plot/figure image — including a figure inside a PDF — into a CSV. The command-line counterpart to [WebPlotDigitizer](https://automeris.io), which is GUI-only.

The bundled `digitize.py` wraps the `plotdigitizer` CLI and hides its two silent footguns (it int-truncates fractional calibration values, and it expects bottom-origin pixel-y), then adds the surrounding workflow: `render` a PDF page to PNG, `inspect` to read calibration ticks off zoomed margins, and `extract` with optional single-series color isolation and a verification overlay. The whole job is usually two or three commands.

Invoke by asking to *"digitize this plot"*, *"extract the data/curve from this figure"*, *"read the points off this chart"*, or *"WebPlotDigitizer but from the CLI"*. Requires Python 3 with `plotdigitizer`, `numpy`, and `Pillow` (`pip install plotdigitizer numpy Pillow`); PDF rendering uses PyMuPDF or the `pdftoppm` binary.

### `claude-log-restore`

Recover context from Claude Code session transcripts. Claude Code stores each session as a local JSONL file under `~/.claude/projects/<encoded-project-path>/<session-id>.jsonl`; this skill locates the right one and mines it.

The bundled `claude_log_restore.py` is dependency-free and streams JSONL line by line, so it stays safe on multi-MB transcripts. It can list recent sessions for a project, find a session by partial UUID/hash (`--all-projects`), search for keywords (`-q`), or surface handoff/summary/next-step notes (`--handoff`), printing the transcript path, session id, an approximate `claude --resume` command, and selected snippets (`--json` for machine-readable output). It reads and summarizes only — in-session code/conversation restore is still done with `/rewind` inside Claude Code.

Invoke by asking to *"restore my Claude session"*, *"find the handoff notes from last time"*, *"resume session 13e617"*, or *"what were the next steps in this project's history?"*. Requires Python 3; no network calls, no dependencies.

## Repository layout

```
.
├── .claude-plugin/
│   └── marketplace.json          # marketplace manifest, lists all plugins
└── plugins/
    ├── download-papers/
    │   ├── .claude-plugin/plugin.json
    │   └── skills/download-papers/SKILL.md
    ├── submit-slurm-job/
    │   ├── .claude-plugin/plugin.json
    │   └── skills/submit-slurm-job/SKILL.md
    ├── verify-references/
    │   ├── .claude-plugin/plugin.json
    │   └── skills/verify-references/
    │       ├── SKILL.md
    │       ├── check_unused_refs.py
    │       ├── compare_refs.py
    │       └── download_crossref.py
    ├── paper-review-checklist/
    │   ├── .claude-plugin/plugin.json
    │   └── skills/paper-review-checklist/SKILL.md
    ├── distill-feedback-from-history/
    │   ├── .claude-plugin/plugin.json
    │   └── skills/distill-feedback-from-history/
    │       ├── SKILL.md
    │       └── scripts/
    │           ├── extract_turns.py
    │           ├── tag_turns.py
    │           └── write_artifact.py
    ├── digitize-plots/
    │   ├── .claude-plugin/plugin.json
    │   └── skills/digitize-plots/
    │       ├── SKILL.md
    │       └── scripts/digitize.py
    └── claude-log-restore/
        ├── .claude-plugin/plugin.json
        └── skills/claude-log-restore/
            ├── SKILL.md
            └── scripts/claude_log_restore.py
```

Helper scripts shipped alongside a `SKILL.md` are referenced from the skill instructions via `${CLAUDE_SKILL_DIR}`, which Claude Code expands to the skill's install directory at invocation time.

## Contributing

Add a new plugin by:

1. Create `plugins/<your-plugin>/.claude-plugin/plugin.json` (use one of the existing files as a template).
2. Add the skill at `plugins/<your-plugin>/skills/<your-plugin>/SKILL.md` with YAML frontmatter (`name`, `description`).
3. Append an entry to `.claude-plugin/marketplace.json`.

Keep skills well-scoped, parameterize any user-specific paths, and document required configuration in this README.

## License

MIT
