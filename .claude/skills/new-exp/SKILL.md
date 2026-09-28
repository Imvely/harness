---
name: new-exp
description: Drafts a new experiment spec configs/exp/<exp_name>.yaml from an approved hypothesis in research/hypotheses/<hypothesis_id>.md using an existing protocol, validates it with scripts/validate_spec.py, and prints protocol_hash and the exact smoke command. Never enables full GPU runs, never writes approvals, never launches.
disable-model-invocation: true
arguments: [exp_name, hypothesis_id]
argument-hint: "<exp_name> <hypothesis_id>   e.g. syn_e04_video_head_only H2"
allowed-tools: Bash(ls *) Bash(cat *) Bash(uv run --no-sync python scripts/validate_spec.py *) Read Write Grep Glob
---

# /new-exp $exp_name $hypothesis_id

Create `configs/exp/$exp_name.yaml` — the only authoring surface for an experiment (§16, §20).

## Steps

1. **Read the hypothesis** `research/hypotheses/$hypothesis_id.md`. Stop and say so if it does
   not exist or has no "Minimal ablation" section: an experiment without an approved hypothesis
   is not created here (`designing-experiments` first).
2. **Read what exists** — `ls configs/exp configs/protocol configs/model configs/data
   configs/adaptation`, and the baseline spec named in the hypothesis. Copy conventions from the
   nearest existing `configs/exp/*.yaml` (key order, mlflow_experiment naming, id prefix `exp_`).
3. **Pick the protocol** — choose an existing `configs/protocol/<protocol_id>.yaml` whose
   `protocol_hash` equals the baseline's (direct comparison, §15) or, for an intentional ablation,
   one that declares `parent_protocol_id` + `change_note`. **Never edit or create a protocol file.**
   If no suitable protocol exists, stop and report what would be needed.
4. **Draft the spec** (block style, no `${}` inside flow mappings):

   ```yaml
   # @package _global_
   defaults:
     - override /model: <model group from hypothesis, e.g. video_baseline>
     - override /data: <data group, e.g. synthetic>
     - override /adaptation: <none | head_only | full_finetune | …>
     - override /protocol: <protocol_id>
   experiment:
     id: exp_$exp_name
     title: <snake_case title>
     hypothesis: "<one sentence, copied from $hypothesis_id>"
     research_question: <RQ1..RQ4>
     parent_experiment_id: <baseline experiment_id or null>
   training:
     seed: 42
     epochs: <int>
     batch_size: <int>
     learning_rate: <float>
   adaptation:
     epochs: <int>            # only when the adaptation group is enabled
   evaluation:
     baseline_experiment_id: <experiment_id the gate compares against, or null>
   execution:
     mode: smoke
     allow_full_gpu_run: false
     require_gpu: false
     expected_gpu: null
   tracking:
     mlflow_experiment: <existing experiment name or a new one per hypothesis>
   ```

   Exactly one factor differs from the baseline spec (the hypothesis' "changed factor"). Note
   any other difference explicitly in the chat and in `experiment.hypothesis`.
5. **Show the full YAML** in chat, then write `configs/exp/$exp_name.yaml`.
6. **Validate** and paste the JSON:
   ```bash
   uv run --no-sync python scripts/validate_spec.py --exp $exp_name --json
   ```
   exit 0 ok / 2 spec error / 3 protocol error / 4 gate / 5 internal. Fix the spec and re-run
   until `ok: true`; report `errors[]` and `warnings[]` verbatim otherwise.
7. **Report**: `experiment_id`, `protocol_id`, `protocol_hash`, `science_hash`, `mode`, whether
   `protocol_hash` equals the baseline's, and the exact next command:
   ```bash
   /smoke $exp_name
   # equivalently:
   uv run --no-sync python scripts/train.py +exp=$exp_name execution.mode=smoke
   ```
   (For adaptation specs: `scripts/adapt.py +exp=$exp_name adaptation.source_run_id=<source run>`.)

## Never

- Set `allow_full_gpu_run: true`, `mode: full`, `require_gpu: true` — full-run flags are a
  separate, human-reviewed edit after a `smoke_ok` run
- Write to `experiments/approvals/`, `experiments/specs/` (`--freeze` is for the human before a
  full run), `experiments/registry.jsonl`, `configs/protocol/**`, `data/manifests/**`
- Launch `scripts/train.py` / `scripts/adapt.py` from this command
- Encode dataset filesystem paths in the spec (data is resolved via `PAD_DATA_ROOT`)
