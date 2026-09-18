# 인수인계 — Codex(또는 다른 에이전트/사람)가 이어서 개발하기 위한 문서

작성일 2026-09-18. 브랜치 `claude/youthful-newton-fl60mp`, PR https://github.com/Imvely/harness/pull/1 (draft).
이 문서 하나로 "무엇을 왜 만들었고, 어디까지 됐고, 다음에 무엇을 어떤 순서로 해야 하는지"를 알 수 있게 썼다.

---

## 0. 30초 요약

- 목표: 연구 헌법 `docs/RESEARCH_CONTRACT.md`(원문, sha256 `05625405…`)의 **Phase 0 Harness MVP**(§29, §38 Task 1~7, §49 DoD 23항목) + 합성 데이터로 CPU에서 end-to-end 도는 frame/video baseline 스켈레톤 + 스킬/루틴 커맨드 레이어.
- 완료: 환경(uv), 요약 CLAUDE.md·rules·agents·hooks·skills, manifest/합성데이터, protocol(schema·hash·validator), PAD metrics·threshold·security gate, 모델/adaptation 전략, experiment spec·gate·registry·validate_spec, 연구 저장소(claims/ADR/가설), Hydra config 트리. 단위/protocol/hook 테스트 ≈ 400개 통과.
- 남은 것(순서대로): **T5 테스트** → **T6 MLflow tracker** → **T7 데이터 로더·trainer·evaluator·`train.py`/`adapt.py`/`evaluate.py`** → **T8 리포트 생성기** → **T11 README·DoD 테스트·E2E 리허설** → **T12 GitHub Actions**. 상세는 §4.
- 실제 실험 서버는 **H100 80GB**. 개발/검증은 CPU + 합성 데이터로 한다(실데이터는 서버에만).

---

## 1. 데스크탑에서 시작하기

```bash
git clone https://github.com/Imvely/harness.git && cd harness
git checkout claude/youthful-newton-fl60mp
# Python 3.11 + uv 필요 (uv: https://docs.astral.sh/uv/)
uv python install 3.11
uv sync                      # torch는 PyPI CUDA 빌드(리눅스). CPU 전용 머신에서도 동작. 약 2GB 다운로드
export PAD_DATA_ROOT=$PWD/data/processed
uv run --no-sync python scripts/prepare_dataset.py --adapter synthetic --dataset-id synthetic_a --dataset-id synthetic_b
uv run --no-sync pytest -q -m "not slow"     # 전부 통과해야 함 (hook 테스트는 리눅스/맥 전제; Windows면 WSL 권장)
uv run --no-sync ruff check . && uv run --no-sync pyright src scripts
```

- Windows 데스크탑이면 **WSL2**에서 진행할 것: hook 스크립트가 `fcntl`/POSIX 경로를 쓴다.
- macOS(Apple Silicon)면 PyPI torch가 CPU/MPS 빌드로 설치되고 CPU 실행은 동일하게 동작한다.
- 도구 실행은 항상 `uv run --no-sync …` (Makefile은 `UV_NO_SYNC=1`을 export). `uv sync`는 lock이 바뀔 때만.
- `.claude/`는 Claude Code 전용 설정이다. **Codex에서는 hooks/permissions/skills가 실행되지 않는다.** 대신 아래 §5 "지켜야 할 규칙"을 사람이/에이전트가 직접 지켜야 한다. 특히 `configs/protocol/**`, `data/manifests/**`, `research/claims/**`, `CLAUDE.md`, `docs/RESEARCH_CONTRACT.md`는 연구 의미가 있는 보호 파일이므로 함부로 고치지 않는다.

---

## 2. 설계 문서 위치 (전부 저장소 안에 있음)

