#!/usr/bin/env python3
"""Search and summarize Claude Code JSONL transcripts.

This helper is intentionally dependency-free. It streams JSONL files from
~/.claude/projects and extracts human-scale snippets for session restore and
handoff recovery.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


HANDOFF_RE = re.compile(
    r"handoff|hand\s*off|hands\s*off|next steps?|summary|summarize|blocked|"
    r"todo|resume|restore|continue from|follow[- ]?up|status",
    re.IGNORECASE,
)


@dataclass
class Transcript:
    path: Path
    session_id: str
    root_session_id: str
    project: str
    kind: str
    size: int
    mtime: float


def encoded_project_path(path: str) -> str:
    resolved = str(Path(path).expanduser().resolve())
    return resolved.replace("/.", "--").replace("/", "-")


def candidate_roots(root: Path, project: str | None, all_projects: bool) -> list[Path]:
    if all_projects or not project:
        return [p for p in root.iterdir() if p.is_dir()] if root.exists() else []
    primary = root / encoded_project_path(project)
    if primary.exists():
        return [primary]
    return [primary]


def is_transcript(path: Path) -> bool:
    return path.is_file() and path.suffix == ".jsonl"


def session_id_from_path(path: Path) -> str:
    name = path.name
    if name.endswith(".jsonl"):
        name = name[:-6]
    return name


def transcript_identity(root: Path, path: Path) -> tuple[str, str, str]:
    """Return project, root session id, and transcript kind."""
    try:
        rel = path.relative_to(root)
        parts = rel.parts
    except ValueError:
        parts = path.parts
    project = parts[0] if parts else path.parent.name
    sid = session_id_from_path(path)
    if len(parts) >= 3:
        return project, parts[1], "nested"
    return project, sid, "main"


def find_transcripts(
    root: Path,
    project: str | None,
    all_projects: bool,
    prefix: str | None,
) -> list[Transcript]:
    roots = candidate_roots(root, project, all_projects)
    files: list[Path] = []

    if prefix:
        prefix = prefix.strip()
        maybe_path = Path(prefix).expanduser()
        if maybe_path.exists() and is_transcript(maybe_path):
            files = [maybe_path]
        else:
            clean = prefix[:-6] if prefix.endswith(".jsonl") else prefix
            for base in roots if roots else [root]:
                if not base.exists():
                    continue
                for path in base.rglob("*.jsonl"):
                    sid = session_id_from_path(path)
                    if sid.startswith(clean) or path.name.startswith(clean):
                        files.append(path)
                    elif sid.startswith(f"agent-{clean}") or path.name.startswith(f"agent-{clean}"):
                        files.append(path)
    else:
        for base in roots:
            if base.exists():
                files.extend(base.rglob("*.jsonl"))

    transcripts: list[Transcript] = []
    for path in sorted(set(files), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            stat = path.stat()
        except OSError:
            continue
        project_name, root_sid, kind = transcript_identity(root, path)
        transcripts.append(
            Transcript(
                path=path,
                session_id=session_id_from_path(path),
                root_session_id=root_sid,
                project=project_name,
                kind=kind,
                size=stat.st_size,
                mtime=stat.st_mtime,
            )
        )
    return transcripts


def flatten_text(value: Any, depth: int = 0) -> str:
    if depth > 5 or value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "\n".join(filter(None, (flatten_text(v, depth + 1) for v in value)))
    if isinstance(value, dict):
        parts: list[str] = []
        for key in ("text", "content", "lastPrompt", "command", "stdout", "stderr"):
            if key in value:
                text = flatten_text(value[key], depth + 1)
                if text:
                    parts.append(text)
        if "message" in value:
            text = flatten_text(value["message"], depth + 1)
            if text:
                parts.append(text)
        return "\n".join(parts)
    return ""


def classify(obj: dict[str, Any]) -> str:
    if obj.get("type") in {"user", "assistant", "system"}:
        role = obj.get("message", {}).get("role")
        return role or obj.get("type", "record")
    if obj.get("type") == "last-prompt":
        return "last-prompt"
    if "attachment" in obj:
        attachment = obj.get("attachment") or {}
        return f"attachment:{attachment.get('type', 'unknown')}"
    return str(obj.get("type") or "record")


def should_skip(obj: dict[str, Any], show_meta: bool) -> bool:
    if show_meta:
        return False
    typ = str(obj.get("type") or "")
    if typ in {"mode", "permission-mode", "file-history-snapshot"}:
        return True
    attachment = obj.get("attachment") or {}
    atype = str(attachment.get("type") or "")
    if atype.startswith("hook_") or atype in {
        "skill_listing",
        "deferred_tools_delta",
        "mcp_instructions_delta",
    }:
        return True
    return bool(obj.get("isMeta") and typ != "last-prompt")


def iter_records(path: Path, show_meta: bool) -> Iterable[tuple[int, dict[str, Any], str]]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict) or should_skip(obj, show_meta):
                continue
            text = flatten_text(obj)
            yield line_no, obj, text


def clip(text: str, limit: int) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    if len(text) <= limit:
        return text
    return text[: limit - 20].rstrip() + "\n... [truncated]"


def transcript_matches(
    transcript: Transcript,
    queries: list[str],
    handoff: bool,
    limit: int,
    snippet_chars: int,
    show_meta: bool,
) -> list[dict[str, Any]]:
    compiled = [re.compile(re.escape(q), re.IGNORECASE) for q in queries]
    matches: list[dict[str, Any]] = []
    keep_recent: list[dict[str, Any]] = []

    for line_no, obj, text in iter_records(transcript.path, show_meta):
        if not text:
            continue
        role = classify(obj)
        timestamp = obj.get("timestamp") or obj.get("snapshot", {}).get("timestamp") or ""
        entry = {
            "line": line_no,
            "timestamp": timestamp,
            "role": role,
            "text": clip(text, snippet_chars),
        }

        hit = False
        if compiled and any(pattern.search(text) for pattern in compiled):
            hit = True
        if handoff and HANDOFF_RE.search(text):
            hit = True

        if hit:
            matches.append(entry)
            if len(matches) >= limit:
                break
        elif not compiled and not handoff and role in {"user", "assistant", "last-prompt"}:
            keep_recent.append(entry)
            keep_recent = keep_recent[-limit:]

    return matches if (compiled or handoff) else keep_recent


def print_recent(transcripts: list[Transcript], limit: int) -> None:
    for transcript in transcripts[:limit]:
        mtime = int(transcript.mtime)
        root = f"\troot={transcript.root_session_id}" if transcript.kind != "main" else ""
        print(
            f"{transcript.session_id}\t{transcript.kind}{root}\t"
            f"{transcript.size} bytes\tmtime={mtime}\t{transcript.path}"
        )


def resume_command(transcript: Transcript) -> str:
    if transcript.kind == "main":
        return f"claude --resume {transcript.session_id}"
    return f"claude --resume {transcript.root_session_id}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prefix", nargs="?", help="Claude session UUID/hash prefix or transcript path")
    parser.add_argument("--project", default=os.getcwd(), help="Project path to prioritize")
    parser.add_argument("--root", default="~/.claude/projects", help="Claude projects root")
    parser.add_argument("--all-projects", action="store_true", help="Search all Claude projects")
    parser.add_argument("-q", "--query", action="append", default=[], help="Text to search for")
    parser.add_argument("--handoff", action="store_true", help="Search for handoff/summary/next-step-like snippets")
    parser.add_argument("--limit", type=int, default=12, help="Maximum sessions/snippets to print")
    parser.add_argument("--snippet-chars", type=int, default=1600, help="Maximum characters per snippet")
    parser.add_argument("--show-meta", action="store_true", help="Include hook/meta/tool records")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON")
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser()
    transcripts = find_transcripts(root, args.project, args.all_projects, args.prefix)
    if not transcripts:
        print("No Claude transcripts matched.", file=sys.stderr)
        return 1

    if not args.prefix and not args.query and not args.handoff:
        print_recent(transcripts, args.limit)
        return 0

    output: list[dict[str, Any]] = []
    for transcript in transcripts:
        snippets = transcript_matches(
            transcript,
            args.query,
            args.handoff,
            args.limit,
            args.snippet_chars,
            args.show_meta,
        )
        if snippets:
            output.append(
                {
                    "session_id": transcript.session_id,
                    "root_session_id": transcript.root_session_id,
                    "project": transcript.project,
                    "kind": transcript.kind,
                    "path": str(transcript.path),
                    "size": transcript.size,
                    "mtime": transcript.mtime,
                    "resume": resume_command(transcript),
                    "snippets": snippets,
                }
            )
        if len(output) >= args.limit:
            break

    if args.as_json:
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0

    if not output:
        print("No matching snippets found.", file=sys.stderr)
        return 1

    for item in output:
        print("=" * 80)
        print(f"session: {item['session_id']}")
        if item["kind"] != "main":
            print(f"root session: {item['root_session_id']}")
            print(f"kind: {item['kind']}")
        print(f"project: {item['project']}")
        print(f"path: {item['path']}")
        print(f"resume: {item['resume']}")
        for snippet in item["snippets"]:
            label = snippet["role"]
            ts = f" {snippet['timestamp']}" if snippet["timestamp"] else ""
            print("-" * 80)
            print(f"line {snippet['line']} [{label}]{ts}")
            print(snippet["text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
