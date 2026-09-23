# ADR-012 — Target 적응을 두 설정으로 병행한다: R(real-only, 주 연구) · S(few-shot supervised, 비교 축)

## Status
Proposed — 방향은 사용자가 결정했다(2026-09-22, "두 가지 버전으로 가보자"). 아래 Decision 3·4의 세부 설계는 제안이며, 사용자 확인 후 Accepted로 바꾼다. 코드는 아직 없다.

## Context

ADR-003은 기본 설정을 real-only(bona-fide-only)로 정하고, target spoof를 소량 쓰는 설정은 E06 "idealized comparison"으로만 남겼다. 그런데 사용자가 지금 쓰는 파이프라인(`da_dataset.py`, 이 저장소 밖, 읽기만 함)은 정확히 그 반대편 설정이다: target 도메인의 subject 일부를 **라벨 전체(real + attack)와 함께** few-shot으로 쓰고 나머지를 평가한다.

두 설정은 답하는 질문이 다르다.

- **R (real-only)**: "target에서 진짜 얼굴만 보고 적응할 때, source에서 배운 공격 탐지 능력을 잃는가?" — 이 저장소의 핵심 연구 질문(계약서 §0).
- **S (few-shot supervised)**: "target 공격 라벨이 조금 있으면 얼마나 나아지는가?" — R의 **상한**이자, "target spoof를 수집할 가치가 있는가"(§53 Q6)에 대한 답.

둘을 같이 보면 R→S 차이가 곧 "target 공격 라벨의 값어치"가 된다. 단, 그 차이는 **두 설정이 같은 test set에서 평가될 때만** 의미가 있다.

## Decision

1. **R: `target_adaptation.supervision: bona_fide_only`** — ADR-003 그대로. 주 연구 설정이다.
2. **S: `target_adaptation.supervision: bona_fide_and_spoof_fewshot`** — E06을 비교군에서 정식 연구 축으로 올린다. protocol schema가 이미 이 값을 지원한다(`protocols/schema.py::Supervision`).
3. **(제안) target test set을 두 설정이 공유한다.** target 도메인을 한 번, 결정적으로, subject 단위로 "적응 풀(pool)"과 "test"로 나눈다(ADR-008과 같은 `sha256(dataset_id:subject_id)` 정렬). R과 S는 적응 샘플을 풀에서만 고른다. 그러면 두 설정의 test clip이 완전히 같다.
   - `supervision`이 `protocol_hash`에 들어가므로 R과 S의 hash는 다르다(ADR-004). 두 설정 비교는 `summarize_experiment.py --justify "same target test set; supervision differs"`로 하고 배너가 붙는다. 이것은 의도된 동작이다.
   - 각 설정의 source-only control(`adaptation.method: none`)은 그 설정의 protocol 아래에서 돌려 hash를 공유한다.
4. **(제안) S의 예산 = R의 bona-fide 적응 집합 + 공격 k개.** S가 R과 "공격 라벨이 추가됐다"는 한 가지만 다르게 만들어, R→S 차이를 그 한 변수에 귀속시킨다. (총 샘플 수를 같게 맞추는 대안은 S가 bona-fide를 덜 보게 되어 두 변수가 섞인다.)
5. **평가는 두 설정 모두 공격별 APCER + security regression gate**(§14.2, §14.3). S는 추가로 **"적응 때 본 PAI" / "보지 않은 PAI"를 나눠** 보고한다. S가 좋아진 것이 본 공격 종류에만 해당하는지를 드러내기 위해서다.
6. `da_dataset.py`의 분할(난수 seed로 subject를 섞고, 원래 split을 무시)은 **재사용하지 않는다.** 그 결과는 이 저장소의 protocol과 다른 분할에서 나온 것이므로 직접 비교 대상이 아니다.

## Alternatives Considered

- **R만 한다(ADR-003 원안)**: 상한이 없어서, R이 얼마나 나쁜지를 "무엇에 비해" 말할 수 없다. 기각.
- **S만 한다(현재 사용자 파이프라인)**: target 공격 라벨을 쓰면 "real-only 적응 중 공격 탐지 능력 상실"이라는 핵심 질문이 측정되지 않는다. 기각.
- **UDA(target 라벨 없는 real+spoof 혼합)**: 세 번째 축이 될 수 있지만, target에 spoof가 사실상 없다는 전제(ADR-003)와 다르고 이번 결정 범위 밖이다. 필요해지면 별도 ADR.
- **두 설정이 test set을 따로 갖는다**: 구현은 간단하지만 R→S 차이에 test set 차이가 섞인다. 기각(Decision 3).

## Why

두 설정을 병행하는 가치는 **차이**에서 나온다. 그 차이가 해석 가능하려면 test set이 같고(Decision 3), 설정 간에 다른 변수가 하나뿐이어야 한다(Decision 4). 이 두 조건이 없으면 "S가 R보다 좋다"는 문장이 어떤 원인을 가리키는지 알 수 없다.

## Risks

- **SiW-Mv2**: 빌드 코드가 공격 clip마다 subject_id를 따로 붙인다(공격과 실제 인물의 연결 정보가 데이터셋에 없음). subject 단위 분할이 공격 clip에 대해서는 사실상 clip 단위 분할이 되고, 같은 인물이 풀(공격)과 test(실제)에 동시에 들어가는 것을 막을 방법이 없다. 이 도메인이 target일 때 결과에 명시한다.
- **작은 도메인**: 풀과 test를 나누면 test의 PAI별 공격 수가 `min_attack_samples_per_pai` 미만이 될 수 있다. 그때 gate verdict는 `inconclusive`이며 그것이 올바른 결과다.
- **k(공격 shot 수)와 PAI 구성**: S의 결과는 k와 어떤 PAI를 보여줬는지에 좌우된다. protocol에 고정하고 hash에 포함한다.

## Evidence

- ADR-003(기본 설정과 E06), ADR-004(protocol_hash), ADR-008(결정적 subject 분할).
- `src/pad_research/protocols/schema.py` — `Supervision = Literal["none", "bona_fide_only", "bona_fide_and_spoof_fewshot"]`.
- 사용자 파이프라인 `da_dataset.py::split_target_domain`(읽기만 함): `random.Random(seed)`로 subject를 섞어 few-shot/eval을 나누고, parquet의 `split` 열을 무시한다.
- 계약서 §0, §14.2, §14.3, §43(E06), §53 Q6/Q7.

## Date
2026-09-22
