---
name: 퇴근
description: End-of-day routine. Gathers git and registry state, writes the handoff via the handoff skill, checks every touched experiment has a §35 status, proposes 0-3 ADRs and 0-3 [LEARN] lines, runs ruff and the fast pytest suite as evidence, drafts a conventional commit message and asks before committing. Never pushes, never starts or stops GPU jobs, never edits protected files.
disable-model-invocation: true
argument-hint: "[optional note for the handoff]"
allowed-tools: Bash(git status *) Bash(git diff *) Bash(git log *) Bash(git branch *) Bash(git add *) Bash(git commit *) Bash(uv run --no-sync ruff check *) Bash(uv run --no-sync pytest *) Bash(ls *) Bash(cat *) Bash(tail *) Bash(head *) Bash(wc *) Bash(date *) Bash(cp *) Bash(mkdir *) Read Write Edit Grep Glob
---

# /퇴근 (end-day)

Note: `$ARGUMENTS`

## Snapshot

### git status
!`git status --short || true`

### diff stat
!`git diff --stat || true`

### registry tail
!`tail -10 experiments/registry.jsonl || true`

### reports / approvals
!`ls experiments/reports experiments/approvals || true`

## Steps (in order)

1. **State** — from the snapshot: uncommitted files, runs touched today (registry rows with
   today's date), any `status: running` job. A running job must appear in the handoff's
   "In flight" table; do not stop it.
2. **Handoff** — invoke the `handoff` skill. It writes `research/handoffs/<YYYY-MM-DD>.md`
   (≤120 lines) and copies it to `research/handoffs/LATEST.md`. Pass `$ARGUMENTS` as the reason.
3. **§35 status check** — for every experiment_id touched today, confirm a final status exists in
   MLflow/registry (`smoke_ok | success | failed_environment | failed_training | invalid_spec |
   invalid_protocol | security_regression | inconclusive | blocked_by_gate`). A run that crashed
   without a status is listed in the handoff as an open item; never delete or hide failures.
4. **ADR candidates (0–3)** — decisions made today that a future session could undo without
   knowing why (rejected alternatives, protocol choices, baseline changes). For each, invoke
   `recording-adrs`: draft first, write only on approval. Zero candidates is a valid answer.
5. **[LEARN] lines (0–3)** — non-obvious lessons, one line each, format
   `[LEARN:<category>] <headline> — why: <one sentence>`. Present them; the user decides where
   they go (CLAUDE.md is protected, so they are only proposed here, not written).
6. **Evidence** — run and paste the summary lines (apply `verifying-before-completion`):
   ```bash
   uv run --no-sync ruff check .
   uv run --no-sync pytest -m "not slow" -q
   ```
   If either fails, say so plainly and put the failure in the handoff's open items. Do not
   "fix quickly" at end of day unless the user asks.
7. **Commit** — draft a conventional commit message (`feat|fix|docs|exp|chore(scope): summary`,
   body listing the files/experiments; include the attribution lines the session requires).
   Show `git status --short` and the message, then **ask** "commit now?". Only on an explicit yes:
   `git add <listed files>` (never `git add -A` when the tree contains `outputs/`, `mlruns*`,
   `data/`, or `.env`) and `git commit`. Never amend, never `--no-verify`.
8. **Report** — handoff path + line count, ADRs written, tests summary, commit hash or
   "not committed".

## Never (in this command)

- `git push`, `git pull`, rebase, reset, stash, branch switching
- Start, stop, or kill any training / adaptation / GPU job; no `nvidia-smi` process kills
- Edit `CLAUDE.md`, `configs/protocol/**`, `data/manifests/**`, `research/claims/**`,
  existing `research/decisions/ADR-*.md`, `experiments/registry.jsonl`, `.claude/**`
- Upload anything anywhere (no GitHub API, no artifact publish, no MLflow remote)
- Embed raw face frames, sample images, or dataset filesystem paths in the handoff, ADRs, or
  commit message — logical `dataset_id` only (§34)
- Claim a result without run_id / protocol_hash / seed / threshold policy (§30)
