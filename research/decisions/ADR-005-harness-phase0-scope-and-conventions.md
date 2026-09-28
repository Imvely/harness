# ADR-005 — Harness Phase 0 범위와 규약(conventions)

## Status
Accepted

## Context

계약서 §29 Phase 0 "Harness MVP"와 §49 DoD(23항목)를 구현하면서 문서가 명시하지 않았거나, 실제 환경 사실 때문에 문서와 달리 결정한 사항이 여럿 있다. 이 ADR은 그 결정을 한 곳에 기록해 이후 세션의 Claude나 사람이 "왜 이렇게 되어 있는지" 모른 채 되돌리지 않게 한다(§26). 각 항목은 필요하면 별도 ADR로 분리해 supersede할 수 있다.

## Decision

### 1. 환경 사실 (2026-09-17 실측)

| 항목 | DEV SANDBOX (하네스 개발·검증) | REAL SERVER (사용자 진술) |
|---|---|---|
| OS / Python | Ubuntu 24.04, Python 3.11.15, uv 0.8.17 | 미확인 — `nvidia-smi`, driver, CUDA, disk, slurm 여부를 첫 H100 세션에서 기록 |
| GPU | **없음** (CUDA 미설치) | NVIDIA **H100 80GB** |
| 데이터 | 없음 → 합성(synthetic) 데이터만 | 실데이터(Replay-Attack, SiW-M, OULU-NPU, CASIA-FASD, MSU-MFSD, AIHub 등)는 서버에만 있음 |
| 네트워크 | PyPI 접근 가능, `download.pytorch.org` 차단 | — |

원칙: 모든 코드 경로(manifest → validator → loader → train → eval → gate → MLflow → report → hook)를 **CPU + 합성 데이터**로 실제 실행해 검증하고, H100에서는 같은 `uv.lock`으로 설치해 experiment YAML의 `execution` 블록만 바꾼다.

### 2. torch 소스: PyPI (CUDA build, CPU에서도 실행)

- `torch`는 base dependency로 **PyPI**에서 받는다. Linux PyPI wheel은 CUDA build이며 CPU-only 머신에서도 동작하므로 **하나의 `uv.lock`** 이 샌드박스와 H100을 모두 서비스한다.
- 이유: 샌드박스에서 `download.pytorch.org`가 차단되어 PyTorch 전용 index를 lock에 넣을 수 없다.
- H100 driver가 해당 CUDA와 맞지 않으면 `pyproject.toml`에 주석으로 남겨 둔 pinned-index 대안(`[[tool.uv.index]] pytorch-cuXXX` + `[tool.uv.sources]`)을 활성화하고 `uv lock` 후 새 lock을 커밋한다(모든 run이 `lock_hash`를 기록하므로 추적 가능).
- 마스터 플랜 D10의 "extras(`cpu`/`cu124`)에만" 안은 위 네트워크 제약으로 **폐기**한다. torchvision은 Phase 0에서 사용하지 않아 제외.

### 3. Python 3.11 고정

`.python-version = 3.11`, `requires-python = ">=3.11,<3.13"`. hydra-core 1.3.7의 classifier가 3.11에서 끝나므로 검증된 조합을 유지한다.

### 4. Experiment spec == Hydra `configs/exp/<name>.yaml`

- §16의 experiment spec은 별도 파일이 아니라 Hydra experiment group 파일 `configs/exp/<name>.yaml`(`# @package _global_`) 하나다. `+exp=<name>`으로 compose → `OmegaConf.to_container(resolve=True)` → `ExperimentSpec.model_validate`.
- 그룹명을 `experiment/`가 아닌 **`exp/`** 로 둔 이유: 최상위 메타 키 `experiment:`(§16)와 config group 이름이 같으면 `experiment.id=...`와 `+experiment=...`가 혼동될 수 있다.
- **기록된 편차**: 문서 §20 예시는 `model.frames=8`이지만 정본 필드는 §16의 **`model.input.frames`** 다. §20의 `model.frames`는 사용하지 않는다.
- `scripts/validate_spec.py --exp <name> --freeze`만이 `experiments/specs/<experiment.id>.resolved.yaml`을 쓴다.

### 5. `science_hash` vs `spec_hash`

