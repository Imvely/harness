---
name: designing-experiments
description: Turns a research idea into a minimal, falsifiable hypothesis and a minimal ablation through one-question-at-a-time dialogue, following contract §11 order (baseline → observed failure mode → minimal hypothesis → minimal ablation). Tags every idea [Established] / [Adaptation] / [Hypothesis] (§46), writes research/hypotheses/<id>.md, and hands off to /new-exp for the config. Use before designing any new experiment, ablation, loss, or adaptation method, and whenever the user says "new idea", "what if we", or "let's try".
metadata:
  origin: https://github.com/obra/superpowers/tree/b36e0829c6d0140e93cfef2ca599b1b07d4a7797/skills/brainstorming
  license: MIT
  commit: b36e0829c6d0140e93cfef2ca599b1b07d4a7797
---

# Designing Experiments (from ideas to a minimal hypothesis)

Help turn a research idea into a hypothesis file and a minimal ablation through natural,
collaborative dialogue. The output of this skill is **text the user approves**, never code, never
a running experiment.

<HARD-GATE>
Do NOT write model/loss/adaptation code, create `configs/exp/*.yaml`, edit `configs/protocol/**`,
or launch anything until (a) the hypothesis file below is written and (b) the user has approved it.
The ceremony scales with the idea; the approval gate never does. `configs/exp/<name>.yaml` is
created only afterwards, by `/new-exp <exp_name> <hypothesis_id>`.
</HARD-GATE>

## Contract Order Is Not Negotiable (§11)

```
1. Dataset protocol 정상화        4. Source-only cross-domain benchmark
2. Frame baseline                 5. Naive real-only DA
3. Video baseline                 6. 실제 security regression 존재 여부 확인
                                  7. 그 다음 preservation method 설계
```

Every design conversation starts by locating the idea on this ladder:

- **Which baseline does it build on?** Name the experiment_id / MLflow run(s). If the baseline
  does not exist yet, the correct experiment is *the baseline*, and the idea waits.
- **Which observed failure mode motivates it?** A real number from a real run (e.g. replay_phone
  APCER 2.0%→15.3% after BF-only FT on protocol X, seed 42). "The paper says it can happen" is a
  motivation for running the *baseline that would show it*, not for building the fix.
- **Never implement Proposed first.** Spoof-preserving video DA (contract §10 "Proposed", §12
  candidates) is a hypothesis. If the request is to implement it, redirect to steps 4–6.

## Three Paths

Classify the request out loud before the first question so the user can override:

- **Question** — "is X true in our data?" whose answer is a number, not a method. Output: which
  existing run(s) or which single new baseline run answers it. No hypothesis file needed unless
  a new run is required.
- **Ablation** — one variable changed against an existing baseline on the *same protocol_hash*
  (or an explicit `parent_protocol_id` with the change noted, §15.1). Output: hypothesis file
  with exactly one changed factor, then `/new-exp`.
- **Method** — a new loss / adaptation / architecture. Output: hypothesis file **plus** the
  ablation ladder that would isolate its effect (each rung one factor). Requires steps 1–6 of §11
  to already have evidence; otherwise downgrade to Ablation or Question and say so.

When in doubt, take the lighter path: the cheapest run that could falsify the idea.

## Idea Tagging (§46) — Mandatory

Every idea sentence in the dialogue and in the file carries exactly one tag:

```
[Established]  proven in a primary paper (cite paper_id + claim_id from research/claims)
[Adaptation]   an established idea moved to our setting (video / bona-fide-only / our protocol)
[Hypothesis]   not yet validated anywhere
```

Never let the three blur. A claim tagged [Established] without a verified claim row is a
[Hypothesis]. Use `fetching-paper-source` to verify before upgrading a tag.

## Process

**Understanding the idea (one question per message):**

- Read first: `research/hypotheses/`, `research/decisions/`, `experiments/registry.jsonl`
  (last rows), `configs/exp/`, `configs/protocol/`. Do not re-propose a rejected ADR idea.
- Ask, one at a time, preferring multiple choice:
  1. Which research question (RQ1–RQ4 in the contract) does this serve?
  2. Which existing run is the baseline, and what number in it is unsatisfying?
  3. What is the *single* factor the experiment changes?
  4. What metric, on which protocol, with which threshold policy, would move — and by how much
     would it have to move to matter (per-attack APCER, not only AUC; §14.2)?
  5. What result would make you abandon the idea (kill criterion)?
- If the request contains several independent ideas, split them; design one.

**Exploring approaches (Ablation / Method paths):**

- Propose 2–3 ways to test the idea, cheapest first, with trade-offs and a recommendation.
- YAGNI ruthlessly: no combinatorial sweeps, no extra losses "while we're at it", no new
  protocol unless the question cannot be asked on an active one.
- Prefer CPU-smoke-able designs; anything needing an H100 full run must explain why smoke
  evidence is insufficient.

**Presenting the design:** in sections, asking after each whether it looks right:
baseline → failure mode → hypothesis → ablation → prediction → kill criterion → risks.

## Output: `research/hypotheses/<id>.md`

Use the next free id (`H1`, `H2`, …; follow the naming of existing files). Show the full draft in
chat and write it only after approval.

```markdown
# H<N> — <short title>

- Status: proposed | active | supported | refuted | withdrawn
- Research question: RQ<k>
- Tag: [Adaptation] | [Hypothesis]      (never [Established]: that is a claim, not a hypothesis)
- Related claims: <claim_id, …> or none

## Baseline it builds on
<experiment_id(s), run_id(s), protocol_id / protocol_hash>

## Observed failure mode
<real numbers: metric, per-attack APCER, seed, threshold policy; or "not yet observed → run baseline X first">

## Hypothesis (one falsifiable sentence)

## Minimal ablation
- Changed factor (exactly one):
- Held fixed: model, data, protocol_id, threshold rule, seed set
- Comparison: same protocol_hash as <baseline_experiment_id>

## Prediction
<metric, direction, minimum meaningful delta; per-attack APCER must not regress (§14.3)>

## Kill criterion
<what result retires the idea>

## Risks / confounds
<leakage, threshold, seed count, dataset licence>

## Next step
`/new-exp <exp_name> H<N>`
```

## Red Flags

| Thought | Reality |
|---------|---------|
| "Let's just implement the spoof-preserving loss and see" | §11: prove the regression exists first. |
| "It's an obvious win, skip the hypothesis file" | Obvious ideas are where unexamined assumptions cost weeks of GPU. |
| "Sweep frames × adaptation × lr" | One factor per ablation. Sweeps need a spec each (§20). |
| "The paper got 2% HTER so this will work" | Verify the claim (§8); it is [Established] only with a verified row. |
| "AUC will improve" | Prediction must name per-PAI APCER behaviour. |
| "We'll pick the threshold that shows it best" | Threshold is fixed on dev (§41-3). |

## After Approval

- Write the hypothesis file; do **not** write a config, code, or launch anything.
- Tell the user the exact next command: `/new-exp <exp_name> H<N>`.
- If the design surfaced a decision worth remembering (a rejected alternative, a protocol
  choice), offer `recording-adrs`.
