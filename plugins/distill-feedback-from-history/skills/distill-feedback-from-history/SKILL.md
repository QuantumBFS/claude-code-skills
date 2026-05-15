---
name: distill-feedback-from-history
description: Use when the user asks to mine their own Claude Code session history for recurring behavioral feedback — corrections, format/voice edicts, error catches, domain-knowledge injections. The output is normally proposed CLAUDE.md additions (the patterns are discipline rules, not workflows). Triggers on phrases like "distill my feedback", "find recurring corrections in my sessions", "what should I add to CLAUDE.md?", "/distill-feedback".
---

# Distill Feedback From History

## Overview

Mine the user's own local AI-interaction trajectories for **recurring behavioral feedback** — places where the user's pushback, format edicts, error catches, or domain-knowledge injections show a consistent preference — and distill each pattern into the right kind of artifact:

- A proposed **CLAUDE.md addition** (default; the right home for discipline rules and preferences).
- An **auto-memory feedback entry** (alternative for the same content if the user prefers the harness memory system).
- A **SKILL.md draft** (rare; only when the pattern describes a parameterizable multi-step workflow, not a single behavioral rule).

**Why three buckets and not one.** A skill is a workflow — multi-step, parameterizable, invokable by a slash-command (e.g. `paper-review-checklist`, `verify-references`). A behavioral preference ("preserve my voice when editing prose", "walk back overclaims when new evidence arrives") is **not** a workflow; it is a discipline rule. Earlier versions of this pipeline rendered every pattern as a SKILL.md, which produced microscopic, mis-categorized output. This version routes each cluster to the right place.

**Scope.** Personal use against the user's own local session JSONLs. Not an institutional capture system; no consent/dedup infra.

## When to use

- "Distill recurring feedback from my sessions."
- "What corrections do I keep giving Claude? What should I add to CLAUDE.md?"
- "Find behavioral patterns I should write down."
- The user invokes `/distill-feedback`.

## When NOT to use

- For one-off corrections that have not yet recurred.
- For cross-user / institutional data — this skill is single-user only.
- For live monitoring — only reads completed session JSONLs.
- For finding reusable **workflows** (multi-step procedures across sessions). The signals this skill detects are behavioral; workflow detection needs a different detector (tool-call-sequence n-grams, recurring phase decompositions). Note that as a limitation.

## Inputs

- Session source: `claude` (Claude Code JSONLs at `~/.claude/projects/`). Codex CLI logs are out of scope for v0.2.
- Project filter: substring of the project directory name, or `all` (default).
- Time window: `--since YYYY-MM-DD`. Default: **30 days ago**.
- Output preference (per cluster): `claude-md` (default), `memory`, or `skill`. The pipeline chooses; the user can override at the gate.

## Signals

A "meaningful input" is detected via four signal types:

| Signal | Detector | Examples |
|---|---|---|
| **correction** | regex heuristic in `tag_turns.py` | "no, do X instead", "that's wrong", "redo this", "you missed Y" |
| **format-edict** | regex heuristic | "use \\lw{} not \\lw{check:…}", "always use unicode math", "preserve my wording verbatim" |
| **error-catch** | regex heuristic | "you messed up", "X should be Y", "verify this — I cannot confirm", "off by a factor of" |
| **domain-injection** | **LLM detector** (you, the running agent) | turn introduces a fact, constraint, or convention not derivable from prior assistant context |

The first three are cheap and run via Python regex. The fourth requires comparing the user's turn against the preceding assistant turn — you do that yourself in Phase 3.

## Workflow

### Phase 1 — Extract turns

The plugin's `scripts/` directory is at `${CLAUDE_PLUGIN_ROOT}/skills/distill-feedback-from-history/scripts/`.

```bash
SCRIPTS="${CLAUDE_PLUGIN_ROOT}/skills/distill-feedback-from-history/scripts"
mkdir -p ./distilled
python3 "$SCRIPTS/extract_turns.py" --source claude --project all > ./distilled/turns.json
```

Override the defaults only if the user requests:
- `--project laughlin` (substring match against project dir name)
- `--since 2026-04-01` (only sessions modified after this date)

### Phase 2 — Heuristic tag

```bash
python3 "$SCRIPTS/tag_turns.py" < ./distilled/turns.json > ./distilled/tagged.json
```

Output adds a `tags` object per turn with booleans for `correction`, `format-edict`, `error-catch`, a `prefilter` flag, and the matched substrings.

Report the prefilter stats briefly:
> "Phase 2 done: {prefilter_positive} of {total_turns} turns ({rate}%) passed the heuristic prefilter."

### Phase 3 — Domain-injection detection + Phase-3 disposition

For every turn with `prefilter: true`, evaluate against the preceding `assistant_prev`. Decide whether the user turn carries meaningful behavioral signal, and tag accordingly:

- **domain-injection: true** if the user introduces a fact, constraint, or named reference not derivable from prior assistant text.
- **drop: true** if the turn is actually a quoted-back assistant fragment, a task spec without a generalizable rule, a slash-command body that slipped through, or otherwise noise.

A turn is **kept for clustering** iff: not dropped, and at least one of {correction, format-edict, error-catch, domain-injection} carries real signal in context.