| 문서 | 내용 |
|---|---|
| `docs/RESEARCH_CONTRACT.md` | 연구 헌법 원문(2,585줄). 모든 결정의 근거. §번호는 이 문서 기준 |
| `CLAUDE.md` | 요약본(78줄). 세션 시작 절차, 요청 흐름, 10대 원칙, 실행 규칙 |
| `.claude/rules/*.md` | research-integrity / experiment-safety(명령 치트시트, smoke→full 절차, hook 규칙표) / data-governance / coding-style |
| `docs/design/master_plan.md` | 3개 설계안을 심사·종합한 마스터 플랜(D1~D15, T0~T12, 컴포넌트 상세). **일부 결정은 아래 plan_decisions로 덮어씀** |
| `docs/design/plan_decisions.md` | 사용자 결정 + 비판 반영 최종 결정(§"최종 확정 설계" 1~18항, T13). master_plan과 충돌하면 이것이 우선 |
| `docs/design/INTERFACES.md` | 모듈 간 인터페이스 계약(함수 시그니처, 모델 필드, toy 벡터). 구현은 이 계약을 따랐다 |
| `docs/design/critique_dod.json`, `critique_hooks.json`, `critique_python_stack.txt` | 설계 비판 보고서 3종(적용 여부는 plan_decisions에 기록) |
| `research/decisions/ADR-001~005` | 결정 기록. ADR-005가 Phase 0 규약(해시, 라벨 규약, torch 정책, 이연 목록) |

---

## 3. 현재 상태 (모듈별)

| 영역 | 상태 | 위치 | 테스트 |
|---|---|---|---|
| 환경 | ✅ `pyproject.toml`(torch PyPI, dev dependency-group, `environments=linux`), `uv.lock`, `Makefile` | 루트 | `uv lock --check` |
| Claude 레이어 | ✅ CLAUDE.md, rules 4, agents 3, `settings.json`(permissions+hooks), hooks 5개, skills 14개, commands 3개 | `.claude/` | `tests/hooks` 163개, `tests/unit/test_skills_layout.py` |
| 기반 유틸 | ✅ `paths.py`(env 재지정), `conventions.py`, `errors.py`, `utils/{canonical_json,hashing,git,seed,device}.py` | `src/pad_research/` | `tests/unit/test_{canonical_json,git_state,paths,seed}.py` |
| 데이터 | ✅ manifest 스키마/해시/로더, `DatasetAdapter`, `SyntheticAdapter`, `scripts/prepare_dataset.py`, 커밋된 `data/manifests/synthetic_{a,b}.*` | `src/pad_research/data/` | `test_manifest.py`, `test_synthetic_data.py` |
| Protocol | ✅ schema(정렬 집합 필드, schema_version), hash(HASH_EXCLUDED), loader, validator(누수/공격유형/adaptation 검사, 부작용 없음), adaptation_set(select/materialize), compare, `scripts/validate_protocol.py`, pinned hashes | `src/pad_research/protocols/` | `tests/protocol/` 44개 |
| Metrics | ✅ APCER per PAI/max/pooled, BPCER, ACER, HTER, AUC, EER/BPCER@APCER threshold, `ThresholdPolicy.fit(dev만)`, security gate verdict | `src/pad_research/metrics/`, `evaluation/scores.py` | `test_metrics.py` 등 37개 |
| 모델 | ✅ `TinyCNN`(GroupNorm), `TinyFrameBaseline`, `FrameEncoderTemporalTransformer`(batch_first), registry, `losses/pad_loss.py`, strategies none/full_finetune/head_only | `src/pad_research/models/`, `adaptation/`, `losses/` | `test_models.py`, `test_adaptation_strategies.py`, `test_losses.py` |
| Spec/Gate | ✅ 코드 완성, CLI 동작 확인(§3.1). **단위/통합 테스트는 아직 없음** | `src/pad_research/config/{schema,compose,freeze}.py`, `experiments/{registry,approvals,gate,validator,status}.py`, `scripts/validate_spec.py`, `scripts/approve_full_run.py` | ❌ T5 테스트 미작성 |
| Tracking | 🟡 `tracking/tags.py`, `env_snapshot.py`만 완료. **`mlflow_tracker.py` 미작성** | `src/pad_research/tracking/` | `test_env_snapshot.py` |
| 학습/평가 | ❌ `data/{clip_dataset,sampling,splits}.py`, `training/{trainer,checkpoint}.py`, `evaluation/evaluator.py`, `scripts/{train,adapt,evaluate}.py` 미작성 | — | — |
| 리포트 | ❌ `reporting/{template,report}.py`, `scripts/summarize_experiment.py` 미작성 | — | — |
| 연구 저장소 | ✅ claims.jsonl(2행), paper_index.yaml(9편), H1~H4, ADR-000~005, `research/claims.py` | `research/`, `src/pad_research/research/` | `test_claims.py`, `test_research_store.py` |
| Config | ✅ `configs/config.yaml`, model 2, data 2, adaptation 5, protocol 3, exp 3, 테스트 fixture exp 2 | `configs/`, `tests/fixtures/configs/exp/` | `tests/protocol/test_protocol_hash.py::test_hash_identical_via_hydra_and_yaml` |
| README/DoD/CI | ❌ README 스텁만. `tests/test_dod_files.py`, `.github/workflows/ci.yml` 미작성 | — | — |