- `spec_hash = sha256(canonical_json(spec.model_dump()))` — MLflow tag/artifact 식별.
- `science_hash = sha256(canonical_json(spec.model_dump(exclude=SCIENCE_EXCLUDE)))` — smoke ↔ full 연결과 비교 단위. smoke spec과 full spec이 같은 값을 갖는다.
- `SCIENCE_EXCLUDE` = `execution`(전체), `tracking`(전체), `adaptation.source_run_id`, `adaptation.source_checkpoint`, `experiment.title`, `experiment.hypothesis`, `experiment.parent_experiment_id`, `protocol.description`, `protocol.status`, `protocol.change_note`, `evaluation.baseline_experiment_id`, `evaluation.latency`, `evaluation.measure_latency`, `training.device`, `training.num_workers`.
- 절대경로/`paths`는 spec에 존재하지 않는다(런타임 전용) → 샌드박스와 H100의 두 hash가 동일하다.

### 6. Label / score 규약 (`src/pad_research/conventions.py`)

- `LABEL_BONA_FIDE = 0`, `LABEL_SPOOF = 1`.
- `score = P(spoof)` (= `sigmoid(logit)`, 높을수록 공격에 가까움).
- 결정: `decide_spoof(score, tau) = score >= tau`.
- 따라서 APCER = 공격 중 `score < tau` 비율, BPCER = bona-fide 중 `score >= tau` 비율. `ThresholdPolicy.fit`은 dev split에서만 가능(`ThresholdLeakageError`).

### 7. Smoke run은 항상 `smoke_ok`로 끝난다

`execution.mode=smoke`의 최종 status는 항상 `smoke_ok`다. gate verdict(`pass | security_regression | inconclusive | comparison_blocked`)는 tag `gate_verdict`와 `regression_check.json`에만 기록하고, `security_regression`/`inconclusive` status는 full run에만 쓴다. `SmokeLimits` 상한: `max_batches ≤ 20`, `max_epochs ≤ 1`, `max_eval_batches ≤ 20`.

### 8. Full run 승인 = 4겹

1. 파일의 `execution.allow_full_gpu_run: true` (CLI override로 주면 `FLAG_NOT_FROM_CLI`로 deny).
2. PreToolUse hook `gate_experiment.py`가 `validate_spec.py --for-launch`를 호출해 mode=full이면 **ask** (실패/timeout은 fail-closed deny).
3. in-process `check_full_run_gate()` (`ALLOW_FLAG, FLAG_NOT_FROM_CLI, CONFIG_SOURCES_OK, PROTOCOL_OK, MANIFESTS_OK, GIT_OK, TRACKING_OK, GPU_OK, SPEC_FROZEN, SMOKE_OK, APPROVAL_TOKEN`).
4. **사람의 승인 토큰** `experiments/approvals/<exp_id>.<science12>.json` — 사람이 자기 터미널에서 `scripts/approve_full_run.py --exp <name>`으로만 생성한다(gitignored). 토큰의 science_hash가 일치하면 hook이 allow, 없으면 ask. Claude는 `permissions.deny`와 guard로 토큰을 만들 수 없다. 무인 실행을 위한 환경변수 우회는 없다.

> **2026-09-19 정정(구현 대조)**: 위 3·4번은 원래 "토큰은 무인 실행용, 사람이 hook의 ask에 직접 답하면 토큰 없이도 full run 가능"으로 읽혔다. 실제 구현은 그보다 엄격하다. `check_full_run_gate(..., require_approval=True)`가 기본값이라 `APPROVAL_TOKEN`은 full run의 **필수 체크**이고, hook에서 사람이 allow를 눌러도 토큰이 없으면 `train.py`/`adapt.py`가 `blocked_by_gate`로 끝난다. 절차상 토큰 생성이 smoke 다음·full 실행 앞으로 온다(`approve_full_run.py`는 `require_approval=False`로 나머지 gate를 먼저 확인하므로 닭-달걀 문제는 없다). 코드가 정본이고, 더 안전한 쪽이므로 코드를 문서에 맞추지 않고 문서(`CLAUDE.md` §4, `.claude/rules/experiment-safety.md`)를 코드에 맞췄다.

### 9. `experiments/registry.jsonl`은 gitignored 로컬 파생 인덱스

