#!/usr/bin/env python3
"""
extract_turns.py — Phase 1 of extract-skills-from-history.

Parse Claude Code session JSONLs into a clean per-session list of
(user, assistant) turn pairs. Strips system reminders, slash-command
wrappers, tool-result echoes.

Usage:
    python3 extract_turns.py --source claude [--project NAME|all] [--since YYYY-MM-DD]

Output: JSON to stdout, schema:
    {
      "source": "claude",
      "sessions": [
        {
          "session_id": "...",
          "project": "...",
          "start_time": "ISO-8601",
          "turns": [
            {
              "index": 0,
              "ts": "ISO-8601",
              "user": "user text",
              "assistant_prev": "preceding assistant text (truncated)",
              "assistant": "assistant reply (truncated)"
            }, ...
          ]
        }, ...
      ]
    }
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
MAX_ASSISTANT_CHARS = 2000
SKIP_USER_PREFIXES = (
    "<system-reminder>",
    "<command-name>",
    "<command-message>",
    "<command-args>",
    "<local-command-stdout>",
    "<local-command-stderr>",
    "Caveat:",
    "[Image:",
    "[Request interrupted",
    "<task-notification>",
    # Slash-command body openings that get inlined into a user turn:
    "Base directory for this skill:",
    "Run a Codex review through the shared built-in reviewer",
    "Please analyze this codebase and create a CLAUDE.md file",
    "# /loop",
    "# /schedule",
    "# /insights",
)

# Substrings that indicate the user message is actually a slash-command body
# being inlined (not a real user prompt). One match anywhere = skip.
SKIP_USER_SUBSTRINGS = (
    "Raw slash-command arguments:",
    "Core constraint:",
    "Argument handling:",
    "Execution mode rules:",
    "<SUBAGENT-STOP>",
    "## How to Access Skills",
)


def extract_text(content):
    """Pull out plain text from a message content (string or list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict):
                if c.get("type") == "text":
                    parts.append(c.get("text", ""))
            elif isinstance(c, str):
                parts.append(c)
        return "\n".join(parts).strip()
    return ""


def is_skippable_user(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    for p in SKIP_USER_PREFIXES:
        if t.startswith(p):
            return True
    for sub in SKIP_USER_SUBSTRINGS:
        if sub in t:
            return True
    # Structural heuristic: an inlined SKILL.md body is heavily marked-down.
    # If the message has 2+ "## " subsection headers anywhere, treat it as
    # an inlined skill body rather than a real user prompt.
    n_headers = t.count("\n## ") + (1 if t.startswith("## ") else 0)
    if n_headers >= 2:
        return True
    return False


def truncate(text: str, n: int = MAX_ASSISTANT_CHARS) -> str:
    if len(text) <= n:
        return text
    return text[:n] + "\n[...truncated...]"


def parse_session(path: Path) -> dict | None:
    """Parse one JSONL file into a session dict with ordered turns."""
    turns_raw = []
    with open(path) as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = rec.get("type")
            if t not in ("user", "assistant"):
                continue
            text = extract_text(rec.get("message", {}).get("content"))
            if not text:
                continue
            turns_raw.append({
                "role": t,
                "ts": rec.get("timestamp", ""),
                "text": text,
            })
    if not turns_raw:
        return None
    # Build (user, assistant_prev, assistant) tuples.
    out_turns = []
    last_assistant = ""
    idx = 0
    for i, r in enumerate(turns_raw):
        if r["role"] != "user":
            if r["role"] == "assistant":
                last_assistant = r["text"]
            continue
        if is_skippable_user(r["text"]):
            continue
        # Find next assistant reply
        next_asst = ""
        for j in range(i + 1, len(turns_raw)):
            if turns_raw[j]["role"] == "assistant":
                next_asst = turns_raw[j]["text"]
                break
        out_turns.append({
            "index": idx,
            "ts": r["ts"],
            "user": r["text"],
            "assistant_prev": truncate(last_assistant),
            "assistant": truncate(next_asst),
        })
        idx += 1
    if not out_turns:
        return None
    return {
        "session_id": path.stem,
        "project": path.parent.name,
        "start_time": out_turns[0]["ts"],
        "turns": out_turns,
    }


def list_project_dirs(project: str) -> list[Path]:
    if not CLAUDE_PROJECTS_DIR.exists():
        return []
    if project == "all":
        return sorted([p for p in CLAUDE_PROJECTS_DIR.iterdir() if p.is_dir()])
    # Substring match against project name (after the leading dashed-path encoding)
    matches = [p for p in CLAUDE_PROJECTS_DIR.iterdir() if p.is_dir() and project in p.name]
    return sorted(matches)


def parse_since(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="claude", choices=["claude"], help="Session source (only 'claude' supported for v0.1).")
    ap.add_argument("--project", default="all", help="Project name substring or 'all'.")
    ap.add_argument("--since", default=None, help="Only include sessions modified after this date (YYYY-MM-DD). Default: 30 days ago.")
    args = ap.parse_args()

    if args.since is None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    else:
        cutoff = parse_since(args.since)

    project_dirs = list_project_dirs(args.project)
    sessions = []
    for pdir in project_dirs:
        for jsonl in sorted(pdir.glob("*.jsonl")):
            mtime = datetime.fromtimestamp(jsonl.stat().st_mtime, tz=timezone.utc)
            if cutoff and mtime < cutoff:
                continue
            try:
                s = parse_session(jsonl)
            except Exception as e:
                print(f"# WARN: failed to parse {jsonl}: {e}", file=sys.stderr)
                continue
            if s:
                sessions.append(s)

    sessions.sort(key=lambda s: s["start_time"])
    out = {
        "source": args.source,
        "since": cutoff.isoformat() if cutoff else None,
        "sessions": sessions,
    }
    print(f"# Extracted {len(sessions)} sessions, "
          f"{sum(len(s['turns']) for s in sessions)} user turns.", file=sys.stderr)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
