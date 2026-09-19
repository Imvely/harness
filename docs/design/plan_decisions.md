# Passive Video PAD + DA Research Harness — Phase 0 설계 계획 (초안, 작성 중)

## Context

- 업로드된 `CLAUDE_PAD_RESEARCH_HARNESS_1.md`(2,586줄)는 이 저장소의 "연구 헌법"이다. 목표는 Passive RGB Video PAD + Bona-fide-only Domain Adaptation 연구를 **Claude가 틀리기 어려운 실험 시스템** 위에서 수행하는 것.
- 저장소 `Imvely/harness`는 현재 `LICENSE`(MIT) 하나뿐인 빈 상태. 브랜치 `claude/youthful-newton-fl60mp`에서 작업.
- 이 계획은 문서 §29 Phase 0(Harness MVP)과 §38 Task 1~10, §49 Definition of Done을 의존성 순서로 구현 가능한 작업으로 바꾼 것이다.

## 환경 점검 결과 (문서 §38 Task 1, 2026-09-17 실측)

| 항목 | 값 |
|---|---|
| OS | Ubuntu 24.04.4, x86_64, 4 vCPU, 15 GB RAM, 디스크 여유 ~30 GB |
| Python | 3.11.15 (`/usr/local/bin/python3`) |
| uv | 0.8.17 (`/root/.local/bin/uv`), PyPI 접근 가능 |
| GPU / CUDA / torch | **없음** (nvidia-smi, nvcc, torch 모두 미설치) |
| 설치된 패키지 | pyyaml 6.0.1 뿐. hydra/mlflow/pydantic/numpy/sklearn/pytest/ruff 파이썬 패키지 없음 (ruff·pytest CLI만 PATH에 있음) |
| Docker / Slurm | docker 있음, slurm 없음 |

**설계상 함의**: 하네스는 GPU 없이 CPU + 합성(synthetic) 데이터로 전 경로(smoke test)가 돌아야 한다. `pyproject.toml`은 `cpu` / `cu12x` extra로 torch index를 분리해 H100 서버에서도 같은 lock으로 설치되게 한다. 실제 얼굴 데이터셋은 이 환경에 없으므로 Task 8~10(실제 baseline 학습)은 데이터 매니페스트 등록 이후 별도 세션 과제로 분리한다.

## Claude Code 문법 검증 결과 (공식 문서, 2026-09-17)

- Hooks: `.claude/settings.json` → `hooks.PreToolUse[]{matcher, hooks[]{type:"command", command, timeout}}`. stdin JSON에 `tool_name`, `tool_input.command`(Bash) / `tool_input.file_path`(Edit·Write). 차단은 exit 2 + stderr 또는 stdout JSON `hookSpecificOutput.permissionDecision: deny|allow|ask`. `${CLAUDE_PROJECT_DIR}` 사용 가능.
- Subagents: `.claude/agents/<name>.md` frontmatter `name, description, tools, disallowedTools, model, permissionMode, maxTurns, memory`. read-only는 `tools: Read, Glob, Grep, WebFetch, WebSearch` + `disallowedTools: Bash, Edit, Write`.
- Rules: `.claude/rules/*.md` 자동 로드, `paths:` frontmatter로 경로 한정 가능. CLAUDE.md에서 `@path` import(4 hop).
- Permissions: `permissions.deny: ["Bash(rm -rf data*)", "Edit(CLAUDE.md)", "Edit(data/manifests/**)"]` 형태 지원, deny→ask→allow 순 first-match.

## 검증된 스택 사실 (PyPI JSON API · 라이브러리 소스 · 논문 원문, 2026-09-17)

