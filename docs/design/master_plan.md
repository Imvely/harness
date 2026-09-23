# PAD Research Harness — Phase 0 "Harness MVP" 최종 구현 계획 (Synthesized Master Plan)

## Context

### 왜 이 문서인가
- 근거 문서: `/root/.claude/uploads/.../CLAUDE_PAD_RESEARCH_HARNESS_1.md` (2,586줄, 연구 헌법). 이 문서는 스스로를 "프로젝트 최상위 운영 문서 = CLAUDE.md"로 정의하며(헤더, §49 "root `CLAUDE.md`"), 수정은 연구 방향 변경으로 간주한다.
- 이 계획은 세 설계(integrity / engineering / claude_ops)를 병합한 것이다. **골격 = engineering**(Hydra experiment group == §16 spec, `check_full_run_gate`, tracker/tag 강제, 결정성), **연구 무결성 의미론 = integrity**(protocol hash 제외 집합, `ThresholdPolicy`, leakage validator error code, `materialize_adaptation_set`, `assert_comparable`, security gate 3분류, ADR-001~004), **운영 레이어 = claude_ops**(규칙 ID가 붙은 hook reason, 업로드 deny/ask 표, validator 통과 후에도 full은 `ask`, `Read(data/raw/**)` ask, session_start 출력, agent 출력 템플릿, registry.jsonl). 두 심사가 지적한 결함은 모두 아래 "핵심 설계 결정"에서 해결 방식과 이유를 적었다.

### 문서가 요구하는 것(요약)
- §29 Phase 0 완료 조건: scaffold, uv, Hydra, MLflow local, manifest schema, protocol schema, metrics tests, protocol validator, experiment spec validator, subagents, safety hooks.
- §49 DoD는 **23개** 항목(과제 지시문의 22개는 오기; 문서 기준 23개로 관리).
- §15 Protocol Lock(hash, same-hash-only 비교), §16 spec(`allow_full_gpu_run`), §17 재현성 16항목, §21 필수 tag 9종·metric 5종, §24 hook 4종, §25 저장소 구조, §27 코딩 규칙, §35 실패 run 저장, §38 Task 1–7(8–10은 Phase 1), §39 과설계 금지, §41 10원칙, §44 리포트 템플릿, §53 열린 질문.

### 환경 사실 (2026-09-17 검증)
| 항목 | DEV SANDBOX (지금 빌드/검증) | REAL SERVER (사용자 진술) |
|---|---|---|
| OS / Python | Ubuntu 24.04, Python 3.11.15, uv 0.8.17, ruff, pytest, docker 있음, slurm 없음 | 미확인 (`nvidia-smi`, driver, CUDA, disk, slurm 여부를 T1 ADR-005에 기록하는 체크리스트로 남김) |
| GPU | 없음 (CUDA/torch 미설치) | NVIDIA H100 80GB |
| 데이터 | 없음 → **합성 데이터**만 | Replay-Attack, SiW-M, OULU-NPU, CASIA-FASD, MSU-MFSD, AIHub 등 실데이터 |
| 자원 | 4 vCPU, 15 GB RAM, ~30 GB disk, PyPI 접근 가능 | — |
| 저장소 | `github.com/Imvely/harness` — MIT LICENSE만 존재, 브랜치 `claude/youthful-newton-fl60mp` | 동일 repo clone |

원칙: **모든 코드 경로(manifest → validator → loader → train → eval → gate → MLflow → report → hook)를 CPU + 합성 데이터로 실제 실행해 검증하고, H100에서는 `uv sync --extra cu124`와 experiment YAML의 `execution` 블록만 바뀐다.** Python 스택은 가정(구현 시 `uv lock`으로 pin): Python 3.11, hydra-core 1.3.x, omegaconf 2.3.x, pydantic v2, mlflow ≥2.15(3.x 허용), scikit-learn, numpy, matplotlib(Agg), pyyaml, pytest + pytest-timeout, ruff, pyright, torch 2.5+/torchvision(extras에만).

---

## 핵심 설계 결정

### D1. §16 experiment spec == Hydra experiment group 파일 (`configs/exp/<name>.yaml`, `# @package _global_`)
- **결정**: 저작 표면은 `configs/exp/<name>.yaml` 하나. `+exp=<name>` → Hydra compose → `OmegaConf.to_container(resolve=True, throw_on_missing=True)` → `ExperimentSpec.model_validate` (Pydantic v2, cross-field 검증). `scripts/validate_spec.py --exp <name> --freeze`만이 `experiments/specs/<experiment.id>.resolved.yaml`(git 추적, 사람이 편집하지 않는 파생물)을 쓴다. 매 run은 resolved spec을 run dir + MLflow artifact로 저장.
- **근거**: spec과 실행 config가 하나여서 drift 0, §20 override/`-m` sweep 그대로 동작, §16 필드가 최상위 키와 1:1.
- **기각**: claude_ops의 `spec=<path>` merge(이중 진실, `model.frames=4,8,16` sweep과 충돌, `spec.model.family`→그룹 선택 메커니즘 미정의); integrity의 "매 실행 freeze + `SpecConflictError`"(smoke 반복 중 마찰; freeze는 `--freeze`에서만 수행하고 full run만 SPEC_FROZEN 요구).
- **그룹명 `exp/`**: 최상위 메타 키 `experiment:`(§16)와 config group 이름이 같으면 Hydra가 `experiment.id=...`와 `+experiment=...`를 혼동할 여지가 있어 그룹을 `exp/`로 둔다. `configs/config.yaml` defaults에 `exp: null`을 두지 않고 항상 `+exp=`로 추가(Hydra 1.3 실동작을 `test_compose_each_exp_file_validates`로 확인 후 주석).

### D2. 두 종류의 hash: `science_hash`(smoke↔full 연결·비교 단위) vs `spec_hash`(artifact 식별)
- `science_hash = sha256(canonical_json(spec.model_dump(exclude={"execution","tracking"})))` — mode/allow flag/smoke limits/tracking URI를 제외하므로 smoke spec과 full spec이 같은 값. registry `latest_success_smoke(science_hash)`, `SMOKE_OK` 게이트, 리포트 baseline 탐색에 사용.
- `spec_hash = sha256(canonical_json(spec.model_dump()))` — MLflow tag/artifact 식별용.
- `paths`/절대경로는 spec에 **존재하지 않는다**(런타임 전용). `tracking.tracking_uri`는 spec에서 `null`이면 `MLFLOW_TRACKING_URI` env → `sqlite:///mlruns.db` 순으로 tracker가 해석. → 샌드박스와 H100의 `science_hash`/`spec_hash`가 동일(§17, §34).
- **기각**: integrity의 `spec_hash`(execution 포함)로 smoke→full 검사(구조적으로 영구 실패); engineering의 `paths` 포함(머신 종속 hash, 절대경로 커밋).

### D3. Full run 승인 = (a) 파일의 `allow_full_gpu_run: true` + (b) hook `ask` + (c) in-process gate
- `execution.mode=full`/`execution.allow_full_gpu_run=true`를 CLI override로 주면 hook deny **및** `HydraConfig.get().overrides.task` 검사로 프로세스 내부에서도 deny(`FLAG_NOT_FROM_CLI`).
- hook `gate_experiment.py`는 `scripts/train.py|scripts/adapt.py` 감지 시 `uv run --no-sync python scripts/validate_spec.py --for-launch --json -- <overrides>`(45 s timeout, torch 미import)를 호출. 실패/timeout → **deny(fail-closed)**. mode=smoke 통과 → allow. mode=full 통과 → **ask**(reason에 exp_id, protocol_hash[:12], require_gpu/expected_gpu, dirty). `-m`/`--multirun` → 항상 ask.
- `check_full_run_gate()` 체크: `ALLOW_FLAG, FLAG_NOT_FROM_CLI, PROTOCOL_OK(active), MANIFESTS_OK, GIT_OK, TRACKING_OK, GPU_OK(require_gpu/expected_gpu), SPEC_FROZEN(science_hash 일치), SMOKE_OK(선행 smoke_ok run, science_hash+git_sha 일치 또는 allow_dirty_tree)`.
- 무인 실행은 환경변수가 아니라 사용자가 `.claude/settings.local.json`의 `permissions.allow`에 특정 명령을 추가하는 방식으로만(LLM이 env를 조작할 수 없게).
- **기각**: integrity의 `Approval{approved_by}` 객체와 stdlib `launch_gate.py` 이중 구현(§16에 없는 관료 절차, stdlib에 YAML 파서 없음); engineering의 통과 시 자동 allow; claude_ops의 `PAD_FULL_RUN_AUTO_ALLOW` env.

### D4. `mode=full`은 CPU에서도 완주 가능해야 한다 (`require_gpu`, `expected_gpu`)
- `ExecutionSpec.require_gpu: bool`, `expected_gpu: str|None`. `GPU_OK = (not require_gpu) or (cuda_available and (expected_gpu is None or expected_gpu.lower() in gpu_name.lower()))`.
- `tests/fixtures/specs/full_cpu_ok.yaml`(mode full, allow true, require_gpu false, allow_dirty_tree true, epochs 2)로 gate 통과 + 완주 + 결정성 검증; `full_needs_gpu.yaml`(require_gpu true)로 `GPU_OK` 거부 검증. H100 실험 파일은 `require_gpu: true, expected_gpu: H100`을 커밋.
- **기각**: integrity의 `FULL_RUN_ON_CPU` 하드코딩(과제 요구 "full gate를 CPU에서 end-to-end" 불충족).

