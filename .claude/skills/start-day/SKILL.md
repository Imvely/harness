---
name: 출근
description: Morning start-of-day routine. Runs the contract §36 checklist read-only (git state, latest handoff, registry, specs awaiting approval, configs, decisions, GPU), lists in-flight and failed runs, proposes today's top-3 tasks classified Research/Code/Experiment/Analysis (§37), and asks which to start. Launches nothing, edits nothing.
disable-model-invocation: true
argument-hint: "[optional focus, e.g. 'RQ2' or 'exp_syn_e03']"
allowed-tools: Bash(git status *) Bash(git log *) Bash(git diff *) Bash(git branch *) Bash(ls *) Bash(cat *) Bash(tail *) Bash(head *) Bash(wc *) Bash(nvidia-smi *) Bash(uv run --no-sync python scripts/validate_spec.py *) Read Grep Glob
---

# /출근 (start-day)

Focus hint: `$ARGUMENTS`

## Snapshot (collected before you read this)

### git status
!`git status --short || true`

### recent commits
!`git log --oneline -10 || true`

### latest handoff
!`cat research/handoffs/LATEST.md || true`

### specs / approvals
!`ls experiments/specs experiments/approvals || true`

### registry tail
!`tail -5 experiments/registry.jsonl || true`

### experiment configs
!`ls configs/exp || true`

### latest decisions
!`ls research/decisions | tail -5 || true`

### GPU
!`nvidia-smi --query-gpu=name,memory.used --format=csv || true`

## Steps

1. **§36 checklist** — confirm, from the snapshot plus `Read`/`Grep` only:
   CLAUDE.md read this session · git status · repository tree · `research/decisions` ·
   experiment registry · relevant configs. Say explicitly if anything is missing
   (e.g. no handoff, empty registry, dirty tree with uncommitted files).
2. **Runs** — from the registry tail (and `Read` more rows if needed) list:
   - in-flight (`status: running`) with experiment_id / run_id / started time
   - failed (`failed_environment`, `failed_training`, `invalid_spec`, `invalid_protocol`,
     `blocked_by_gate`) — these are information, not noise (§35)
   - `security_regression` / `inconclusive` results not yet reviewed (`experiments/reports/`)
3. **Specs awaiting approval** — `configs/exp/*.yaml` with `mode: full` whose approval token
   (`experiments/approvals/<exp_id>.<science12>.json`) is absent. You may run
   `uv run --no-sync python scripts/validate_spec.py --exp <name> --json` (read-only) to report
   `protocol_hash`, `science_hash`, `approval_token_ok`.
4. **Diff against the handoff** — compare "Next 1–3 actions" in LATEST.md with what git and
   the registry show actually happened.
5. **Propose today's top-3**, each classified per §37 and with the flow it follows:
   - `Research` → primary paper search → verify → review → claims → link to RQ
   - `Code` → read module → call path → config deps → tests → minimal change
   - `Experiment` → spec → validation → smoke → full-run flag → MLflow → evaluation → reviewer
   - `Analysis` → report / review-run / ADR / handoff
   Order by: unblocking others > §11 ladder position (baselines before methods) > cheapness.
6. **Ask** which one to start. Stop there.

## Never (in this command)

- Launch `scripts/train.py` / `scripts/adapt.py`, any GPU job, or a sweep
- Edit or create any file (no configs, no specs, no handoff, no ADR)
- `git pull`, `git fetch`, `git checkout`, `git stash`, or any write to git
- Touch `data/` (no `ls -R data/raw`, no sample opening), print dataset paths or frames
- Create approval tokens or write to `experiments/approvals/`