| 사실 | 설계 반영 |
|---|---|
| torch 2.14.0 / torchvision 0.29.0, Python ≥3.10. uv 공식 가이드의 index는 `pytorch-cpu`, `cu118`, `cu126`, `cu128`, `cu130` (cu124 없음) | extras `cpu` / `cu128`, `[tool.uv] conflicts`, `explicit = true` 인덱스 |
| hydra-core 1.3.7 (classifier 3.7~3.11), omegaconf 2.3.1. 1.3.4+에 `instantiate` 보안 blocklist | 프로젝트 Python **3.11 고정**(`.python-version`), `hydra-core>=1.3.7` |
| mlflow 3.16.1: 기본 tracking URI가 이미 `sqlite:///mlflow.db`. metric/tag key는 `[A-Za-z0-9_.- :/]`, 250자 이하. `search_runs(filter_string="tags.protocol_hash = '...'")` 유효 | key 이름 규칙을 tracking 모듈에서 검증. 실험 비교는 tag 기반 검색 |
| numpy(3.11)→2.4.6, scikit-learn 1.9.1(≥3.11), pydantic 2.13.5, pytest 9.1.1, ruff 0.16.8, dvc 3.67.1 | 그대로 pin |
| **torchvision.io.read_video는 0.26에서 제거됨**. decord는 2021년 이후 방치. PyAV 18.1.0은 FFmpeg 번들 wheel(≥3.11) | 비디오 디코딩은 **PyAV(`av`)** 로 통일, opencv-headless는 face crop용 |
| ISO/IEC 30107-3: APCER는 **PAI species별**로 정의, 시스템 평가는 max over PAI 권고. **ACER는 표준에서 deprecated**(OULU-NPU/경진대회 관례). HTER=(FAR+FRR)/2 + dev-set EER threshold는 cross-dataset 문헌 관례. 표준 준수 보고는 BPCER@APCER=10%/1% 운영점 | metrics 모듈에 `apcer_per_pai`, `apcer_max`, `bpcer_at_apcer(target)` 추가. ACER/HTER는 "convention" 태그와 함께 계산. 문서 §14와 일치 |

## 사용자가 이미 내린 결정 (2026-09-17)

| 결정 | 선택 |
|---|---|
| 실제 실험 서버 | **NVIDIA H100 80GB** (실데이터는 서버에만 있음). 이 샌드박스는 CPU 전용 → 하네스는 CPU+합성데이터로 개발·검증, H100에서 같은 lock으로 실행 |
| CLAUDE.md 형태 | **요약 CLAUDE.md(200~300줄) + 전문은 `docs/RESEARCH_CONTRACT.md`에 원문 그대로 + `.claude/rules/` 4개 파일로 규칙 분리** |
| Phase 0 범위 | **DoD 22항목 전부 + 합성데이터로 도는 frame/video baseline 스켈레톤(CPU smoke test end-to-end)**. 실데이터 baseline(Task 8~10)은 H100 세션 과제 |
| 언어 | **코드·식별자·docstring·commit 영어 / CLAUDE.md·rules·agent 프롬프트·ADR·report 템플릿 한국어(용어 영어 병기)** |
| 커밋·PR 단위 | **브랜치 `claude/youthful-newton-fl60mp`에 의존성 순 커밋, draft PR 하나**. 각 커밋마다 ruff+pytest 통과 |

## (아래 섹션은 설계 워크플로우 결과를 반영해 채운다)

## 핵심 설계 결정
## 저장소 파일 트리
## 작업 순서 (의존성 순)
## 각 컴포넌트 상세 설계
## Hooks / Subagents / Rules 설계
## 검증 방법
## 리스크
## 사용자 결정 필요 항목

---

# 최종 확정 설계 (워크플로우 종합안 + 비판 반영, 2026-09-17)

종합 마스터 플랜 원문: `/tmp/claude-0/-home-user-harness/c23e4ea2-9a1e-5092-a984-5827b32b240a/scratchpad/master_plan.md` (D1~D15, 파일 트리, T0~T12, 컴포넌트 상세). 아래는 비판(DoD critic 10건, hook refuter 22건)을 반영해 **바뀐 점**만 적는다. 그 외는 마스터 플랜대로.

## 사용자 결정 반영 (마스터 플랜 D9 덮어씀)
- CLAUDE.md = 요약본(≤300줄) + `docs/RESEARCH_CONTRACT.md` = 원문 verbatim(sha256 pin) + `.claude/rules/` 4개(운영 델타 + §37 4개 흐름 표 + §25 대비 실제 구조 편차표).
- CI: GitHub Actions 1 job(ruff+pyright+pytest CPU) 포함. CUDA extra는 `cu128`(uv 공식 페이지의 현행 index; H100 서버 `nvidia-smi` CUDA Version ≥12.8 확인 후 필요 시 cu126/cu130으로 1줄 교체). torchvision 제외(Phase 0 미사용). dvc는 별도 extra.
- protocol_hash에 `protocol_id` 포함. `PAD_DATA_ROOT` 단일 env. research-reviewer `model: inherit`. `.claude/**` deny 승격은 Phase 0 완료 후 사용자.

