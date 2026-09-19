# ADR-006 — 읽기 전용 로컬 대시보드를 §39 예외로 허용하고 계약서를 개정한다

## Status
Accepted

## Context

계약서 §39("구현하지 말아야 할 것 — 초기 과설계 방지")는 Phase 0에서 **자체 experiment dashboard**를 만들지 말라고 명시한다. 금지 취지는 §39 말미가 밝히듯 인프라를 늘리는 대신 **재현 가능성 · protocol integrity · metric integrity · research traceability** 네 가지에 자원을 쓰라는 것이다.

그런데 Phase 0 구현 중 다음이 저장소에 들어왔다.

- `src/pad_research/dashboard/{export,schema}.py` (약 550줄): MLflow run과 `experiments/registry.jsonl`, run artifact(`regression_check.json`, `eval_test.json`)를 읽어 단일 JSON으로 내보낸다.
- `scripts/export_dashboard_data.py`: 위 내보내기의 CLI 진입점.
- `web-mockup/` (React + Vite, 약 400KB): 내보낸 정적 JSON을 `fetch`해서 run 목록, per-PAI APCER, gate verdict, 리포트를 렌더링한다.

이 상태를 그대로 두면 §39와 정면으로 충돌하고, 충돌 사실이 어디에도 기록되지 않는다. 사용자는 대시보드를 유지하되 **계약서를 개정해서** 정합성을 맞추기로 결정했다.

코드를 읽어 확인한 사실:

- `export.py`는 읽기 전용이다. MLflow와 registry를 읽고 JSON 한 개를 쓸 뿐이며 run을 만들거나 수정하지 않는다.
- `web-mockup`에는 실행 경로가 없다. `dashboardLoader.ts`의 `fetch("/dashboard-demo.json")` 외에 네트워크 호출이 없고, `subprocess`·POST·백엔드가 없다.
- `ControlView.tsx`/`controlPreview.ts`는 실행 명령 **문자열을 미리 보여줄 뿐** 실행하지 않는다. 오히려 UI 안에서 "`execution.*` 변경은 `configs/exp/*.yaml`에만", "CLI는 `execution.mode`를 smoke로 낮추는 것만 허용"이라는 §16 규칙을 반복해 표시한다.
- `export.py`에는 `_is_safe_relative_path`, `_safe_tags`, `redact_*`(`utils/redaction.py`)가 있어 절대경로·데이터 경로가 산출물에 섞이지 않게 한다(§34).
- `_research_claim_allowed`와 `_dataset_pii_policies`가 `ManifestMeta.pii_policy`를 읽어 합성 데이터 run에 배너를 붙인다(§30, ADR-005).

## Decision

계약서 §39의 "자체 experiment dashboard" 항목에 다음 예외를 추가하고, 문서 끝에 `부록 D. 개정 이력`을 신설한다.

> **2026-09-19 개정(ADR-006)**: MLflow run·registry·report 산출물을 읽기 전용으로 렌더링하는 로컬 정적 대시보드는 예외로 허용한다. 실험을 실행하거나 config를 바꾸는 control plane, 상시 서버, DB, 인증은 여전히 만들지 않는다.

예외의 경계를 명시한다. 허용되는 것은 **산출물 → 정적 JSON → 정적 렌더링** 한 방향뿐이다. 다음은 계속 금지한다.

- 대시보드에서 학습·적응·평가를 실행하거나 큐에 넣는 기능(§16, §41-9의 spec → validation → smoke → 승인 경로를 우회하게 된다).
- `configs/**`, `data/manifests/**`, `research/claims/**`를 쓰는 기능(§24.4 보호 파일).
- 상시 구동 서버, 데이터베이스, 인증·계정 관리, 원격 호스팅(§34: 얼굴 데이터·artifact 외부 유출 경로).
- 내보낸 JSON에 raw frame, 절대경로, 사용자 경로를 담는 것(§34).

계약서 개정에 따라 `conventions.CONTRACT_SHA256`과 pin된 테스트(`tests/unit/test_research_store.py`, `tests/test_dod_files.py`), `.claude/hooks/session_start.py`, `README.md`, `CLAUDE.md`의 sha를 같은 커밋에서 갱신한다.

## Alternatives Considered

