---
name: recording-adrs
description: Records important research and engineering decisions as Architecture Decision Records in research/decisions/ADR-NNN-slug.md using the contract §26 template (Status, Context, Decision, Alternatives Considered, Why, Risks, Evidence, Date), written in Korean, with the draft shown for approval before any file is written and the index research/decisions/README.md updated. Use when the user says "ADR", "record this decision", "we decided", when an alternative is rejected with a stated reason, or when asked why an earlier choice was made.
metadata:
  origin: https://github.com/affaan-m/ECC/tree/dd6ee538aee0f548d4a6b520118f875431fd749e/skills/architecture-decision-records
  license: MIT
  commit: dd6ee538aee0f548d4a6b520118f875431fd749e
---

# ADR 기록 (recording-adrs)

중요한 연구/엔지니어링 결정을 코드 옆에 남긴다. 목적은 계약 §26 그대로: **나중에 Claude가 과거에
버린 아이디어를 이유도 모르고 다시 도입하지 않게** 하는 것이다. Slack, PR 코멘트, 대화 기억에만 있는
결정은 없는 결정이다.

## 언제 발동하는가

- 사용자가 "ADR", "이 결정 기록해", "우리 X로 가기로 했다", "Y 대신 X를 쓰는 이유는…"이라고 말할 때
- 두 개 이상의 대안(프로토콜 설계, 모델 계층, DA 방법, threshold 규칙, 데이터 정책, 도구 선택)을
  비교한 뒤 하나를 고르고 이유를 말했을 때 → **기록을 제안**한다(자동 생성은 하지 않는다)
- "왜 X를 골랐지?"라는 질문 → 기존 ADR을 읽어서 답한다
- `designing-experiments` / `/end-day`가 결정 후보를 넘겼을 때

## 기록 위치와 이름

```
research/decisions/
├── README.md                     ← 색인 (표)
├── ADR-001-use-video-input.md
├── ADR-002-switch-dg-to-da.md
└── ADR-NNN-<kebab-slug>.md       ← 세 자리 번호, 영문 slug
```

번호는 `ls research/decisions/ADR-*.md`의 최댓값 + 1. 기존 ADR 파일은 보호 대상(수정 시 사용자
확인)이며, 이 스킬은 **새 파일 추가**와 README 색인 갱신만 한다. 과거 ADR을 바꾸려면 새 ADR로
`Superseded` 처리한다.

## 템플릿 (계약 §26 — 헤더 이름과 순서를 바꾸지 않는다)

```markdown
# ADR-NNN — 제목

## Status
Accepted / Proposed / Superseded

## Context

## Decision

## Alternatives Considered

## Why

## Risks

## Evidence

## Date
```

작성 지침(각 절 2–6문장, 전체 2분 안에 읽히는 길이):

- **Status**: 세 값 중 하나만. Superseded면 `Superseded by ADR-MMM`.
- **Context**: 어떤 문제/제약이 이 결정을 강제했는가. 연구 결정이면 RQ 번호와 protocol_id를 적는다.
- **Decision**: 현재형 한두 문장. "우리는 X를 쓴다."
- **Alternatives Considered**: 대안마다 `- **이름** — 장점 / 단점 / 기각 이유`. "그냥 골랐다"는
  기각 이유가 아니다. 최소 1개.
- **Why**: 결정의 근거. 무엇보다 이 절이 중요하다.
- **Risks**: 이 결정이 틀렸을 때 무엇이 깨지는지, 되돌리는 조건.
- **Evidence**: 실험 결정이면 run_id, protocol_hash, seed, metric(공격별 APCER 포함), 논문 결정이면
  claim_id. 근거 수치 없이 "더 좋았다"고 쓰지 않는다(§30). 없으면 `없음 — 설계 판단`이라고 명시.
- **Date**: `YYYY-MM-DD`.

## 절차

1. **결정 식별** — 한 문장으로 핵심 선택을 요약해 사용자에게 확인한다.
2. **문맥 수집** — 관련 hypotheses / 실험 리포트 / claims / 기존 ADR을 읽는다. 같은 주제의 ADR이
   이미 있으면 새로 쓰지 말고 Superseded 관계를 제안한다.
3. **대안과 근거 정리** — 대화에서 실제로 언급된 대안만 적는다. 지어내지 않는다.
4. **번호 배정** — 기존 최댓값 + 1.
5. **초안 제시** — 전체 초안을 채팅에 보여주고 명시적 승인을 기다린다. **승인 전에는 파일을 쓰지
   않는다.** 거절하면 초안을 버린다.
6. **파일 쓰기** — `research/decisions/ADR-NNN-slug.md`.
7. **색인 갱신** — `research/decisions/README.md`에 행 추가(없으면 표 헤더와 함께 생성).

## 색인 형식 (`research/decisions/README.md`)

```markdown
# Architecture Decision Records

| ADR | 제목 | Status | Date |
|-----|------|--------|------|
| [001](ADR-001-use-video-input.md) | Video 입력 채택 | Accepted | 2026-09-10 |
```

## 기존 ADR 읽기 ("왜 X를 골랐지?")

1. `research/decisions/README.md`에서 관련 행을 찾는다.
2. 해당 파일의 Context / Decision / Why를 요약해 답한다.
3. 없으면: "관련 ADR이 없습니다. 지금 기록할까요?"

## 기록할 가치가 있는 결정 / 없는 결정

| 기록한다 | 기록하지 않는다 |
|---------|----------------|
| 입력 모달리티(frame vs video), DG→DA 전환, real-only 설정 | 변수 이름, 포맷팅 |
| protocol 정의·threshold 규칙·ACER 정책·gate tolerance | 한 번 쓰고 버릴 스크립트 |
| baseline 채택/기각, 논문 재현 포기 사유 | 이미 계약(§)에 명시된 규칙의 반복 |
| 도구 선택(uv, MLflow, DVC), 데이터 거버넌스 정책 | 실험 결과 자체(→ experiments/reports) |
| 실패한 실험에서 얻은 "다시 하지 말 것" | |

## 금지

- 승인 없이 파일 쓰기, 기존 ADR 본문 수정, 번호 재사용
- Evidence에 검증되지 않은 수치·논문 수치 기입 (claims.jsonl의 `verified: true` 행만)
- 데이터셋 경로·얼굴 프레임 포함 (logical dataset_id만, §34)
- 템플릿 헤더 추가/삭제/순서 변경