## 비판 수용 (설계 변경)
1. **registry는 로컬 파생 인덱스**(gitignored, deny 유지). MLflow가 진실. `SMOKE_OK`는 registry, `find_baseline`은 MLflow. spec 파싱 실패도 registry `invalid_spec` row. `GitState.dirty`는 tracked 변경만, untracked는 count만.
2. **adaptation set**은 `data/manifests/adaptation/`(gitignored, 결정적 재생성)에 train/adapt 시작 시 또는 `validate_protocol --materialize`로만 생성. validator는 파일을 쓰지 않는다.
3. **smoke 최종 status는 항상 `smoke_ok`**(gate verdict는 tag `gate_verdict` + `regression_check.json`에만). `security_regression|inconclusive`는 full에만.
4. **protocol ↔ adaptation 결합 해제**: `adaptation.enabled ⇒ protocol.target_adaptation.enabled`(단방향). e01/e02/e03 모두 `syn_a_to_b_bf_adapt_v1` 아래에서 실행 → 같은 protocol_hash로 source-only vs DA 직접 비교(§14.3). `syn_a_to_b_v1`은 parent/ablation용.
5. 합성 protocol `min_attack_samples_per_pai: 4`, 합성 데이터 subject당 8 clip(bona 4/print 2/replay_phone 1/replay_tablet 1) → test PAI당 ≥4 → gate가 `pass|security_regression`을 실제로 계산.
6. `research_claim_allowed`는 `ManifestMeta.pii_policy == "synthetic"` 기준(§27.3 이름 분기 금지).
7. adapt.py는 source dev도 재평가해 `regression_check.json`에 `source_domain_delta` 기록(verdict 미반영, §41-7).
8. `ThresholdPolicy.fit(table: ScoreTable)` — role != dev면 `ThresholdLeakageError`(타입 수준).
9. `science_hash` 제외: `execution`, `tracking`, `adaptation.source_run_id/source_checkpoint`, `experiment.title/hypothesis`, `training.num_workers/device`.
10. `DataSpec.source/target` optional(§16 예시 그대로 검증, protocol과 불일치 시 error). `model.input.frames`가 정본. `losses/pad_loss.py` 추가. 데이터 스크립트는 `scripts/prepare_dataset.py --adapter <name>` 하나.
11. `SmokeLimits` 상한(`max_batches ≤ 20`, `max_epochs ≤ 1`, `max_eval_batches ≤ 20`). latency.json에 `smoke: true` 플래그.
12. 테스트 격리: `PAD_REPO_ROOT` env로 REPO_ROOT 재지정(패키지만; hook은 env 분기 없음). conftest `tmp_repo` fixture가 configs 복사 + 소형 합성 manifest + tmp sqlite MLflow.
13. **무인 full run = 승인 토큰 파일**: 사용자가 자기 터미널에서 `python scripts/approve_full_run.py --exp X` → `experiments/approvals/<exp_id>.<science12>.json`(gitignored). hook: 토큰 science_hash 일치 → allow, 없으면 ask. Claude는 permissions.deny + guard로 토큰 생성 불가.
14. Hook 파서: shlex(punctuation_chars) 세그먼트 분할, wrapper 제거, `bash -c`/`eval` 1단계 재귀, `$`/`~`/cd 체인 → ask, 절대경로 realpath → 프로젝트 상대화. 복합 명령에는 절대 `allow`를 내지 않음(결정 없음 → permissions). 규칙 ID DG-01~14 / EXP-01~10 / PF-01~11 / HK-00,02,03,99. Python 3.8 호환 문법, fail-safe(예외 → ask; gate는 deny). deny는 비가역 손실만, `git reset --hard`·`clean -f`·`branch -D`·`push --force`(non-main)·업로드류는 ask.
15. matcher: `Edit|MultiEdit|Write|NotebookEdit`, SessionStart `startup|resume|compact`. MCP 쓰기 도구(`mcp__github__push_files`, `create_or_update_file`, `delete_file`, `create_repository`, `fork_repository`, Notion 업로드) permissions.deny; `Artifact` ask. 3 agent 모두 `disallowedTools`로 상속 차단. paper-researcher는 `tools:` 생략(학술 MCP 상속) + disallowed.
16. PostToolUse 매핑은 명시적 dict, integration 테스트는 `test_validate_cli`만 예외, `uv run --no-sync`, `-p no:cacheprovider --timeout 60 -m "not slow and not integration"`, 내부 100 s / hook 120 s. conftest에서 torch import는 fixture 내부, `MLFLOW_TRACKING_URI`/`PAD_DATA_ROOT` autouse monkeypatch.
17. Makefile은 train/adapt를 호출하지 않음(치트시트에 직접 명령). `session_start.py`에 최상위 디렉터리·exp 목록·계약서 sha 불일치 경고·`disableAllHooks`/`Bash(*)` 경고 추가.
18. `test_cpu_extra_has_no_cuda` → 설치된 torch build에 맞춰 검증(H100에서도 통과). hooks는 세션 재시작 후 적용됨을 README에 명시.