### 3.1 validate_spec 동작 확인 (2026-09-18 실측)
```
validate_spec --exp syn_e01_frame_source_only --for-launch     → ok, mode=smoke, gate allowed (smoke는 항상 allow)
validate_spec --exp syn_e01_... --for-launch -- execution.mode=full → exit 2 FULL_REQUIRES_ALLOW_FLAG (CLI 승격 차단)
validate_spec --exp full_cpu_ok --config-dir tests/fixtures/configs --for-launch → exit 4 (SPEC_FROZEN, SMOKE_OK 실패: 아직 freeze/smoke 전이라 정상)
```

---

## 4. 남은 작업 (이 순서대로; 각 항목의 "완료 기준"을 지킬 것)

### T5-b. Spec/Gate 테스트 (코드는 있음)
- `tests/unit/test_spec_schema.py`: `test_compose_each_exp_file_validates`(parametrize `configs/exp/*.yaml`), `test_smoke_and_full_share_science_hash`(같은 exp를 `execution.mode=smoke`로 compose해도 science_hash 동일), `test_science_hash_ignores_source_run_id_device_and_text_fields`, `test_spec_hash_machine_independent`(PAD_DATA_ROOT 바꿔도 동일), `test_adaptation_without_protocol_budget_rejected`, `test_draft_protocol_forces_smoke`, `test_not_implemented_method_rejected`(`adaptation=prototype`), `test_video_needs_frames`, `test_smoke_limits_bounded`(max_batches 21 → ValidationError), `test_section16_derived_fixture_validates`(data.source/target 있는 §16형 fixture).
- `tests/unit/test_gate.py`: 9건 — smoke always allowed / full denied without flag / denied when flag from CLI(`++execution.mode=full`) / denied require_gpu on cpu / allowed with fixture full_cpu_ok after frozen+smoke row / denied dirty tree / denied without frozen / denied without prior smoke / passes after smoke row appended; `test_config_sources_ok`.
- `tests/unit/test_registry.py`: append/query, failed run kept, `latest_success_smoke` git_sha 필터.
- `tests/unit/test_approvals.py`: write/read roundtrip, mismatch → None.
- `tests/integration/test_validate_cli.py`: exit codes 0/2/3/4, `--freeze`가 `experiments/specs/<id>.resolved.yaml`을 쓰고 절대경로가 없음(`grep -c "/home/" == 0`), `--for-launch -- execution.mode=full` → 4 또는 2, `--json` 스키마. **주의**: `--freeze`는 `paths.specs_dir()`(=`PAD_REPO_ROOT/experiments/specs`)에 쓰므로 테스트에서는 `PAD_REPO_ROOT`를 tmp로 두거나 configs를 tmp에 복사해 실제 `experiments/specs`를 오염시키지 않는다. 현재 `paths.specs_dir()`는 `repo_root()/experiments/specs`이며 `PAD_REPO_ROOT`로 재지정 가능.
- `tests/hooks/test_settings_json.py`의 skip이 풀리는지 확인(`settings.json`에 hooks 블록이 이미 있음).

