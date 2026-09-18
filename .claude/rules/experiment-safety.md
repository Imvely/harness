# 실험 안전 규칙 (experiment-safety)

전문 §16, §17, §20, §21, §24, §35 참조.

## 명령 치트시트
```bash
uv sync                                                     # 최초/lock 변경 시에만 (그 외는 항상 uv run --no-sync)
export PAD_DATA_ROOT=$PWD/data/processed                    # 데이터 루트 (매니페스트 relative_path의 기준)
uv run --no-sync python scripts/prepare_dataset.py --adapter synthetic --dataset-id synthetic_a --dataset-id synthetic_b
uv run --no-sync python scripts/validate_protocol.py --protocol syn_a_to_b_bf_adapt_v1 --json
uv run --no-sync python scripts/validate_spec.py --exp syn_e01_frame_source_only --json          # spec + protocol 검증
uv run --no-sync python scripts/validate_spec.py --exp syn_e01_frame_source_only --freeze         # experiments/specs/<id>.resolved.yaml
uv run --no-sync python scripts/train.py +exp=syn_e01_frame_source_only                           # smoke (파일 기본값)
uv run --no-sync python scripts/train.py +exp=<full-exp> execution.mode=smoke                     # full 파일을 smoke로 강등 실행
uv run --no-sync python scripts/adapt.py +exp=syn_e03_video_full_ft_bf_only adaptation.source_run_id=<run_id>
uv run --no-sync python scripts/summarize_experiment.py --experiment-id <id> --baseline-experiment-id <id> [--justify "..."]
uv run --no-sync python scripts/evaluate.py +exp=<name> evaluation.checkpoint=<path>
```
- `-m`/`--multirun` sweep은 사용자 확인 후에만(§20 무분별한 sweep 금지). `model.input.frames=4,8,16` 형태.
- `execution.*`는 파일에서만 바꾼다. CLI 허용 예외는 `execution.mode=smoke` 강등뿐. `--config-dir/--config-path/--config-name`은 테스트 fixture(`tests/fixtures/configs`) 외 금지.
- `PAD_REPO_ROOT`, `PAD_REGISTRY_PATH`, `MLFLOW_TRACKING_URI`를 실험 명령 앞에 붙이지 않는다(테스트 전용).

## smoke → full 절차 (§16, ADR-005)
1. `configs/exp/<name>.yaml`에 `execution: {mode: full, allow_full_gpu_run: true, require_gpu: true, expected_gpu: H100}`를 적고 **커밋**한다.
2. `validate_spec --exp <name> --freeze` → `experiments/specs/<id>.resolved.yaml` 생성(커밋).
3. 같은 커밋에서 `train.py +exp=<name> execution.mode=smoke` → registry에 `smoke_ok` row(같은 `science_hash`, 같은 `git_sha`).
4. `train.py +exp=<name>` → in-process gate 검사: `ALLOW_FLAG, FLAG_NOT_FROM_CLI, CONFIG_SOURCES_OK, PROTOCOL_OK(active), MANIFESTS_OK, GIT_OK(tracked clean 또는 allow_dirty_tree), TRACKING_OK, GPU_OK, SPEC_FROZEN, SMOKE_OK`. 하나라도 실패하면 `blocked_by_gate`로 기록하고 종료.
5. hook `gate_experiment`는 full run에 대해 사람 확인(`ask`)을 요구한다. 무인 실행은 사람이 자기 터미널에서 `python scripts/approve_full_run.py --exp <name>`으로 만든 토큰(`experiments/approvals/<id>.<science12>.json`, gitignore)이 있을 때만 `allow`. Claude는 이 토큰을 만들 수 없다.
- `science_hash` = spec에서 `execution`, `tracking`, `adaptation.source_run_id/source_checkpoint`, `experiment.title/hypothesis/parent_experiment_id`, protocol의 hash 제외 필드, `evaluation.baseline_experiment_id/latency/measure_latency`, `training.device/num_workers`를 뺀 canonical JSON의 sha256. smoke와 full이 같은 값을 가진다.
- `experiments/specs/*.resolved.yaml`과 `experiments/registry.jsonl`은 손으로 편집하지 않는다.

## Run status (§35)
`running, smoke_ok, success, failed_environment, failed_training, invalid_spec, invalid_protocol, security_regression, inconclusive, blocked_by_gate`. smoke run은 항상 `smoke_ok`(gate verdict는 `gate_verdict` 태그와 `regression_check.json`에만). 실패 run도 삭제하지 않는다. MLflow가 진실, registry는 로컬 파생 인덱스.

## Hook 규칙 요약 (전체 표: `python3 .claude/hooks/_common.py --rules-table`)
- `guard_destructive` (Bash): 비가역 손실만 deny(`rm -r` 보호 경로, 보호 파일 삭제, `dvc destroy/gc`, `mlflow gc/delete`, `find -delete` 보호 경로, `git filter-*`, main으로 force push, 공개 허브 업로드, registry/approvals 쓰기). 그 외 위험 명령(`git reset --hard`, `git clean -f`, `branch -D`, 업로드류, `sed -i` 보호 파일, raw data `cat`)은 ask. 복합 명령에 `allow`를 내지 않는다.
- `gate_experiment` (Bash): `train.py`/`adapt.py` 감지 시 `validate_spec --for-launch --json` 실행. smoke 통과 → allow(단일 명령일 때), full → ask(토큰 있으면 allow), `execution.*` 승격 override → deny, `+exp=` 없음 → deny, sweep → ask.
- `protect_files` (Edit/Write): CLAUDE.md, 계약서, manifests, claims, protocol, `.claude/**`, uv.lock, 기존 ADR → ask(연구 의미를 reason에 표시); registry/frozen spec/approvals → deny; `configs/exp/**`는 `execution.*` 키 변경 시에만 ask.
- `post_edit_check` (PostToolUse): 편집한 .py에 ruff + 1:1 매핑 단위 테스트(통합 테스트 제외), configs YAML은 validator.
- hooks 설정 변경은 세션 재시작 후 적용된다.
