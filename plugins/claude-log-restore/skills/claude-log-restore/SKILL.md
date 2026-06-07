---
name: claude-log-restore
description: Use when restoring, reading, searching, summarizing, or resuming Claude Code logs/history from a session hash, UUID prefix, project path, or handoff/hands-off request. Also use when mining ~/.claude/projects JSONL transcripts for handoff notes, summaries, next steps, or lost conversation context.
---

# Claude Log Restore

Use this skill to recover useful context from Claude Code transcripts. Claude
Code stores session transcripts as local JSONL files under
`~/.claude/projects/<encoded-project-path>/<session-id>.jsonl`. The encoded
project path is normally the absolute path with `/` replaced by `-`; for
example `/Users/foo/repo` becomes `-Users-foo-repo`.

Official Claude Code docs say `/resume`, `claude --resume`, and `/export` are
the supported session interfaces. They also document that transcript files live
under `~/.claude/projects/<project>/<session-id>.jsonl` and are cleaned up after
30 days by default unless configured otherwise. Checkpoint restore is done from
Claude Code itself with `/rewind`; local transcript recovery only reads and
summarizes the saved JSONL.

## Fast path

Use the bundled script first:

```bash
python ${CLAUDE_SKILL_DIR}/scripts/claude_log_restore.py <hash-or-uuid-prefix> --project "$PWD" --handoff
```

Common variants:

```bash
# List recent Claude sessions for the current project.
python ${CLAUDE_SKILL_DIR}/scripts/claude_log_restore.py --project "$PWD"

# Find a session by partial UUID/hash across all Claude projects.
python ${CLAUDE_SKILL_DIR}/scripts/claude_log_restore.py 13e617 --all-projects

# Search current project's transcripts for handoff-like notes.
python ${CLAUDE_SKILL_DIR}/scripts/claude_log_restore.py --project "$PWD" --handoff --limit 20

# Search all projects for keywords.
python ${CLAUDE_SKILL_DIR}/scripts/claude_log_restore.py --all-projects -q "ringMPS" -q "next steps"
```

The script streams JSONL line by line, so it is safe for multi-MB transcript
files. It prints the matching transcript path, session id, approximate resume
command, and selected snippets. Add `--json` for machine-readable output.

## Manual fallback

When the script is unavailable, do not `cat` large transcript files. Check sizes
and search first:

```bash
project_dir="$HOME/.claude/projects/$(pwd | sed 's|^/|-|; s|/\.\([^/]*\)|--\1|g; s|/|-|g')"
find "$project_dir" -maxdepth 2 -name '*.jsonl' -print0 | xargs -0 ls -lh
rg -n -i 'handoff|hand off|hands off|next steps|summary|blocked|todo|resume' "$project_dir"
```

If the user gives a hash or UUID prefix, locate the transcript by prefix:

```bash
find "$HOME/.claude/projects" -name '<prefix>*' -print
```

Once the session id is known, the normal resume command is:

```bash
claude --resume <session-id>
```

If Claude needs in-session restore of code or conversation, tell the user to use
`/rewind` inside that Claude session. Transcript mining can recover context and
handoff notes, but it does not rewrite Claude's checkpoint state.

## Output discipline

Report recovered context with concrete paths and session IDs. Separate direct
log evidence from inference. If the transcript contains large tool outputs or
hook-injected instructions, summarize only the relevant user/assistant messages
and avoid pasting secrets or huge outputs.