### T6. MLflow tracker — `src/pad_research/tracking/mlflow_tracker.py`
계약(INTERFACES.md §8 + master_plan "### 8"):
```python
class MlflowTracker:
    def __init__(self, tracking: TrackingSpec, repo_root: Path)   # uri: spec → env MLFLOW_TRACKING_URI → sqlite:///<repo>/mlruns.db ; os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT","1") 후 import mlflow
    def start_run(self, spec, pv: ProtocolValidation, env: EnvSnapshot, *, adaptation_set_hash=None, run_name=None, model_init="random", checkpoint_source="none") -> str
        # 필수 tag 9종(tags.REQUIRED_TAGS) 누락 → ValueError; dataset_manifest_hash = ",".join(f"{id}:{h[:12]}") 정렬;
        # research_claim_allowed = str(pv.research_claim_allowed).lower(); experiment 생성 시 artifact_location=str(paths.artifact_root())
    def log_metrics(self, m: PadMetrics, *, prefix="", step=None)     # 5종 누락 → ValueError; apcer_<pai>, apcer_max, apcer_pooled, tau도; math.isfinite 아닌 값은 기록하지 않음
    def log_epoch(self, epoch, train_loss, dev: PadMetrics|None)
    def log_artifact_json(name, obj) / log_artifact_file(path) / log_figure(fig, name)
    def find_baseline(self, experiment_id, protocol_hash, include_smoke) -> BaselineRef|None   # mlflow.search_runs(search_all_experiments=True, filter_string="tags.experiment_id = '...' and tags.protocol_hash = '...'" (+ " and tags.status = 'success'" if not include_smoke), order_by=["attributes.start_time DESC"]); BaselineRef{run_id, metrics: PadMetrics(eval_test.json artifact에서 복원), protocol_hash}
    def end_run(self, status: RunStatus)                               # status tag 갱신 + mlflow.end_run
```
- 테스트 `tests/unit/test_mlflow_tracker.py`: tmp sqlite에 run 생성 후 `mlflow.search_runs`로 9개 tag 확인, 필수 tag/metric 누락 시 ValueError, `find_baseline` cross-experiment, 비유한 metric skip, `research_claim_allowed=false`(synthetic). conftest가 `MLFLOW_TRACKING_URI`를 tmp로 이미 monkeypatch한다.

