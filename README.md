# Claude Code Skills — QuantumBFS

A small marketplace of [Claude Code](https://code.claude.com) plugins, each shipping one skill.

## Install

In Claude Code, add this repo as a marketplace, then install whichever plugin(s) you want:

```text
/plugin marketplace add QuantumBFS/claude-code-skills
/plugin install download-papers@quantum-bfs
/plugin install submit-slurm-job@quantum-bfs
/plugin install verify-references@quantum-bfs
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
    └── verify-references/
        ├── .claude-plugin/plugin.json
        └── skills/verify-references/
            ├── SKILL.md
            ├── check_unused_refs.py
            ├── compare_refs.py
            └── download_crossref.py
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
