---
name: verifying-before-completion
description: Requires fresh verification evidence before any claim that work is complete, fixed, passing, or that an experiment worked. Runs ruff, pyright and pytest and reads their output; for experiments cites MLflow run_id, status, per-attack APCER table and protocol_hash. Use before committing, before reporting results, before a handoff, and before any wording that implies success.
metadata:
  origin: https://github.com/obra/superpowers/tree/b36e0829c6d0140e93cfef2ca599b1b07d4a7797/skills/verification-before-completion
  license: MIT
  commit: b36e0829c6d0140e93cfef2ca599b1b07d4a7797
---

# Verification Before Completion

## Overview

**Core principle:** Evidence before claims, always.

**Violating the letter of this rule is violating the spirit of this rule.**

## The Iron Law

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

If you haven't run the verification command in this message, you cannot claim it passes.

## The Gate Function

```
BEFORE claiming any status or expressing satisfaction:

1. IDENTIFY: What command proves this claim?
2. RUN: Execute the FULL command (fresh, complete)
3. READ: Full output, check exit code, count failures
4. VERIFY: Does output confirm the claim?
   - If NO: State actual status with evidence
   - If YES: State claim WITH evidence
5. ONLY THEN: Make the claim

Skip any step = lying, not verifying
```

## Project Evidence List (pad-research)

Code claims require the output of these exact commands, run from the repo root:

| Claim | Command | Evidence to quote |
|-------|---------|-------------------|
| Lint clean | `uv run --no-sync ruff check .` | `All checks passed!` |
| Types clean | `uv run --no-sync pyright src scripts` | `0 errors` line |
| Tests pass | `uv run --no-sync pytest -m "not slow"` | summary line: N passed, 0 failed |
| Hook behaves | the `tests/hooks` case for that hook | pass/fail count |

Experiment claims require **all** of:

- MLflow `run_id` and final `status` tag (`smoke_ok`, `success`, `failed_*`, `security_regression`, `inconclusive`)
- `protocol_id` + `protocol_hash` (and `science_hash` for smoke↔full pairing)
- the per-attack APCER table (`per_attack.csv` or `regression_check.json`), not only AUC/ACER
- threshold policy and where tau was fitted (dev set only)
- seed(s); one seed is a single observation, not a result (contract §31)

A smoke run proves only that the pipeline executes (`smoke_ok`). It is never evidence about research questions.

## Result Wording (contract §30)

Never say "성공", "DA works", "video is better", "this model is better".
Every result statement carries dataset, protocol, seed(s), metric, and threshold policy:

```
✅ "On syn_a_to_b_bf_adapt_v1 (protocol_hash 3f2a…), seed 42, tau fixed on source dev (EER),
    naive BF-only FT lowered BPCER 8.0%→2.1% but raised replay_phone APCER 2.0%→15.3%
    → gate verdict security_regression (run_id 0c1d…)."
❌ "DA improved the model."
```

## Common Failures

| Claim | Requires | Not Sufficient |
|-------|----------|----------------|
| Tests pass | Test command output: 0 failures | Previous run, "should pass" |
| Linter clean | Linter output: 0 errors | Partial check, extrapolation |
| Build succeeds | Build command: exit 0 | Linter passing, logs look good |
| Bug fixed | Test original symptom: passes | Code changed, assumed fixed |
| Regression test works | Red-green cycle verified | Test passes once |
| Agent completed | VCS diff shows changes | Agent reports "success" |
| Requirements met | Line-by-line checklist | Tests passing |
| Experiment worked | MLflow status + per-attack table + hash | AUC went up, log "looks fine" |
| Smoke ok ⇒ full ok | Full run with gate passed | smoke_ok status |

## Red Flags - STOP

- Using "should", "probably", "seems to"
- Expressing satisfaction before verification ("Great!", "Perfect!", "Done!", etc.)
- About to commit/push/PR without verification
- Trusting agent success reports
- Relying on partial verification
- Reporting a metric without its protocol_hash, seed and threshold source
- Thinking "just this once"
- Tired and wanting work over
- **ANY wording implying success without having run verification**

## Rationalization Prevention

| Excuse | Reality |
|--------|---------|
| "Should work now" | RUN the verification |
| "I'm confident" | Confidence ≠ evidence |
| "Just this once" | No exceptions |
| "Linter passed" | Linter ≠ type checker ≠ tests |
| "Agent said success" | Verify independently |
| "I'm tired" | Exhaustion ≠ excuse |
| "Partial check is enough" | Partial proves nothing |
| "AUC improved" | Check per-PAI APCER and the security gate (§14.3) |
| "Different words so rule doesn't apply" | Spirit over letter |

## Key Patterns

**Tests:**
```
✅ [Run test command] [See: 34/34 pass] "All tests pass"
❌ "Should pass now" / "Looks correct"
```

**Regression tests (TDD Red-Green):**
```
✅ Write → Run (pass) → Revert fix → Run (MUST FAIL) → Restore → Run (pass)
❌ "I've written a regression test" (without red-green verification)
```

**Requirements:**
```
✅ Re-read plan → Create checklist → Verify each → Report gaps or completion
❌ "Tests pass, phase complete"
```

**Agent delegation:**
```
✅ Agent reports success → Check VCS diff → Verify changes → Report actual state
❌ Trust agent report
```

**Experiments:**
```
✅ Read regression_check.json + per_attack.csv → quote run_id/status/protocol_hash → state result with §30 conditions
❌ "The adaptation run finished, so DA helps"
```

## When To Apply

**ALWAYS before:**
- ANY variation of success/completion claims
- ANY expression of satisfaction
- ANY positive statement about work state
- Committing, PR creation, task completion, handoff
- Moving to next task
- Delegating to agents

**Rule applies to:**
- Exact phrases
- Paraphrases and synonyms
- Implications of success
- ANY communication suggesting completion/correctness