### T7. 데이터 로더 · trainer · evaluator · 스크립트
- `data/sampling.py::sample_frame_indices(n_frames, T, strategy, rng)` (T=1 중앙 프레임, n_frames<T면 반복 패딩), `data/clip_dataset.py::read_clip(record, root)`(npy_clip만; video/frames_dir/image는 `NotImplementedError("Phase 1")`), `ClipDataset(records, root, frames, sampling, image_size, train, seed)` → `{"clip": float32 [T,3,H,W] in [0,1], "label": int, "pai": str, "sample_id", "subject_id"}`, `collate`; `data/splits.py::build_splits(protocol, manifests, adaptation_selection) -> ProtocolSplits{source_train, source_dev, target_dev, target_test(adaptation sample 제외), adaptation}` + disjoint assert.
- `training/checkpoint.py`: **state_dict + JSON 메타만** 저장(`torch.load(weights_only=True)`로 로드 가능): `{"state_dict", "meta": {"spec": spec.model_dump(mode="json"), "threshold": ThresholdPolicy dump|None, "protocol_hash", "science_hash", "git_sha", "strategy_state", "format_version": 1}}`.
- `training/trainer.py::Trainer(model, strategy, loaders, spec, tracker, limits: SmokeLimits|None, device).fit() -> TrainResult{epochs_run, steps, train_curve, wall_clock_s}`; limits가 있으면 epoch당 max_batches에서 break, epoch=min(spec.epochs, max_epochs); `limits = spec.execution.smoke if mode=="smoke" else None` 한 곳에서만 결정.
- `evaluation/evaluator.py`: `collect_scores(model, strategy, loader, device, max_batches, role, domain) -> ScoreTable`, `evaluate(...) -> EvalResult{experiment_id, science_hash, spec_hash, protocol_id, protocol_hash, manifest_hashes, adaptation_set_hash, seed, mode, domain, metrics: PadMetrics, threshold: ThresholdPolicy, n_test, latency, status}`, `measure_latency(...)`(`ms = seconds*1000.0` 단 한 곳, smoke면 `smoke: true` 플래그), `roc_png`. Threshold는 `ThresholdPolicy.fit(dev_table)`만(test 테이블을 넘기면 `ThresholdLeakageError`).
- `scripts/train.py` (`@hydra.main(config_path=<abs configs>, config_name="config", version_base="1.3")`): 호출 그래프는 master_plan "### 10". 순서: `spec_from_cfg` → `validate_protocol` → (adaptation enabled면) `select_adaptation_set`+`materialize_adaptation_set(manifests_dir/"adaptation")` → `collect_env_snapshot` → `check_full_run_gate(spec, git, task_overrides(), pv, tracking_ok, Registry(), read_frozen_spec, GpuInfo(torch 기준), config_sources(), repo_root)` (full & !allowed → registry `blocked_by_gate`, exit 4) → `seed_everything` → tracker.start_run + registry `running` → `write_resolved_spec(run_dir)`·artifacts → loaders → model → `Trainer.fit` → threshold fit on source dev → evaluate target test → latency → checkpoint(항상) → `tracker.log_metrics` → `end_run(smoke_ok|success)` + registry final row. 예외는 `failed_training|failed_environment`로 기록 후 re-raise. spec 파싱 실패는 registry `invalid_spec`.
- `scripts/adapt.py`: 동일 전처리 + `load_checkpoint(adaptation.source_run_id|source_checkpoint)` → checkpoint의 protocol_hash가 현재 protocol_hash(또는 parent의 hash)와 다르면 `CheckpointProtocolMismatchError` → `build_strategy` → adaptation loader(bona_fide only, label 0)로 `Trainer.fit` → threshold: `dev_domain==source`면 checkpoint threshold 재사용, `target`이면 target dev로 재fit → target test 평가 + **source dev 재평가**(`eval_source_dev.json`, `regression_check.json`의 `source_domain_delta`; verdict 미반영) → `tracker.find_baseline(evaluation.baseline_experiment_id, protocol_hash, include_smoke=mode=="smoke")` → `run_security_gate` → `regression_check.json`, tag `gate_verdict` → 최종 status: smoke면 항상 `smoke_ok`, full이면 `security_regression|inconclusive|success`.
- `scripts/evaluate.py`: checkpoint + protocol → checkpoint threshold 재사용(protocol_hash 일치 시) → test 평가만, 별도 run.
- 완료 기준: `uv run --no-sync python scripts/train.py +exp=syn_e01_frame_source_only`(smoke) 60초 내 종료, MLflow run 1개(status smoke_ok), `outputs/.../eval_test.json`·`checkpoint.pt`, registry 1행; e02 동일; `scripts/adapt.py +exp=syn_e03_video_full_ft_bf_only adaptation.source_run_id=<e02 run_id>` → `regression_check.json`의 verdict가 `pass|security_regression`(합성 protocol은 `min_attack_samples_per_pai: 4`라 inconclusive가 아니어야 함). 통합 테스트 `tests/integration/test_train_smoke.py`, `test_adapt_smoke.py`, `test_train_full_cpu.py`(slow: full_cpu_ok fixture로 `validate_spec --freeze` → smoke → full 완주 + 같은 seed 2회 metric allclose 1e-6; `torch.set_num_threads(1)`, dropout 0, drop_last).
- 통합 테스트는 subprocess로 스크립트를 띄우므로 `PAD_REPO_ROOT`(configs·manifests 복사한 tmp), `PAD_REGISTRY_PATH`, `PAD_OUTPUT_ROOT`, `MLFLOW_TRACKING_URI`, `PAD_DATA_ROOT`를 env로 넘겨 실제 저장소 상태를 오염시키지 않는다.