MLflow가 진실(source of truth)이다. registry는 `SMOKE_OK` 조회용 로컬 인덱스이며 `Edit|Write`는 deny. **pre-run 실패도 registry에 기록**한다: `invalid_spec`, `invalid_protocol`, `blocked_by_gate` (§35 "실험 실패도 저장").

### 10. Adaptation 집합은 run 시작 시에만 materialize

`data/manifests/adaptation/<protocol_id>.<hash12>.jsonl`(gitignored)은 train/adapt 시작 시 또는 `validate_protocol --materialize`로만 생성한다. `(subject_id, sample_id)` 정렬 후 `random.Random(selection_seed).sample()`로 결정적이며 `adaptation_set_hash`를 MLflow tag에 기록한다. validator는 파일을 쓰지 않는다.

### 11. 합성 데이터는 sanity check 전용

- 합성 데이터(`scripts/prepare_dataset.py --adapter synthetic`)는 실데이터와 같은 코드 경로를 타지만 **연구 결과가 아니다**.
- `research_claim_allowed=false` 태그는 `ManifestMeta.pii_policy == "synthetic"`에서 파생한다(dataset 이름 분기 금지, §27.3). 리포트에 배너를 강제한다.
- 합성 protocol은 `security_gate.min_attack_samples_per_pai: 4`(실데이터 기본 20)로 두어 gate가 `pass|security_regression`을 실제로 계산하게 한다. 이 값은 합성 protocol에만 적용된다.
- `research/hypotheses/H*.md`와 `claims.jsonl`에 합성 run을 증거로 기록하지 않는다.

### 12. CLAUDE.md = 요약본, 계약서 원문은 `docs/RESEARCH_CONTRACT.md`

- `CLAUDE.md`는 condensed summary(≤300줄)이고 원문은 `docs/RESEARCH_CONTRACT.md`에 verbatim으로 둔다. sha256 `37a849366fb16754b29b93c59eb97543e841c64f2c00c7bad28aae7746261d2f`(2026-09-19 ADR-006 개정 반영; 개정 전 값은 `0562540579b1…`)을 `conventions.CONTRACT_SHA256`과 테스트에 pin해 조용한 편집을 검출한다.
- `.claude/rules/` 4개 파일은 문서 재복사가 아니라 운영 델타(hook 표, 명령 치트시트, science_hash/smoke→full 절차, 요청 분류표)만 담는다.
- 마스터 플랜 D9(원문 verbatim CLAUDE.md)는 사용자 결정으로 덮어썼다.

### 13. Skills / commands 레이어 (사용자 추가 요청, T13)

- 개별 스킬만 vendoring(MIT), 각 폴더에 `ATTRIBUTION.md`(출처 URL·commit·라이선스):
  - superpowers: `verification-before-completion`, `systematic-debugging`, `brainstorming`
  - ECC: `architecture-decision-records`
  - REMvisual: `handoff`
  - pedrohcgs: `checkpoint`
  - K-Dense: `paper-lookup`
  - davila7: `verify_citations`
- **플러그인 통째 설치는 기각**(SessionStart hook·강제 게이트가 §37과 충돌). CC BY-NC 저장소, 자율 실험 실행 도구, 무라이선스 저장소도 기각.
- 루틴 커맨드(`/start-day`, `/end-day`, `/handoff`, `/new-exp`, `/smoke`, `/review-run`, `/paper`, `/adr`)는 모두 `disable-model-invocation: true`, 본문에 금지 사항(full run 실행·protocol/manifest/claims 편집·업로드·approvals 쓰기 금지) 명시.

### 14. Phase 0 이연 목록 (§39 과설계 방지)

| 항목 | 이유 / 대체 |
|---|---|
| Dockerfile | `uv.lock` + `lock_hash` 태그가 Phase 0의 재현성 수단(§17) |
| pre-commit | ruff/pyright/pytest는 PostToolUse hook과 CI가 실행 |
| pytest-cov | 커버리지 수치보다 DoD 항목 테스트가 우선 |
| GRU variant, resnet18 | 모델은 `TinyFrameBaseline`, `FrameEncoderTemporalTransformer` 2개만 |
| 실행 가능한 prototype / spoof_preserve adaptation | method 이름만 등록, validator가 `NOT_IMPLEMENTED_IN_PHASE0`(§11 순서) |
| Replay-Attack adapter | 파일명 파서를 추측 구현하면 §27.2 위반; 실데이터 확인 후 |
| E04 / E05 experiment 파일 | 위 adaptation 이연에 종속 |
| 비디오 디코딩 | Phase 1에서 **PyAV**(`av`)로. `torchvision.io.read_video`는 torchvision 0.26에서 제거됨 |
| `check_dod` CLI | `tests/test_dod_files.py`로 대체 |

