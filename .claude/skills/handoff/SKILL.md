---
name: handoff
description: Writes a compact session handoff (≤120 lines) to research/handoffs/YYYY-MM-DD.md and copies it to research/handoffs/LATEST.md so the next session can resume in under a minute, with sections Goal, Where we are, What we tried, Decisions, Evidence (real run_ids and protocol_hash), Open questions, Next 1-3 actions and Quick-start commands. Use at end of day, before a long break, before context compaction, when the user says "handoff", "인수인계", "save state", or when /end-day calls it.
argument-hint: "[optional reason, e.g. 'end of day', 'context low']"
allowed-tools: Bash(git status *) Bash(git log *) Bash(git diff *) Bash(git branch *) Bash(ls *) Bash(cat *) Bash(tail *) Bash(head *) Bash(date *) Bash(cp *) Bash(mkdir *) Read Write Grep Glob
metadata:
  origin: https://github.com/REMvisual/claude-handoff/tree/c407845e4c571f355b48901828f9cb0ad82272ec
  origin_secondary: https://github.com/pedrohcgs/claude-code-my-workflow/tree/9d371f0bf8a8bc99569feca3210ef5133af28d33/.claude/skills/checkpoint
  license: MIT
  commit: c407845e4c571f355b48901828f9cb0ad82272ec
  commit_secondary: 9d371f0bf8a8bc99569feca3210ef5133af28d33
---

# Session Handoff

Produce the file the next session (you, a collaborator, or a fresh-context reboot) reads first.
The conversation is ground truth; git and MLflow are the cross-check. `/handoff` alone is
sufficient — the user need not provide anything. Reason hint: `$ARGUMENTS`.

**Guards**
- Not in plan mode (this skill writes files).
- Never produce a freeform "summary" instead of this file: freeform summaries lose failed
  approaches and evidence, which are the most expensive things to rediscover.
- Only write when the user asked for a handoff now, or `/end-day` invoked this skill.

## Step 1 — Gather state (cheap parallel Bash, never subagents)

Run in one message:

| Commands | Returns |
|---|---|
| `git branch --show-current`, `git log --oneline -15`, `git status --short`, `git diff --stat` | branch, commits this session, uncommitted files |
| `tail -20 experiments/registry.jsonl` (if present) | recent runs: experiment_id, run_id, status, science_hash |
| `ls experiments/specs experiments/approvals experiments/reports configs/exp` | specs frozen, approvals pending, reports written |
| `ls research/hypotheses research/decisions`, `cat research/handoffs/LATEST.md` (if present) | prior handoff to diff against |

If a read fails, write `(none on disk)` — never fabricate.

**In-flight work is mandatory to capture.** Any run, sweep, or background job this session
started and did not wait for gets a row: what is running, where artifacts land, the command that
checks on it, and what verdict ends it. A handoff that omits a running job orphans it.

## Step 2 — Mine the conversation

Extraction checklist (apply to the whole conversation, not the last hour):

- [ ] Goal and which RQ / hypothesis it serves
- [ ] Every file changed and why; tests added
- [ ] Every approach tried, **chronologically, including failures and why they failed**
- [ ] Decisions made and alternatives rejected (with the reason)
- [ ] Real numbers: run_ids, status, protocol_id + protocol_hash, per-attack APCER, BPCER, AUC,
      seeds, threshold rule; gate verdicts
- [ ] User corrections and preferences voiced this session
- [ ] Open questions, blockers, risks
- [ ] The single most important next action

If you are skimming, stop and re-read. Details are the value.

## Step 3 — Write `research/handoffs/YYYY-MM-DD.md`

Date from `date +%F`. If the file already exists today, overwrite it (one handoff per day; the
previous content is already in git history if it was committed). Hard limit **120 lines**:
prefer tables and numbers over prose; drop adjectives before dropping evidence.

```markdown
# Handoff — YYYY-MM-DD — <one-line summary>

- Status: IN PROGRESS | BLOCKED | COMPLETED
- Branch: <branch>    Uncommitted: <n files>
- Prior handoff: research/handoffs/<prev>.md | none

## Goal
<2–4 sentences: objective, RQ/hypothesis id, why it matters>

## Where we are
<5–12 bullets: files/functions changed, tests count, what works / what does not>

## What we tried (chronological, incl. failures)
| # | Hypothesis / change | Result (numbers) | Outcome / why |
|---|---|---|---|

## Decisions
- Chosen: … — why
- Rejected: … — why (→ ADR-NNN if recorded)

## Evidence
| experiment_id | run_id | status | protocol_id / hash[:12] | seed | key metrics (per-PAI APCER, BPCER, AUC) |
|---|---|---|---|---|---|
<plus paths to regression_check.json / per_attack.csv / reports>

## In flight
| What is running | Artifacts land in | Check with | Ends when |
|---|---|---|---|
<or "(none)">

## User feedback & preferences
<direct corrections and preferences voiced this session; never omit>

## Open questions
- Q1 …

## Next 1–3 actions
1. <imperative, concrete>
2. …

## Quick-start
```bash
cat research/handoffs/LATEST.md
git status --short && git log --oneline -5
uv run --no-sync pytest -m "not slow" -q
<the exact command for action 1, e.g. uv run --no-sync python scripts/validate_spec.py --exp <name> --json>
```
```

## Step 4 — Copy to LATEST and validate

```bash
cp research/handoffs/YYYY-MM-DD.md research/handoffs/LATEST.md
```

Self-check before reporting (fix, do not skip):

- [ ] ≤120 lines (`wc -l`)
- [ ] "What we tried" has one row per distinct approach, failures included
- [ ] "Evidence" has real run_ids and protocol_hash, not "improved"
- [ ] "In flight" section present (even if "(none)")
- [ ] "Next 1–3 actions" starts with a concrete command, not "continue working"
- [ ] No dataset filesystem paths, no raw face frames, no sample images — logical
      `dataset_id` only (contract §34)
- [ ] No unverified claim stated as fact (§8, §30)

## Step 5 — Report

Tell the user: file path, line count, status, the next action. Do **not** commit here
(`/end-day` handles the commit question). Do not `git push`.
