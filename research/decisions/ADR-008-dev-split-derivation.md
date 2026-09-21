# ADR-008 — dev split이 없는 데이터셋에서 threshold용 dev set을 만드는 규칙

## Status
Proposed — 코드는 아직 없다. Phase 1 adapter를 쓰기 **전에** 결정되어야 하며, 사용자가 승인하면 adapter가 이 규칙을 구현한다.

## Context

계약서의 타협 불가능한 규칙 하나: **threshold는 dev set에서만 정한다.** 코드 수준에서도 막혀 있다 — `ThresholdPolicy.fit(table)`은 `ScoreTable.role == "dev"`가 아니면 예외를 던진다.

이유는 단순하다. 모델은 각 영상에 "가짜일 확률" 점수를 뱉고, `score >= tau`면 spoof로 판정한다. 이 `tau`를 test set을 보고 고르면 성능이 마법처럼 좋아지는데, 그것은 시험 문제를 보고 답을 고른 것이라 아무 의미가 없다.

문제는 **네 데이터셋이 모두 공식 dev split을 제공하지는 않는다**는 것이다. 어떤 것은 train/dev/test 3분할이고, 어떤 것은 train/test 2분할이다. 정확히 어느 쪽인지는 각 데이터셋에 동봉된 공식 protocol 파일을 읽어야 확정되며, 이 ADR은 **그 확인 전에 규칙을 정해 두기 위한 것**이다 — adapter를 쓰다가 즉석에서 정하면, 그 결정이 코드 한 줄에 묻힌 채 아무도 모르게 결과를 좌우한다.

`ocim_target_i_v1`은 `threshold.dev_domain: source`다. 즉 tau는 source 쪽에서 정해진다. 그러면 질문은 "**source train에서 dev를 어떻게 떼어내는가**"로 좁혀진다.

## Decision

**규칙 A — source train에서 subject-disjoint하게 떼어낸다.** 공식 dev split이 있으면 그것을 쓰고, 없으면 해당 데이터셋의 train에서 일부 **subject 전체**를 dev로 옮긴다.

구체적으로:

1. **subject 단위로만 자른다.** 클립 단위로 자르면 같은 사람이 train과 dev에 동시에 들어가 `SUBJECT_OVERLAP_SPLITS` validator에 걸리고, 걸리지 않더라도 tau가 "이 사람에 맞춘 tau"가 된다.
2. **비율은 subject의 20%**, 최소 2명. 데이터셋마다 다른 숫자를 쓰지 않는다.
3. **선택은 결정적(deterministic)이다.** `sha256(f"{dataset_id}:{subject_id}")`로 정렬해 앞에서부터 고른다. 난수 seed가 아니라 해시를 쓰는 이유는, subject 목록이 바뀌지 않는 한 **언제 어디서 빌드해도 같은 dev set**이 나오고 그 사실이 `manifest_hash`에 박히기 때문이다.
4. **bona-fide와 각 PAI가 dev에 모두 존재해야 한다.** 없으면 adapter가 실패한다 — 공격이 한 종류도 없는 dev set에서 정한 tau는 EER을 계산할 수조차 없다.
5. 이 파생은 **adapter가 manifest를 만들 때** 일어나고, `ManifestRecord.split`에 `dev`로 기록된다. 학습 시점에 나누지 않는다. manifest가 유일한 진실이어야 `manifest_hash`가 의미를 갖는다.
6. 공식 split을 쓴 경우와 파생한 경우를 **각 record의 `official_protocol` 필드**로 구분한다(파생된 dev record는 `official_protocol: null`).

## Alternatives Considered