### D5. Protocol이 비교 가능성에 영향을 주는 모든 것을 소유하고 hash에 포함한다
- `ProtocolSpec`에 `threshold{source, policy, rule, rule_param, dev_domain}`, `acer_policy: max_pai|pooled`(기본 `max_pai`, ISO 30107-3), `security_gate{abs_tolerance 0.01, rel_tolerance 0.0, min_attack_samples_per_pai 20}`, `target_adaptation{..., source_split, selection_seed, subject_disjoint_from_test}`, `allow_image_dataset_as_clip`.
- `HASH_EXCLUDED = {"description", "parent_protocol_id", "change_note", "status"}`; **`protocol_id`는 포함**.
- **근거**: 같은 `protocol_hash`면 같은 ACER 정의·같은 gate 기준·같은 threshold 규칙이어야 §15 비교가 성립. tolerance를 느슨하게 바꾸려면 `configs/protocol/**`(ask 보호)를 건드려야 한다. `protocol_id` 포함은 §15.1 "canonical protocol JSON"의 literal 해석이며 보수적(이름만 바꿔도 `--justify`를 요구하는 쪽이 안전한 실패 모드).
- **기각**: engineering의 `evaluation.acer_rule`/`regression_gate` (spec에 두면 같은 hash로 다른 정의 비교 가능); claude_ops의 `parent_protocol_id` hash 포함(문서화 링크 추가만으로 비교 불가); integrity의 `protocol_id` 제외(두 심사 중 하나가 지지했으나 위 근거로 포함; 사용자 결정 항목 #4).

### D6. Adaptation 집합은 protocol이 결정하고 materialize한다
- manifest `split ∈ {train, dev, test}`만. `materialize_adaptation_set(protocol, target_manifest)` → target `source_split`에서 supervision에 맞는 label만, `(subject_id, sample_id)` 정렬 후 `random.Random(selection_seed).sample()` → `data/manifests/adaptation/<protocol_id>.<hash12>.jsonl` + `adaptation_set_hash`(MLflow tag, registry). validator error: `ADAPT_TEST_SAMPLE_OVERLAP`, `ADAPT_TEST_SUBJECT_OVERLAP`, `ADAPT_FROM_TEST_SPLIT`, `ADAPT_SUPERVISION_LABEL_MISMATCH`.
- **기각**: claude_ops의 manifest `adapt` split(protocol `total_samples`와 이중 진실, `selection_seed` 없음 → 비재현, 실데이터 공식 split에 없음).

### D7. 합성 데이터도 실데이터와 같은 코드 경로: 디스크 `.npy` clip + 진짜 manifest 행
- `scripts/make_synthetic_data.py`가 `data/processed/synthetic_a/<sample_id>.npy`(uint8 `[T,H,W,3]`, gitignored, `sha256(sample_id)` 시드로 결정적 재생성)와 `data/manifests/synthetic_a.jsonl` + `.meta.json`을 쓴다(dvc.yaml의 유일한 stage). `ClipDataset`이 `PAD_DATA_ROOT + relative_path`를 `media_type` 분기(`npy_clip` 구현, `video`는 Phase 1 `NotImplementedError`)로 읽는다.
- cue: bona_fide = 저주파 블롭 + 미세 drift, print = 정적 고주파 격자, replay_phone/tablet = 서로 다른 주파수 flicker + stripe. dataset B는 밝기/gain/노이즈/color cast가 다르다. ADR-005에 "연구 결과 아님" 명시, `dataset_id`가 `synthetic_*`이면 tag `research_claim_allowed=false` + 리포트 배너.
- **기각**: claude_ops의 manifest `generator` 블록(leakage validator·manifest_hash가 샌드박스에서 실행되지 않음); engineering의 `synthetic://` URI 즉석 생성(좋은 아이디어지만 `PAD_DATA_ROOT` 상대경로 해석이라는 실데이터 경로를 타지 않음 → 디스크 방식 채택, 시드 아이디어만 흡수).

### D8. 보호 파일은 `permissions.ask` + `protect_files.py`(변경 요약 reason); deny는 파괴 Bash와 `registry.jsonl`만
- ask 대상: `CLAUDE.md`, `data/manifests/**`, `research/claims/**`, `configs/protocol/**`, `.claude/**`, `uv.lock`, 기존 `research/decisions/ADR-*.md`(신규 ADR Write는 allow). deny: `Edit|Write(experiments/registry.jsonl)`.
- hook은 permission 프롬프트가 보여주지 못하는 **연구 의미**("protocol_hash가 바뀌면 기존 run과 비교 불가(§15)", "변경 키 추정: target_adaptation.total_samples")를 reason에 싣는다(§24.4 literal). 환경변수 우회 없음; 부트스트랩 마찰은 작업 순서(T0에서 CLAUDE.md/rules/agents를 settings.json보다 먼저 생성, manifest는 Bash 스크립트로 생성)로 해결. `.claude/settings.json`·hooks는 Phase 0 완료 후 사용자가 deny로 승격(README 안내).
- **기각**: integrity의 `Edit(CLAUDE.md)` deny(부트스트랩 교착, §24.4 위반); engineering의 `PAD_ALLOW_PROTECTED_EDIT`.

### D9. CLAUDE.md = 원문 verbatim; `.claude/rules/`는 문서 재복사가 아닌 운영 델타만
- Phase 0는 원문 2,586줄을 그대로 `CLAUDE.md`로 둔다(§49 literal, drift 0). rules 4개는 §를 verbatim 재복사하지 않고 hook 표, 명령 치트시트, science_hash/smoke→full 절차, 요청 분류표/위임 정책, 테스트 매핑 규칙만 담는다. `data-governance.md`는 **전역**(업로드 금지는 데이터 파일을 만지지 않을 때도 적용), `coding-style.md`만 path-scoped.
- 토큰 비용 논거(claude_ops)는 ADR-005에 "분할 보류, 컨텍스트 압박이 측정되면 재검토"로 기록. 원문 뒤에 운영 절을 append할지는 사용자 결정 #2(권장: rules에만 두고 원문 무수정).

### D10. torch는 extras(`cpu`/`cu124`)에만; base deps에서 제외
- extra 없는 `uv sync`는 torch 부재로 시끄럽게 실패 → PyPI CUDA torch를 조용히 받는 사고 방지. `[tool.uv] conflicts`로 동시 설치 금지, `--frozen`으로 두 환경의 `sha256(uv.lock)` 동일(tag `lock_hash`).

### D11. Phase 0 범위 컷(§39, §11)
- 포함: Makefile, `.dvcignore` + `dvc.yaml` 스켈레톤(remote 없음), `scripts/*.py` 단일 엔트리(`[project.scripts]` 없음), 모델 2개(`TinyFrameBaseline`, `FrameEncoderTemporalTransformer`), adaptation 3개(none/full_finetune/head_only; `prototype.yaml`/`spoof_preserve.yaml`은 method 이름만 등록되어 validator가 `NOT_IMPLEMENTED_IN_PHASE0` error), 실험 파일 3개(syn_e01/e02/e03), protocol 3개(합성 2 + `ocim_target_i_v1` draft), `tests/test_dod_files.py`, `experiments/registry.jsonl`.
- 제외(ADR-005 이연 목록): Dockerfile, pre-commit, pytest-cov, skills, GRU 변형, resnet18, 실행 가능한 prototype adaptation, Replay-Attack 파일명 파서(§27.2 위반), E04/E05 experiment 파일, `check_dod` CLI. GitHub Actions 1 job은 사용자 결정 #1(권장: 포함, 25줄).

### D12. Score/label 규약 한 곳 고정 (`conventions.py`, ADR-005)
- `LABEL_BONA_FIDE = 0`, `LABEL_SPOOF = 1`, `attack_score = sigmoid(logit) = P(spoof)`, `decide_spoof = score >= tau`. APCER = 공격 중 `score < tau`, BPCER = bona_fide 중 `score >= tau`. `ThresholdPolicy`는 `split_name="dev"`로만 `fit()` 가능.

### D13. Security gate verdict = `pass | security_regression | inconclusive | comparison_blocked`
- `bpcer_improved: bool`은 별도 필드(§30 "DA가 성공했다" 표현 금지, §35 enum 준수). `EvalResult`가 `protocol_hash`를 가지며 gate가 불일치 시 `comparison_blocked`(justify 없으면 `ProtocolMismatchError`).

### D14. research-reviewer / paper-researcher는 검증된 read-only 템플릿
- reviewer `tools: Read, Glob, Grep`; paper-researcher `tools: Read, Glob, Grep, WebFetch, WebSearch`; 둘 다 `disallowedTools: Bash, Edit, Write`. 리뷰/claims 파일 기록과 `summarize_experiment.py` 실행은 main agent가 수행. **기각**: claude_ops의 reviewer Bash(§23.3 위반), engineering의 researcher Write.

### D15. Hook 파서는 중간 복잡도
- `re.split(r"\s*(?:;|&&|\|\||\||\n)\s*")` → `shlex.split` → 선행 `sudo/env/time/nohup/nice/VAR=` 제거 → argv[0]과 타겟 경로(`resolve_targets`)만 검사. `$(`, 백틱, heredoc, shlex 실패 → `ask`. stdin JSON 파싱 실패 → `ask`(파괴 가드 fail-safe), launch validator 실패 → `deny`. 규칙 ID(`DG-xx`, `EXP-xx`, `PF-xx`)와 매칭 세그먼트를 reason에 표기. 테스트 ~20건.
- **기각**: claude_ops의 서브셸 재귀/히어독 파서 + 40건(파서 자체가 false-negative 표면); engineering의 fail-open(exit 0).

---

## 저장소 파일 트리

```text
harness/
├── CLAUDE.md                              # 업로드 문서 원문 verbatim (2,586줄). ask 보호
├── README.md                              # quickstart, H100 이관 체크리스트, DoD 23항목, deny 승격 안내
├── LICENSE                                # 기존 MIT
├── pyproject.toml                         # deps, extras cpu/cu124/dev, uv index/sources/conflicts, ruff/pyright/pytest
├── uv.lock                                # 단일 universal lock (ask 보호)
├── .python-version                        # 3.11
├── .gitignore                             # .venv outputs multirun mlruns* checkpoints/* data/raw/* data/processed/* *.pt
├── .dvcignore                             # outputs/ multirun/ mlruns/ .venv/
├── dvc.yaml                               # stage synthetic_data: make_synthetic_data.py (remote 없음)
├── Makefile                               # setup-cpu setup-cu124 lint typecheck test test-all manifests smoke smoke-adapt report verify-dod mlflow-ui
├── .claude/
│   ├── settings.json                      # permissions(allow/ask/deny) + hooks 4 이벤트
│   ├── hooks/
│   │   ├── _common.py                     # stdin 파싱, split_commands, shlex, resolve_targets, decide(), 규칙 ID
│   │   ├── guard_destructive.py           # PreToolUse Bash: 파괴/업로드/mlflow 삭제 명령 deny/ask
│   │   ├── gate_experiment.py             # PreToolUse Bash: train/adapt 감지 → validate_spec --for-launch
│   │   ├── protect_files.py               # PreToolUse Edit|Write: 보호 파일 ask + 변경 요약 reason
│   │   ├── post_edit_check.py             # PostToolUse Edit|Write: ruff + targeted pytest (exit 2 + stderr)
│   │   └── session_start.py               # SessionStart: git/env/registry/ADR 요약 ≤45줄
│   ├── rules/
│   │   ├── research-integrity.md          # 전역: §41 포인터, --justify 규칙, 요청 분류표, 위임 정책, 표현 규칙 포인터
│   │   ├── experiment-safety.md           # 전역: hook deny/ask 표, 명령 치트시트, smoke→freeze→full 절차, science_hash
│   │   ├── data-governance.md             # 전역: 업로드 금지, Read(data/raw) 금지, manifest relative_path/PAD_DATA_ROOT
│   │   └── coding-style.md                # paths: src/** tests/** scripts/** configs/**: ruff/pyright, 테스트 매핑, conventions.py
│   └── agents/
│       ├── paper-researcher.md            # read-only + web, §23.1 템플릿 + claims 초안 절
│       ├── experiment-engineer.md         # tools 상속, §23.2 금지, Engineering Report 템플릿
│       └── research-reviewer.md           # read-only, §23.3 체크리스트, Verdict 템플릿
├── configs/
│   ├── config.yaml                        # defaults(model/data/adaptation/protocol) + experiment/training/evaluation/execution/tracking 기본값
│   ├── model/
│   │   ├── frame_baseline.yaml            # family frame_baseline, frames 1, TinyFrameBaseline
│   │   └── video_baseline.yaml            # family video_baseline, frames 8, FrameEncoderTemporalTransformer
│   ├── data/
│   │   ├── synthetic.yaml                 # manifests_dir, root_env_var PAD_DATA_ROOT, loader/transform 기본
│   │   └── replay_attack.yaml             # Phase 1 placeholder: dataset_id + root_env_var만
│   ├── adaptation/
│   │   ├── none.yaml  full_finetune.yaml  head_only.yaml
│   │   ├── prototype.yaml                 # method 이름만 (implemented: false)
│   │   └── spoof_preserve.yaml            # method 이름만 (implemented: false)
│   ├── protocol/
│   │   ├── syn_a_to_b_v1.yaml             # source-only, active
│   │   ├── syn_a_to_b_bf_adapt_v1.yaml    # parent syn_a_to_b_v1, bona_fide_only adaptation 24개, active
│   │   └── ocim_target_i_v1.yaml          # §15 예시 그대로, status: draft (manifest 없음, Phase 1 확장점)
│   └── exp/
│       ├── syn_e01_frame_source_only.yaml
│       ├── syn_e02_video_source_only.yaml
│       └── syn_e03_video_full_ft_bf_only.yaml
├── data/
│   ├── raw/.gitkeep   processed/.gitkeep  # 내용 gitignored; processed/synthetic_{a,b}/*.npy 는 스크립트가 생성
│   └── manifests/
│       ├── README.md                      # 스키마, 생성 절차(adapter → build_manifest), 실데이터 adapter 작성 절차
│       ├── synthetic_a.jsonl  synthetic_a.meta.json
│       ├── synthetic_b.jsonl  synthetic_b.meta.json
│       └── adaptation/.gitkeep            # <protocol_id>.<hash12>.jsonl materialized adaptation sets
├── research/
│   ├── papers/paper_index.yaml            # §7 9편, code_status: verify
│   ├── papers/reviews/.gitkeep
│   ├── claims/claims.jsonl                # §8.2 예시 1건 + local_dg_repro_001
│   ├── claims/README.md
│   ├── hypotheses/H1.md H2.md H3.md H4.md # §42
│   └── decisions/
│       ├── ADR-000-template.md            # §26 템플릿
│       ├── ADR-001-use-video-input.md
│       ├── ADR-002-switch-dg-to-da.md     # §3.1 "일반화 금지" 문구 포함
│       ├── ADR-003-real-only-target-setting.md   # §53-6/7 링크
│       ├── ADR-004-protocol-lock.md       # hash 규칙, HASH_EXCLUDED, --justify
│       └── ADR-005-harness-phase0-scope-and-conventions.md  # 환경 사실, spec==Hydra, 합성=sanity-only, label 규약, 이연 목록, CLAUDE.md 분할 보류
├── src/pad_research/
│   ├── __init__.py                        # 비움 (torch import 없음 — validator가 가볍게 import되도록)
│   ├── paths.py                           # REPO_ROOT, CONFIGS_DIR, MANIFESTS_DIR, SPECS_DIR, REGISTRY_PATH
│   ├── conventions.py                     # LABEL_*, ATTACK_SCORE_CONVENTION, decide_spoof()
│   ├── utils/
│   │   ├── canonical_json.py              # canonical_json(), sha256_text()
│   │   ├── hashing.py                     # sha256_file()
│   │   ├── git.py                         # git_state() -> GitState
│   │   ├── seed.py                        # seed_everything, make_generator, worker_init_fn (torch import는 함수 내부)
│   │   └── device.py                      # resolve_device(spec)
│   ├── data/
│   │   ├── manifest.py                    # Label/PAI/Split/MediaType, ManifestRecord, ManifestMeta, load/write/hash
│   │   ├── adapters/base.py               # DatasetAdapter ABC (build_manifest, meta)
│   │   ├── adapters/synthetic.py          # SyntheticAdapter, SyntheticDomain, generate_clip()
│   │   ├── clip_dataset.py                # ClipDataset(torch), collate, read_clip(media_type 분기)
│   │   ├── sampling.py                    # sample_frame_indices()
│   │   └── splits.py                      # build_splits(protocol, manifests, adaptation_set) -> ProtocolSplits
│   ├── protocols/
│   │   ├── schema.py                      # ProtocolSpec, TargetAdaptation, TargetTest, ThresholdSpec, SecurityGateConfig, pai_matches()
│   │   ├── hashing.py                     # HASH_EXCLUDED, protocol_hash()
│   │   ├── loader.py                      # load_protocol(name|path)
│   │   ├── validator.py                   # validate_protocol(), ValidationIssue, error codes
│   │   ├── adaptation_set.py              # materialize_adaptation_set(), AdaptationSet
│   │   └── compare.py                     # assert_comparable(), ProtocolMismatchError, Comparability
│   ├── config/
│   │   ├── schema.py                      # ExperimentSpec + 하위 모델, science_hash(), spec_hash()
│   │   ├── compose.py                     # compose_spec(overrides), spec_from_cfg(cfg)
│   │   └── freeze.py                      # write_resolved_spec(), read_frozen_spec()
│   ├── experiments/
│   │   ├── validator.py                   # validate_spec(...) -> SpecValidationReport (torch 미import)
│   │   ├── gate.py                        # check_full_run_gate(), GateResult
│   │   ├── registry.py                    # RegistryRow, append_row(), latest_success_smoke(), find_runs()
│   │   └── status.py                      # RunStatus StrEnum
│   ├── metrics/
│   │   ├── pad_metrics.py                 # apcer_per_pai, apcer_pooled, apcer_max, bpcer, acer, hter, roc_auc, eer_threshold, compute_pad_metrics, PadMetrics
│   │   ├── threshold.py                   # ThresholdPolicy, ThresholdLeakageError, NotFittedError
│   │   └── security_gate.py               # run_security_gate(), SecurityGateResult, PaiDelta
│   ├── models/
│   │   ├── base.py                        # PADModel, ModelOutput
│   │   ├── encoders.py                    # TinyCNN
│   │   ├── heads.py                       # LinearHead
│   │   ├── frame/frame_baseline.py        # TinyFrameBaseline (per-frame logit mean)
│   │   ├── video/video_baseline.py        # FrameEncoderTemporalTransformer
│   │   └── registry.py                    # build_model(model_cfg)
│   ├── adaptation/
│   │   ├── base.py                        # AdaptationStrategy Protocol
│   │   └── strategies.py                  # NoAdaptation, FullFinetune, HeadOnly, build_strategy()
│   ├── training/
│   │   ├── trainer.py                     # Trainer.fit() with SmokeLimits
│   │   └── checkpoint.py                  # save_checkpoint/load_checkpoint (state_dict+spec+threshold+protocol_hash)
│   ├── evaluation/
│   │   ├── scores.py                      # ScoreTable (role dev|test)
│   │   └── evaluator.py                   # collect_scores, evaluate(), EvalResult, measure_latency, roc_png
│   ├── tracking/
│   │   ├── tags.py                        # REQUIRED_TAGS(9), EXTRA_TAGS, REQUIRED_METRICS(5)
│   │   ├── env_snapshot.py                # collect_env_snapshot() -> EnvSnapshot
│   │   └── mlflow_tracker.py              # MlflowTracker
│   ├── reporting/
│   │   ├── template.py                    # §44 string.Template
│   │   └── report.py                      # generate_report(), RunRecord 집계
│   └── research/claims.py                 # Claim 모델, load_claims, validate_claims_file
├── scripts/
│   ├── make_synthetic_data.py             # 합성 clip + manifest 생성 (adapter 경유)
│   ├── build_manifest.py                  # 범용: --adapter <name> --root $PAD_DATA_ROOT/<dir> (Phase 1 실데이터 진입점)
│   ├── validate_protocol.py               # --protocol NAME|--path FILE [--manifests-dir] [--json]
│   ├── validate_spec.py                   # --exp NAME [-- overrides] [--freeze] [--for-launch] [--json]
│   ├── train.py                           # @hydra.main
│   ├── adapt.py                           # @hydra.main (source checkpoint 로드 → adaptation → eval → gate)
│   ├── evaluate.py                        # @hydra.main (checkpoint + protocol → test 평가만)
│   └── summarize_experiment.py            # --experiment-id --baseline-experiment-id [--justify] [--include-smoke] -o
├── experiments/
│   ├── specs/.gitkeep                     # <id>.resolved.yaml (validate_spec --freeze 산출물, 사람이 편집하지 않음)
│   ├── reports/.gitkeep                   # <experiment_id>.md
│   └── registry.jsonl                     # append-only (deny Edit/Write)
├── artifacts/figures/.gitkeep  artifacts/tables/.gitkeep
├── checkpoints/.gitkeep                   # 내용 gitignored
└── tests/
    ├── conftest.py                        # tmp repo_root, tmp mlflow sqlite, synthetic manifests fixture, torch threads=1
    ├── fixtures/
    │   ├── protocols/ section15_example.yaml  bad_subject_overlap.jsonl ...
    │   ├── specs/ full_cpu_ok.yaml  full_needs_gpu.yaml  section16_example.yaml
    │   └── hook_inputs/*.json
    ├── test_dod_files.py                  # §49 23항목 파일/구성 존재 assert
    ├── unit/  test_canonical_json.py test_manifest.py test_synthetic_data.py test_protocol_schema.py test_protocol_hash.py
    │          test_metrics.py test_threshold.py test_security_gate.py test_spec_schema.py test_compose.py test_spec_validator.py
    │          test_gate.py test_registry.py test_env_snapshot.py test_mlflow_tracker.py test_models.py test_adaptation_strategies.py
    │          test_seed.py test_claims.py test_report.py test_compare.py
    ├── protocol/ test_leakage.py test_adaptation_set.py test_protocol_configs.py test_threshold_source.py
    ├── integration/ test_validate_cli.py test_train_smoke.py test_train_full_cpu.py test_adapt_smoke.py test_evaluate_cli.py test_summarize.py
    └── hooks/ test_common.py test_guard_destructive.py test_gate_experiment.py test_protect_files.py test_post_edit_check.py test_session_start.py test_settings_json.py
```

---

## 작업 순서 (T0 … T12)

크리티컬 패스: T0 → T1 → T2 → T3 → T5 → T6 → T7 → T8 → T9 → T11. 병렬 가능: T4 ‖ T2/T3, T10 ‖ T6~T9.

### T0 — 연구 헌법과 Claude Code 정적 레이어 (hook 없이)
- **목표**: 하네스를 만드는 동안 Claude가 헌법 아래에서 작업하도록 최우선 배치. settings.json보다 CLAUDE.md를 먼저 써서 ask 교착 방지.
- **산출물**: `CLAUDE.md`(원문 `cp`), `.claude/rules/*.md` 4개, `.claude/agents/*.md` 3개, `.claude/settings.json`(permissions만; `hooks` 키는 T9에서 추가), `.gitignore`, `README.md` 스텁, 디렉터리 골격(`.gitkeep`).
- **의존**: 없음.
- **검증**: `diff <(cat CLAUDE.md) /root/.claude/uploads/.../CLAUDE_PAD_RESEARCH_HARNESS_1.md` 출력 없음; `wc -l CLAUDE.md` = 2586; `python3 -c "import json;json.load(open('.claude/settings.json'))"`; agent frontmatter 3개가 `name/description/tools` 키를 가짐(`head -8`).
- **규모**: 파일 10개, 신규 텍스트 ~400줄(원문 제외).

### T1 — Python 환경 + 기반 유틸 + 환경 기록
- **산출물**: `pyproject.toml`, `.python-version`, `uv.lock`, `Makefile`, `src/pad_research/{__init__,paths,conventions}.py`, `utils/{canonical_json,hashing,git}.py`, `research/decisions/ADR-000-template.md`, `ADR-005`(초안: §38 Task 1 환경 사실 + H100 확인 체크리스트), `tests/unit/test_canonical_json.py`, `tests/test_env_smoke.py`.
- **의존**: T0.
- **검증**: `uv sync --extra cpu --extra dev` 성공; `uv run python -c "import torch,hydra,mlflow,pydantic,sklearn;print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"` → `None False`; `uv lock --check`; `uv run ruff check .`; `uv run pytest -q`(2~3개 통과); `uv sync`(extra 없이)는 torch 부재로 `import torch` 실패함을 README에 기록.
- **규모**: ~250줄.

### T2 — Dataset manifest + 합성 데이터 + DVC 스켈레톤 (§38 Task 7)
- **산출물**: `data/manifest.py`, `data/adapters/{base,synthetic}.py`, `scripts/make_synthetic_data.py`, `scripts/build_manifest.py`, `data/manifests/README.md`, 생성된 `synthetic_a/b.jsonl + .meta.json`, `.dvcignore`, `dvc.yaml`, `tests/unit/test_manifest.py`, `test_synthetic_data.py`.
- **의존**: T1.
- **검증**: `PAD_DATA_ROOT=$PWD/data/processed uv run python scripts/make_synthetic_data.py --dataset synthetic_a --dataset synthetic_b` 두 번 실행 → `sha256sum data/manifests/synthetic_*.jsonl` 동일; `uv run pytest tests/unit/test_manifest.py tests/unit/test_synthetic_data.py`; `du -sh data/processed` < 30 MB.
- **규모**: ~450줄 + 테스트 ~200줄.

### T3 — Protocol schema / hash / validator / adaptation set / compare (§38 Task 4)
- **산출물**: `protocols/{schema,hashing,loader,validator,adaptation_set,compare}.py`, `configs/protocol/*.yaml` 3개, `scripts/validate_protocol.py`, `tests/unit/test_protocol_schema.py`, `test_protocol_hash.py`, `test_compare.py`, `tests/protocol/*` 4개, `tests/fixtures/protocols/*`.
- **의존**: T2(enums, manifests).
- **검증**: `uv run python scripts/validate_protocol.py --protocol syn_a_to_b_v1` → `ok=True hash=<64hex>`; `--protocol ocim_target_i_v1` → `status=draft, MISSING_MANIFEST=warning, ok=True`; `uv run pytest tests/unit/test_protocol_* tests/protocol -q`; `ls data/manifests/adaptation/syn_a_to_b_bf_adapt_v1.*.jsonl`.
- **규모**: ~600줄 + 테스트 ~350줄.

### T4 — PAD metrics / ThresholdPolicy / security gate (§38 Task 5) — T2/T3와 병렬
- **산출물**: `metrics/{pad_metrics,threshold,security_gate}.py`, `experiments/status.py`, `tests/unit/test_metrics.py`, `test_threshold.py`, `test_security_gate.py`.
- **의존**: T1.
- **검증**: `uv run pytest tests/unit/test_metrics.py tests/unit/test_threshold.py tests/unit/test_security_gate.py -v` — 아래 toy vector 값이 그대로 통과.
- **규모**: ~350줄 + 테스트 ~300줄.

### T5 — Experiment spec + Hydra 트리 + spec validator + gate + registry
- **산출물**: `config/{schema,compose,freeze}.py`, `experiments/{validator,gate,registry}.py`, `configs/config.yaml`, `configs/{model,data,adaptation,exp}/*.yaml`, `scripts/validate_spec.py`, `tests/fixtures/specs/*`, `tests/unit/test_spec_schema.py`, `test_compose.py`, `test_spec_validator.py`, `test_gate.py`, `test_registry.py`, `tests/integration/test_validate_cli.py`.
- **의존**: T3, T4.
- **검증**: `uv run python scripts/validate_spec.py --exp syn_e01_frame_source_only --json` → `ok: true`; `--freeze` → `experiments/specs/exp_syn_e01_frame_source_only.resolved.yaml` 생성(절대경로 문자열 `grep -c "/home/" = 0`); `--for-launch -- execution.mode=full` → exit 4 (`ALLOW_FLAG`, `FLAG_NOT_FROM_CLI`); `uv run python -c "import sys,pad_research.experiments.validator;assert 'torch' not in sys.modules"`; `uv run pytest tests/unit/test_spec_* tests/unit/test_compose.py tests/unit/test_gate.py tests/unit/test_registry.py tests/integration/test_validate_cli.py`.
- **규모**: ~700줄 + YAML ~200줄 + 테스트 ~400줄.

### T6 — Env snapshot + MLflow tracker (§38 Task 6)
- **산출물**: `tracking/{tags,env_snapshot,mlflow_tracker}.py`, `tests/unit/test_env_snapshot.py`, `test_mlflow_tracker.py`.
- **의존**: T5(spec 타입), T1.
- **검증**: `uv run pytest tests/unit/test_env_snapshot.py tests/unit/test_mlflow_tracker.py` — tmp `sqlite:///<tmp>/mlruns.db`에 run 생성 후 `mlflow.search_runs`로 9개 tag 확인; `test_cpu_extra_has_no_cuda`(`torch.version.cuda is None`).
- **규모**: ~300줄 + 테스트 ~150줄.

### T7 — 모델 / 데이터 로딩 / adaptation / trainer / evaluator / train·adapt·evaluate 스크립트
- **산출물**: `models/**`, `adaptation/**`, `data/{clip_dataset,sampling,splits}.py`, `training/{trainer,checkpoint}.py`, `evaluation/{scores,evaluator}.py`, `utils/{seed,device}.py`, `scripts/{train,adapt,evaluate}.py`, `tests/unit/test_models.py`, `test_adaptation_strategies.py`, `test_seed.py`, `tests/integration/test_train_smoke.py`, `test_train_full_cpu.py`, `test_adapt_smoke.py`, `test_evaluate_cli.py`.
- **의존**: T2, T4, T5, T6.
- **검증**: `make smoke`(= `uv run python scripts/train.py +exp=syn_e01_frame_source_only`) 60 s 내 종료, MLflow run 1개(status `smoke_ok`), `outputs/.../eval_test.json`·`checkpoint.pt` 존재, registry 1줄; `make smoke-video`(e02); `make smoke-adapt`(e02 run id → `scripts/adapt.py +exp=syn_e03_video_full_ft_bf_only adaptation.source_run_id=<id>`) → `regression_check.json`; `uv run pytest tests/integration/test_train_full_cpu.py -m slow` — `full_cpu_ok.yaml`로 gate 통과 + 2 epoch 완주 + 같은 seed 2회 metric `allclose(atol=1e-6)`.
- **규모**: ~1,100줄 + 테스트 ~450줄.

### T8 — 리포트 생성기
- **산출물**: `reporting/{template,report}.py`, `scripts/summarize_experiment.py`, `tests/unit/test_report.py`, `tests/integration/test_summarize.py`.
- **의존**: T7.
- **검증**: `uv run python scripts/summarize_experiment.py --experiment-id exp_syn_e03_video_full_ft_bf_only --baseline-experiment-id exp_syn_e02_video_source_only --include-smoke -o experiments/reports/exp_syn_e03.md` → §44 헤딩 17개 전부 존재, "SYNTHETIC SANITY — NOT A RESEARCH RESULT" 배너; e03(parent 다름)을 e02와 `--justify` 없이 비교하면 `ProtocolMismatchError` exit 6; `--justify "ablation: adaptation enabled"` 시 상단 `NOT DIRECTLY COMPARABLE` 배너.
- **규모**: ~350줄 + 테스트 ~150줄.

### T9 — Hooks + settings.json hooks 블록
- **산출물**: `.claude/hooks/*.py` 6개, `settings.json`에 `hooks` 추가, `tests/hooks/*` 7개, `tests/fixtures/hook_inputs/*.json`.
- **의존**: T5(validate_spec), T7(train.py 존재).
- **검증**: `uv run pytest tests/hooks -q`; 수동 파이프 테스트(아래 "Claude Code 하네스" 절 명령); 실제 `claude` 세션에서 `rm -rf data/raw` 시도 → deny 메시지에 `DG-01` 표시 확인.
- **규모**: ~600줄 + 테스트 ~300줄.

### T10 — Research store (claims / papers / hypotheses / ADR-001~004) — T6~T9와 병렬
- **산출물**: `research/claims.py`, `research/claims/{claims.jsonl,README.md}`, `research/papers/paper_index.yaml`, `research/hypotheses/H1-H4.md`, `ADR-001~004`, `ADR-005` 최종화, `tests/unit/test_claims.py`.
- **의존**: T1.
- **검증**: `uv run pytest tests/unit/test_claims.py`; `uv run python -c "from pad_research.research.claims import validate_claims_file as v;print(v('research/claims/claims.jsonl'))"` → `[]`; ADR 5개 모두 `## Status` 다음 줄이 `Accepted`.
- **규모**: ~120줄 코드 + 문서 ~300줄.

### T11 — DoD 점검 + README + end-to-end 리허설
- **산출물**: `tests/test_dod_files.py`, `README.md` 완성(H100 이관 절차, `permissions.deny` 승격 안내, DoD 23항목 표), `make verify-dod`.
- **의존**: 전부.
- **검증**: `make ci-local`(= `ruff check . && ruff format --check . && pyright src && pytest -m "not slow"`), `make test-all`, 아래 "검증 방법" 표의 명령 전부 실행.
- **규모**: ~150줄.

### T12 (선택, 사용자 결정 #1) — GitHub Actions 1 job
- `.github/workflows/ci.yml`: `astral-sh/setup-uv`, `uv sync --extra cpu --extra dev --frozen`, `ruff check`, `pyright src`, `pytest -m "not slow"`. 실데이터/시크릿 없음. ADR-005에 "§39 예외 사유: 재현성 게이트" 기록.

---

## 컴포넌트 상세 설계

### 1. pyproject & 환경

```toml
[project]
name = "pad-research"
version = "0.1.0"
description = "Passive Video PAD + Domain Adaptation research harness"
requires-python = ">=3.11,<3.12"
license = "MIT"
dependencies = [
  "hydra-core>=1.3.2,<1.4",
  "omegaconf>=2.3,<2.4",
  "pydantic>=2.7,<3",
  "mlflow>=2.15",
  "numpy>=1.26",
  "scikit-learn>=1.4",
  "matplotlib>=3.8",
  "pyyaml>=6",
]

[project.optional-dependencies]
cpu   = ["torch>=2.5", "torchvision>=0.20"]   # torch는 base deps에 없음 (D10)
cu124 = ["torch>=2.5", "torchvision>=0.20"]
dev   = ["pytest>=8", "pytest-timeout>=2.3", "ruff>=0.6", "pyright>=1.1.380", "dvc>=3.50"]

[tool.uv]
conflicts = [[{ extra = "cpu" }, { extra = "cu124" }]]

[[tool.uv.index]]
name = "pytorch-cpu"
url = "https://download.pytorch.org/whl/cpu"
explicit = true

[[tool.uv.index]]
name = "pytorch-cu124"           # H100 nvidia-smi 확인 후 cu126으로 교체 가능 (URL 1줄 + uv lock)
url = "https://download.pytorch.org/whl/cu124"
explicit = true

[tool.uv.sources]
torch       = [{ index = "pytorch-cpu", extra = "cpu" }, { index = "pytorch-cu124", extra = "cu124" }]
torchvision = [{ index = "pytorch-cpu", extra = "cpu" }, { index = "pytorch-cu124", extra = "cu124" }]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/pad_research"]

[tool.ruff]
line-length = 100
target-version = "py311"
src = ["src", "tests", "scripts"]
[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "N", "SIM", "RUF"]
ignore = ["E501"]
[tool.ruff.lint.per-file-ignores]
"tests/**" = ["N802", "N806"]
".claude/hooks/**" = ["T201"]

[tool.pyright]
include = ["src", "scripts"]
typeCheckingMode = "standard"
pythonVersion = "3.11"
venvPath = "."
venv = ".venv"
reportMissingTypeStubs = false

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra -q --strict-markers --timeout=300"
markers = ["integration: end-to-end CLI tests", "protocol: protocol integrity tests", "slow: > 30s", "hooks: subprocess hook tests"]
filterwarnings = ["ignore::DeprecationWarning:mlflow.*"]
```

- 샌드박스: `uv sync --extra cpu --extra dev`. H100: `uv sync --extra cu124 --extra dev --frozen`. `lock_hash = sha256(uv.lock)`를 env snapshot과 MLflow tag에 기록.
- `Makefile` 타깃: `setup-cpu`, `setup-cu124`, `lock`, `lint`, `format`, `typecheck`, `test`(`pytest -m "not slow"`), `test-all`, `ci-local`, `manifests`(make_synthetic_data), `validate-protocols`, `smoke`, `smoke-video`, `smoke-adapt RUN=<id>`, `freeze EXP=<name>`, `report EXP=<id> BASE=<id>`, `mlflow-ui`, `verify-dod`(= `pytest tests/test_dod_files.py -v`), `clean-outputs`(outputs/ multirun/만; data/mlruns/checkpoints는 절대 미접촉).
- `.gitignore`: `.venv/ outputs/ multirun/ mlruns/ mlruns.db mlruns_artifacts/ checkpoints/* !checkpoints/.gitkeep data/raw/* data/processed/* !**/.gitkeep __pycache__/ .pytest_cache/ .ruff_cache/ *.pt *.pth .dvc/cache .dvc/tmp .env`. 추적: `data/manifests/`, `experiments/specs/`, `experiments/reports/`, `experiments/registry.jsonl`.
- DVC: `dvc init`은 로컬에서 실행(`.dvc/config` 커밋, remote 없음), `dvc.yaml`:

```yaml
stages:
  synthetic_data:
    cmd: uv run python scripts/make_synthetic_data.py --dataset synthetic_a --dataset synthetic_b
    deps: [src/pad_research/data/adapters/synthetic.py, src/pad_research/data/manifest.py]
    outs:
      - {path: data/manifests/synthetic_a.jsonl, cache: false}
      - {path: data/manifests/synthetic_b.jsonl, cache: false}
```

### 2. Hydra config

`configs/config.yaml`:
```yaml
defaults:
  - _self_
  - model: frame_baseline
  - data: synthetic
  - adaptation: none
  - protocol: syn_a_to_b_v1
  # exp 그룹은 defaults에 두지 않는다 → 항상 `+exp=<name>` (Hydra 1.3 실동작을 test_compose에서 확인)

experiment:
  id: exp_dev_scratch
  title: scratch
  hypothesis: ""
  research_question: RQ1
  parent_experiment_id: null

training:
  seed: 42
  epochs: 1
  batch_size: 8
  learning_rate: 1.0e-3
  weight_decay: 0.0
  optimizer: adamw
  deterministic: true
  device: auto            # auto|cpu|cuda
  num_workers: 0
  checkpoint_selection: last   # last | best_dev_acer

evaluation:
  metrics: [APCER, BPCER, ACER, HTER, AUC]
  per_attack_apcer: true
  measure_latency: true
  latency: {warmup: 2, repetitions: 5, batch_size: 1}
  baseline_experiment_id: null   # adapt.py의 security gate baseline (protocol_hash는 gate가 검사)

execution:
  mode: smoke               # smoke | full
  smoke_test_first: true
  allow_full_gpu_run: false # 파일 안에서만 true 허용
  allow_dirty_tree: false
  require_gpu: false
  expected_gpu: null
  smoke: {max_batches: 2, max_epochs: 1, max_eval_batches: 2, latency_repetitions: 1}

tracking:
  mlflow_experiment: pad-dev
  tracking_uri: null        # null → env MLFLOW_TRACKING_URI → sqlite:///mlruns.db (tracker가 해석, spec/hash 밖)
  run_name: null
  log_checkpoint: true
  extra_tags: {}

hydra:
  run:   {dir: outputs/${experiment.id}/${now:%Y%m%d-%H%M%S}}
  sweep: {dir: multirun/${experiment.id}/${now:%Y%m%d-%H%M%S}, subdir: "${hydra.job.num}"}
  job:   {chdir: false}
```

`configs/model/video_baseline.yaml`:
```yaml
family: video_baseline
checkpoint: null
input: {modality: rgb, frames: 8, frame_sampling: uniform, image_size: [32, 32]}
net:
  _target_: pad_research.models.video.video_baseline.FrameEncoderTemporalTransformer
  embed_dim: 64
  width: 16
  depth: 1
  heads: 4
  pooling: mean
```
`configs/model/frame_baseline.yaml`: `family: frame_baseline`, `input.frames: 1`, `net._target_: pad_research.models.frame.frame_baseline.TinyFrameBaseline`, `embed_dim: 64, width: 16`.

`configs/data/synthetic.yaml`:
```yaml
name: synthetic
manifests_dir: data/manifests      # repo 상대경로 (절대경로 금지)
root_env_var: PAD_DATA_ROOT        # 실제 경로는 env에서만
loader: {batch_size: ${training.batch_size}, num_workers: ${training.num_workers}, pin_memory: false}
transform: {normalize: unit}
```
`configs/data/replay_attack.yaml`: `name: replay_attack`, `manifests_dir: data/manifests`, `root_env_var: PAD_DATA_ROOT`, `note: "Phase 1: build manifest via scripts/build_manifest.py --adapter replay_attack"`.

`configs/adaptation/full_finetune.yaml`:
```yaml
enabled: true
method: full_finetune
implemented: true
source_run_id: null        # MLflow run id (checkpoint artifact)
source_checkpoint: null    # 또는 로컬 경로
epochs: 1
learning_rate: 1.0e-4
batch_size: 8
```
`head_only.yaml` 동일 구조(`method: head_only`), `none.yaml`(`enabled: false, method: none, implemented: true`), `prototype.yaml`/`spoof_preserve.yaml`(`enabled: true, method: prototype|spoof_preserve, implemented: false`).

`configs/exp/syn_e03_video_full_ft_bf_only.yaml`:
```yaml
# @package _global_
defaults:
  - override /model: video_baseline
  - override /data: synthetic
  - override /adaptation: full_finetune
  - override /protocol: syn_a_to_b_bf_adapt_v1
experiment:
  id: exp_syn_e03_video_full_ft_bf_only
  title: synthetic_naive_bf_only_full_finetune
  hypothesis: "Synthetic sanity only: pipeline exercises E03 (naive bona-fide-only full FT). Not a research result."
  research_question: RQ2
  parent_experiment_id: exp_syn_e02_video_source_only
training: {seed: 42, epochs: 2, batch_size: 8, learning_rate: 1.0e-3}
adaptation: {epochs: 1}
evaluation: {baseline_experiment_id: exp_syn_e02_video_source_only}
execution: {mode: smoke, allow_full_gpu_run: false, require_gpu: false, expected_gpu: null}
tracking: {mlflow_experiment: pad-synthetic-sanity}
```
e01/e02는 `adaptation: none`, protocol `syn_a_to_b_v1`, e01은 `model: frame_baseline`.

H100 실험 파일은 `execution: {mode: full, allow_full_gpu_run: true, require_gpu: true, expected_gpu: H100}`을 **파일에** 적어 커밋한다.

`config/compose.py`:
```python
def compose_spec(overrides: list[str], config_name: str = "config") -> tuple[DictConfig, ExperimentSpec]:
    with initialize_config_dir(version_base="1.3", config_dir=str(CONFIGS_DIR)):
        cfg = compose(config_name=config_name, overrides=overrides)
    raw = OmegaConf.to_container(cfg, resolve=True, throw_on_missing=True)
    raw = {k: v for k, v in raw.items() if k != "hydra"}
    return cfg, ExperimentSpec.model_validate(raw)

def spec_from_cfg(cfg: DictConfig) -> ExperimentSpec  # @hydra.main 경로용, 동일 검증
def task_overrides() -> list[str]                      # HydraConfig.get().overrides.task (main 경로) / argparse 목록 (CLI 경로)
```

### 3. Dataset manifest / adapters / 합성 데이터

`data/manifest.py`:
```python
class Label(StrEnum): bona_fide = "bona_fide"; spoof = "spoof"
class PAI(StrEnum):
    none = "none"; print = "print"; replay = "replay"; replay_phone = "replay_phone"
    replay_tablet = "replay_tablet"; replay_display = "replay_display"; display = "display"
    mask_3d = "mask_3d"; other = "other"
class Split(StrEnum): train = "train"; dev = "dev"; test = "test"          # adapt 없음 (D6)
class MediaType(StrEnum): video = "video"; frames_dir = "frames_dir"; image = "image"; npy_clip = "npy_clip"

class ManifestRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    dataset_id: str                 # ^[a-z0-9_]+$ (validator가 lower()로 정규화 → §15 예시 대문자도 통과)
    sample_id: str                  # ^[A-Za-z0-9_\-.]+$, dataset 내 유일
    subject_id: str
    split: Split
    label: Label
    pai: PAI                        # bona_fide ⇔ pai == none (model_validator)
    pai_detail: str | None = None
    relative_path: str              # 절대경로/".."/선행 "/" 거부
    media_type: MediaType
    fps: float | None = None; n_frames: int | None = None; width: int | None = None; height: int | None = None
    capture_device: str | None = None; session: str | None = None; environment: str | None = None
    official_protocol: str | None = None
    extra: dict[str, str | int | float | bool] = {}

class ManifestMeta(BaseModel):
    dataset_id: str; version: str; adapter: str; license: str; pii_policy: Literal["synthetic","internal_only","licensed_research"]
    root_env_var: str = "PAD_DATA_ROOT"; temporal_valid: bool; manifest_hash: str; n_records: int; n_subjects: int
    splits: dict[str, dict[str, int]]; pai_counts: dict[str, int]; created_at: str; generator_commit: str | None

def manifest_hash(records: Sequence[ManifestRecord]) -> str      # sample_id 정렬 → canonical_json 줄 결합 → sha256
def write_manifest(records, meta_partial, out_dir: Path) -> ManifestMeta   # <id>.jsonl + <id>.meta.json
def load_manifest(dataset_id: str, manifests_dir: Path) -> Manifest        # Manifest{records, meta, by_split(), subjects()}
def verify_manifest_hash(m: Manifest) -> None                              # 불일치 → ManifestTamperedError
def resolve_path(record: ManifestRecord, root: Path) -> Path
def data_root(root_env_var: str) -> Path                                    # env 미설정 → DataRootNotConfiguredError
```

`data/adapters/base.py`:
```python
class DatasetAdapter(ABC):
    dataset_id: str; version: str; license: str; pii_policy: str; temporal_valid: bool = True
    @abstractmethod
    def build_manifest(self, root: Path) -> list[ManifestRecord]: ...
    def meta_partial(self) -> dict: ...
ADAPTERS: dict[str, type[DatasetAdapter]] = {"synthetic": SyntheticAdapter}   # Phase 1: "replay_attack": ReplayAttackAdapter
```

`data/adapters/synthetic.py`:
```python
@dataclass(frozen=True)
class SyntheticDomain: brightness: float; gain: float; noise_std: float; color_cast: tuple[float,float,float]; blur: int
SYN_DOMAINS = {"synthetic_a": SyntheticDomain(0.0, 1.0, 0.02, (0,0,0), 0),
               "synthetic_b": SyntheticDomain(-0.15, 1.3, 0.05, (0.05,-0.03,0.02), 1)}
class SyntheticAdapter(DatasetAdapter):
    def __init__(self, dataset_id: str, n_subjects=20, clips_per_subject=6, num_frames=16, size=(32,32), fps=30.0,
                 split_ratio=(0.6,0.2,0.2), subject_offset=0): ...
    def build_manifest(self, root: Path) -> list[ManifestRecord]
        # subject 단위 split (12/4/4), subject당 bona_fide 3 / print 1 / replay_phone 1 / replay_tablet 1
        # relative_path = f"{dataset_id}/{sample_id}.npy", media_type npy_clip, 클립을 root 아래에 실제로 저장
def generate_clip(sample_id: str, pai: PAI, domain: SyntheticDomain, T: int, H: int, W: int) -> np.ndarray  # uint8 [T,H,W,3]
    # rng = np.random.default_rng(int.from_bytes(sha256(sample_id.encode())[:8], "little"))
```
`scripts/make_synthetic_data.py --dataset <id>... [--root $PAD_DATA_ROOT] [--manifests-dir data/manifests]` — root 기본값은 `data/processed`(env 미설정 시), 두 번 실행해도 바이트 동일.

`data/clip_dataset.py`:
```python
def read_clip(record: ManifestRecord, root: Path) -> np.ndarray   # npy_clip: np.load; video/frames_dir/image → NotImplementedError("Phase 1")
class ClipDataset(Dataset):
    def __init__(self, records: list[ManifestRecord], root: Path, frames: int, sampling: str, image_size: tuple[int,int], train: bool, seed: int)
    def __getitem__(self, i) -> dict   # {"clip": float32 [T,3,H,W] in [0,1], "label": int, "pai": str, "sample_id": str, "subject_id": str}
def collate(batch) -> dict[str, Tensor | list[str]]
```
`data/sampling.py::sample_frame_indices(n_frames: int, T: int, strategy: Literal["uniform","consecutive","random_crop"], rng: np.random.Generator|None) -> list[int]` (T=1이면 중앙 프레임; n_frames < T면 반복 패딩).

`data/splits.py`:
```python
@dataclass
class ProtocolSplits:
    source_train: list[ManifestRecord]; source_dev: list[ManifestRecord]
    target_dev: list[ManifestRecord]; target_test: list[ManifestRecord]; adaptation: list[ManifestRecord]
def build_splits(protocol: ProtocolSpec, manifests: dict[str, Manifest], adaptation_set: AdaptationSet | None) -> ProtocolSplits
    # target_test = target test split − adaptation sample_ids (exclude_adaptation_samples) ; assert disjoint (subject도)
```

### 4. Protocol schema / hash / validators

`protocols/schema.py`:
```python
class TargetAdaptation(BaseModel):
    enabled: bool
    supervision: Literal["none","bona_fide_only","bona_fide_and_spoof_fewshot"] = "none"
    shots_per_subject: int | None = None
    total_samples: int | None = None
    source_split: Split = Split.train           # test 금지 (validator ADAPT_FROM_TEST_SPLIT)
    selection_seed: int = 0
    subject_disjoint_from_test: bool = True
    # model_validator: enabled ⇒ supervision != none and (shots xor total)

class TargetTest(BaseModel):
    exclude_adaptation_samples: bool = True
    split: Split = Split.test

class ThresholdSpec(BaseModel):
    source: Literal["dev_set"] = "dev_set"     # test 불허 (타입으로)
    policy: Literal["fixed_after_dev"] = "fixed_after_dev"
    rule: Literal["eer","bpcer_at_apcer"] = "eer"
    rule_param: float | None = None            # bpcer_at_apcer의 target APCER
    dev_domain: Literal["source","target"] = "source"

class SecurityGateConfig(BaseModel):
    abs_tolerance: float = 0.01
    rel_tolerance: float = 0.0
    min_attack_samples_per_pai: int = 20

class ProtocolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    protocol_id: str = Field(pattern=r"^[a-z0-9_]+_v\d+$")
    status: Literal["active","draft"] = "active"          # hash 제외
    description: str = ""                                  # hash 제외
    parent_protocol_id: str | None = None                  # hash 제외; 있으면 change_note 필수
    change_note: str | None = None                         # hash 제외
    source_datasets: list[str] = Field(min_length=1)       # lower() 정규화
    target_dataset: list[str] = []
    source_classes: list[Label] = [Label.bona_fide, Label.spoof]
    target_adaptation: TargetAdaptation
    target_test: TargetTest = TargetTest()
    attack_types: list[PAI] = Field(min_length=1)          # generic "replay" 허용
    threshold: ThresholdSpec = ThresholdSpec()
    acer_policy: Literal["max_pai","pooled"] = "max_pai"
    security_gate: SecurityGateConfig = SecurityGateConfig()
    allow_image_dataset_as_clip: bool = False

def pai_matches(protocol_pai: PAI, record_pai: PAI) -> bool   # replay ↔ replay_* prefix, display ↔ replay_display, 그 외 동일성
```
`protocols/hashing.py`:
```python
HASH_EXCLUDED = frozenset({"description", "parent_protocol_id", "change_note", "status"})
def protocol_hash(p: ProtocolSpec) -> str:
    return sha256(canonical_json(p.model_dump(mode="json", exclude=HASH_EXCLUDED)).encode()).hexdigest()
def short_hash(h: str) -> str: return h[:12]
```
`utils/canonical_json.py::canonical_json(obj) = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)` (리스트 순서 보존, float는 json 기본 repr).

`protocols/validator.py`:
```python
class ValidationIssue(BaseModel): code: str; severity: Literal["error","warning"]; message: str; details: dict = {}
class ProtocolValidation(BaseModel):
    protocol_id: str; protocol_hash: str; status: str; manifest_hashes: dict[str, str]
    adaptation_set_hash: str | None; issues: list[ValidationIssue]
    @property
    def ok(self) -> bool: ...   # error 없음
def validate_protocol(p: ProtocolSpec, manifests_dir: Path, *, frames: int = 1, require_manifests: bool | None = None) -> ProtocolValidation
```
error codes: `MISSING_MANIFEST`(draft면 warning), `MANIFEST_HASH_MISMATCH`, `SUBJECT_OVERLAP_SPLITS`, `SOURCE_TARGET_DATASET_OVERLAP`, `LABEL_PAI_INCONSISTENT`, `ATTACK_TYPE_ABSENT_IN_TEST`(pai_matches 사용), `ADAPT_FROM_TEST_SPLIT`, `ADAPT_TEST_SAMPLE_OVERLAP`, `ADAPT_TEST_SUBJECT_OVERLAP`, `ADAPT_SUPERVISION_LABEL_MISMATCH`, `ADAPT_TEST_NOT_EXCLUDED`(`exclude_adaptation_samples=false`), `IMAGE_DATASET_AS_CLIP`(`temporal_valid=False and frames>1 and not allow_image_dataset_as_clip`), `THRESHOLD_SOURCE_NOT_DEV`, `TARGET_REQUIRED`, `PARENT_REQUIRES_CHANGE_NOTE`. warning: `SMALL_PAI_SUPPORT`(< `min_attack_samples_per_pai`), `DEV_DOMAIN_TARGET_WITHOUT_SPOOF`.

`protocols/adaptation_set.py`:
```python
class AdaptationSet(BaseModel): protocol_id: str; protocol_hash: str; sample_ids: list[str]; subject_ids: list[str]; adaptation_set_hash: str; path: str
def materialize_adaptation_set(protocol: ProtocolSpec, target: Manifest, out_dir: Path) -> AdaptationSet
    # 정렬 → random.Random(selection_seed).sample → data/manifests/adaptation/<protocol_id>.<hash12>.jsonl (이미 있고 hash 같으면 재사용)
```
`protocols/compare.py`:
```python
class Comparability(StrEnum): same_hash = "same_hash"; justified_diff = "justified_diff"
class ProtocolMismatchError(RuntimeError): ...
def assert_comparable(a_hash: str, b_hash: str, justify: str | None) -> Comparability
```

`configs/protocol/syn_a_to_b_bf_adapt_v1.yaml`:
```yaml
protocol_id: syn_a_to_b_bf_adapt_v1
status: active
description: "Synthetic sanity: A -> B with bona-fide-only adaptation (24 samples)"
parent_protocol_id: syn_a_to_b_v1
change_note: "target_adaptation.enabled false -> true, bona_fide_only, total_samples 24"
source_datasets: [synthetic_a]
target_dataset: [synthetic_b]
source_classes: [bona_fide, spoof]
target_adaptation: {enabled: true, supervision: bona_fide_only, shots_per_subject: null, total_samples: 24, source_split: train, selection_seed: 0, subject_disjoint_from_test: true}
target_test: {exclude_adaptation_samples: true, split: test}
attack_types: [print, replay_phone, replay_tablet]
threshold: {source: dev_set, policy: fixed_after_dev, rule: eer, rule_param: null, dev_domain: source}
acer_policy: max_pai
security_gate: {abs_tolerance: 0.01, rel_tolerance: 0.0, min_attack_samples_per_pai: 20}
allow_image_dataset_as_clip: false
```
`ocim_target_i_v1.yaml`은 §15 예시를 그대로(`source_datasets: [OULU_NPU, CASIA_FASD, MSU_MFSD]`, `attack_types: [print, replay]` 등) + `status: draft`.

테스트(고정값): `test_hash_golden_value`(구현 시 첫 계산값을 pin), `test_hash_stable_under_key_order`, `test_hash_ignores_parent_description_status_change_note`, `test_hash_sensitive_to_total_samples`(100→101), `test_hash_sensitive_to_acer_policy`, `test_hash_sensitive_to_gate_tolerance`, `test_hash_includes_protocol_id`, `test_parent_protocol_requires_change_note`, `test_yaml_roundtrip_matches_section15`(fixture = §15 YAML + `protocol_id`만 있음 → 기본값으로 로드), `test_pai_matches_replay_prefix`, `test_every_protocol_yaml_valid_or_draft`(parametrize), `test_active_protocols_have_manifests`, leakage: `test_subject_overlap_detected`, `test_adapt_test_sample_overlap_detected`, `test_adapt_test_subject_overlap_detected`, `test_adapt_from_test_split_rejected`, `test_image_dataset_as_clip_rejected`, `test_attack_type_absent_detected`, `test_label_pai_inconsistent_detected`, `test_materialize_is_deterministic`, `test_materialize_bona_fide_only`, `test_assert_comparable_raises_without_justify`.

### 5. PAD metrics & tests

`metrics/pad_metrics.py` (규약: `y_attack: bool[]`(True=spoof), `score: float[]`(높을수록 spoof), `pai: str[]`, `predict_attack = score >= tau`):
```python
def apcer_per_pai(score, y_attack, pai, tau) -> dict[str, float]   # PAI별 (score<tau)/n_pai; 공격 0개인 PAI는 제외; 전체 공격 없으면 EmptyPAIError
def apcer_pooled(score, y_attack, tau) -> float
def apcer_max(per_pai: dict[str, float]) -> float
def bpcer(score, y_attack, tau) -> float
def acer(apcer_value: float, bpcer_value: float) -> float           # (a+b)/2; a는 acer_policy에 따라 max 또는 pooled
def hter(apcer_pooled_value: float, bpcer_value: float) -> float    # 항상 pooled
def roc_auc(score, y_attack) -> float                               # sklearn.roc_auc_score
def eer_threshold(score_dev, y_attack_dev) -> tuple[float, float]   # (tau, eer); roc_curve(drop_intermediate=False), thr[0]==inf 제외, argmin|fpr-fnr| 첫 index
def bpcer_at_apcer(score_dev, y_attack_dev, target_apcer) -> tuple[float, float]
def compute_pad_metrics(score, y_attack, pai, tau, acer_policy) -> PadMetrics
class PadMetrics(BaseModel):
    tau: float; apcer_per_pai: dict[str,float]; apcer_max: float; apcer_pooled: float; apcer: float  # apcer = policy 선택값
    bpcer: float; acer: float; hter: float; auc: float; acer_policy: str; n_bona_fide: int; n_attack_per_pai: dict[str,int]
```
`metrics/threshold.py`:
```python
class ThresholdLeakageError(RuntimeError): ...
class NotFittedError(RuntimeError): ...
class ThresholdPolicy(BaseModel):
    spec: ThresholdSpec; tau: float | None = None; fitted_on: str | None = None
    dev_n_bona_fide: int | None = None; dev_n_attack: int | None = None; dev_eer: float | None = None
    def fit(self, score, y_attack, *, split_name: str) -> "ThresholdPolicy"   # split_name != "dev" → ThresholdLeakageError
    def apply(self, score) -> np.ndarray                                       # tau None → NotFittedError
```
`metrics/security_gate.py`:
```python
class PaiDelta(BaseModel): pai: str; apcer_before: float; apcer_after: float; delta: float; n_attack: int; regressed: bool; insufficient_support: bool
class SecurityGateResult(BaseModel):
    verdict: Literal["pass","security_regression","inconclusive","comparison_blocked"]
    per_pai: list[PaiDelta]; bpcer_before: float; bpcer_after: float; bpcer_delta: float; bpcer_improved: bool
    auc_before: float; auc_after: float; protocol_hash: str | None; note: str
def run_security_gate(before: PadMetrics, after: PadMetrics, before_hash: str, after_hash: str, cfg: SecurityGateConfig, justify: str | None = None) -> SecurityGateResult
    # regressed = delta > max(abs_tol, rel_tol*apcer_before); 지지 부족 PAI는 insufficient_support
    # hash 불일치: justify 없으면 ProtocolMismatchError, 있으면 verdict comparison_blocked + note
```

Toy vectors (`tests/unit/test_metrics.py`, `tau=0.5`; bona `[0.1,0.2,0.3,0.7]`, print `[0.9,0.8,0.4,0.6]`, replay_phone `[0.3,0.2,0.9,0.95,0.1]`):
| 테스트 | 기대값 |
|---|---|
| `test_bpcer_toy` | 0.25 |
| `test_apcer_per_pai_toy` | `{print: 0.25, replay_phone: 0.6}` |
| `test_apcer_max_toy` | 0.6 |
| `test_apcer_pooled_toy` | 4/9 |
| `test_acer_iso_max_pai` | 0.425 |
| `test_hter_pooled` | (4/9+0.25)/2 = 0.34722… |
| `test_acer_max_pai_vs_hter_pooled_differ` | 0.425 ≠ 0.3472 |
| `test_bpcer_boundary_score_equal_threshold_is_spoof` | bona `[0.5]`, tau 0.5 → BPCER 1.0 |
| `test_eer_threshold_separable` | dev bona `[0.1,0.2,0.3,0.4]`, attack `[0.6,0.7,0.8,0.9]` → `tau=0.6, eer=0.0`; test bona `[0.1,0.5,0.65,0.2]`, attack `[0.55,0.7,0.9,0.61]` → BPCER 0.25, APCER 0.25, HTER 0.25 |
| `test_eer_threshold_overlap` | dev bona `[0.2,0.4,0.6,0.8]`, attack `[0.3,0.5,0.7,0.9]` → `tau=0.6, eer=0.5` |
| `test_auc_perfect` / `test_auc_partial` / `test_auc_ties_half` | 1.0 / 0.625 / 0.5 |
| `test_empty_pai_raises` | `EmptyPAIError` |
| `test_label_convention_spoof_is_one` | `conventions.LABEL_SPOOF == 1` |
`test_threshold.py`: `test_threshold_fit_on_test_raises`, `test_apply_before_fit_raises`, `test_fit_records_dev_stats`. `test_security_gate.py`: before `{print .02, replay_phone .02}` BPCER .08 / after `{print .02, replay_phone .15}` BPCER .02, n=50 → `security_regression`, `replay_phone.delta == 0.13`, `bpcer_improved True`; `test_gate_within_tolerance_passes`(after replay .025); `test_gate_insufficient_attack_samples_inconclusive`(n=10); `test_gate_refuses_protocol_hash_mismatch`; `test_gate_justified_mismatch_is_comparison_blocked`; `test_auc_improvement_does_not_change_verdict`.

### 6. Threshold policy & security regression gate (실행 경로)
- `evaluate(model, dev_loader, test_loader, protocol, device, limits)`는 dev `ScoreTable(role="dev")`로 `ThresholdPolicy.fit(split_name="dev")` → test `ScoreTable(role="test")`에 `apply` → `compute_pad_metrics(acer_policy=protocol.acer_policy)`. `ScoreTable.role != "dev"`인 테이블을 `fit`에 넘기는 코드는 컴파일 단계에서 없고, 런타임에도 `ThresholdLeakageError`.
- `adapt.py`: `protocol.threshold.dev_domain == source`면 source checkpoint의 `ThresholdPolicy`를 재사용(`fixed_after_dev`), `target`이면 target dev로 재fit. baseline은 `evaluation.baseline_experiment_id` + 같은 `protocol_hash` + status ∈ {success, smoke_ok(smoke 모드일 때)} 최신 run; 없으면 `inconclusive` + note. 결과 `regression_check.json` artifact + status tag/registry 갱신(`security_regression|inconclusive|success|smoke_ok`).

### 7. Experiment spec / validator / registry

`config/schema.py`:
```python
class ExperimentMeta(BaseModel): id: str = Field(pattern=r"^exp_[a-z0-9_]+$"); title: str; hypothesis: str; research_question: Literal["RQ1","RQ2","RQ3","RQ4","harness"]; parent_experiment_id: str | None = None
class InputSpec(BaseModel): modality: Literal["rgb"] = "rgb"; frames: int = Field(ge=1, le=64); frame_sampling: Literal["uniform","consecutive","random_crop"]; image_size: tuple[int,int]
class ModelSpec(BaseModel): family: Literal["frame_baseline","video_baseline"]; checkpoint: str | None; input: InputSpec; net: dict
class DataSpec(BaseModel): name: str; manifests_dir: str; root_env_var: str = "PAD_DATA_ROOT"; loader: dict; transform: dict
    # field_validator: manifests_dir는 상대경로여야 함
class AdaptationSpec(BaseModel): enabled: bool; method: Literal["none","full_finetune","head_only","prototype","spoof_preserve"]; implemented: bool = True
    source_run_id: str | None = None; source_checkpoint: str | None = None; epochs: int = 1; learning_rate: float = 1e-4; batch_size: int = 8
class TrainingSpec(BaseModel): seed: int; epochs: int; batch_size: int; learning_rate: float; weight_decay: float = 0.0; optimizer: Literal["adamw","sgd"] = "adamw"
    deterministic: bool = True; device: Literal["auto","cpu","cuda"] = "auto"; num_workers: int = 0; checkpoint_selection: Literal["last","best_dev_acer"] = "last"
class LatencySpec(BaseModel): warmup: int = 2; repetitions: int = 5; batch_size: int = 1
class EvaluationSpec(BaseModel): metrics: list[Literal["APCER","BPCER","ACER","HTER","AUC"]]; per_attack_apcer: bool = True; measure_latency: bool = True; latency: LatencySpec; baseline_experiment_id: str | None = None
class SmokeLimits(BaseModel): max_batches: int = 2; max_epochs: int = 1; max_eval_batches: int = 2; latency_repetitions: int = 1
class ExecutionSpec(BaseModel): mode: Literal["smoke","full"] = "smoke"; smoke_test_first: bool = True; allow_full_gpu_run: bool = False; allow_dirty_tree: bool = False; require_gpu: bool = False; expected_gpu: str | None = None; smoke: SmokeLimits = SmokeLimits()
class TrackingSpec(BaseModel): mlflow_experiment: str = Field(min_length=1); tracking_uri: str | None = None; run_name: str | None = None; log_checkpoint: bool = True; extra_tags: dict[str,str] = {}

class ExperimentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    experiment: ExperimentMeta; model: ModelSpec; data: DataSpec; adaptation: AdaptationSpec; protocol: ProtocolSpec
    training: TrainingSpec; evaluation: EvaluationSpec; execution: ExecutionSpec; tracking: TrackingSpec
    @model_validator(mode="after")
    def _cross(self):
        # adaptation.enabled == protocol.target_adaptation.enabled ; method=="none" ⇔ not enabled
        # adaptation.implemented is False → ValueError("NOT_IMPLEMENTED_IN_PHASE0")
        # model.family == frame_baseline ⇒ frames >= 1 (T>1이면 per-frame 평균) ; video_baseline ⇒ frames >= 2
        # protocol.status == draft ⇒ execution.mode == smoke
        # execution.mode == full ⇒ allow_full_gpu_run (형식 검사; 출처 검사는 gate)
        # threshold.rule == bpcer_at_apcer ⇒ rule_param not None
def science_hash(spec) -> str   # exclude {"execution","tracking"}
def spec_hash(spec) -> str
```
`config/freeze.py::write_resolved_spec(spec, specs_dir) -> Path`(`<id>.resolved.yaml`, 헤더 주석에 `science_hash`, `spec_hash`, `protocol_hash`, 생성 시각), `read_frozen_spec(id) -> ExperimentSpec | None`.

`experiments/validator.py` (torch 미import; `pad_research/__init__.py` 비움):
```python
class SpecValidationReport(BaseModel):
    ok: bool; exit_code: int; errors: list[str]; warnings: list[str]
    experiment_id: str | None; science_hash: str | None; spec_hash: str | None; protocol_id: str | None; protocol_hash: str | None
    manifest_hashes: dict[str,str]; adaptation_set_hash: str | None; mode: str | None; gate: GateResult | None
def validate_spec(overrides: list[str], *, for_launch: bool, freeze: bool, repo_root: Path) -> SpecValidationReport
```
검사 순서: compose+Pydantic(실패 exit 2) → `validate_protocol(frames=model.input.frames)`(실패 exit 3) → `freeze`면 write → `for_launch`면 `check_full_run_gate(...)`(smoke면 allowed=True; full에서 거부 exit 4). `TRACKING_OK`는 mlflow를 import하지 않고 sqlite URI면 파일 디렉터리 쓰기 가능 여부, http면 warning. `GPU_OK`는 hook 경로에서 `nvidia-smi` 존재/출력으로 근사, 프로세스 내부에서 `torch.cuda`로 확정.

`experiments/gate.py`:
```python
@dataclass
class GateResult: allowed: bool; reasons: list[str]; checks: dict[str, bool]
def check_full_run_gate(spec: ExperimentSpec, env: EnvSnapshot | None, task_overrides: list[str], pv: ProtocolValidation,
                        tracking_ok: bool, registry: Registry, frozen: ExperimentSpec | None) -> GateResult
  # mode=="smoke" → allowed=True (checks 기록만)
  # ALLOW_FLAG, FLAG_NOT_FROM_CLI(overrides에 "execution." 접두 토큰 없음), PROTOCOL_OK(pv.ok and status active),
  # MANIFESTS_OK, GIT_OK(sha not None and (not dirty or allow_dirty_tree)), TRACKING_OK, GPU_OK,
  # SPEC_FROZEN(frozen is not None and science_hash(frozen)==science_hash(spec)),
  # SMOKE_OK(not smoke_test_first or registry.latest_success_smoke(science_hash, git_sha if not allow_dirty_tree else None) is not None)
```
`experiments/registry.py`:
```python
class RegistryRow(BaseModel): exp_id: str; seed: int; mode: str; science_hash: str; spec_hash: str; protocol_id: str; protocol_hash: str
    adaptation_set_hash: str | None; mlflow_run_id: str | None; status: str; git_sha: str | None; git_dirty: bool; started_at: str; finished_at: str | None; results_dir: str | None
class Registry:
    def __init__(self, path: Path = REGISTRY_PATH)
    def append(self, row: RegistryRow) -> None            # fcntl.flock, 한 줄 JSON
    def rows(self) -> list[RegistryRow]
    def latest_success_smoke(self, science_hash: str, git_sha: str | None) -> RegistryRow | None   # status == smoke_ok
    def find_runs(self, *, protocol_hash: str | None = None, exp_id: str | None = None, mode: str | None = None, status: set[str] | None = None) -> list[RegistryRow]
```
`experiments/status.py::RunStatus`: `running, smoke_ok, success, failed_environment, failed_training, invalid_protocol, security_regression, inconclusive, blocked_by_gate`. 시작 시 `running` row, 종료 시 최종 status row(같은 run_id로 두 줄; 실패도 반드시 기록 §35).

`scripts/validate_spec.py --exp NAME [--freeze] [--for-launch] [--json] [-- OVERRIDE ...]` exit: 0 ok / 2 spec / 3 protocol / 4 gate / 5 internal.

테스트: `test_spec_from_section16_example`(fixture: §16 YAML에서 `family: g2v2former`→`video_baseline`, dataset id 소문자, 주석 명시), `test_adaptation_protocol_mismatch_rejected`, `test_draft_protocol_forces_smoke`, `test_not_implemented_method_rejected`, `test_smoke_and_full_share_science_hash`, `test_spec_hash_machine_independent`(env `PAD_DATA_ROOT` 변경 후 동일), `test_resolved_spec_contains_no_absolute_paths`, `test_compose_default_config_validates`, `test_compose_each_exp_file_validates`(parametrize `configs/exp/*.yaml`), `test_override_frames_propagates`, `test_validator_does_not_import_torch`, `test_smoke_always_allowed`, `test_full_denied_without_flag`, `test_full_denied_when_flag_from_cli`, `test_full_denied_require_gpu_on_cpu`, `test_full_allowed_cpu_fixture`, `test_full_denied_dirty_tree`, `test_full_denied_without_frozen_spec`, `test_full_denied_without_prior_smoke`, `test_full_requires_prior_smoke_success_then_passes`(smoke row append 후 통과), `test_registry_append_and_query`, `test_registry_failed_run_is_kept`, CLI: `test_validate_spec_exit_codes`, `test_freeze_writes_resolved_yaml`, `test_for_launch_denies_cli_mode_full`.

### 8. MLflow tracking & env snapshot

`tracking/tags.py`:
```python
REQUIRED_TAGS = ("research_question","protocol_id","protocol_hash","model_family","adaptation_method","target_supervision","dataset_manifest_hash","git_sha","status")
EXTRA_TAGS = ("experiment_id","science_hash","spec_hash","execution_mode","seed","git_dirty","git_branch","lock_hash","parent_experiment_id","adaptation_set_hash","threshold_source","threshold_rule","research_claim_allowed","checkpoint_source","model_init")
REQUIRED_METRICS = ("apcer","bpcer","acer","hter","auc")
```
`tracking/env_snapshot.py`:
```python
class EnvSnapshot(BaseModel):
    timestamp_utc: str; hostname: str; platform: str; python_version: str; cpu_count: int
    git_sha: str | None; git_dirty: bool; git_branch: str | None; untracked_count: int
    torch_version: str | None; torchvision_version: str | None; cuda_available: bool; cuda_version: str | None; cudnn_version: int | None
    gpu_count: int; gpu_names: list[str]; driver_version: str | None      # nvidia-smi --query-gpu=driver_version
    lock_hash: str | None; pad_research_version: str; deterministic_algorithms: bool
def collect_env_snapshot(repo_root: Path, *, with_torch: bool = True) -> EnvSnapshot   # torch 없으면 None 필드
```
`tracking/mlflow_tracker.py`:
```python
class MlflowTracker:
    def __init__(self, tracking: TrackingSpec, repo_root: Path)     # uri 해석: spec → env MLFLOW_TRACKING_URI → sqlite:///mlruns.db
    def start_run(self, spec, pv: ProtocolValidation, env: EnvSnapshot, *, adaptation_set_hash=None, run_name=None) -> str
        # dataset_manifest_hash = ",".join(f"{id}:{h[:12]}" for id,h in sorted(...)); 필수 tag 누락 → ValueError
        # research_claim_allowed = "false" if any dataset_id startswith "synthetic" else "true"
        # log_params: training.*, model.family, model.input.*, adaptation.method, execution.mode
    def log_metrics(self, m: PadMetrics, *, prefix: str = "", step: int | None = None) -> None   # 5종 누락 → ValueError; apcer_<pai>, apcer_max, apcer_pooled, tau, eer_dev도 기록
    def log_epoch(self, epoch: int, train_loss: float, dev: PadMetrics | None) -> None
    def log_artifact_json(self, name: str, obj) / log_artifact_file(self, path: Path) / log_figure(self, fig, name: str)
    def find_baseline(self, experiment_id: str, protocol_hash: str, include_smoke: bool) -> BaselineRef | None
    def end_run(self, status: RunStatus) -> None                   # status tag 갱신
```
artifacts: `resolved_spec.yaml`, `protocol.json`, `env_snapshot.json`, `eval_test.json`, `scores_dev.csv`, `scores_test.csv`, `roc_curve.png`, `confusion.json`, `per_attack.csv`, `training_curves.csv`, `latency.json`, `checkpoint.pt`(smoke 포함 항상; tiny 모델이라 KB 단위), adapt: `adaptation_set.jsonl`, `regression_check.json`.

테스트: `test_start_run_sets_required_tags`, `test_missing_required_tag_raises`, `test_log_metrics_requires_all_five`, `test_end_run_status_tag`, `test_find_baseline_by_experiment_and_protocol_hash`, `test_synthetic_sets_research_claim_allowed_false`, `test_snapshot_fields_present`, `test_no_gpu_in_sandbox_is_recorded`, `test_lock_hash_matches_file`, `test_git_sha_and_dirty`, `test_cpu_extra_has_no_cuda`.

### 9. Models & adaptation strategies & training

`models/base.py`:
```python
@dataclass
class ModelOutput: logits: Tensor; clip_embedding: Tensor; frame_embeddings: Tensor | None   # logits (B,)
class PADModel(nn.Module):
    family: str
    def forward(self, clip: Tensor) -> ModelOutput      # clip (B,T,3,H,W) — frame/video 공통 계약
    def encoder_parameters(self) -> Iterator[nn.Parameter]
    def head_parameters(self) -> Iterator[nn.Parameter]
    def embed(self, clip: Tensor) -> Tensor            # (B,D) — Phase 5 prototype 확장점
```
- `encoders.TinyCNN(width=16, embed_dim=64)`: conv(3→w)→BN→ReLU→pool ×3, AdaptiveAvgPool, Linear→embed_dim (~50k params @32×32).
- `frame/frame_baseline.TinyFrameBaseline`: (B,T,…)→(B·T)→encoder→head→(B,T) logits → mean over T (T=1 기본).
- `video/video_baseline.FrameEncoderTemporalTransformer(embed_dim, width, depth=1, heads=4, pooling="mean")`: shared encoder per frame → (B,T,D) + learned pos-emb(≤64) → `nn.TransformerEncoder` → pool → head.
- `models/registry.build_model(model_cfg: dict) -> PADModel = hydra.utils.instantiate(model_cfg["net"])`.
- `adaptation/base.AdaptationStrategy(Protocol)`: `name`, `requires_grad`, `prepare(model, source_ckpt) -> None`, `trainable_parameters(model) -> list`, `loss(output, batch) -> Tensor`, `score(output) -> Tensor`(기본 sigmoid), `state() -> dict`. 구현: `NoAdaptation`(BCE, all params), `FullFinetune`(all params, BCE with label 0), `HeadOnly`(encoder `requires_grad=False`, BN eval, head만). `build_strategy(spec.adaptation)`; `prototype/spoof_preserve` → `NotImplementedError("Phase 5/6")`(validator가 이미 차단).
- `training/trainer.Trainer(model, strategy, loaders, spec, tracker, limits: SmokeLimits | None, device).fit() -> TrainResult{epochs_run, steps, train_curve, wall_clock_s, checkpoint_path}`; `limits`가 있으면 epoch당 `max_batches`에서 break, epoch = min(spec.epochs, max_epochs).
- `training/checkpoint.save_checkpoint(path, model, spec, threshold: ThresholdPolicy | None, protocol_hash, strategy_state) / load_checkpoint(path) -> Checkpoint{state_dict, spec, threshold, protocol_hash, science_hash, git_sha}`. `adapt.py`는 checkpoint의 `protocol_hash`가 현재 protocol hash 또는 `parent_protocol_id`의 hash와 같지 않으면 `CheckpointProtocolMismatchError`.
- `utils/seed.seed_everything(seed, deterministic)`(random/numpy/torch, `use_deterministic_algorithms(True, warn_only=True)`, cudnn deterministic, `CUBLAS_WORKSPACE_CONFIG=:4096:8`), `make_generator`, `worker_init_fn`.
- `evaluation/evaluator.py`: `collect_scores(model, strategy, loader, device, max_batches) -> ScoreTable`, `evaluate(...) -> EvalResult{experiment_id, science_hash, spec_hash, protocol_id, protocol_hash, manifest_hashes, adaptation_set_hash, seed, mode, metrics: PadMetrics, threshold: ThresholdPolicy, n_test, latency: LatencyResult | None, git, env, status}`, `measure_latency(model, clip_shape, device, warmup, repetitions, batch_size) -> LatencyResult{ms_per_clip, fps_equiv, conditions{clip_length, resolution, includes_preprocessing: False, includes_face_detector: False, batch_size, device, warmup, repetitions}, peak_memory_mb}` (`ms_per_clip = seconds * 1000.0` 단일 지점 §32), `roc_png(scores, path)`.

테스트: `test_frame_baseline_forward_shape_T1`, `test_frame_baseline_T8_mean_logits`, `test_video_baseline_shape`, `test_registry_instantiate_from_yaml`, `test_encoder_head_parameter_partition`, `test_head_only_freezes_encoder`, `test_full_finetune_all_trainable`, `test_none_strategy_bce`, `test_prototype_raises_not_implemented`, `test_two_runs_same_seed_same_loss_sequence`, `test_worker_init_reproducible`, 통합 `test_train_frame_smoke_creates_run_and_artifacts`(tag 9종, metric 5종, artifact 목록), `test_train_video_smoke_8_frames`, `test_smoke_limits_batches`, `test_full_mode_cpu_fixture_runs_2_epochs_and_auc_above_0_6`(slow), `test_determinism_same_seed_same_metrics`(slow), `test_evaluate_checkpoint_matches_train_test_metrics`, `test_full_finetune_bf_only_produces_regression_check`, `test_head_only_leaves_encoder_unchanged`(state_dict 비교), `test_adapt_refuses_checkpoint_with_other_protocol_hash`, `test_adapt_test_excludes_adaptation_samples`.

### 10. Scripts (호출 그래프)

```text
scripts/train.py  (@hydra.main(config_path=str(CONFIGS_DIR), config_name="config", version_base="1.3"))
  spec = spec_from_cfg(cfg)                      [실패 → exit 2, 기록 없음]
  pv = validate_protocol(spec.protocol, manifests_dir, frames)     [error → registry status invalid_protocol, exit 3]
  aset = materialize_adaptation_set(...) if protocol.target_adaptation.enabled else None
  env = collect_env_snapshot(); registry = Registry()
  gate = check_full_run_gate(spec, env, task_overrides(), pv, tracking_ok, registry, read_frozen_spec(id))
        [mode full & !allowed → registry status blocked_by_gate, exit 4]
  seed_everything(); device = resolve_device(spec)
  tracker.start_run(...) ; registry.append(running)
  write_resolved_spec(run_dir) ; log artifacts
  splits = build_splits(); loaders = build_loaders(spec, splits, limits=effective_limits(spec))
  model = build_model(); strategy = NoAdaptation()
  Trainer.fit() → threshold fit on dev → evaluate(test) → latency → save_checkpoint(항상)
  tracker.log_metrics ; tracker.end_run(smoke_ok|success) ; registry.append(final)
  예외: status failed_training | failed_environment(CUDA/import) 기록 후 re-raise

scripts/adapt.py  (@hydra.main) — 동일 전처리 + load_checkpoint(source_run_id|source_checkpoint) → protocol_hash 검사
  strategy = build_strategy(spec.adaptation); strategy.prepare(model, ckpt)
  Trainer.fit(adaptation loader: bona_fide only, label 0)
  threshold: dev_domain==source → ckpt.threshold 재사용 ; target → target dev로 fit
  evaluate(target_test) → baseline = tracker.find_baseline(evaluation.baseline_experiment_id, protocol_hash, include_smoke=mode=="smoke")
  gate_result = run_security_gate(baseline.metrics, result.metrics, baseline.protocol_hash, protocol_hash, protocol.security_gate)
  regression_check.json ; end_run(status = security_regression | inconclusive | success | smoke_ok)

scripts/evaluate.py (@hydra.main) — checkpoint + protocol → dev fit(또는 ckpt threshold) + test 평가만, 별도 run(status success/smoke_ok)
scripts/validate_protocol.py / validate_spec.py — argparse (§7 참조)
scripts/summarize_experiment.py — argparse (§11)
scripts/make_synthetic_data.py / build_manifest.py — argparse (§3)
```

### 11. Report generator

`reporting/report.py`:
```python
@dataclass
class RunRecord: registry: RegistryRow; eval: EvalResult; spec: ExperimentSpec; mlflow_run_id: str
def load_runs(experiment_id: str, *, include_smoke: bool, tracker: MlflowTracker) -> list[RunRecord]
def generate_report(method: list[RunRecord], baseline: list[RunRecord] | None, out: Path, *, justify: str | None) -> ReportBundle
    # assert_comparable(baseline.protocol_hash, method.protocol_hash, justify)
    # seed 집계 mean/std/individual → run_security_gate(baseline_mean, method_mean, ...) + seed별 결과
    # §44 헤딩 17개 그대로 (string.Template). Interpretation = §30 문장 템플릿(dataset/protocol/seed/metric/threshold policy 포함) + "TODO(reviewer)"
    # What This Does NOT Prove 자동 항목: seed<3, synthetic dataset, insufficient PAI support, justified protocol diff, smoke runs included
    # 상단 배너: "SYNTHETIC SANITY — NOT A RESEARCH RESULT" (synthetic_*), "NOT DIRECTLY COMPARABLE: <justify>" (justified_diff)
    # 출력: experiments/reports/<experiment_id>.md + artifacts/tables/<experiment_id>_per_attack.csv
```
테스트: `test_report_contains_all_section44_headings`, `test_report_excludes_smoke_runs_by_default`, `test_report_single_seed_note`, `test_report_synthetic_banner`, `test_report_blocks_protocol_mismatch_without_justify`, `test_report_justify_banner`.

### 12. Research store (claims / papers / ADR)

`research/claims.py`:
```python
class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_id: str; claim: str; paper_id: str
    source_type: Literal["primary_paper","official_code","secondary","local_observation"]
    section: str; table: str; protocol: str; metric: str; value: float | None; verified: bool; notes: str
    verified_by: str | None = None; verified_at: str | None = None
    # validator: value is not None ⇒ verified and source_type == primary_paper ; secondary ⇒ verified False
def load_claims(path) -> list[Claim]; def validate_claims_file(path) -> list[str]
```
- `claims.jsonl` 초기 2행: §8.2 예시(`ota_2025_oneclass_001`, value null) + `local_dg_repro_001`(source_type `local_observation`, verified true, value null, notes "local reproduction only; not generalizable (§3.1)").
- `paper_index.yaml`: §7 9편(`liu2018auxiliary, yu2020cdcn, wang2022ttn, yang2025g2v2former, liu2022sdafas, guo2022mdl, liu2024sdafaspp, he2024ccga, li2025ota`) `title, venue, year, urls[], code_url, code_status: verify, review: null`.
- ADR: `ADR-000-template.md`(§26 그대로), `ADR-001-use-video-input`(§0/§4 RQ1, 대안 frame-only), `ADR-002-switch-dg-to-da`(§3.1 관측 + "일반화 금지" 정확한 표현 verbatim), `ADR-003-real-only-target-setting`(§2.8/§5, 대안 few-shot spoof, §53-6/7 링크), `ADR-004-protocol-lock`(§15, `HASH_EXCLUDED`, protocol_id 포함 이유, `--justify`, parent 규칙), `ADR-005-harness-phase0-scope-and-conventions`(샌드박스/H100 환경 사실, spec==Hydra `exp/` 그룹, science/spec hash, label/score 규약, 합성 데이터 sanity-only, torch extras-only, CLAUDE.md 분할 보류 + 토큰 비교표, 이연 목록: Docker/pre-commit/pytest-cov/skills/GRU/resnet18/prototype/Replay-Attack adapter/E04-E05, CI 결정).
- `hypotheses/H1-H4.md`: §42 원문 + 관련 실험 ID(E01–E07) + 상태 `untested`.
- 테스트: `test_all_claims_parse`, `test_unverified_claim_value_must_be_null`, `test_secondary_cannot_be_verified`, `test_paper_index_loads_nine_papers`.

---

## Claude Code 하네스

### CLAUDE.md
- 원문 verbatim. 수정은 `permissions.ask` + `protect_files.py`(reason: "PF-01 CLAUDE.md는 연구 헌법(§헤더). 연구 방향/운영 규칙 변경으로 간주"). 운영 델타는 rules에만(사용자 결정 #2).

### `.claude/rules/*.md`
| 파일 | frontmatter | 내용(문서 재복사 없음, 포인터 + 델타) |
|---|---|---|
| `research-integrity.md` | 없음(전역) | §41 10원칙 한 줄씩 + "CLAUDE.md §N 참조"; `protocol_hash` 다르면 `--justify` 필수·배너; 요청 분류표(Research/Code/Experiment/Analysis → 경로); 위임 정책(paper-researcher 병렬 ≤2, 파일 3개 이상 신규면 experiment-engineer, full run 후 반드시 research-reviewer 경유 전 "성공" 표현 금지); [Established]/[Adaptation]/[Hypothesis] 태깅 포인터(§46); `research_claim_allowed=false` run은 연구 주장 금지 |
| `experiment-safety.md` | 없음(전역) | hook deny/ask 표(아래), 명령 치트시트(`uv sync --extra cpu --extra dev`, `make manifests`, `uv run python scripts/validate_spec.py --exp X --json`, `... --freeze`, `uv run python scripts/train.py +exp=X`(smoke 기본), full은 파일에서 `mode: full` + `allow_full_gpu_run: true` 커밋 후 동일 명령, `-m`은 사용자 확인), smoke→freeze→full 절차와 `science_hash`/`SMOKE_OK` 설명, `execution.*` CLI override 금지, `experiments/specs/*.resolved.yaml` 수동 편집 금지, `registry.jsonl` 편집 금지, §35 status enum |
| `data-governance.md` | 없음(전역) | 외부 업로드 명령 목록은 hook이 deny/ask(§22/§34), `Read(data/raw/**)`·`Read(data/processed/**)`는 ask(얼굴 프레임 컨텍스트 유입 금지), 로그/리포트에는 `dataset_id`·`manifest_hash`만, manifest는 `relative_path` + `PAD_DATA_ROOT`, manifest 생성은 `scripts/build_manifest.py`/`make_synthetic_data.py` 경유가 정식 경로, CelebA-Spoof류 `temporal_valid=false` |
| `coding-style.md` | `paths: ["src/**", "tests/**", "scripts/**", "configs/**"]` | ruff/pyright 명령, 타입힌트 필수, `bona_fide` 명명, `conventions.py` 규약 참조, 테스트 매핑 규칙(`src/pad_research/<pkg>/<mod>.py ↔ tests/unit/test_<mod>.py` 또는 `tests/unit/test_<pkg>_<mod>.py`; protocols → `tests/protocol/`), 실험 로직에 dataset 이름 분기 금지(§27.3), 단위 변환은 `evaluator.measure_latency` 한 곳(§32), §27.1 읽기→call path→config→테스트→최소 수정 |

### Subagents (`.claude/agents/`)
`paper-researcher.md`:
```yaml
---
name: paper-researcher
description: 논문 검색, primary source 확인, Paper Review(§23.1 템플릿) 작성, claims.jsonl 초안 제안. 코드/실험 금지. 논문·수치·protocol 질문에 사용.
tools: Read, Glob, Grep, WebFetch, WebSearch
disallowedTools: Bash, Edit, Write
model: sonnet
permissionMode: default
maxTurns: 40
---
```
본문: §8 흐름, §8.1 금지 5개, §33 iBeta 규칙, 출력 = §23.1 15개 헤더 + `## Proposed claims.jsonl entries`(value null, verified false 기본). 파일 기록은 main agent가 수행(ask 보호).

`experiment-engineer.md`:
```yaml
---
name: experiment-engineer
description: repo 분석, 환경, dataset/model adapter, Hydra config, smoke test, unit/integration test, MLflow 로깅 구현. protocol 변경·full GPU run·raw data 삭제·test로 threshold tuning 금지.
model: inherit
permissionMode: default
maxTurns: 80
memory: project
---
```
본문: §23.2 역할/금지, §27.1 절차, "smoke 기본, `execution.mode=full` 직접 실행 금지, 보호 파일 수정 전 이유 보고", 출력 템플릿 `# Engineering Report / Task / Files Changed / Commands Run (+exit codes) / Tests (added, passed, failed) / Smoke Run (exp_id, mode, mlflow_run_id, protocol_hash, science_hash) / Open Issues`; Interpretation 작성 금지.

`research-reviewer.md`:
```yaml
---
name: research-reviewer
description: 실험 리포트·regression_check.json·PR을 비판적 reviewer로 read-only 검토. leakage/protocol hash/threshold/per-PAI APCER/seed 점검.
tools: Read, Glob, Grep
disallowedTools: Bash, Edit, Write, WebFetch, WebSearch
model: inherit
permissionMode: default
maxTurns: 30
---
```
본문: §23.3 9개 질문 + §14.3 + §15 + §31 + §30, 입력 경로(`experiments/reports/<id>.md`, run dir의 `regression_check.json`, `per_attack.csv`)는 main agent가 넘김, 출력 `# Review / Verdict: ACCEPT|ACCEPT_WITH_CAVEATS|REJECT|SECURITY_REGRESSION / Protocol Check / Leakage Check / Threshold Check / Security Check(per-PAI delta 표) / Statistical Check / Claims the report makes that the evidence does not support / Required fixes before conclusions`.

### `.claude/settings.json` (T0에 permissions, T9에 hooks 추가한 최종형)
```json
{
  "permissions": {
    "allow": [
      "Bash(uv sync*)", "Bash(uv lock*)", "Bash(uv run pytest*)", "Bash(uv run ruff*)", "Bash(uv run pyright*)",
      "Bash(uv run python scripts/validate_spec.py*)", "Bash(uv run python scripts/validate_protocol.py*)",
      "Bash(uv run python scripts/summarize_experiment.py*)", "Bash(uv run python scripts/make_synthetic_data.py*)",
      "Bash(make lint*)", "Bash(make test*)", "Bash(make typecheck*)", "Bash(make manifests*)", "Bash(make verify-dod*)",
      "Bash(git status*)", "Bash(git diff*)", "Bash(git log*)", "Bash(git branch*)", "Bash(git show*)",
      "Bash(ls*)", "Bash(tree*)", "Bash(wc*)", "Bash(nvidia-smi*)", "Bash(tail experiments/registry.jsonl*)"
    ],
    "ask": [
      "Edit(CLAUDE.md)", "Write(CLAUDE.md)",
      "Edit(data/manifests/**)", "Write(data/manifests/**)",
      "Edit(research/claims/**)", "Write(research/claims/**)",
      "Edit(configs/protocol/**)", "Write(configs/protocol/**)",
      "Edit(.claude/**)", "Write(.claude/**)", "Edit(uv.lock)", "Write(uv.lock)",
      "Read(data/raw/**)", "Read(data/processed/**)",
      "Bash(git push*)", "Bash(git commit*)", "Bash(uv add*)", "Bash(uv remove*)", "Bash(dvc push*)", "Bash(dvc pull*)", "Bash(docker*)"
    ],
    "deny": [
      "Edit(experiments/registry.jsonl)", "Write(experiments/registry.jsonl)",
      "Bash(rm -rf data*)", "Bash(rm -rf checkpoints*)", "Bash(rm -rf mlruns*)", "Bash(rm -rf .git*)",
      "Bash(git reset --hard*)", "Bash(git clean -f*)", "Bash(dvc destroy*)", "Bash(git push --force*)",
      "Bash(sudo rm*)", "Bash(curl * | sh*)", "Bash(wget * | sh*)"
    ]
  },
  "hooks": {
    "PreToolUse": [
      {"matcher": "Bash", "hooks": [
        {"type": "command", "command": "python3 \"${CLAUDE_PROJECT_DIR}/.claude/hooks/guard_destructive.py\"", "timeout": 10},
        {"type": "command", "command": "python3 \"${CLAUDE_PROJECT_DIR}/.claude/hooks/gate_experiment.py\"", "timeout": 60}
      ]},
      {"matcher": "Edit|Write", "hooks": [
        {"type": "command", "command": "python3 \"${CLAUDE_PROJECT_DIR}/.claude/hooks/protect_files.py\"", "timeout": 10}
      ]}
    ],
    "PostToolUse": [
      {"matcher": "Edit|Write", "hooks": [
        {"type": "command", "command": "python3 \"${CLAUDE_PROJECT_DIR}/.claude/hooks/post_edit_check.py\"", "timeout": 180}
      ]}
    ],
    "SessionStart": [
      {"matcher": "startup|resume", "hooks": [
        {"type": "command", "command": "python3 \"${CLAUDE_PROJECT_DIR}/.claude/hooks/session_start.py\"", "timeout": 20}
      ]}
    ]
  }
}
```
`permissions.deny`의 Bash 패턴은 prefix 매칭이라 2차 방어이며 주 방어는 hook. Phase 0 완료 후 사용자가 `Edit(.claude/settings.json)`, `Write(.claude/settings.json)`, `Edit(.claude/hooks/**)`, `Write(.claude/hooks/**)`를 deny로 승격(README).

### Hooks (stdlib-only Python 3)

`_common.py`: `read_input() -> dict | None`(파싱 실패 → `ask("HK-00 stdin JSON 파싱 실패")`), `split_commands(cmd) -> list[str] | None`(`$(`/백틱/`<<` 포함 시 None → ask), `argv_of(segment) -> list[str] | None`(shlex 실패 None → ask; `sudo/env/time/nohup/nice/VAR=` 제거), `resolve_targets(argv, cwd) -> list[Path]`, `project_root()`(`CLAUDE_PROJECT_DIR` → `pyproject.toml` 탐색), `decide(decision, reason)`: stdout `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow|deny|ask","permissionDecisionReason":"<규칙ID> ..."}}` + exit 0; deny는 추가로 stderr에 reason(양쪽 지원).

`guard_destructive.py` 규칙표 (세그먼트 argv[0] + 타겟 기준, 최고 심각도 채택):
| ID | 패턴 | 결정 |
|---|---|---|
| DG-01 | `rm` + 재귀 옵션, 타겟이 `data/`, `data/raw`, `data/processed`, `data/manifests`, `checkpoints/`, `mlruns*`, `research/`, `experiments/`, `.git`, `/`, `~`, `*`, 프로젝트 상위 | deny |
| DG-02 | `rm` 재귀, 그 외 경로(outputs/, .venv 등) | ask |
| DG-03 | `rm`(비재귀) 타겟 `data/manifests/**`, `research/claims/**`, `configs/protocol/**`, `experiments/registry.jsonl`, `mlruns.db`, `experiments/specs/**` | deny |
| DG-04 | `git reset --hard`, `git clean` + `-f/-x/-d`, `git checkout -- .`, `git restore .`, `git branch -D`, `git push` + `-f/--force/--force-with-lease`, `git filter-branch/filter-repo` | deny |
| DG-05 | `dvc destroy`, `dvc gc`, `dvc remove` | deny |
| DG-06 | `find … -delete` / `-exec rm`, `truncate`, `shred`, `dd of=` 보호 경로 | deny |
| DG-07 | `mlflow gc`, `mlflow experiments delete`, `mlflow runs delete` | deny (§35) |
| DG-08 | 업로드류(`scp`, `rsync`(원격), `sftp`, `aws s3 cp/sync/mv`, `gsutil cp/rsync/mv`, `gcloud storage cp/rsync`, `az storage blob upload*`, `curl -T/--upload-file/-F *@*/--data-binary @*`, `wget --post-file`, `dvc push`, `git lfs push`, `huggingface-cli upload`, `hf upload`, `gh release upload`): 소스가 `data/raw`, `data/processed`, `checkpoints/`, `artifacts/`, `mlruns` 하위 | deny |
| DG-09 | 업로드류 그 외 소스 | ask (`--dry-run`/`-n`은 allow) |
| DG-10 | `python -c`/`uv run python -c` 안에 `shutil.rmtree|os.remove|unlink` + 보호 경로 문자열 | deny |
| DG-11 | `chmod -R 000`, `chown -R` 보호 경로 | ask |
거짓 양성 회피: `echo "rm -rf data"`, `grep`, `rg`, 주석은 argv[0]이 아니므로 통과.

`gate_experiment.py`:
| ID | 조건 | 결정 |
|---|---|---|
| EXP-00 | 세그먼트에 `scripts/train.py`, `scripts/adapt.py`(또는 `-m pad_research...` 없음; 단일 엔트리) 없음 | 관여 안 함(exit 0, 출력 없음) |
| EXP-01 | `execution.allow_full_gpu_run=` 또는 `execution.mode=` 또는 `execution=` CLI 토큰 | deny ("execution.*는 configs/exp 파일에서만") |
| EXP-02 | `-m`/`--multirun`/`hydra.sweeper` | ask (§20 무분별한 sweep 금지) |
| EXP-03 | `+exp=` 토큰 없음 | deny ("§16 spec 없이 실행 금지; +exp=<name>") |
| EXP-04 | `uv run --no-sync python scripts/validate_spec.py --for-launch --json -- <overrides>` 실행(cwd=project root, timeout 45 s): exit≠0 / timeout / 예외 | deny (errors 최대 8줄) |
| EXP-05 | 통과 & `mode == smoke` | allow (reason에 exp_id, protocol_hash[:12]) |
| EXP-06 | 통과 & `mode == full` | **ask** (reason: exp_id, protocol_hash[:12], require_gpu/expected_gpu, git dirty, SMOKE_OK run id) |
`scripts/evaluate.py`는 대상 아님(체크포인트 평가는 저비용).

`protect_files.py` (Edit|Write): 보호 glob 매칭 시 `ask` + 변경 요약. `PF-01 CLAUDE.md`, `PF-02 data/manifests/**`("build_manifest.py 경유가 정식 경로; manifest_hash 변경 시 기존 run과 연결 끊김"), `PF-03 configs/protocol/**`("protocol_hash가 바뀌면 기존 run과 비교 불가(§15); 변경 요약: old N자→new M자, 변경 키 추정: …"(라인 diff 기반)), `PF-04 research/claims/**`("value는 primary source 검증 전 null"), `PF-05 .claude/**`, `PF-06 uv.lock`, `PF-07 research/decisions/ADR-*.md` 기존 파일 Edit/Write(신규 ADR Write는 allow), `PF-08 experiments/registry.jsonl` deny, `PF-09 experiments/specs/*.resolved.yaml` deny("validate_spec --freeze로만 생성"). 그 외 exit 0.

`post_edit_check.py` (PostToolUse): `.py`이고 `src/|tests/|scripts/|.claude/hooks/` 하위일 때 `uv run ruff check --output-format concise <file>` → 테스트 매핑(`src/pad_research/<pkg>/<mod>.py` → `tests/unit/test_<mod>.py`, `tests/unit/test_<pkg>_<mod>.py`; `protocols/*` → `tests/protocol/` 추가; `scripts/<name>.py` → `tests/integration/test_<name>*.py`; `tests/**` → 자기 자신; `.claude/hooks/*` → `tests/hooks/`) 존재하는 것만 `uv run pytest -q -x --timeout 90 -m "not slow" <files>`(subprocess timeout 150 s). 실패 → **exit 2** + stderr 요약(파일, 실패 테스트, 첫 15줄). 매핑 없음 → exit 0 + stdout 경고. `configs/**.yaml` 편집 → `protocol/`이면 `validate_protocol.py --path`, `exp/`이면 `validate_spec.py --exp`, 그 외 `yaml.safe_load`(uv run). 통합 테스트·전체 테스트는 절대 hook에서 실행하지 않음(§24.2).

`session_start.py` (≤45줄 stdout):
```text
[pad-harness] branch=<b> sha=<7> dirty=<n> untracked=<n>
git status --short (최대 12줄)
env: python=3.11.x venv=<yes/no> torch=<version|MISSING> cuda=<yes/no> gpu=<name|none> lock=<12hex>
   (torch 판정: .venv/lib/python3.11/site-packages/torch/version.py 존재+내용 파싱, subprocess 없음)
registry (last 5): ts | exp_id | mode | status | run_id[:8] | protocol_hash[:8]
ADRs: ADR-001 <title> [Accepted] ...            (## Status 다음 줄 파싱)
specs: <n> frozen | reports: <n> | protocols: <active n>/<draft n>
open questions: CLAUDE.md §53 (12)
reminder: §36 체크리스트 → 요청을 Research/Code/Experiment/Analysis로 분류
```

수동 테스트(샌드박스):
```bash
echo '{"tool_name":"Bash","tool_input":{"command":"rm -rf data/raw"}}' | python3 .claude/hooks/guard_destructive.py            # deny DG-01
echo '{"tool_name":"Bash","tool_input":{"command":"echo \"rm -rf data\""}}' | python3 .claude/hooks/guard_destructive.py       # 출력 없음(allow)
echo '{"tool_name":"Bash","tool_input":{"command":"scp checkpoints/a.pt host:"}}' | python3 .claude/hooks/guard_destructive.py  # deny DG-08
echo '{"tool_name":"Bash","tool_input":{"command":"rsync -n ./x host:/y"}}' | python3 .claude/hooks/guard_destructive.py       # allow (dry-run)
echo '{"tool_name":"Bash","tool_input":{"command":"uv run python scripts/train.py +exp=syn_e01_frame_source_only"}}' | python3 .claude/hooks/gate_experiment.py   # allow EXP-05
echo '{"tool_name":"Bash","tool_input":{"command":"uv run python scripts/train.py +exp=syn_e01_frame_source_only execution.mode=full"}}' | python3 .claude/hooks/gate_experiment.py   # deny EXP-01
echo '{"tool_name":"Edit","tool_input":{"file_path":"configs/protocol/syn_a_to_b_v1.yaml","old_string":"total_samples: 24","new_string":"total_samples: 48"}}' | python3 .claude/hooks/protect_files.py   # ask PF-03
echo '{"tool_name":"Write","tool_input":{"file_path":"research/decisions/ADR-006-x.md","content":"# ADR"}}' | python3 .claude/hooks/protect_files.py   # allow
echo '{"tool_name":"Edit","tool_input":{"file_path":"experiments/registry.jsonl"}}' | python3 .claude/hooks/protect_files.py   # deny PF-08
echo '{}' | python3 .claude/hooks/session_start.py   # exit 0, "branch=" 포함
```
`tests/hooks/*`(subprocess, ~22건): `test_denies_rm_rf_data_raw`, `test_denies_rm_rf_checkpoints`, `test_allows_echo_containing_rm`, `test_asks_rm_r_outputs`, `test_denies_git_reset_hard`, `test_denies_git_push_force`, `test_denies_scp_checkpoints`, `test_asks_scp_other_source`, `test_allows_rsync_dry_run`, `test_denies_mlflow_gc`, `test_asks_on_subshell`, `test_asks_on_invalid_json`, `test_allows_uv_run_pytest`, `test_gate_ignores_non_train_commands`, `test_gate_denies_cli_mode_full`, `test_gate_denies_missing_exp`, `test_gate_asks_multirun`, `test_gate_allows_smoke_valid_spec`, `test_gate_asks_full_valid_fixture`, `test_gate_denies_when_validator_fails`, `test_gate_denies_on_timeout`(env로 validator 경로를 sleep 스크립트로 교체), `test_protect_asks_claude_md`, `test_protect_asks_protocol_with_summary`, `test_protect_allows_new_adr`, `test_protect_denies_registry`, `test_post_edit_maps_module_to_test`, `test_post_edit_exit2_on_failing_test`, `test_session_start_prints_branch`, `test_settings_json_parses_and_matchers_valid`(matcher ∈ {Bash, Edit|Write, startup|resume}, command 파일 존재).

---

## 검증 방법 (§49 DoD 23항목 ↔ 증명 명령)

| # | DoD 항목 | 증명 |
|---|---|---|
| 1 | root `CLAUDE.md` | `diff CLAUDE.md <upload>` 무출력; `tests/test_dod_files.py::test_claude_md_verbatim`(줄 수 2586) |
| 2 | `.claude/rules/` | 4개 파일 존재, `coding-style.md`만 `paths:` frontmatter (`test_rules_files`) |
| 3 | 3개 subagent | frontmatter `name` 3개, reviewer/researcher에 `disallowedTools: Bash` (`test_agents_frontmatter`) |
| 4 | destructive-command safety hook | `uv run pytest tests/hooks/test_guard_destructive.py` + 수동 파이프 |
| 5 | experiment launch validation | `tests/hooks/test_gate_experiment.py` + `tests/integration/test_validate_cli.py::test_for_launch_denies_cli_mode_full` |
| 6 | uv-based environment | `uv sync --extra cpu --extra dev && uv lock --check`; `test_env_smoke.py::test_cpu_extra_has_no_cuda` |
| 7 | Hydra config | `tests/unit/test_compose.py::test_compose_each_exp_file_validates` |
| 8 | dataset manifest | `test_manifest.py`(roundtrip, hash 안정, relative_path 거부), `make manifests` 바이트 동일 |
| 9 | protocol schema | `test_protocol_schema.py`, `test_yaml_roundtrip_matches_section15` |
| 10 | protocol hash | `test_protocol_hash.py::test_hash_golden_value` 등 7건 |
| 11–15 | APCER/BPCER/ACER/HTER/AUC unit test | `uv run pytest tests/unit/test_metrics.py -v -k "apcer or bpcer or acer or hter or auc"` (각 이름 1:1) |
| 16 | MLflow run logging | `test_mlflow_tracker.py`, `test_train_frame_smoke_creates_run_and_artifacts`(tag 9·metric 5·artifact) |
| 17 | Git SHA logging | `test_git_sha_and_dirty`, smoke run tag `git_sha` |
| 18 | environment metadata logging | `test_snapshot_fields_present`, artifact `env_snapshot.json` |
| 19 | smoke-test mode | `make smoke` <60 s, status `smoke_ok`, `test_smoke_limits_batches` |
| 20 | full GPU run gate | `test_gate.py` 9건 + `test_train_full_cpu.py`(fixture full_cpu_ok 완주, full_needs_gpu 거부) + hook EXP-06 ask |
| 21 | experiment report generator | `test_summarize.py::test_report_contains_all_section44_headings`, `make report` |
| 22 | research claim store | `test_claims.py`, `claims.jsonl` 2행 |
| 23 | ADR structure | `test_dod_files.py::test_adrs_have_status`(ADR-000~005) |

End-to-end 리허설(T11, 순서대로):
```bash
uv sync --extra cpu --extra dev && uv lock --check
export PAD_DATA_ROOT=$PWD/data/processed
make manifests && make validate-protocols
uv run ruff check . && uv run ruff format --check . && uv run pyright src
uv run pytest -m "not slow" -q                       # 단위/protocol/hooks/통합(smoke)
uv run python scripts/validate_spec.py --exp syn_e02_video_source_only --freeze --json
make smoke && make smoke-video                        # e01, e02 (registry 2줄, MLflow run 2개)
RUN=$(uv run python - <<'EOF'
import mlflow; mlflow.set_tracking_uri("sqlite:///mlruns.db")
df = mlflow.search_runs(experiment_names=["pad-synthetic-sanity"], filter_string="tags.experiment_id = 'exp_syn_e02_video_source_only'")
print(df.iloc[0].run_id)
EOF
); make smoke-adapt RUN=$RUN                           # e03 → regression_check.json, status ∈ {smoke_ok, security_regression, inconclusive}
uv run python scripts/summarize_experiment.py --experiment-id exp_syn_e03_video_full_ft_bf_only --baseline-experiment-id exp_syn_e02_video_source_only --include-smoke --justify "ablation: adaptation enabled (parent syn_a_to_b_v1)" -o experiments/reports/exp_syn_e03.md
uv run pytest -m slow -q                              # full_cpu_ok 완주 + 결정성
make verify-dod                                       # 23항목 PASS
uv run dvc repro                                      # no-op
```
H100 이관(README, 코드 변경 없음): `git clone` → `uv python install 3.11` → `nvidia-smi`(driver ≥ 12.4 아니면 index를 cu126으로 교체 후 `uv lock` 커밋) → `uv sync --extra cu124 --extra dev --frozen` → `make test` → `make smoke-video`(CUDA smoke, env snapshot에 gpu_names) → 실데이터 manifest(`scripts/build_manifest.py --adapter <name>`) → protocol `status: active` → `validate_spec --freeze` → smoke → 실험 파일에 `execution: {mode: full, allow_full_gpu_run: true, require_gpu: true, expected_gpu: H100}` 커밋 → `uv run python scripts/train.py +exp=<name>`(hook ask → y).

---

## 리스크와 완화

| 리스크 | 완화 |
|---|---|
| Hydra 1.3에서 `+exp=` 추가/그룹명 충돌 동작이 예상과 다름 | 그룹을 `exp/`로 분리, `test_compose_each_exp_file_validates`가 실제 compose로 확인, 실동작을 config.yaml 주석에 기록 |
| PostToolUse JSON 출력 형식 불확실 | exit 2 + stderr만 사용(문서화 경로); PreToolUse는 JSON stdout + deny 시 stderr 병행 |
| hook의 `uv run` validator가 45 s 초과 | `--no-sync`, validator/`pad_research/__init__` torch 미import(`test_validator_does_not_import_torch`), timeout은 deny(fail-closed) |
| hook 우회(SSH/터미널/subagent) | in-process `check_full_run_gate` + 파일 flag + SPEC_FROZEN/SMOKE_OK가 hook과 독립적으로 동작 |
| sklearn `roc_curve` tie/inf로 EER threshold 흔들림 | `drop_intermediate=False`, inf 제외, argmin 첫 index 규칙, toy 3종 고정 |
| 합성 결과의 연구 오독 | tag `research_claim_allowed=false`, 리포트 배너, ADR-005, hypothesis 파일에 "synthetic은 근거 아님" |
| CPU 결정성이 BLAS 스레드에 흔들림 | conftest `torch.set_num_threads(1)`, `OMP_NUM_THREADS=1`, `allclose(atol=1e-6)` |
| MLflow 2.x/3.x API 차이 | `MlflowTracker` 래퍼 뒤 격리, lock 고정, tmp sqlite 실제 호출 테스트 |
| extra 없는 `uv sync`로 torch 부재 | 시끄러운 실패(의도); README/Makefile 타깃만 문서화; `test_cpu_extra_has_no_cuda` |
| cu124 index와 H100 driver 불일치 | ADR-005 체크리스트 선행, index URL 1줄 교체 + `uv lock` 커밋(lock_hash 변경 기록) |
| ask 프롬프트 피로 → hook 우회 유혹 | allow 목록에 읽기/검증 명령 열거, smoke는 validator 통과 시 allow, full만 ask, 무인은 `settings.local.json`으로 사용자가 |
| Claude가 자기 가드 수정 | `.claude/**` ask + PF-05 reason, hooks 편집 시 `tests/hooks` 자동 실행, 완료 후 사용자가 deny 승격 |
| PostToolUse targeted pytest가 편집 속도 저하 | 1:1 매핑만, `-x --timeout 90 -m "not slow"`, 통합 테스트 제외 |
| 보호 파일 ask가 부트스트랩을 막음 | T0 순서(CLAUDE.md → rules → agents → settings.json), manifest는 Bash 스크립트 생성, protocol YAML은 T3에서 ask 1회 수용 |
| `registry.jsonl`과 MLflow 불일치 | MLflow가 진실, registry는 파생 인덱스(README 명시); `SMOKE_OK`는 registry, `find_baseline`은 MLflow |

---

## Phase 0 이후 (Task 8–10, H100)

**바뀌는 것**
- `data/adapters/replay_attack.py`(+ 등록) — 실제 디렉터리를 보고 파서 작성(§27.2), `build_manifest.py --adapter replay_attack --root $PAD_DATA_ROOT/replay_attack`; `read_clip`에 `media_type=video` 디코딩(torchvision.io/decord) 추가; 얼굴 crop 파이프라인은 `data/processed/<dataset_id>/` + `media_type=frames_dir|npy_clip` manifest로 기록.
- `configs/protocol/ocim_target_i_v1.yaml` `status: draft → active`(manifest 준비 후), 실데이터 protocol 추가(parent/change_note 규칙).
- `configs/model/` 강한 baseline(CDCN/ResNet, TTN/G²V²former)은 YAML + 모델 모듈 추가만(§53-1,2 backlog 확인 후 §27.2 절차).
- `configs/exp/` E01–E03 실데이터판(`require_gpu: true, expected_gpu: H100`), E04(head_only)·E05(prototype, Phase 5 구현 후).
- `pyproject` index를 driver에 맞춰 `cu124`/`cu126` 선택 후 `uv lock` 커밋; `dvc add data/raw/<dataset>` + remote는 §22/§34 정책 확인 후.
- ADR-006+ (real dataset protocol 결정, low-motion 정의 §53-12).

**그대로인 것**
- manifest/protocol/spec 스키마, hash 정의, validator error code, `ThresholdPolicy`, gate 체크 목록, hook 규칙, tracker tag 강제, 리포트 템플릿, registry, 스크립트 명령(`uv run python scripts/train.py +exp=<name>`), 테스트 스위트(합성 데이터로 CI/로컬 회귀 유지).

---

## 사용자 결정 필요 항목
(StructuredOutput의 `user_decisions_needed` 참조 — 9개)
