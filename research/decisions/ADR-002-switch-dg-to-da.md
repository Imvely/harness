# ADR-002 — 연구 중심을 Domain Generalization에서 Domain Adaptation으로 전환한다

## Status
Accepted

## Context

과거에는 DG 계열(GD-FAS, IADG, ResNet 기반 방법, CLIP feature 활용 방법)을 검토/구현했다(계약서 §3.1). 로컬 재현에서 다음이 관측되었다.

- cross-dataset에서 정확도가 약 50% 수준까지 떨어진 실험이 있었음
- AUC가 약 0.5 근처까지 떨어진 실험이 있었음
- 논문 표의 성능과 공개 코드/로컬 재현 성능 사이에 큰 차이를 경험함

이 관측은 `research/claims/claims.jsonl`의 `local_dg_repro_001`(source_type `local_observation`, value null)로 기록되어 있다.

한편 실제 제품 조건에서는 Target 환경(새 카메라/조명/매장)의 **bona-fide 비디오**를 비교적 쉽게 수집할 수 있다(§2.8, §0).

## Decision

연구 중심을 **Video + Domain Adaptation**(§3.2)으로 전환한다. 구체적으로:

```text
Passive RGB Video → Video PAD backbone → Spatio-temporal representation
  → Target adaptation → Spoof knowledge preservation
```

이 결정의 **정확한 표현**은 다음 문장이며, 리포트·논문·대화에서 이 표현을 사용한다.

> 현재 사용한 데이터 구성, 구현, 전처리, 학습 조건에서 DG 계열 재현 성능이 기대보다 낮았으며, 실제 Target 환경 데이터를 활용할 수 있는 제품 조건을 고려해 DA를 중심으로 연구 방향을 전환했다.

다음과 같이 **일반화하지 않는다**(§3.1 주의):

```text
"DG는 모두 안 된다" ❌
"해당 논문은 성능을 조작했다" ❌
```

## Alternatives Considered

1. **DG 계열 재현을 계속 시도** — 재현 격차의 원인(데이터 구성, 전처리, 구현)을 끝까지 추적하는 선택. 학술적으로 가치가 있으나 제품 일정과 Target 데이터 활용 가능성을 고려해 우선순위에서 내림. DG-style source pretraining은 SFDA의 전처리 단계(`liu2024sdafaspp`)로 다시 들어올 수 있으므로 완전히 버리지 않는다.
2. **DA 없이 source-only video 모델만 배포** — E02(source-only)가 baseline이며, 항상 함께 측정한다. 단독 채택은 target domain shift에 대한 대응이 없다.
3. **Target에서 spoof까지 수집하는 supervised DA** — 이상적 비교(E06)로 유지하되, 현실 제약(§2.8, §53 Q6)상 기본 설정이 아니다(ADR-003).

## Why

- 제품 조건에서 target bona-fide 데이터가 존재하므로 이를 활용하지 않는 DG보다 DA가 자연스럽다.
- 로컬 DG 재현 실패는 **현재 로컬 구현에서 관측한 결과**이지 방법 전체의 무효를 뜻하지 않는다(§0 마지막 항목). 따라서 "DG 폐기"가 아니라 "우선순위 전환"이다.
- 전환 후 핵심 위험(real-only DA의 security regression, §5)이 새 연구 문제(RQ2/RQ3)를 정의한다.

## Risks

- DG 재현 격차의 원인을 규명하지 않은 채 전환하므로, 같은 원인(데이터 구성/전처리)이 DA 실험에도 영향을 줄 수 있다. → Phase 1 "Data & Evaluation Sanity"(§29)에서 protocol·manifest·metric을 먼저 검증한다.
- Real-only DA는 spoof knowledge를 잊을 수 있다(§5). → E03을 반드시 측정(§43)하고 security regression gate(§14.3)를 둔다.
- 과거 DG 관측을 근거로 논문을 폄하하는 표현이 리포트에 섞일 수 있다. → 위 "정확한 표현"과 금지 표현을 리뷰어(§23.3) 체크 항목으로 둔다.

## Evidence

- 계약서 §0, §2.6, §2.8, §3.1, §3.2, §5.
- `research/claims/claims.jsonl`: `local_dg_repro_001` (로컬 관측, 일반화 불가).
- 정량 근거(과거 run의 정확한 설정·로그)는 아카이브되어 있지 않다. 이 ADR은 방향 결정의 기록이며 DG 방법에 대한 실험적 판정이 아니다.

## Date
2026-09-17