### T8. 리포트 생성기
- `reporting/template.py`(§44 헤딩 17개, `string.Template`), `reporting/report.py::generate_report(method_runs, baseline_runs, out, justify)`: `assert_comparable` → seed 집계 mean/std/individual → `run_security_gate(baseline_mean, method_mean)` → 배너("SYNTHETIC SANITY — NOT A RESEARCH RESULT" when `research_claim_allowed=false`, "NOT DIRECTLY COMPARABLE: <justify>") → Interpretation은 §30 문장 템플릿 + `TODO(reviewer)` → "What This Does NOT Prove" 자동 항목(seed<3, synthetic, insufficient PAI support, justified diff, smoke 포함) → `experiments/reports/<experiment_id>.md` + `artifacts/tables/<id>_per_attack.csv`. `scripts/summarize_experiment.py --experiment-id --baseline-experiment-id [--justify] [--include-smoke] -o`. 테스트 6건(master_plan "### 11").

### T11. README · DoD · E2E
- `README.md`: quickstart, 명령 치트시트, smoke→full 절차, H100 이관 체크리스트(`nvidia-smi` "CUDA Version" ≥ 13.0이면 PyPI torch 그대로, 아니면 pyproject 주석의 index 블록 활성화 + `uv lock`), `.claude/**` deny 승격 안내, DoD 23항목 표(각 항목 ↔ 증명 테스트/명령).
- `tests/test_dod_files.py`: §49 23항목 존재·구성 검증(얇게; 계약서 sha pin 포함). `make verify-dod`.
- E2E 리허설(순서): `uv sync` → `make manifests` → `make validate-protocols` → `make ci-local` → `validate_spec --exp syn_e02_video_source_only --freeze` → e01/e02 smoke → e03 adapt smoke → summarize → `pytest -m slow` → `make verify-dod`.

### T12. GitHub Actions (`.github/workflows/ci.yml`, 1 job)
`astral-sh/setup-uv` → `uv sync --frozen` → `uv run --no-sync ruff check .` → `pyright src scripts` → `prepare_dataset`(합성) → `pytest -m "not slow"`. 실데이터/시크릿 없음. torch 다운로드(≈2GB)는 uv 캐시 활성화.

---

## 5. 지켜야 할 규칙 (Codex에는 hook이 없으므로 사람이 지켜야 함)

1. **실험 로직에 dataset 이름 분기 금지**(§27.3). 합성 여부는 `ManifestMeta.pii_policy`로 판단.
2. **Threshold는 dev set에서만**(`ThresholdPolicy.fit(dev_table)`). test 테이블로 fit하는 코드를 만들지 않는다.
3. **`execution.*`는 파일에서만** 바꾼다. CLI 예외는 `execution.mode=smoke` 강등뿐. `SmokeLimits` 상한(max_batches ≤ 20, max_epochs = 1)을 늘리지 않는다.
4. **보호 파일**: `configs/protocol/**`(바꾸면 protocol_hash가 바뀌어 기존 run과 비교 불가; `tests/fixtures/protocol_hashes.json`도 함께 갱신하고 ADR에 기록), `data/manifests/**`(`prepare_dataset.py`로만 생성), `research/claims/**`(value는 primary PDF 확인 전 null), `CLAUDE.md`·`docs/RESEARCH_CONTRACT.md`(연구 헌법; 바꾸면 `conventions.CONTRACT_SHA256`·`test_contract_sha_pinned` 갱신).
5. `experiments/registry.jsonl`, `experiments/approvals/**`, `experiments/specs/*.resolved.yaml`은 손으로 편집하지 않는다(생성 스크립트만). registry·approvals·adaptation set·data/processed·mlruns·outputs는 gitignore.
6. 모든 `__init__.py`는 비운다(validator/hook이 torch·mlflow 없이 import되어야 함; `tests`가 `light import`를 확인).
7. 코드·docstring·커밋은 영어, 문서·ADR·리포트는 한국어. `ruff format` + `ruff check` + `pyright` 통과 후 커밋. 커밋은 의존성 순서로 작게, PR은 #1 하나에 계속 쌓는다.
8. 결과 문장에 "성공했다/더 좋다"를 쓰지 않는다(§30). 합성 데이터 결과는 연구 근거가 아니다(`research_claim_allowed=false`).
9. 얼굴 데이터·checkpoint·mlruns를 외부(클라우드/HF/공개 저장소)에 올리지 않는다(§34).
10. `scripts/approve_full_run.py`는 **사람이 자기 터미널에서만** 실행한다(에이전트는 실행 금지). H100에서 full run 전 절차는 `.claude/rules/experiment-safety.md` "smoke → full 절차".

