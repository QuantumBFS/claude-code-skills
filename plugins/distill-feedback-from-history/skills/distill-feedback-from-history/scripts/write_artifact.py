#!/usr/bin/env python3
"""
write_artifact.py — final phase of distill-feedback-from-history.

Render ONE artifact (CLAUDE.md addition, auto-memory feedback entry, or
SKILL.md draft) from a cluster spec and append a row to INDEX.md.

Most clusters mined by this pipeline are behavioral patterns (discipline
rules, preferences, format/voice edicts) — they are NOT reusable skills.
Default output type is `claude-md`, which writes a CLAUDE.md insertion
proposal you can copy/paste into your global or project CLAUDE.md. Only
clusters that describe a parameterizable multi-step workflow should be
rendered as `skill`.

Input: cluster JSON via stdin or --json-file. Schema:
{
  "slug": "kebab-case-name",
  "title": "Human Title",
  "signal": "correction|domain-injection|format-edict|error-catch",
  "rule": "The rule itself, <= 2 sentences.",
  "why": "Rationale, <= 1 sentence.",
  "how_to_apply": "When this kicks in, <= 2 sentences.",
  "evidence": [
    {"session": "abc123", "turn": 4, "ts": "2026-05-12T...", "quote": "verbatim user text"},
    ...
  ],
  "confidence": 4.2,
  "occurrences": 5,
  # Optional, type-specific:
  "claude_md_section": "Existing section to extend, or new section header (for --type claude-md)",
  "skill_description": "YAML frontmatter description (for --type skill only)"
}

Usage:
    write_artifact.py --type claude-md --staging ./distilled < cluster.json
    write_artifact.py --type memory   --staging ./distilled < cluster.json
    write_artifact.py --type skill    --staging ./distilled < cluster.json
"""
import argparse
import json
import sys
from pathlib import Path

INDEX_HEADER = """# Distilled Feedback Candidates

Each row below is a draft artifact in one of three buckets. Review and
move the ones you want to keep into the right place:

- `claude-md-additions/<slug>.md` — proposed text + insertion point for
  your global or project `CLAUDE.md`. Copy/paste into the named section.
- `feedback-memories/<slug>.md` — a ready-to-drop auto-memory file. Move
  to `~/.claude/projects/<your-project>/memory/` and add a pointer line
  in `MEMORY.md`.
- `skill-candidates/<slug>/SKILL.md` — full SKILL.md draft. Move to
  `~/.claude/skills/<slug>/` or into a plugin.

| Slug | Type | Signal | Occ | Confidence | Status |
|---|---|---|---|---|---|
"""

CLAUDE_MD_TEMPLATE = """# Proposed CLAUDE.md addition: `{slug}`

**Primary signal:** {signal}   **Occurrences:** {n}   **Confidence:** {confidence}

## Insertion point

{section_hint}

## Proposed text

{section_header}

{rule}

**Why:** {why}

**How to apply:** {how_to_apply}

## Evidence

{evidence_block}
"""

MEMORY_TEMPLATE = """---
name: feedback-{slug}
description: {desc_short}
metadata:
  type: feedback
---

{rule}

**Why:** {why}

**How to apply:** {how_to_apply}

**Evidence:**
{evidence_block}
"""

SKILL_TEMPLATE = """---
name: {slug}
description: {skill_description}
---

# {title}

## Rule

{rule}

## Why

{why}

## How to apply

{how_to_apply}

## Evidence

{evidence_block}

---

_Distilled by `distill-feedback-from-history` from {n} occurrence(s)
across the user's local session history. Primary signal: **{signal}**.
Confidence score: {confidence}._
"""


def fmt_evidence_md(items):
    out = []
    for it in items:
        quote = it["quote"].replace("\n", " ").strip()
        if len(quote) > 280:
            quote = quote[:277] + "..."
        ts = (it.get("ts") or "")[:10]
        sess = (it.get("session") or "")[:8]
        turn = it.get("turn", "?")
        out.append(f"- **{sess} · turn {turn} · {ts}** — \"{quote}\"")
    return "\n".join(out) if out else "_No verbatim examples recorded._"


