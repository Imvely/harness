# CLAUDE.md — Passive Video PAD + Domain Adaptation Research Harness (요약본)

> 이 파일은 **요약본**이다. 연구 헌법(research contract) 전문은 `docs/RESEARCH_CONTRACT.md`(2,585줄, sha256 `05625405…`, `conventions.CONTRACT_SHA256`에 pin)에 원문 그대로 있다.
> 이 요약과 전문이 충돌하면 **전문이 우선**하되, 저장소 구조·이름의 편차는 `research/decisions/ADR-005`가 우선한다.
> 운영 규칙은 `.claude/rules/`(research-integrity, experiment-safety, data-governance, coding-style)에 있고 세션마다 자동 로드된다.
> 이 파일과 전문을 수정하는 것은 연구 방향/운영 규칙의 변경이다. 사소한 코드 변경 때문에 바꾸지 않는다.

## 0. 2분 요약 (전문 §0)

- 목표: 얼굴인식 시스템용 **Passive Face PAD**(Presentation Attack Detection = 위조 얼굴 탐지). RGB 짧은 비디오의 미세한 temporal cue를 쓰고, 사용자에게 고개 돌리기 같은 동작을 요구하지 않는다.
- 핵심 연구 질문: **Target 환경의 Bona-fide(진짜) 비디오만으로 모델을 적응(DA)시키면서 Source에서 배운 Spoof 탐지 능력을 어떻게 보존하는가?**
  → "Bona-fide-only Video Domain Adaptation with Spoof Knowledge Preservation".
- 현재 우선순위: 2D print/replay 공격, RGB 우선(ToF는 Phase 8), DG 재현 실패 후 DA로 전환(ADR-002). Proposed method는 아직 **가설**이며 baseline으로 문제 존재를 증명한 뒤에만 구현한다(§11).
- 이 저장소의 목적은 Claude를 더 자율적으로 만드는 것이 아니라 **Claude가 틀리기 어려운 연구 시스템**을 만드는 것이다(§54).

## 1. 세션 시작 절차 (§36) — `/출근` 또는 `/start-day`

1. 이 파일 읽기 (필요 시 전문의 해당 절) 2. `git status` 3. 저장소 트리 4. `research/decisions/` 5. `experiments/registry.jsonl`·MLflow 최근 run 6. 관련 `configs/` 7. 요청을 **Research / Code / Experiment / Analysis**로 분류.
새 구현 전에 반드시 기존 구현을 검색한다.

## 2. 요청 유형별 흐름 (§37)

| 유형 | 흐름 |
|---|---|
| Research | primary paper 검색 → 원문 확인 → Paper Review(§23.1 16개 헤더) → `research/claims/claims.jsonl` → 연구와 연결. `paper-researcher` 위임, `/paper` |
| Reproduction | official repo 확인 → commit pin → env → dataset protocol → smoke → baseline (§27.2) |
| 새 아이디어 | 기존 baseline → failure mode → 최소 가설(`research/hypotheses/`) → 최소 ablation (`designing-experiments` 스킬) |
| Full experiment | spec(`configs/exp/*.yaml`) → `validate_spec` → smoke → full-run flag+승인 → MLflow → evaluation → `research-reviewer`(`/review-run`) |

## 3. 절대 원칙 10개 (§41)

1. Paper claim은 primary source로 검증한다. 2. Protocol이 다르면 metric을 직접 비교하지 않는다(`protocol_hash`). 3. Target adaptation sample과 test sample leakage를 막는다. 4. AUC만 보고 PAD 성공을 판단하지 않는다. 5. DA 전후 **공격별 APCER**를 반드시 비교한다. 6. Real-only DA는 기본적으로 security regression을 의심한다. 7. Source spoof knowledge를 잃는지 측정한다. 8. 실패한 experiment도 기록한다. 9. LLM이 장시간 GPU 명령을 즉흥 실행하지 않고 spec→validation을 통과한다. 10. Proposed 모델보다 문제 존재를 baseline으로 먼저 증명한다.

## 4. 실험 실행 규칙 (§15, §16, §24 요약)