- **규칙 B — source 데이터셋 하나를 통째로 dev로 쓴다** (예: O+C+M 중 M 전체). 깔끔하고 subject leakage가 원천 차단된다. 기각: source가 세 개뿐인데 하나를 빼면 학습 데이터가 1/3 줄고, 더 나쁘게는 tau가 **한 데이터셋의 도메인 특성에 맞춰진다**. cross-domain 연구에서 threshold가 특정 source 도메인에 과적합되는 것은 측정하려는 것을 오염시킨다.
- **규칙 C — target에서 dev를 뗀다.** 기각. target bona-fide는 adaptation 예산이고 target test는 평가 대상이다. 여기서 tau를 고르면 계약서 §41-3(adaptation/test leakage 금지)을 정면으로 위반한다.
- **규칙 D — 데이터셋별로 다르게 처리한다** (공식 dev가 있으면 그것, 없으면 다른 비율). 기각: 계약서 §27.3이 실험 로직의 dataset 이름 분기를 금지한다. 규칙 A는 "있으면 쓰고 없으면 같은 방식으로 만든다"이므로 분기가 아니라 하나의 규칙이다.
- **난수 seed로 subject 선택.** 기각: seed를 바꾸면 dev가 바뀌고, 그러면 `manifest_hash`가 바뀌고, 그러면 이전 run 전체가 비교 불가가 된다. 해시 기반 선택은 재현 가능하면서 seed 관리가 필요 없다.

## Why

이 결정의 핵심은 "어떤 방법이 가장 좋은가"가 아니라 **"어떤 방법이 스스로를 기록하는가"** 다. tau는 모든 metric의 기준점이고, 그 기준점이 어디서 왔는지 추적할 수 없으면 APCER·BPCER·HTER이 전부 출처 불명이 된다. manifest 시점에 결정적으로 파생하면 그 사실이 `manifest_hash`에 들어가고, `protocol_hash`에 들어가고, 결국 "이 숫자는 이 dev set에서 정한 tau로 계산됐다"가 해시로 증명된다.

20%라는 숫자 자체에 강한 근거는 없다. 강한 근거가 있는 것은 **그 숫자가 어디에나 같게 적용되고, 바뀌면 해시가 바뀐다**는 점이다.

## Risks

- **train 데이터 손실**: subject의 20%를 빼면 학습량이 준다. 공식 dev가 있는 데이터셋은 영향이 없고, 없는 데이터셋만 해당한다. Phase 1에서 실제 subject 수를 확인한 뒤 20%가 과한지 재검토한다.
- **작은 데이터셋에서 dev가 너무 작아짐**: 최소 2명 규칙이 하한을 주지만, subject가 매우 적은 데이터셋에서는 dev의 PAI 표본이 부족해 결정 4에 걸려 빌드가 실패할 수 있다. 그때는 실패가 올바른 동작이다 — 조용히 부실한 tau를 쓰는 것보다 낫다.
- **공식 protocol과의 불일치**: 논문이 보고한 숫자와 우리 숫자를 비교할 때, 우리가 train의 일부를 dev로 뺐다는 사실이 차이의 일부다. `protocol_hash`가 다르므로 직접 비교는 이미 차단되지만, 리포트에 명시해야 한다.
- **아직 실측하지 않음**: 네 데이터셋 중 어느 것이 공식 dev를 갖는지 확인 전이다. 확인 결과 전부 3분할이면 이 ADR은 발동하지 않고 그대로 남는다(해가 되지 않는다). 전부 2분할이면 네 번 모두 적용된다.

## Evidence

- `src/pad_research/metrics/threshold.py::ThresholdPolicy.fit` — dev가 아닌 table을 거부한다(타입 수준 강제).
- `configs/protocol/ocim_target_i_v1.yaml` — `threshold: {source: dev_set, policy: fixed_after_dev, rule: eer, dev_domain: source}`.
- `src/pad_research/data/manifest.py::validate_records` — subject leakage 검사.
- 계약서 §6.1(subject leakage 금지, 공식 protocol 우선), §27.3(dataset 이름 분기 금지), §41-3(adaptation/test leakage 금지).
- **아직 없는 근거**: 각 데이터셋의 공식 split 구성. `find $PAD_DATA_ROOT -iname "*protocol*" -o -iname "*README*"`로 확인한 뒤 이 ADR에 표를 추가한다.

## Date
2026-09-21