---

## 6. 알아두면 좋은 함정

- Hydra `configs/**.yaml`에서 flow mapping(`{...}`) 안에 `${...}` 보간을 쓰면 파싱 오류. block style만.
- `nn.TransformerEncoderLayer`는 `batch_first=True` 필수(이미 반영). BatchNorm 대신 GroupNorm(배치 1 대응).
- torch ≥ 2.6은 `torch.load` 기본 `weights_only=True` → 체크포인트에 Pydantic 객체를 pickle하지 말 것(T7 규약).
- MLflow 3은 `import mlflow` 시 stderr에 힌트 로그를 찍는다 → `MLFLOW_DISABLE_AGENT_HINT=1`(conftest·validate_spec에 이미 설정).
- `sklearn.roc_curve(drop_intermediate=False)` + `thr==inf` 제외가 EER threshold 규칙(구현·테스트 완료).
- 합성 protocol의 `security_gate.min_attack_samples_per_pai`는 4(test split 4 subject). 실데이터 protocol은 20.
- `paths.py`는 함수형(`repo_root()` 등)이라 `PAD_REPO_ROOT`/`PAD_REGISTRY_PATH`/`PAD_OUTPUT_ROOT` env로 테스트 격리.
- 커밋된 protocol 3개의 hash는 `tests/fixtures/protocol_hashes.json`에 pin. 스키마 기본값을 바꾸면 전부 바뀐다(의도적 결정만).

---

## 7. 검증 명령 모음

```bash
uv run --no-sync pytest -q -m "not slow"                       # 단위 + protocol + hooks + 통합(smoke)
uv run --no-sync pytest tests/protocol -q                       # 44
uv run --no-sync pytest tests/hooks -q                          # 163 (+ slow 1)
uv run --no-sync python scripts/validate_protocol.py --protocol syn_a_to_b_bf_adapt_v1
uv run --no-sync python scripts/validate_spec.py --exp syn_e02_video_source_only --for-launch
uv run --no-sync python scripts/validate_spec.py --exp full_cpu_ok --config-dir tests/fixtures/configs --for-launch
python3 .claude/hooks/_common.py --rules-table                  # hook 규칙표
uv run --no-sync python -c "import sys,pad_research.experiments.validator; assert not ({'torch','mlflow'} & set(sys.modules))"
```

---

## 8. DoD (§49) 현황

| # | 항목 | 상태 |
|---|---|---|
| 1 | root CLAUDE.md | ✅ 요약본 + 전문(sha pin) |
| 2 | .claude/rules/ | ✅ 4개 |
| 3 | 3개 subagent | ✅ |
| 4 | destructive-command safety hook | ✅ `guard_destructive.py` |
| 5 | experiment launch validation | ✅ `gate_experiment.py` + `validate_spec --for-launch` |
| 6 | uv 환경 | ✅ |
| 7 | Hydra config | ✅ |
| 8 | dataset manifest | ✅ |
| 9 | protocol schema | ✅ |
| 10 | protocol hash | ✅ pinned |
| 11–15 | APCER/BPCER/ACER/HTER/AUC unit test | ✅ |
| 16 | MLflow run logging | ❌ T6 |
| 17 | Git SHA logging | 🟡 env_snapshot 완료, run 기록은 T6/T7 |
| 18 | environment metadata logging | 🟡 동상 |
| 19 | smoke-test mode | 🟡 spec/gate 완료, trainer는 T7 |
| 20 | full GPU run gate | 🟡 gate·validator 완료, train.py 연결은 T7, 테스트 T5-b |
| 21 | experiment report generator | ❌ T8 |
| 22 | research claim store | ✅ |
| 23 | ADR structure | ✅ ADR-000~005 |
