# pad-research — Passive Video PAD + Domain Adaptation Harness

Phase 0 provides a local research harness for passive video face PAD and bona-fide-only domain adaptation. It is an MVP harness, not a completed research result.

Read these files before changing code:

1. `docs/HANDOFF_CODEX.md`
2. `CLAUDE.md`
3. `docs/design/plan_decisions.md`
4. `docs/design/INTERFACES.md`
5. `docs/RESEARCH_CONTRACT.md`

The research contract is pinned at sha256 `0562540579b17857205945eb5584d6fda07852c52c48c020d4ff3de2a632d35d`.

> SYNTHETIC SANITY — NOT A RESEARCH RESULT. Synthetic data is for harness sanity checks only.

## Quickstart

Use Python 3.11 and run tools through `uv run --no-sync` after the environment is ready.

### Linux or H100 shell

```bash
uv python install 3.11
uv sync
export PAD_DATA_ROOT=$PWD/data/processed
uv run --no-sync python scripts/prepare_dataset.py --adapter synthetic --dataset-id synthetic_a --dataset-id synthetic_b
uv run --no-sync pytest -q -m "not slow"
```

### PowerShell developer shell

```powershell
uv python install 3.11
uv sync
$env:PAD_DATA_ROOT = "$PWD\data\processed"
uv run --no-sync python scripts/prepare_dataset.py --adapter synthetic --dataset-id synthetic_a --dataset-id synthetic_b
uv run --no-sync pytest -q -m "not slow"
```

If `uv sync` rejects the platform on Windows, use a Linux shell for lock-accurate validation. For local Windows smoke checks only, a temporary editable install can be made with `uv pip install -e . --group dev --project .`. Do not change `uv.lock` for that workaround.

## Command cheat sheet

| Purpose | Command |
|---|---|
| Prepare synthetic manifests and clips | `uv run --no-sync python scripts/prepare_dataset.py --adapter synthetic --dataset-id synthetic_a --dataset-id synthetic_b` |
| Validate one protocol | `uv run --no-sync python scripts/validate_protocol.py --protocol syn_a_to_b_v1 --json` |
| Validate one experiment spec | `uv run --no-sync python scripts/validate_spec.py --exp syn_e02_video_source_only --json` |
| Freeze a resolved spec | `uv run --no-sync python scripts/validate_spec.py --exp syn_e02_video_source_only --freeze` |
| Train frame source-only smoke | `uv run --no-sync python scripts/train.py +exp=syn_e01_frame_source_only` |
| Train video source-only smoke | `uv run --no-sync python scripts/train.py +exp=syn_e02_video_source_only` |
| Adapt from a source run | `uv run --no-sync python scripts/adapt.py +exp=syn_e03_video_full_ft_bf_only adaptation.source_run_id=<run_id>` |
| Evaluate a checkpoint | `uv run --no-sync python scripts/evaluate.py +exp=syn_e02_video_source_only evaluation.checkpoint=<checkpoint>` |
| Summarize an experiment | `uv run --no-sync python scripts/summarize_experiment.py --experiment-id <id> --baseline-experiment-id <id> [--include-smoke] -o experiments/reports/<id>.md` |
| Export dashboard JSON | `uv run --no-sync python scripts/export_dashboard_data.py --include-smoke -o web-mockup/public/dashboard-demo.json` |
| Format | `uv run --no-sync ruff format .` |
| Lint | `uv run --no-sync ruff check .` |
| Type-check | `uv run --no-sync pyright src scripts` |
| Test non-slow suite | `uv run --no-sync pytest -q -m "not slow"` |
| Test full CPU fixture | `uv run --no-sync pytest -q tests/integration/test_train_full_cpu.py -m slow` |
| Verify DoD files | `make verify-dod` or `uv run --no-sync pytest tests/test_dod_files.py -v` |

Do not run `scripts/approve_full_run.py` from an automated agent session.

## Smoke to full procedure

A full run is allowed only after a matching smoke run and a frozen spec exist.

1. Edit only `configs/exp/<name>.yaml` for `execution.*` full-run settings.
2. Set `execution.mode: full`, `allow_full_gpu_run: true`, `require_gpu: true`, and `expected_gpu: H100` in that file.
3. Freeze the resolved spec with `uv run --no-sync python scripts/validate_spec.py --exp <name> --freeze`.
4. Run the same experiment once in smoke mode with `uv run --no-sync python scripts/train.py +exp=<name> execution.mode=smoke`.
5. Run the full command only from a human-controlled terminal.
6. Keep smoke limits at `max_epochs <= 1` and `max_batches <= 20`.
7. Tune thresholds only on the development split.

The full gate checks the allow flag, config source, protocol state, manifests, Git state, tracking writability, GPU state, frozen spec, and prior smoke row.

## H100 migration checklist

Use this checklist before moving from CPU sanity checks to the H100 server.

- Run `nvidia-smi` and read the `CUDA Version` field.
- If CUDA is `13.0` or newer, keep the default PyPI torch policy.
- If CUDA is older, uncomment the PyTorch index block in `pyproject.toml`, choose the matching `cuXXX` index, and run `uv lock`.
- Run `uv sync --frozen` on the server after the lock is finalized.
- Set `PAD_DATA_ROOT` to the server-side processed-data root.
- Build or copy only approved manifests through `scripts/prepare_dataset.py` or an approved adapter.
- Validate protocols before launch with `scripts/validate_protocol.py`.
- Validate and freeze each full experiment spec before launch.
- Use local or approved MLflow tracking only.
- Keep raw frames, checkpoints, and MLflow artifacts out of public remotes.
- Treat synthetic results as sanity checks only.