def write_claude_md(cluster: dict, staging: Path) -> Path:
    """Write a CLAUDE.md insertion proposal."""
    out_dir = staging / "claude-md-additions"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{cluster['slug']}.md"
    section_hint = cluster.get(
        "claude_md_section",
        "Add as a new top-level section (or fold into the nearest existing one).",
    )
    section_header = "## " + cluster["title"]
    content = CLAUDE_MD_TEMPLATE.format(
        slug=cluster["slug"],
        signal=cluster.get("signal", "?"),
        n=cluster.get("occurrences", len(cluster.get("evidence", []))),
        confidence=cluster.get("confidence", "?"),
        section_hint=section_hint,
        section_header=section_header,
        rule=cluster["rule"],
        why=cluster["why"],
        how_to_apply=cluster["how_to_apply"],
        evidence_block=fmt_evidence_md(cluster.get("evidence", [])),
    )
    path.write_text(content)
    return path


def write_memory(cluster: dict, staging: Path) -> Path:
    """Write an auto-memory feedback file."""
    out_dir = staging / "feedback-memories"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{cluster['slug']}.md"
    # Memory description: short, "what triggers this rule".
    # Use the first sentence of the rule (or the rule itself if shorter),
    # capped at the nearest word boundary under 200 chars.
    desc_short = cluster.get("memory_description")
    if not desc_short:
        first_sentence = cluster["rule"].split(".")[0].strip()
        if len(first_sentence) <= 200:
            desc_short = first_sentence
        else:
            # Truncate at last whitespace before char 200, append ellipsis.
            cutoff = first_sentence.rfind(" ", 0, 200)
            desc_short = first_sentence[:cutoff if cutoff > 0 else 200].rstrip() + "…"
    content = MEMORY_TEMPLATE.format(
        slug=cluster["slug"],
        desc_short=desc_short,
        rule=cluster["rule"],
        why=cluster["why"],
        how_to_apply=cluster["how_to_apply"],
        evidence_block=fmt_evidence_md(cluster.get("evidence", [])),
    )
    path.write_text(content)
    return path


def write_skill(cluster: dict, staging: Path) -> Path:
    """Write a full SKILL.md draft (only for true workflow patterns)."""
    out_dir = staging / "skill-candidates" / cluster["slug"]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "SKILL.md"
    skill_description = cluster.get(
        "skill_description",
        f"Use when {cluster.get('how_to_apply', '...').split('.')[0]}.",
    )
    content = SKILL_TEMPLATE.format(
        slug=cluster["slug"],
        skill_description=skill_description,
        title=cluster["title"],
        rule=cluster["rule"],
        why=cluster["why"],
        how_to_apply=cluster["how_to_apply"],
        evidence_block=fmt_evidence_md(cluster.get("evidence", [])),
        n=cluster.get("occurrences", len(cluster.get("evidence", []))),
        signal=cluster.get("signal", "?"),
        confidence=cluster.get("confidence", "?"),
    )
    path.write_text(content)
    return path


WRITERS = {
    "claude-md": write_claude_md,
    "memory": write_memory,
    "skill": write_skill,
}


def append_index(cluster: dict, staging: Path, artifact_type: str, status: str):
    index = staging / "INDEX.md"
    if not index.exists():
        index.write_text(INDEX_HEADER)
    slug = cluster["slug"]
    if artifact_type == "skill":
        link = f"./skill-candidates/{slug}/SKILL.md"
    elif artifact_type == "memory":
        link = f"./feedback-memories/{slug}.md"
    else:
        link = f"./claude-md-additions/{slug}.md"
    row = "| [{slug}]({link}) | {atype} | {signal} | {occ} | {conf} | {status} |\n".format(
        slug=slug,
        link=link,
        atype=artifact_type,
        signal=cluster.get("signal", "?"),
        occ=cluster.get("occurrences", len(cluster.get("evidence", []))),
        conf=cluster.get("confidence", "?"),
        status=status,
    )
    with open(index, "a") as f:
        f.write(row)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", choices=list(WRITERS), default="claude-md",
                    help="Artifact type to render (default: claude-md).")
    ap.add_argument("--staging", default="./distilled",
                    help="Staging directory root.")
    ap.add_argument("--json-file", default=None,
                    help="Read cluster JSON from this path instead of stdin.")
    ap.add_argument("--status", default="drafted",
                    help="INDEX.md status column (default: drafted).")
    args = ap.parse_args()

    cluster = json.load(open(args.json_file)) if args.json_file else json.load(sys.stdin)
    staging = Path(args.staging)
    staging.mkdir(parents=True, exist_ok=True)
    writer = WRITERS[args.type]
    path = writer(cluster, staging)
    append_index(cluster, staging, args.type, args.status)
    print(str(path))


if __name__ == "__main__":
    main()
