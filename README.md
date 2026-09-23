# pad-research — Passive Video PAD + Domain Adaptation Harness

Phase 0 provides a local research harness for passive video face PAD and bona-fide-only domain adaptation. It is an MVP harness, not a completed research result.

Read these files before changing code:

1. `CLAUDE.md`
2. `docs/design/plan_decisions.md`
3. `docs/design/INTERFACES.md`
4. `docs/RESEARCH_CONTRACT.md`

The research contract is pinned at sha256 `37a849366fb16754b29b93c59eb97543e841c64f2c00c7bad28aae7746261d2f`.

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
| Check this machine can read a dataset | `uv run --no-sync python scripts/check_storage.py --storage lmdb --dataset-id oulu_npu` |
| Check every dataset an experiment needs | `uv run --no-sync python scripts/check_storage.py --exp syn_e02_video_source_only` |
| Validate one experiment spec | `uv run --no-sync python scripts/validate_spec.py --exp syn_e02_video_source_only --json` |
| Freeze a resolved spec | `uv run --no-sync python scripts/validate_spec.py --exp syn_e02_video_source_only --freeze` |
| Train frame source-only smoke | `uv run --no-sync python scripts/train.py +exp=syn_e01_frame_source_only` |
| Train video source-only smoke | `uv run --no-sync python scripts/train.py +exp=syn_e02_video_source_only` |
| Read the same experiment from an LMDB store | `uv run --no-sync python scripts/train.py +exp=syn_e02_video_source_only storage=lmdb` |
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

## Where the data lives

A dataset reaches the harness through one of three backends, chosen per machine and documented
in [ADR-010](research/decisions/ADR-010-storage-backends.md):

| `storage=` | Reads | Set this |
|---|---|---|
| `local` (default) | a directory tree, including an NFS, SMB or **sshfs** mount | `PAD_DATA_ROOT` |
| `lmdb` | one memory-mapped key/value store | `PAD_LMDB_PATH` |
| `sftp` | a remote directory over SSH (needs `uv sync --extra sftp`) | `PAD_SFTP_HOST`, `PAD_SFTP_ROOT`, `PAD_SFTP_USER` |

Three things are worth knowing before you pick one.

**The choice is not part of the experiment.** The storage block is excluded from `science_hash`,
so `storage=lmdb` may be passed on the CLI — even for a full run — and two people reading one
dataset two different ways still produce directly comparable runs (contract §14.3). `spec_hash`
still records which route was used.

**Locations are variable names, never values.** `configs/storage/*.yaml` and the frozen resolved
spec are both committed; a literal path or hostname in either is a machine path in a public git
history (contract §34) and the reason a spec stops working on the next person's machine.

**Prefer a mount over `sftp`.** `sshfs user@host:/data /mnt/data` plus `storage=local` gets the
kernel's page cache and a real file descriptor the video decoder can stream from; `sftp` pulls
each whole object into every worker's memory.

Before queueing anything, prove the connection works:

```bash
uv run --no-sync python scripts/check_storage.py --exp <name>
```

It checks the backend, then the manifest, then a real sample, and stops at the first failure. It
tells apart "the store is unreachable" from "the store is fine but its keys do not match the
manifest" — the latter being the LMDB mistake that otherwise shows up as thousands of identical
not-found errors. The `Data source` screen in `web-mockup/` composes the same commands for you.

## Smoke to full procedure

A full run is allowed only after a matching smoke run and a frozen spec exist.

1. Edit only `configs/exp/<name>.yaml` for `execution.*` full-run settings.
2. Set `execution.mode: full`, `allow_full_gpu_run: true`, `require_gpu: true`, and `expected_gpu: H100` in that file.
3. Freeze the resolved spec with `uv run --no-sync python scripts/validate_spec.py --exp <name> --freeze`.
4. Run the same experiment once in smoke mode with `uv run --no-sync python scripts/train.py +exp=<name> execution.mode=smoke`.
5. Get a human approval, in your own terminal, in one of two forms
   ([ADR-011](research/decisions/ADR-011-full-run-approval-transport.md)):
   - `python scripts/approve_full_run.py --exp <name>` writes `experiments/approvals/`, valid
     24h by default (`--ttl-hours`, `--no-expiry`).
   - `python scripts/approve_full_run.py --exp <name> --print` prints a signed token valid two
     hours, which you `export PAD_APPROVAL_TOKEN=...` in the launching shell. Needs a signing
     key once: `--init-key`.
6. Run the full command only from a human-controlled terminal.
7. Keep smoke limits at `max_epochs <= 1` and `max_batches <= 20`.
8. Tune thresholds only on the development split.

The full gate checks the allow flag, config source, protocol state, manifests, Git state, tracking writability, GPU state, frozen spec, and prior smoke row.

## H100 migration checklist

Use this checklist before moving from CPU sanity checks to the H100 server.

- Run `nvidia-smi` and read the `CUDA Version` field.
- If CUDA is `13.0` or newer, keep the default PyPI torch policy.
- If CUDA is older, uncomment the PyTorch index block in `pyproject.toml`, choose the matching `cuXXX` index, and run `uv lock`.
- Run `uv sync --frozen` on the server after the lock is finalized.
- Set the storage variables for the backend you will use, then run
  `scripts/check_storage.py --exp <name>` and read it before queueing anything.
- Build or copy only approved manifests through `scripts/prepare_dataset.py` or an approved adapter.
- Validate protocols before launch with `scripts/validate_protocol.py`.
- Validate and freeze each full experiment spec before launch.
- Use local or approved MLflow tracking only.
- Keep raw frames, checkpoints, and MLflow artifacts out of public remotes.
- Treat synthetic results as sanity checks only.

## `.claude/**` deny-promotion guidance

Hooks only run inside Claude Code. On any other agent surface, or with hooks disabled, apply the same rules by hand.

- Do not promote protected-file edits from `ask` to `allow`.
- Do not weaken `deny` rules for `experiments/registry.jsonl`, frozen specs, approvals, raw data, or public upload tools.
- Do not create approval tokens with `scripts/approve_full_run.py`; it is human-only.
- Review `.claude/hooks/**`, `.claude/rules/**`, `.claude/agents/**`, `.claude/skills/**`, and `.claude/settings.json` changes before use.
- Restart Claude Code after hook or settings changes before relying on them.

## Implementation notes

Non-obvious choices that are easy to undo by accident. Each one is explained where it lives.

- Encoders use `GroupNorm`, not `BatchNorm`, so batch size 1 works in train mode (`src/pad_research/models/encoders.py`).
- `nn.TransformerEncoderLayer` is constructed with `batch_first=True`; the temporal head assumes `[B, T, D]` (`src/pad_research/models/video/video_baseline.py`).
- EER uses `roc_curve(drop_intermediate=False)` and drops the sentinel `+inf` threshold (`src/pad_research/metrics/pad_metrics.py`).
- Every entry point sets `MLFLOW_DISABLE_AGENT_HINT=1` before importing mlflow, which otherwise writes a hint banner to stderr.
- Checkpoints store a `state_dict` plus JSON metadata only, so `torch.load(weights_only=True)` can read them. Do not pickle Pydantic objects into them.
- Hydra YAML must use block style; a `${...}` interpolation inside a flow mapping (`{...}`) fails to parse.

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


