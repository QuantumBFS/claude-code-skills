---
name: paper-review-checklist
description: Use when the user asks to review a research-paper draft (typically LaTeX). Walks a fixed checklist of common issues — notation, figures, citations, structure, equations, style, reproducibility — and inserts inline author-comment reminders at locations that fail each check. Triggers on phrases like "review my paper", "check my draft", "apply the checklist".
---

# Paper Review Checklist

Use this skill when reviewing a research-paper draft. The goal is to walk the checklist below, examine the draft systematically, and **insert inline author-comment macros at the relevant locations in the .tex source** so the author sees the feedback in context.

The default comment macro is whatever the project's preamble defines for author notes — e.g. `\lw{...}`, `\todo{...}`, or a custom command. Check the preamble first; if no such macro exists, fall back to `\todo{...}` (the `todonotes` package). Examples in this skill use `\lw{...}`.

## Workflow

1. **Read the entire .tex file first.** Do not start commenting until you have read every section, including appendices. Context matters; many checklist items (e.g. notation consistency) cannot be judged from a single line.
2. **Run programmatic checks** before subjective ones — they are fast and unambiguous (see "Programmatic checks" below).
3. **Walk the checklist** category by category. For each item, scan the relevant parts of the draft.
4. **Insert `\lw{<brief reminder>}` comments** inline at the exact spot of the issue. Keep each comment short (≤ 20 words). Do not rewrite prose — the author decides how to fix.
5. **End with a summary** (≤ 200 words) listing categories with the most issues and the three most impactful single comments.

## Programmatic checks

Run these before subjective review:

- **Unresolved `\ref` / `\cite`**: compile if possible (`latexmk -pdf <file>` or `pdflatex`), then `grep -E "Reference .* undefined|Citation .* undefined" <file>.log`. Flag each undefined target.
- **Unreferenced equation labels**: extract `\label{eq:...}` and check that each appears in a `\ref{...}` or `\eqref{...}` elsewhere. Numbering equations that are never referenced is item 15.
- **Symbol-consistency spot checks**: for any suspected synonym pair (e.g. `\avg{s}` vs `\avg{\sign}`), run `grep -c` on both and flag if both are nonzero.
- **Stale TODOs**: `grep -n "\\lw{\\|\\todo{\\|TODO\\|FIXME" <file>` to surface any pending author notes (don't remove existing ones, but list them in the summary).
- **One-use acronyms**: `grep -oE '\b[A-Z]{2,}\b' <file> | sort | uniq -c | sort -n` and flag any acronym with count = 1. If an acronym appears only once, spell it out instead.

## Checklist

### A. Notation & symbols
1. Every symbol is defined at its first occurrence.
2. One symbol = one meaning throughout. No two symbols denote the same quantity (e.g., `\avg{s}` vs. `\avg{\sign}`).
3. No symbol clashes with field conventions (e.g., `\tau` is imaginary time in QMC — don't repurpose it).
4. Notation is introduced upfront and never silently redefined.

### B. Figures & tables
5. Every figure has axes labels with units (or "dimensionless" if so), a legend, and panel labels (a), (b), (c) where applicable.
6. Caption is self-contained: a reader who only sees the figure understands it without the main text.
7. Line widths ≥ 2, fonts ≥ 2/3 of body text, color choices projector- and greyscale-friendly.
8. Parameters used in each figure are stated explicitly inside the figure or its caption.

### C. Citations & literature
9. Every citation has been verified — author, year, journal, DOI — no hallucinated references.
10. Every numerical claim attributed to others has a verifiable source.
11. Cite the original work, not just a review, when stating a specific result.
12. Acknowledge contemporary or closely related work; do not claim novelty without verifying.

### D. Introduction
13. Introduction places the work in context: prior approaches, the gap, this work's contribution.

### E. Structure
14. Each section opens with a one-sentence statement of what it does.

### F. Equations
15. Only equations that are later referenced are numbered.
16. Every symbol in an equation is defined immediately before or after.
17. Equations are embedded in sentence grammar, not isolated as standalone objects.
18. All cross-references (`\ref`, `\cite`) point to existing, correctly labeled targets.

### G. Writing style
19. Sentences over ~40 words are split.
20. Avoid passive voice when first person ("we find", "we observe") works.
21. Use consistent terminology — don't switch between synonyms for the same concept.
22. No acronym is used only once. If a term appears once, spell it out; if many times, define on first use.

### H. Reproducibility
23. Source code link and key hyperparameters are stated.

## What NOT to flag

Reserve `\lw{...}` comments for items that genuinely fall short on the checklist. Do NOT insert comments for:

- Personal stylistic preferences not on the checklist.
- Single-word phrasing that could be improved but is acceptable.
- Equation typography you would write differently but is correct as is.
- Issues the author is already flagging in an existing `\lw{...}` or `\todo{...}` note.
- Every instance of a recurring issue — insert at the first occurrence and add one global note at the top.

When in doubt, do not flag. A draft with 50 review comments is harder to act on than one with 10 well-chosen ones.

## Comment format examples

```
\lw{define $\rho$ at first use}
\lw{$\avg{s}$ and $\avg{\sign}$ used interchangeably --- pick one}
\lw{verify Smith2019 --- author/year/DOI}
\lw{caption should state $\beta$ and lattice used}
\lw{section opening --- one-sentence statement of scope}
\lw{split this sentence (>40 words)}
\lw{equation never referenced --- remove number}
\lw{\ref{fig:foo} --- does this label exist?}
```

## Summary format

End the review with a short report:

```
Reviewed: <path>
Comments inserted: <N>

By category:
  A. Notation:       <count>
  B. Figures:        <count>
  ...

Top 3 issues (most impactful):
  1. <one-line description, with line number>
  2. ...
  3. ...

Pre-existing TODOs untouched: <N>  (lines: ...)
```
