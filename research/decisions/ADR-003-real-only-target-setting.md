# ADR-003 — 기본 DA 설정은 Real-only(Bona-fide-only) Target Adaptation이다

## Status
Accepted

## Context

Target 환경에는 Spoof 샘플이 거의 없고 정상 사용자(bona-fide) 데이터만 있는 것이 현실적 상황이다(계약서 §2.8).

```text
Target
Real
Real
Real
Real
...
```

이 데이터를 그대로 전체 모델에 fine-tuning하면 기존 spoof knowledge가 약해질 수 있다(§2.8, §5).

- §5.1 Naive fine-tuning: 모델이 받는 메시지는 "이 Target 카메라에서 들어오는 패턴은 Real이다" 뿐이며, Real 영역이 과도하게 넓어지면 Spoof가 Real 영역으로 들어올 수 있다.
- §5.2 Catastrophic forgetting: 잊어버리는 대상이 print texture, display artifact, replay temporal artifact, reflection, moiré, spoof-specific representation이라 일반 forgetting보다 위험하다.
- §5.3 Video에서는 Replay Attack이 **같은 target 카메라로 촬영**되므로 환경 cue(sensor noise, FPS, codec, compression, exposure, illumination flicker)를 Real cue로 학습하면 Replay에 취약해진다.

## Decision

- Protocol의 기본 `target_adaptation.supervision`은 **`bona_fide_only`**다(§15 예시). Adaptation 집합은 target `source_split`에서 bona-fide 라벨만, `selection_seed`로 결정적으로 선택하고 test와 subject-disjoint여야 한다(validator: `ADAPT_SUPERVISION_LABEL_MISMATCH`, `ADAPT_TEST_SUBJECT_OVERLAP` 등).
- 이 설정의 위험(security regression)을 **먼저 측정**한다: E03(naive full FT, real only)은 필수(§43), 그 다음 preservation 방법(E04/E05/E07)을 설계한다(§11).
- 평가는 항상 공격 유형별 APCER(§14.2)와 security regression gate(§14.3)를 포함하며, target BPCER 개선만으로 "DA 성공"이라 말하지 않는다(§30).

## Alternatives Considered

1. **Few-shot spoof 포함(Real + Spoof few-shot)** — E06 "idealized comparison"(§43)으로 유지한다. 상한(upper bound) 비교로서 가치가 있지만, Target에서 spoof를 소량이라도 의도적으로 수집할 수 있는지가 미확정(§53 Q6)이므로 기본 설정으로 채택하지 않는다.
2. **Unsupervised DA(target unlabeled real+spoof 혼합)** — 문헌(`liu2022sdafas`, `he2024ccga`)의 표준 설정이지만, target에 spoof가 사실상 없다는 우리 조건과 다르다. 비교군으로만 참고한다(§10).
3. **DA를 하지 않음(source-only 배포)** — E02가 baseline. Domain shift에 대한 대응이 없으므로 채택하지 않지만 항상 같은 protocol_hash로 함께 보고한다.

## Why

- 제품 배포 시 실제로 얻을 수 있는 데이터가 target bona-fide뿐이라는 제약이 연구 질문(§0 핵심 질문, RQ2/RQ3)을 정의한다.
- 가장 위험한 설정을 기본으로 두어야 preservation 방법의 필요성과 효과를 정직하게 검증할 수 있다(§11, §43).
- Protocol이 supervision을 소유하고 hash에 포함하므로, real-only와 few-shot spoof 결과가 같은 hash로 섞여 비교되는 일을 막는다(ADR-004).

## Risks

- 열린 질문 §53 **Q7**: "Real-only라는 연구 설정이 실제 운영 제약인지, 단순 연구 설정인지?" — 운영 제약이 아니라면 few-shot spoof(E06)가 실무 기본이 될 수 있다. 이 ADR은 그 답이 나오면 재검토한다.
- 열린 질문 §53 **Q6**: "Target에서 spoof를 소량 의도적으로 수집할 수 있는가?" — 가능하다면 E06이 현실적 비교군이 된다.
- Real-only adaptation이 §5의 security regression을 실제로 일으키는지는 아직 측정되지 않았다(H2 untested). regression이 관측되지 않으면 preservation 연구의 동기가 약해진다 — 그 경우에도 결과를 그대로 기록한다(§35).
- Adaptation 샘플이 test와 겹치면 결과가 무효다(§6.1 leakage 금지) → validator와 `exclude_adaptation_samples: true`로 강제.

## Evidence

- 계약서 §0, §2.8, §4 RQ2/RQ3, §5, §10, §11, §14.3, §43(E03/E06), §53 Q6/Q7.
- 문헌 claim: `research/claims/claims.jsonl` `ota_2025_oneclass_001`(`li2025ota` one-class 분석, **미검증**, value null).
- 실험 증거는 아직 없음. 합성 데이터 run은 증거가 아니다.

## Date
2026-09-17
