---
name: using-hydra-mlflow-dvc
description: "Background rules for editing configs and tracking code in this repo (contract §20-22): +exp=<name> is the only way to run, no per-model train scripts, block-style YAML only, execution.* never on the CLI except execution.mode=smoke, required MLflow tags and metrics, DVC and PAD_DATA_ROOT data rules. Loaded automatically when files under configs/, src/pad_research/tracking, src/pad_research/config, scripts/train.py or scripts/adapt.py are touched."
user-invocable: false
paths:
  - "configs/**"
  - "src/pad_research/tracking/**"
  - "src/pad_research/config/**"
  - "scripts/train.py"
  - "scripts/adapt.py"
---

# Hydra · MLflow · DVC 사용 규칙 (계약 §20–22 요약)

## 1. Hydra — 실험은 `configs/exp/<name>.yaml` 하나로 정의한다

- **실행 방법은 `+exp=<name>` 뿐이다.** `scripts/train.py`, `scripts/adapt.py`는 공용이며
  모델마다 `train_g2v2_8frame.py` 같은 파일을 복사해 만들지 않는다(§20).
  ```bash
  uv run --no-sync python scripts/train.py +exp=<name> execution.mode=smoke
  uv run --no-sync python scripts/adapt.py +exp=<name> adaptation.source_run_id=<run_id>
  ```
- `configs/exp/<name>.yaml`은 `# @package _global_`로 시작하고 `defaults:`에서
  `override /model`, `/data`, `/adaptation`, `/protocol` 그룹을 고른다. 최상위 키는 §16과 1:1
  (`experiment`, `model`, `data`, `adaptation`, `training`, `evaluation`, `execution`, `tracking`).
- 값은 **block style**로 쓴다. flow-mapping `{a: 1, b: ${x}}` 안의 `${}` interpolation은 금지
  (OmegaConf가 flow 안에서 interpolation을 잘못 파싱한다). interpolation이 필요하면 줄을 나눈다.
- `experiments/specs/<id>.resolved.yaml`은 `validate_spec.py --freeze`가 쓰는 파생물이다. 손으로
  편집하지 않는다. 검증은 항상:
  ```bash
  uv run --no-sync python scripts/validate_spec.py --exp <name> --json   # exit 0 ok / 2 spec / 3 protocol / 4 gate
  ```
- **`execution.*`는 CLI override로 주지 않는다.** 유일한 예외는 demotion `execution.mode=smoke`.
  `execution.mode=full`, `execution.allow_full_gpu_run=true`를 CLI로 주면 hook과 프로세스 내부
  gate가 모두 거부한다. full run은 파일에 `mode: full, allow_full_gpu_run: true`를 적어 커밋하고,
  사용자가 `scripts/approve_full_run.py`로 승인 토큰을 만든다. Claude는 토큰을 만들지 않는다.
- `-m` sweep은 허용되지만 무분별한 combinatorial sweep은 만들지 않는다. sweep 축은 한 번에 하나.
- `configs/protocol/**`는 보호 파일이다. protocol을 바꾸면 `protocol_hash`가 바뀌어 기존 run과 비교
  불가(§15). 변경이 필요하면 `parent_protocol_id` + `change_note`를 가진 **새** protocol 파일.
- `science_hash`는 `execution`, `tracking`, `adaptation.source_run_id/source_checkpoint`,
  `experiment.title/hypothesis`, `training.num_workers/device`를 제외한다. 이 키만 바꾸면 smoke와
  full이 같은 `science_hash`를 갖는다(SMOKE_OK 게이트의 전제).
- 데이터셋 이름을 실험 로직에 하드코딩하지 않는다(§27.3). 분기는 manifest meta(`pii_policy`,
  `media_type`)로 한다.

## 2. MLflow — 모든 실행은 run이고, 실패도 run이다

- Tracking URI: spec `tracking.tracking_uri`가 null이면 `MLFLOW_TRACKING_URI` env → 기본
  `sqlite:///<repo>/mlruns.db`. 절대경로는 spec에 넣지 않는다(§17, §34).