## `.claude/**` deny-promotion guidance

Claude hooks do not protect Codex sessions. Apply the same rules manually.

- Do not promote protected-file edits from `ask` to `allow`.
- Do not weaken `deny` rules for `experiments/registry.jsonl`, frozen specs, approvals, raw data, or public upload tools.
- Do not create approval tokens with `scripts/approve_full_run.py`; it is human-only.
- Review `.claude/hooks/**`, `.claude/rules/**`, `.claude/agents/**`, `.claude/skills/**`, and `.claude/settings.json` changes before use.
- Restart Claude Code after hook or settings changes before relying on them.

## Agent-surface notes

The workspace multi-agent source is `C:/Harness/docs/constitution/05-multi-agent-architecture.md`.

- Under Aimember CodeAgent, use `gpt-5.5` for every tier.
- Do not pass native Codex model IDs such as `gpt-5.6-sol`, `gpt-5.6-terra`, or `gpt-5.6-luna` to Aimember CodeAgent.
- For long or parallel subagent work, use short wait windows and require file-system checkpoints.
- Treat `report.md` and `status.json` checkpoints as authoritative if a subagent handle is unavailable.
- For workspace PM Gateway gate rulings, write `docs/decisions/DEC-YYYYMMDD-NN.md` before dispatch continues.
## Local evidence workflow

Run this before marking a task complete:

```bash
uv run --no-sync ruff format .
uv run --no-sync ruff check .
uv run --no-sync pyright src scripts
uv run --no-sync pytest -q -m "not slow"
```

T11 end-to-end rehearsal order:

```bash
uv sync
make manifests
make validate-protocols
make ci-local
uv run --no-sync python scripts/validate_spec.py --exp syn_e02_video_source_only --freeze
uv run --no-sync python scripts/train.py +exp=syn_e01_frame_source_only
uv run --no-sync python scripts/train.py +exp=syn_e02_video_source_only
uv run --no-sync python scripts/adapt.py +exp=syn_e03_video_full_ft_bf_only adaptation.source_run_id=<e02_run_id>
uv run --no-sync python scripts/summarize_experiment.py --experiment-id syn_e03_video_full_ft_bf_only --baseline-experiment-id syn_e02_video_source_only --include-smoke -o experiments/reports/syn_e03_video_full_ft_bf_only.md
uv run --no-sync pytest -q -m slow
make verify-dod
```

On PowerShell, `make validate-protocols` may require a POSIX shell. If it fails only because of shell syntax, run each `configs/protocol/*.yaml` file through `scripts/validate_protocol.py` directly and report the limitation.

## Definition of Done evidence map

| # | DoD item | Local proof |
|---:|---|---|
| 1 | root `CLAUDE.md` | `tests/test_dod_files.py`; `CLAUDE.md` points to the pinned contract. |
| 2 | `.claude/rules/` | `tests/test_dod_files.py`; four rule files exist. |
| 3 | 3개 subagent | `tests/test_dod_files.py`; three `.claude/agents/*.md` files exist. |
| 4 | destructive-command safety hook | `tests/hooks/test_guard_destructive.py`; `.claude/hooks/guard_destructive.py`. |
| 5 | experiment launch validation | `tests/unit/test_gate.py`; `tests/hooks/test_gate_experiment.py`; `scripts/validate_spec.py`. |
| 6 | uv-based environment | `pyproject.toml`, `.python-version`, and `uv.lock`; `uv sync --frozen` on Linux. |
| 7 | Hydra config | `tests/unit/test_spec_schema.py`; `configs/config.yaml`; `configs/exp/*.yaml`. |
| 8 | dataset manifest | `make manifests`; `tests/unit/test_manifest.py`; synthetic manifest metadata. |
| 9 | protocol schema | `tests/protocol/test_protocol_schema.py`; `src/pad_research/protocols/schema.py`. |
| 10 | protocol hash | `tests/protocol/test_protocol_hash.py`; `src/pad_research/protocols/hashing.py`. |
| 11 | APCER unit test | `tests/unit/test_metrics.py::test_apcer_per_pai_toy`. |
| 12 | BPCER unit test | `tests/unit/test_metrics.py::test_bpcer_toy`. |
| 13 | ACER unit test | `tests/unit/test_metrics.py::test_acer_iso_max_pai`. |
| 14 | HTER unit test | `tests/unit/test_metrics.py::test_hter_pooled`. |
| 15 | AUC unit test | `tests/unit/test_metrics.py::test_auc_perfect`. |
| 16 | MLflow run logging | `tests/unit/test_mlflow_tracker.py`; `src/pad_research/tracking/mlflow_tracker.py`. |
| 17 | Git SHA logging | `tests/unit/test_env_snapshot.py`; registry and MLflow tags include `git_sha`. |
| 18 | environment metadata logging | `tests/unit/test_env_snapshot.py`; `env_snapshot.json` is logged per run. |
| 19 | smoke-test mode | `tests/integration/test_train_smoke.py`; `execution.smoke` config limits. |
| 20 | full GPU run gate | `tests/unit/test_gate.py`; `tests/hooks/test_gate_experiment.py`. |
| 21 | experiment report generator | `tests/unit/test_report.py`; `scripts/summarize_experiment.py`. |
| 22 | research claim store | `tests/unit/test_research_store.py`; `research/claims/claims.jsonl`. |
| 23 | ADR structure | `tests/unit/test_research_store.py`; `research/decisions/ADR-000~005`. |

Run `make verify-dod` to check the DoD scaffold directly.