## 기각
- 하네스 자체 실행 가능 prototype adaptation, GRU 변형, Dockerfile, pre-commit, pytest-cov, skills, 별도 `guard_mcp.py` hook(permissions.deny로 충분), `dvc` 필수 설치(별도 extra).

## 구현 순서
T0 스캐폴드·계약서·rules·agents·settings(permissions) → T1 pyproject/uv/utils → T2 manifest+synthetic → T3 protocol → T4 metrics → T5 spec/Hydra/validator/gate/registry → T6 tracking → T7 models/adaptation/trainer/evaluator/scripts → T8 report → T9 hooks → T10 research store → T11 README/DoD/E2E → T12 CI. 단일 브랜치, 의존성 순 커밋, draft PR 1개.

## T13 — 스킬 + 루틴 커맨드 레이어 (사용자 추가 요청, 2026-09-17)
- 근거: 커뮤니티 조사(superpowers 288k★, ECC 261k★, awesome-claude-code 54k★ 등). 플러그인 통째 설치는 기각(SessionStart hook·강제 게이트가 계약 §37과 충돌). 개별 스킬만 vendoring, 각 폴더에 `ATTRIBUTION.md`(출처 URL·commit·라이선스).
- vendoring(MIT): `verifying-before-completion`(superpowers), `debugging-systematically`(superpowers + ML 체크: seed/loader 결정성/protocol hash/NaN), `designing-experiments`(superpowers brainstorming → 최소 가설·ablation, 출력은 `research/hypotheses/` → `configs/exp/`), `recording-adrs`(ECC, §26 템플릿·`research/decisions/`), `handoff`(REMvisual 구조 + pedrohcgs checkpoint 필드), `fetching-paper-source`(K-Dense paper-lookup + davila7 verify_citations.py; 비-arXiv PDF는 Anthropic pdf 스킬). 자체 작성: `using-hydra-mlflow-dvc`(§20~22 요약, `paths:`로 configs/·tracking/에만 로드, `user-invocable: false`).
- 루틴 커맨드(모두 `disable-model-invocation: true`, `allowed-tools` 최소, `!`주입은 `|| true`): `/출근`(=start-day), `/퇴근`(=end-day), `/handoff`, `/new-exp <id> <H>`, `/smoke <exp>`, `/review-run <run_id>`(context: fork, agent: research-reviewer, background: false), `/paper <id|doi|url>`(context: fork, agent: paper-researcher), `/adr <slug>`. 금지 사항을 각 본문에 명시(full run 실행·protocol/manifest/claims 편집·업로드·approvals 쓰기 금지). 한글 디렉터리명 등록 여부 미검증 → `start-day/` 폴더 + `.claude/commands/출근.md` 별칭으로 이중 등록 후 확인.
- 기각: academic-research-skills(CC BY-NC), ARIS(자율 실험 실행), 무라이선스 저장소, HF trackio.