Update each turn's `tags` object with `keep` (bool), `signal_final` (chosen primary signal), and a short rationale.

### Phase 4 — Cluster

Group the kept turns into **feedback candidates**. A candidate is a cluster of ≥2 turns covered by a single one-sentence rule. Singletons are dropped unless the single occurrence is unmistakable and broadly applicable.

For each cluster, compute:

```
confidence = (avg_signal_strength) × log2(1 + occurrences) × homogeneity
  where homogeneity = 1.0 if all turns share signal_final, else 0.5
```

### Phase 5 — Classify each cluster into an artifact bucket

For each surviving cluster, decide: `claude-md` | `memory` | `skill`.

**Default is `claude-md`.** The patterns this pipeline detects are almost always discipline rules / preferences, which belong in CLAUDE.md (or auto-memory, an equivalent home).

A cluster is rendered as **`skill`** only when it describes a **parameterizable multi-step workflow** that meets all of:

- Members describe a procedure with phases (extract → tag → cluster, or read → check → comment, etc.), not a single behavioral rule.
- The procedure is parameterizable (it takes inputs and produces outputs).
- The procedure would benefit from having an explicit invocation point (slash command, skill activation phrase).
- The pattern recurs across ≥3 sessions with the same phase structure.

In practice, the four signals this pipeline detects rarely surface true workflows. If your output has any `skill` entries, sanity-check them carefully — they are most likely behavioral rules misclassified.

A cluster is rendered as **`memory`** instead of `claude-md` when:

- It is project-specific (mentions a specific paper/repo/file path) and the user wants it scoped to that project's auto-memory.
- The user explicitly asks for memory format.

For each cluster, also propose:
- `claude_md_section`: which existing section in the user's CLAUDE.md it should extend, or a header for a new section. Read `~/.claude/CLAUDE.md` and the project CLAUDE.md first (if present) to make this choice grounded.
- `memory_description`: a short one-liner for the auto-memory `description:` frontmatter field.

### Phase 6 — Distill (autonomous or gated)

**For each cluster** decide autonomous vs. gated using the SKILL.md threshold: `confidence ≥ 2.5 AND occurrences ≥ 3 AND homogeneity == 1.0`.

- **High-confidence**: autonomous distillation — write the artifact directly.
- **Ambiguous** (≥2 occurrences but below threshold): present A/B/C/D/E gate.

**Gate format** (one cluster at a time, do NOT batch):

> **Candidate: <slug>** — bucket=<claude-md|memory|skill>, signal=<signal>, occurrences=<N>, confidence=<X>
>
> _Verbatim user turns:_
> 1. [session abc · turn N · date] "<quote 1>"
> 2. [session def · turn M · date] "<quote 2>"
>
> **Three possible rule formulations:**
> **(A)** `<narrow reading — applies only to the exact context shown>`
> **(B)** `<broader reading — generalizes across a category of tasks>`
> **(C)** `<meta reading — the rule is about a different aspect entirely>`
> **(D)** None — I'll write the rule myself.
> **(E)** Skip — not actually a useful pattern.

If `A/B/C`, use that rule. If `D`, the user writes it. If `E`, drop.

### Phase 7 — Render

For each cluster that survived Phase 6, call the renderer with the chosen artifact type:

```bash
echo '<cluster-json>' | python3 "$SCRIPTS/write_artifact.py" --type claude-md --staging ./distilled
# or:
echo '<cluster-json>' | python3 "$SCRIPTS/write_artifact.py" --type memory --staging ./distilled
echo '<cluster-json>' | python3 "$SCRIPTS/write_artifact.py" --type skill --staging ./distilled
```

The renderer writes to the right subdirectory and appends an INDEX.md row.

### Phase 8 — Hand back

Summarize the distilled output:

> Wrote N artifacts to `./distilled/`:
>
> - K CLAUDE.md additions (review and copy into `~/.claude/CLAUDE.md` or your project CLAUDE.md)
> - M feedback memory files (review and move to `~/.claude/projects/.../memory/`)
> - S skill drafts (rare — if any, double-check they are real workflows)
>
> Open `./distilled/INDEX.md` for the full list.

**Do NOT auto-install.** Drafts stay in `./distilled/` until the user reviews and moves them.

## What this skill does NOT do

- It does **not** auto-edit your CLAUDE.md or memory directory. Output stops at staging.
- It does **not** detect reusable workflows. Detecting "the user runs paper-review-checklist → verify-references → write reply.tex three times" requires a different signal set (tool-call-sequence patterns), not implemented here.
- It does **not** modify your session JSONLs. Read-only.
- It does **not** call external services. No network, no telemetry.
- It does **not** cluster across users. Single-user, single-machine.

## Output language

CLAUDE.md additions and memory files are written in **English**. Verbatim user quotes are preserved in their original language.

## Notes on quality

- A candidate with only 2 occurrences and `confidence < 2.5` is a hypothesis, not a rule — the gate exists to keep these from polluting your CLAUDE.md.
- Heuristic regexes produce false positives; Phase 3 is where most get filtered. If Phase 3 retains < 50% of prefilter hits, that's normal and good — the regexes are intentionally permissive.
- Most clusters route to `claude-md`. If your output has many `skill` entries, the classification is wrong — sanity-check.
