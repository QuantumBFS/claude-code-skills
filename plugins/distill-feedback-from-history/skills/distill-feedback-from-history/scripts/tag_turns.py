#!/usr/bin/env python3
"""
tag_turns.py — Phase 2 of extract-skills-from-history.

Read extract_turns.py JSON output (stdin) and tag each user turn against
three deterministic signals:

    - correction         — pushback, redirect, contradiction
    - format-edict       — "use X not Y", "always", "never", explicit notation/style commands
    - error-catch        — points at a concrete mistake with corrective value

The fourth signal — `domain-injection` — requires comparing turn semantics
to prior assistant context and is left for the SKILL.md workflow to detect
via an LLM call.

Turns with zero deterministic tags are kept in output (with empty tags)
so the orchestration layer can still consider them for domain-injection,
but they are flagged `prefilter=False`.

Usage:
    extract_turns.py ... | tag_turns.py > tagged.json
"""
import json
import re
import sys

# Pre-compiled regex per signal. Cheap and deterministic.
#
# Tuning notes:
# - "no" / "stop" / "wait" only count as correction when sentence-initial OR
#   followed by a pronoun, to avoid quantifier "no" ("there are no errors")
#   and imperative "stop" inside benign phrases.
# - format-edicts permit "does not / doesn't / shouldn't" with whitespace.
PATTERNS = {
    "correction": [
        # Sentence-initial refusal/pushback (^ with re.MULTILINE)
        re.compile(r"^(no|nope|don['']?t|stop|wait|hold on)\b[\s,!.\-]", re.I | re.M),
        # "no, that's …" / "no — actually …"
        re.compile(r"\b(no|nope)[,!]\s+(that|this|it|you|i|we)\b", re.I),
        re.compile(r"\b(that['']?s|this is|it['']?s)\s+(wrong|not right|incorrect|backwards|the wrong|not what)\b", re.I),
        re.compile(r"\b(not\s+(like that|that one|what i|what we|the way)|rather than|instead of|other than)\b", re.I),
        re.compile(r"\b(redo|undo|revert|roll back|walk back|throw (it|that) away)\b", re.I),
        re.compile(r"\byou\s+(messed (it|that)? up|got it wrong|misunderstood|missed|misread)\b", re.I),
        re.compile(r"\b(go back to|start over|let['']?s restart)\b", re.I),
    ],
    "format-edict": [
        re.compile(r"\buse\s+[^.\n]{1,40}\bnot\s+[^.\n]{1,40}", re.I),
        re.compile(r"\b(always|never)\s+(use|do|write|prefer|put|include|skip|omit|add)\b", re.I),
        re.compile(r"\b(prefer|preferred)\s+[^.\n]{0,30}\s+over\b", re.I),
        # "(it) does not / doesn't / shouldn't need to be ..." / "just use ..." / "only use ..." / "stick to ..."
        re.compile(r"\b(it\s+)?(does\s*not|doesn['']?t|shouldn['']?t)\s+need\s+to\s+be\b", re.I),
        re.compile(r"\b(just\s+(use|write|do|say)|only\s+use|stick to|stay with)\b", re.I),
        re.compile(r"\b(format|wording|phrasing|tone|voice|style|notation)\b[^.\n]{0,40}\b(should|must|shall|change|be)\b", re.I),
        re.compile(r"\b(preserve|keep|don['']?t change)\s+(my|the|original)\s+(words?|wording|voice|phrasing|prose|text)\b", re.I),
        re.compile(r"\b(rule|convention|from now on|going forward|in future|every time)\b", re.I),
    ],
    "error-catch": [
        re.compile(r"\b(you|claude|the (script|code|model|output))\s+(messed|got it wrong|made (a|an)\s+(mistake|error|bug)|are wrong|is wrong)\b", re.I),
        re.compile(r"\b(should be|is actually|the (correct|real) (value|answer|number) is|isn['']?t (it|that))\b", re.I),
        re.compile(r"\b(double[- ]?check|please verify|that['']?s not (verified|right|correct))\b", re.I),
        re.compile(r"\b(hallucinat|fabricat|made (it|that) up|cannot (verify|confirm)|don['']?t (verify|confirm))\b", re.I),
        re.compile(r"\b(off by|miscalibrated|misconfigur|wrong (count|number|version|file)|missing\s+\w+)\b", re.I),
        re.compile(r"\bactually\b[^.\n]{0,40}\b(is|are|was|were|equals?|should be)\b", re.I),
    ],
}


def tag_turn(text: str) -> dict:
    out = {}
    hits = []
    for signal, regs in PATTERNS.items():
        matched = []
        for r in regs:
            m = r.search(text)
            if m:
                matched.append(m.group(0)[:60])
                break  # one match per signal is enough
        if matched:
            out[signal] = True
            hits.extend(matched)
    out["prefilter"] = bool(hits)
    out["hits"] = hits
    return out


def main():
    data = json.load(sys.stdin)
    n_turns = 0
    n_prefilter = 0
    for s in data.get("sessions", []):
        for t in s.get("turns", []):
            tags = tag_turn(t["user"])
            t["tags"] = tags
            n_turns += 1
            if tags["prefilter"]:
                n_prefilter += 1
    data["stats"] = {
        "total_turns": n_turns,
        "prefilter_positive": n_prefilter,
        "prefilter_rate": round(n_prefilter / max(1, n_turns), 3),
    }
    print(
        f"# Tagged {n_turns} turns, {n_prefilter} passed the heuristic prefilter "
        f"({100 * n_prefilter / max(1, n_turns):.1f}%).",
        file=sys.stderr,
    )
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
