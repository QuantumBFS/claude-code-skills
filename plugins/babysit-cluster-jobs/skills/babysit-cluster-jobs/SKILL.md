---
name: babysit-cluster-jobs
description: Use when the user hands over ongoing tracking of running cluster jobs OR asks about the collective status of their tracked jobs. Triggers on phrases like "babysit job <id> for me", "babysit my jobs", "keep watching these", "track these across sessions", "wake me up when X", AND on plural-status queries like "what's happening to my jobs", "any update on my jobs", "how are my tracked jobs doing", "give me a babysit report". Also triggers on un-babysit phrases: "stop babysitting X", "drop X from babysit", "un-babysit X". This skill maintains a tracking file (BABYSIT.md) on the remote cluster's project directory so the same monitoring state survives across sessions, machines, and conversation resets. Do NOT trigger for one-off specific-job status checks ("is 19629 running?"), `tail` requests, job submission, or single-job post-completion analysis — those are normal work.
user_invocable: true
allowed-tools:
  - Bash
  - Edit
  - Write
  - Read
---

# Babysit Cluster Jobs

## Trigger discipline

**Trigger on (any of):**
- Babysit handoff: "babysit job <id> for me" / "babysit my jobs" / "keep watching these" / "track these across sessions" / "wake me up when …"
- Plural-status query: "what's happening to my jobs" / "any update on my jobs" / "how are my [babysat|tracked] jobs" / "babysit report"
- Un-babysit: "stop babysitting X" / "drop X from babysit" / "un-babysit X"

**Don't trigger on:**
- Specific-job one-offs: "is 19629 running?", "tail the log for X" → just answer directly
- Submission help / sbatch questions → not babysitting
- Single-job retrospective: "what was the result of job 19620 last week?" → if not in BABYSIT.md, just answer; if it is, mention but don't run full sweep

## Core idea

The chat is ephemeral. The cluster filesystem isn't. Persist motivation + watch criteria + decision rules to a single markdown file on the cluster (`<project>/runs/BABYSIT.md`). On the next invocation — same conversation, next morning, different machine — read that file first; everything needed to resume is in it.

## The state file

**Path:** `<cluster project>/runs/BABYSIT.md`.
If the project's cluster path isn't known yet, ask the user once and save it to memory so future invocations don't need to ask again.

Read–modify–write each invocation. The file is the source of truth; the chat is scratch.

## Workflow each time the skill fires