### 15. GitHub Actions 1 job 허용

§39는 Kubernetes/Ray/dashboard 등 인프라 과설계를 금지하지만, ruff + pyright + pytest(CPU)를 도는 **1 job**은 "재현 가능성" 게이트이며 §39가 강조하는 네 가지(재현 가능성·protocol integrity·metric integrity·research traceability)에 직접 기여하므로 예외로 포함한다. 학습 실행은 CI에서 하지 않는다.

### 16. §16 `data.source/target`은 protocol 소유

`DataSpec.source/target`은 optional이며(§16 예시 그대로 검증 가능), 값이 있으면 protocol의 `source_datasets`/`target_dataset`과 교차 검증해 불일치 시 error. 정본은 protocol이다(ADR-004).

### 17. 스크립트·모듈 이름 편차

- `scripts/prepare_dataset.py --adapter <name>`이 문서의 `make_synthetic_data` / `build_manifest` 이름을 대체한다(단일 진입점).
- `src/pad_research/losses/pad_loss.py`는 §13 loss 설계의 확장점으로만 존재한다(`L_pad`만 구현; `L_domain`, `L_spoof_preserve`, `L_temporal`은 H2 확인 이후).

## Alternatives Considered

- torch를 extras(`cpu`/`cu124`)로 분리 + PyTorch index (D10) — 샌드박스 네트워크 제약으로 lock 불가, 폐기.
- CLAUDE.md 원문 verbatim (D9) — 사용자 결정으로 요약본 채택.
- 승인 없이 gate 통과 시 자동 allow / `PAD_FULL_RUN_AUTO_ALLOW` env — LLM이 env를 조작할 수 있어 기각.
- manifest에 `adapt` split 추가 — protocol `total_samples`와 이중 진실, `selection_seed` 없음 → 기각.
- registry를 git 추적 — 머신마다 다른 로컬 상태를 커밋하게 되어 기각.
- 합성 데이터 `synthetic://` URI 즉석 생성 — `PAD_DATA_ROOT` 상대경로라는 실데이터 경로를 타지 않아 기각(시드 아이디어만 흡수).

## Why

- 샌드박스(GPU·데이터 없음)와 H100(실데이터)의 분리는 사실이며, 하네스는 그 사실 위에서 "같은 lock, 같은 hash, 다른 execution 블록"만으로 이식되어야 한다.
- 문서와의 편차(`exp/` 그룹, `model.input.frames`, 스크립트 이름)는 감추지 않고 기록해야 §36·§41의 "문서가 곧 규칙"이 유지된다.
- 이연 목록은 §11·§39의 "문제가 실제로 존재하는지 확인하기 전에 복잡한 것을 만들지 않는다"의 적용이다.

## Risks

- H100 driver가 PyPI torch의 CUDA와 맞지 않을 수 있다 → §2 대안 절차, 첫 H100 세션 체크리스트.
- 합성 데이터 통과가 실데이터 통과를 보장하지 않는다 → Phase 1 "Data & Evaluation Sanity"(§29)를 실데이터로 반복.
- 요약 CLAUDE.md가 원문과 drift할 수 있다 → 계약서 sha pin + `session_start.py` 불일치 경고.
- 승인 토큰 파일은 사람이 만든다는 전제가 사람의 습관에 의존한다 → `approve_full_run.py`만이 유효한 포맷을 쓰고, hook은 science_hash 일치를 검사한다.

## Evidence

- 계약서 §11, §13, §15, §16, §17, §20, §24, §27.2, §27.3, §29, §35, §38 Task 1, §39, §41, §49.
- 마스터 플랜 D1–D15, 최종 확정 설계 항목 1–18, T13.
- 환경 실측: 2026-09-17 (`python3 --version`, `uv --version`, `nvidia-smi` 부재, `download.pytorch.org` 접근 실패).
- 스택 사실: hydra-core 1.3.7 classifier, torchvision 0.26 changelog(`read_video` 제거), PyAV wheel 번들 FFmpeg.

## Date
2026-09-17
