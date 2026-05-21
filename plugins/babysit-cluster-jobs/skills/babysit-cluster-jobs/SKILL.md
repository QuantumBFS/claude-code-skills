---
name: babysit-cluster-jobs
description: Use when the user wants a live, auto-refreshing figure of cluster-job state pinned to their screen. Triggers on phrases like "babysit my X plot", "watch X live", "live view of <script>", "keep refreshing <figure>", "babysit scripts/foo.py", "open babysit". Also triggers on stop phrases: "stop babysit", "stop watching", "close the live view". This skill runs a project-owned plotter on the cluster on a recurring schedule, fetches the rendered PNG back to the local machine, and opens it. The plot updates in place as new data arrives on the cluster. Do NOT trigger for one-off plot generation ("run scripts/foo.py once"), status-only queries ("is job 12345 running?"), job submission, or analysis of a finished run — those are normal work.
user_invocable: true
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
---

# Babysit Cluster Jobs — Live Figure Mode

## What this skill does

Periodically:

1. Runs a **project-owned plotter** on the cluster (`python <project>/<plotter>`)
2. Fetches the produced PNG back to the local machine (base64 over the cluster MCP)
3. `open`s the PNG on macOS so Preview auto-refreshes when the file is overwritten

That's it. No state file, no lifecycle, no archival, no per-job tracking. The
figure on screen IS the babysit output. The plotter decides what's interesting.

## Trigger discipline

**Trigger on:**
- "babysit <path/to/plotter>" / "babysit my X plot" / "watch X live"
- "live view of <script>" / "keep refreshing <figure>" / "open babysit"
- Stop phrases: "stop babysit" / "stop watching" / "close the live view"

**Don't trigger on:**
- "run scripts/foo.py" (one-off, no recurrence)
- "is job 12345 running?" (status query — answer directly)
- "submit this sbatch" / sbatch help — not babysitting
- "what was the result of job 19620?" — finished-run analysis

## Required context — record on the cluster, never re-prompt

What's being babysat lives **on the cluster**, in a tiny config file at
`<cluster_project>/runs/babysit.json`. The skill reads it on every invocation
on any machine — there is no per-machine setup question to answer twice.

Schema:

```json
{
  "plotter":          "scripts/plot_nct_T001_vs_ed.py",
  "output_png":       "runs/nct_n4m3/FES_vs_step_T001.png",
  "interval_seconds": 300,
  "started_at":       "2026-05-21T15:33:00",
  "started_on_host":  "macbook-air.local"
}
```

On the **first** invocation in a project, the file won't exist. Ask the user
once for the plotter and output paths (try to infer: if the user said "babysit
my <X> plot" and there's exactly one plausible `<project>/scripts/plot_*.py`
matching `<X>`, use it without asking), then write `babysit.json` on the
cluster. Every later invocation — same machine, different machine, weeks later
— reads that file and resumes with zero questions.

You still need to know **which** cluster project the user means. The local
working directory plus the user's known cluster-path mapping (in `~/.claude`
memory) resolves this; if the mapping is missing, ask once and save it to
memory as a `reference` entry. This is a per-user fact, not a per-project one,
so it's correctly machine-local.

Default refresh interval: **300 seconds**. User can override ("every 2 min").

## Refresh cycle (one tick)

```
1. Run plotter on cluster:
     cluster_exec:
       export PATH=/opt/data/hpc/common/softwares/anaconda3/bin:$PATH
       cd <cluster_project>
       python <plotter>

2. Encode PNG over the wire:
     cluster_exec: base64 -w0 <cluster_project>/<output_png>
     # Result is large; the harness saves it to a tool-result file.
     # Parse the b64 from that file with the Bash tool.

3. Decode + write local mirror:
     local path = <local_project>/<output_png>     # same relative path
     mkdir -p its parent, write the decoded bytes

4. Open (first tick only):
     /usr/bin/open <local_path>            # macOS — Preview auto-refreshes
     xdg-open <local_path>                 # linux

5. Schedule next tick:
     ScheduleWakeup(
       delaySeconds = <interval>,
       prompt       = the same "babysit ..." input,
       reason       = "live figure refresh"
     )
```

Subsequent ticks: skip step 4. Preview reloads in place when the file changes.

## Cross-machine transferability

This is the whole point of how the pieces are split:

| Piece | Location | How it survives a machine switch |
|---|---|---|
| **Skill prose** (this file) | QuantumBFS plugin git repo | `git pull` on the new machine |
| **Plotter** (`scripts/plot_*.py`) | Project repo's clone **on the cluster** | Already there — runs server-side, no local Python env needed |
| **Source data** (`runs/.../data.txt`) | Cluster filesystem | Authoritative copy; never edited locally |
| **What's being babysat** (plotter, output_png, interval) | Cluster (`<project>/runs/babysit.json`) | Read fresh on every invocation; nothing to re-type after a machine switch |
| **PNG** | Local `<project>/<output_png>` | Regenerated each tick from cluster state — no sync |
| **The recurring loop itself** | `CronCreate` (this Claude Code session) or `ScheduleWakeup` (in /loop dynamic mode) | Dies when the session ends. On a new machine, user says "babysit" and the skill reads `babysit.json` and re-arms the cron — same recipe, no re-config |

The deliberate split: **the only thing a new machine needs is `git pull` of the
QuantumBFS plugin and `git pull` of the project (so the local PNG mirror has a
parent dir to land in)**. Everything else — including what's being babysat —
is pulled from cluster state on demand.

## Stop

When the user says "stop babysit" / "stop watching":
1. Do NOT schedule another wakeup.
2. Report: "live view stopped; last PNG left at `<local_path>`."
3. The Preview window stays open with the last refresh; user closes it themselves.

## Anti-patterns

| Don't | Do |
|---|---|
| Sync `data.txt` files from cluster to local before plotting | Run the plotter ON the cluster; only the PNG crosses the wire |
| Ship a generic dashboard renderer with the skill | The plotter is the project's responsibility — each project knows what's interesting |
| Save a giant tracking-state file (BABYSIT.md, job lifecycle) | This skill is the figure-on-screen, nothing else. If the user wants per-job tracking, that's not this skill anymore |
| Re-open the PNG every tick (will pop a new window) | `open` once on first tick; later ticks just overwrite the file and Preview reloads |
| Poll faster than the plotter's own update cadence | Default 300s. The user's jobs typically log ~once per minute; a faster refresh just wastes cluster CPU on identical figures |
| Schedule a wakeup after a "stop" | "Stop" means the loop ends |

## Red flags — STOP

- About to write a Python plotter inside the skill → no; the plotter is the project's, on the cluster
- About to fetch `data.txt` files individually → no; run the plotter on the cluster
- About to put `BABYSIT.md` back → no; this skill is intentionally stateless
- About to schedule a wakeup faster than ~60s → check with the user; cluster CPU isn't free
- About to do anything other than (run plotter → fetch PNG → open → reschedule) → stop and re-read this skill