1. **대시보드를 삭제한다.** §39를 글자 그대로 지키는 가장 단순한 선택. 이미 작성되어 테스트와 CI까지 붙은 약 17,000줄을 버리게 되고, per-PAI APCER와 gate verdict를 한눈에 보는 수단이 사라진다. 기각.
2. **별도 저장소/브랜치로 분리한다.** 계약서를 건드리지 않아도 되지만, 대시보드가 읽는 스키마(`dashboard/schema.py`)가 `RunRecord`·`PadMetrics`·registry와 강하게 묶여 있어 두 곳이 조용히 어긋난다. 스키마 변경이 테스트로 잡히지 않게 되는 쪽이 더 위험하다고 판단해 기각.
3. **계약서는 두고 ADR로만 예외를 기록한다.** §39 본문과 실제 저장소가 계속 모순이므로, 다음에 이 문서를 읽는 사람이 어느 쪽을 따를지 알 수 없다. 계약서가 헌법이라는 전제(문서 서두)와 맞지 않아 기각.
4. **지금 선택: 계약서 §39를 개정하고 예외의 경계를 명문화한다.** 금지의 취지(인프라 과설계 방지)를 유지하면서 실제 저장소와 문서를 일치시킨다. 개정 이력과 sha pin으로 조용한 편집은 계속 검출된다.

## Why

- §39가 막으려던 것은 "운영 부담이 있는 실험 관리 인프라"다. 서버도 DB도 실행 경로도 없는 정적 렌더링은 그 부담을 만들지 않는다.
- 오히려 §14.3(Security Regression Gate)과 §30(결과 표현 규칙)이 요구하는 것, 즉 **AUC 하나가 아니라 공격별 APCER와 gate verdict를 같이 보게 만드는 것**을 대시보드가 강제한다. §39가 지키려던 네 가지 중 research traceability에 기여한다.
- 예외를 좁게(읽기 전용, 로컬, 정적) 못 박아 두면, 다음에 "대시보드에서 실험 돌리게 하자"는 제안이 나왔을 때 이 ADR이 근거가 되어 막는다.
- 문서와 코드가 어긋난 채로 두는 것이 가장 나쁜 선택이다. 계약서는 이 프로젝트에서 Claude와 사람 모두의 판단 기준이므로, 예외가 생겼으면 계약서에 드러나야 한다.

## Risks

- **범위가 넓어질 위험**: "조회만"이 시간이 지나며 "여기서 실행도"로 번질 수 있다. 완화: 위 Decision의 금지 목록을 명시했고, 실행·쓰기 기능이 필요해지면 새 ADR로 이 결정을 `Superseded` 해야 한다.
- **유지보수 비용**: `dashboard/schema.py`가 `RunRecord`/`PadMetrics` 변경을 따라가야 한다. 완화: `tests/unit/test_dashboard_export.py`와 `tests/test_web_mockup_files.py`가 스키마 어긋남을 잡는다. CI에 `web mockup build` job이 있다.
- **데이터 유출**: 내보낸 JSON에 경로나 샘플이 섞이면 §34 위반이다. 완화: `_is_safe_relative_path`, `_safe_tags`, `utils/redaction.py`와 `tests/unit/test_redaction.py`가 방어한다. 내보낸 JSON을 외부에 올리는 것은 여전히 금지다.
- **계약서 개정 선례**: 개정이 쉬워지면 헌법의 구속력이 약해진다. 완화: `부록 D. 개정 이력`에 모든 개정을 남기고, sha pin 6곳을 같은 커밋에서 갱신해야만 테스트가 통과하도록 했다.

## Evidence

- 계약서 §39(금지 목록과 "재현 가능성 + protocol integrity + metric integrity + research traceability" 취지), §14.3, §16, §24.4, §30, §34, §41-9.
- 코드 확인: `src/pad_research/dashboard/export.py`(MLflow·registry 읽기, `_is_safe_relative_path`, `_safe_tags`, `_research_claim_allowed`), `web-mockup/src/data/dashboardLoader.ts`(정적 JSON `fetch` 한 곳), `web-mockup/src/db/controlPreview.ts`(명령 문자열 생성만), `web-mockup/src/components/ControlView.tsx`(§16 규칙을 UI에 표시).
- 검증 실행(2026-09-19, 커밋 `4802dc1` 기준): `pytest -m "not slow"` 514 통과, `pytest -m slow` 2 통과, `ruff check` · `pyright src scripts` 통과, GitHub Actions `lint typecheck test` / `web mockup build` 모두 success.
- 하네스 동작 근거: E03 적응 smoke(run `34ee9f1093414b7f8059f312c2fdc713`, baseline `ade62c7e12c64d87a247dfd43f7f7f0a`, protocol_hash `c9b36ca83c9a…`)에서 BPCER 1.0 → 0.0인 동시에 print APCER 0 → 1이 되어 gate가 `security_regression`을 냈다. 합성 데이터이므로 연구 결과가 아니라 파이프라인 동작 증거다(§30, `research_claim_allowed=false`).
- 관련 결정: ADR-005(Phase 0 범위·규약, 계약서 sha pin 메커니즘), ADR-004(protocol hash).

## Date
2026-09-19