1. **Read** `BABYSIT.md` (create with empty header if missing).
2. **Determine intent** from the user's phrasing:
   - Adding a new job → go to step 3a
   - Status query on tracked jobs → go to step 3b
   - Un-babysit a job → go to step 3c
   3a. **Add new job**: ask for motivation + watch-criteria + decision rule, append an ACTIVE section (don't accept "just monitor it" — push for specifics).
   3b. **Status sweep** for every ACTIVE-status job:
   - `squeue -j <id>` — state, used/limit time
   - `tail` of `.out` and `.err` — latest metric line + any new stderr
   - Compare against the entry's "Watch for" criteria
   - If a job is no longer in `squeue` → change its status to `ACTIVE-ENDED`, flag to user as "needs verdict"
   3c. **Un-babysit**: confirm once with the user, then move the entry to ARCHIVED with `status: DROPPED, reason: "<one-liner>"`. Do NOT delete the entry — the archive line is the audit trail.
4. **Reconcile** any other discrepancies:
   - Job in `squeue -u $USER` but not in `BABYSIT.md` → mention to the user, ask if they want to start tracking it (don't add silently)
   - Job in `ACTIVE-ENDED` for >1 session → re-prompt for verdict
5. **Append** a dated one-line update to each ACTIVE section processed this turn.
6. **Report** to the user using the per-job block format below (see "Report format"). Brief summary of any archived changes goes after the per-job blocks.
7. **Write back** `BABYSIT.md` (update `Last updated` header + hostname).

## Report format

For each ACTIVE / ACTIVE-ENDED job touched this turn, render a key-value block, jobs separated by a horizontal rule:

```
Job:         <jobid> <short-name>
Description: <ONE sentence summarizing content + goal — distilled from the entry's Motivation field>
Latest:      <current step / metric / phase, in one line>
Verdict vs watch criteria:  ✓ healthy / ⚠ flag-worthy: <reason> / ⛔ failing: <reason> / ⏳ awaiting verdict
────────────────────────────────────────
```

Rules for the Description line:
- One sentence, ≤ 25 words. Distilled from the entry's `**Motivation:**` field — say what the job is doing AND what question it answers.
- Stable across reports (don't paraphrase differently each turn). If the Motivation changes mid-run, update the entry first, then mirror.
- Examples:
  - ✓ "VMC refinement of gnn_small KL ckpt against full disk-jellium H to test whether VMC descent matches the canonical phys-flow reference."
  - ✗ "Running VMC." (too vague — doesn't say the goal)
  - ✗ "Phase 2 of the 3-architecture comparison investigating whether the increased fidelity from the GNN with three-body channel translates to lower variational energy on the bare Coulomb interaction." (too long)

For ACTIVE-ENDED jobs, set `Latest:` to "ENDED at <date>, awaiting verdict" and `Verdict:` to `⏳ awaiting verdict`.

After all per-job blocks: a brief summary line of archived/state-changed jobs this turn (e.g. "Archived: 19638 → COMPLETED-failure. New: 19641 added to ACTIVE.").

## BABYSIT.md template

```markdown
# Babysit log — <project>

_Last updated: <ISO timestamp> from <hostname>_

## ACTIVE

### <jobid> — <short name>  [status: ACTIVE | ACTIVE-ENDED]
- **Motivation:** <why this is running, user's words>
- **Watch for:** <signals — thresholds, failure modes, what's interesting>
- **Expected end:** <wallclock estimate or "step N of M">
- **Outputs:** <key file path to inspect on completion>
- **Decision rule:** <what to do if X / if Y>
- **Updates:**
  - <YYYY-MM-DD HH:MM>: <one-line observation>

## ARCHIVED (last 30 days, newest first)

- <jobid> <name> — **DROPPED**, reason: "<one-liner>" (archived <date>)
- <jobid> <name> — **COMPLETED-success**: <key result> (ended <date>)
- <jobid> <name> — **COMPLETED-failure**: <how it failed> (ended <date>)
- <jobid> <name> — **COMPLETED-partial**: <what worked / didn't> (ended <date>)
```

**Lifecycle states:**

```
ACTIVE (still in squeue)
   │
   ├──► ACTIVE-ENDED (not in squeue, awaiting verdict)
   │        │
   │        └──► ARCHIVED { COMPLETED-{success|failure|partial} }
   │
   └──► ARCHIVED { DROPPED, reason: "..." }   ← user said "stop babysitting"
```

## When adding a new job, require from the user

Don't accept "just monitor it" — push for specifics:
- **Motivation:** the WHY in their words
- **Watch for:** what would they want to know first thing tomorrow?
- **Decision rule:** what to do if it crashes / what to do if a metric blows up

If they genuinely don't have a criterion: write "no specific watch — confirm it doesn't crash and report final result." That's still a valid criterion; don't leave the field blank.

## When a tracked job ends naturally

Don't auto-archive. On next babysit check, the job's status flips to `ACTIVE-ENDED` and the report flags "<jobid> needs verdict". Pull the final result line, ask the user:
1. Does the outcome match the hypothesis?
2. What's the verdict (one line)?
3. Archive as COMPLETED-{success|failure|partial}, or keep in ACTIVE-ENDED for further analysis?

Move from ACTIVE-ENDED → ARCHIVED only on confirmation.

## When the user says "un-babysit" / "stop babysitting X"

1. Confirm once: "Confirm: drop <jobid> <name> from active tracking? Reason?"
2. On confirmation, move the entry to ARCHIVED with `status: DROPPED, reason: "<user's words>"`
3. The job may still be running on the cluster — un-babysit only stops *tracking*, it does NOT cancel the slurm job. If the user wants to cancel, that's a separate `scancel`.
4. If reason isn't given, accept a generic one but record it: e.g., "no longer of interest".

## Cross-session recovery

When invoked cold (next morning / different machine):
1. Read `BABYSIT.md` from cluster.
2. `squeue -u $USER` — diff against the ACTIVE list.
3. Report:
   - **Still running, tracked:** <list, one-line latest>
   - **Tracked but ended:** <list — needs verdict>
   - **Running but untracked:** <list — should I track?>
4. Let the user direct from there.

## Anti-patterns

| Don't | Do |
|---|---|
| Trigger on "is job X running?" | Just answer; don't run full babysit sweep |
| Infer motivation from script comments | Ask the user explicitly the first time |
| Auto-archive ended jobs | Move to ACTIVE-ENDED, ask for verdict |
| Delete an entry on un-babysit | Move to ARCHIVED with `DROPPED` status + reason |
| Store state on this laptop | Always cluster-side at `<project>/runs/BABYSIT.md` |
| Poll repeatedly inside one turn | Read once, check once, write back, stop |
| Add a job to ACTIVE without watch criteria | Push for specifics or write "no specific watch" |
| Confuse un-babysit with `scancel` | Un-babysit only stops tracking; the slurm job keeps running unless separately cancelled |

## Red flags — STOP

- About to call `squeue` before reading `BABYSIT.md` → read it first
- About to claim a status without an entry in `BABYSIT.md` for that job → either decline (one-off check) or ask user to add it
- `BABYSIT.md` `Last updated` > 24 h old with jobs still in ACTIVE → reconcile against `squeue` before reporting
- About to write a metric into chat that isn't in `BABYSIT.md` → put it in the job's `Updates` line first