- **필수 tags (§21)**: `research_question`, `protocol_id`, `protocol_hash`, `model_family`,
  `adaptation_method`, `target_supervision`, `dataset_manifest_hash`, `git_sha`, `status`.
  하네스 추가: `science_hash`, `spec_hash`, `git_dirty`, `execution_mode`, `gate_verdict`(adapt),
  `research_claim_allowed`(synthetic이면 false), `adaptation_set_hash`(adapt).
- **필수 metrics**: `apcer`, `bpcer`, `acer`, `hter`, `auc`. 가능하면 `apcer_<pai>`
  (`apcer_print`, `apcer_replay_phone`, `apcer_replay_tablet` …) — 공격별 값 없이는 §14.2 위반.
- **필수 artifacts**: `resolved_spec.yaml`, `protocol.json`, `env_snapshot.json`(§17 항목 전부),
  `eval_test.json`, `scores_dev.csv`, `scores_test.csv`, `roc_curve.png`, `confusion.json`,
  `per_attack.csv`, `training_curves.csv`, `latency.json`, `checkpoint.pt`; adapt 추가:
  `adaptation_set.jsonl`, `regression_check.json`.
- `status` 값은 `RunStatus`만: `running, smoke_ok, success, failed_environment, failed_training,
  invalid_spec, invalid_protocol, security_regression, inconclusive, blocked_by_gate`.
  smoke의 최종 status는 항상 `smoke_ok`(gate verdict는 tag에만). 실패 run을 삭제하지 않는다(§35).
- `experiments/registry.jsonl`은 MLflow에서 파생된 로컬 인덱스(gitignored)다. 직접 편집 금지;
  진실은 MLflow.
- threshold는 dev set에서만 fit한다. `ThresholdPolicy.fit`에 test table을 주면
  `ThresholdLeakageError`가 나는 것이 정상이다.

## 3. DVC / 데이터 — raw data는 git에 없다

- `data/raw/`, `data/processed/`, `checkpoints/`는 gitignored. 대용량은 DVC(`dvc` extra) 또는
  조직이 허용한 저장소. git에 커밋되는 것은 `data/manifests/*.jsonl` + `.meta.json`뿐이다.
- 파일 위치는 **`PAD_DATA_ROOT` env + manifest `relative_path`**로만 해석한다
  (`resolve_path(record, data_root())`). 절대경로, `..`, 선행 `/`는 manifest에서 거부된다.
- manifest는 `manifest_hash`로 봉인된다. 내용을 바꾸면 `load_manifest`가
  `ManifestTamperedError`를 낸다. manifest 재생성은 `scripts/prepare_dataset.py --adapter <name>`
  하나로만 한다(`data/manifests/**`는 보호 파일).
- 얼굴 데이터는 사용자의 명시적 승인 없이 외부 저장소(GitHub, cloud, MLflow 원격 artifact
  store 포함)에 올리지 않는다. 로그·리포트·이슈에 raw frame이나 전체 dataset path를 넣지 않고
  logical `dataset_id`만 쓴다(§34).
- 데이터셋 licence · 개인정보 정책 · 외부 업로드 가능 여부는 manifest meta(`license`,
  `pii_policy`)에 기록되어 있어야 한다.

## 4. 자주 하는 실수

| 실수 | 대신 |
|------|------|
| `python scripts/train.py model=g2v2former protocol=...` (exp 없이) | `+exp=<name>` 파일을 먼저 만든다 |
| `execution.allow_full_gpu_run=true` CLI override | 파일에 적고 사용자가 승인 토큰 생성 |
| `training: {seed: 42, lr: ${base_lr}}` | block style로 풀어 쓴다 |
| `configs/protocol/x_v1.yaml` 수정 | `x_v2.yaml` + `parent_protocol_id: x_v1` |
| `experiments/registry.jsonl` 편집 | MLflow run을 고치고 registry는 재파생 |
| 결과 리포트에 `/mnt/data/replay_attack/...` | `dataset_id: replay_attack_v1` |