- 실험 spec = Hydra experiment 파일 `configs/exp/<name>.yaml` 하나. 실행은 항상 `uv run --no-sync python scripts/train.py +exp=<name>` (adaptation은 `scripts/adapt.py`).
- `execution.mode: smoke`(기본)에서는 데이터 검증·forward·1~N batch·short dry-run만. `execution.*`는 CLI에서 바꾸지 않는다(유일한 예외: `execution.mode=smoke` 강등).
- Full run 조건: 실험 파일에 `execution.mode: full` + `allow_full_gpu_run: true` 커밋 → `validate_spec --freeze` → 같은 커밋에서 smoke 성공(`smoke_ok`) → in-process gate 통과 → hook의 사람 확인(또는 사람이 만든 승인 토큰 `experiments/approvals/`). 자세한 절차와 hook 규칙표는 `.claude/rules/experiment-safety.md`.
- Protocol(`configs/protocol/*.yaml`)은 source/target 데이터셋, adaptation 예산, test 규칙, threshold 규칙, ACER 정책, security gate 허용치를 소유한다. `protocol_hash`가 같을 때만 직접 비교, 다르면 `--justify` + 배너.
- Threshold는 **dev set에서만** 결정한다(`ThresholdPolicy.fit`는 dev 테이블만 받는다). Security regression gate verdict: `pass | security_regression | inconclusive | comparison_blocked`.
- 합성 데이터(`synthetic_a/b`)는 파이프라인 sanity 전용이며 연구 근거가 아니다(`research_claim_allowed=false`).

## 5. 저장소 구조 (실제; 전문 §25 대비 편차는 ADR-005)

```text
CLAUDE.md  docs/RESEARCH_CONTRACT.md  README.md  pyproject.toml  uv.lock  Makefile
.claude/{settings.json, rules/, agents/, hooks/, skills/, commands/}
configs/{config.yaml, model/, data/, adaptation/, protocol/, exp/}
data/{raw/, processed/, manifests/}          # raw/processed는 gitignore, manifests는 커밋
research/{papers/, claims/, hypotheses/, decisions/, handoffs/}
src/pad_research/{paths, conventions, errors, utils/, data/, protocols/, config/, experiments/,
                  metrics/, models/, adaptation/, losses/, training/, evaluation/, tracking/, reporting/, research/}
scripts/{prepare_dataset, validate_protocol, validate_spec, approve_full_run, train, adapt, evaluate, summarize_experiment}.py
experiments/{specs/ (frozen), reports/, registry.jsonl (로컬 인덱스, gitignore), approvals/ (사람만)}
tests/{unit/, protocol/, integration/, hooks/, fixtures/}
```

## 6. 코딩 규칙 요약 (§27) — 상세는 `.claude/rules/coding-style.md`

읽기 → call path → config 의존성 → 테스트 → 최소 수정. 논문 구현은 official code 우선, 없으면 spec→review→implementation("아마 이렇겠지" 금지). 실험 로직에 dataset 이름 분기 금지(`load_protocol`). APCER/BPCER/HTER는 toy unit test 필수. 코드·docstring·커밋은 영어, 문서·ADR·리포트는 한국어.

## 7. 결과 표현 규칙 (§30, §46)

"이 모델이 더 좋다 / DA가 성공했다 / Video가 확실히 우수하다"는 금지. 반드시 dataset·protocol·seed·metric·threshold policy와 함께 조건부로 말한다. 아이디어는 `[Established]` / `[Adaptation]` / `[Hypothesis]`로 태깅한다. 주요 결과는 3 seeds 이상(mean/std/individual). iBeta/ISO 기준은 기억으로 쓰지 않는다(§33).

## 8. 데이터 거버넌스 (§22, §34) — 상세는 `.claude/rules/data-governance.md`

얼굴 데이터는 민감 biometric data. 외부 업로드(클라우드, public GitHub, HF, MCP 업로드 도구, Artifact 공개)와 raw frame의 로그/리포트 삽입 금지. 로그에는 `dataset_id`와 `manifest_hash`만. 데이터 경로는 `PAD_DATA_ROOT` + manifest `relative_path`.

## 9. 서브에이전트 · 스킬 · 커맨드

- 서브에이전트 3개(§23): `paper-researcher`(read-only + web), `experiment-engineer`(구현·smoke, protocol 변경/full run 금지), `research-reviewer`(read-only 비판적 리뷰).
- 자동 스킬: `verifying-before-completion`, `debugging-systematically`, `designing-experiments`, `recording-adrs`, `handoff`, `fetching-paper-source`, `using-hydra-mlflow-dvc`(configs/tracking 편집 시).
- 루틴 커맨드: `/출근`(`/start-day`), `/퇴근`(`/end-day`), `/인수인계`(`/handoff`), `/new-exp`, `/smoke`, `/review-run`, `/paper`, `/adr`.

## 10. 현재 우선순위와 열린 질문

P0 하네스 무결성·protocol/metric 정확성 → P1 video baseline, real-only DA regression 확인 → P2 prototype/preservation DA, low-motion 평가 → P3 RGB+ToF, 배포 최적화 (§47). 열린 질문 12개는 전문 §53을 backlog로 유지한다.
