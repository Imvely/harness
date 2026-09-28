---
name: smoke
description: Validates configs/exp/<exp_name>.yaml and runs it in smoke mode (train.py, or adapt.py with adaptation.source_run_id when the spec enables adaptation), then reports run_id, status, protocol_hash and science_hash with fresh evidence. Never overrides other execution.* keys and never edits the spec.
disable-model-invocation: true
arguments: [exp_name, source_run_id]
argument-hint: "<exp_name> [source_run_id]   (source_run_id only for adaptation specs)"
allowed-tools: Bash(uv run --no-sync python scripts/validate_spec.py *) Bash(uv run --no-sync python scripts/train.py *) Bash(uv run --no-sync python scripts/adapt.py *) Bash(ls *) Bash(cat *) Bash(tail *) Read Grep Glob
---

# /smoke $exp_name

Smoke = data validation + forward pass + a few batches (`SmokeLimits`: ≤20 batches, ≤1 epoch,
≤20 eval batches). It proves the pipeline runs; it proves nothing about the research question.

## Steps

1. **Validate first**
   ```bash
   uv run --no-sync python scripts/validate_spec.py --exp $exp_name --json
   ```
   If `ok` is false, stop and report `errors[]` / `warnings[]`. Do not edit the spec here; tell
   the user what `/new-exp` or a manual edit must change.
2. **Choose the entrypoint** from the resolved spec (`Read configs/exp/$exp_name.yaml` and the
   adaptation group it overrides):
   - `adaptation.enabled: false` → `scripts/train.py`
   - `adaptation.enabled: true` → `scripts/adapt.py`; requires `$source_run_id` (a `smoke_ok` or
     `success` run of `evaluation.baseline_experiment_id` on the **same protocol_hash**). If it
     was not given, look it up in `experiments/registry.jsonl` and confirm with the user before
     running; never guess.
3. **Run** (the only override allowed is the demotion `execution.mode=smoke`):
   ```bash
   uv run --no-sync python scripts/train.py +exp=$exp_name execution.mode=smoke
   # or
   uv run --no-sync python scripts/adapt.py +exp=$exp_name execution.mode=smoke adaptation.source_run_id=$source_run_id
   ```
   The launch hook re-validates with `--for-launch`; if it denies, report its reason verbatim.
4. **Collect evidence** (apply `verifying-before-completion`): from stdout / the run dir under
   `outputs/` / the registry row:
   `run_id`, final `status` (must be `smoke_ok`; anything else is a failure to report with its
   reason), `protocol_id`, `protocol_hash`, `science_hash`, `git_sha` + dirty flag, elapsed time,
   and for adapt runs the `gate_verdict` tag and `regression_check.json` per-PAI table.
5. **Report** in this shape:
   ```
   experiment_id: … run_id: … status: smoke_ok
   protocol_id: … protocol_hash: … science_hash: …
   entrypoint: train.py|adapt.py  source_run_id: …|n/a  gate_verdict: …|n/a
   artifacts: outputs/<…>/ (resolved_spec.yaml, eval_test.json, per_attack.csv[, regression_check.json])
   next: full run requires editing the file (mode: full, allow_full_gpu_run: true) + human approval token
   ```
   Metrics from a smoke run are pipeline sanity only — never quote them as results.

## Never

- Pass `execution.mode=full`, `execution.allow_full_gpu_run=…`, `execution.require_gpu=…`,
  `execution.smoke_limits.*`, or any other `execution.*` override
- Pass `-m` / `--multirun`
- Edit `configs/exp/$exp_name.yaml`, protocol files, manifests, approvals, or the registry
- Retry a failed run with "just one more override"; a failure goes to `debugging-systematically`
