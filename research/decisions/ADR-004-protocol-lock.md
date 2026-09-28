# ADR-004 — Protocol Lock: protocol_hash 정의와 비교 규칙

## Status
Accepted

## Context

계약서 §15 「Protocol Lock」: 서로 다른 protocol 결과를 직접 우열 비교하지 않는다. 각 experiment는 protocol(`protocol_id`, source/target datasets, classes, `target_adaptation`, `target_test`, `attack_types`, `threshold`)을 저장하고, §15.1에 따라 canonical protocol JSON의 SHA256을 `protocol_hash`로 만든다.

```text
same protocol_hash → direct comparison allowed
different hash     → comparison requires explicit justification
```

Ablation에서 의도적으로 한 요소를 바꾼 경우 `parent_protocol_id`와 변경점을 기록한다.

Phase 0 구현 시 결정해야 했던 것: hash에 무엇을 포함/제외하는가, 비교 가능성에 영향을 주는 요소를 누가 소유하는가, 다른 hash를 비교할 때의 절차, source-only 대조군과 DA 실험이 같은 hash를 가질 수 있는가.

## Decision

### 1. hash 정의

```python
protocol_hash = sha256(canonical_json(protocol.model_dump(mode="json", exclude=HASH_EXCLUDED)))
HASH_EXCLUDED = {"description", "parent_protocol_id", "change_note", "status"}
```

- `canonical_json` = `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`. 집합(set-like) 필드(`source_datasets`, `attack_types`, `source_classes` 등)는 **hash 전에 정렬**해 순서가 hash를 바꾸지 않게 한다.
- **`protocol_id`는 hash에 포함**한다. §15.1 "canonical protocol JSON"의 literal 해석이며, 이름만 바꿔도 비교가 막히는 쪽이 안전한 실패 모드다(보수적 선택; 마스터 플랜 사용자 결정 #4).
- `schema_version = 1`을 protocol에 포함해 hash에 반영한다. 스키마가 바뀌면 hash도 바뀌어 과거 run과의 우연한 비교를 막는다.
- `description`, `parent_protocol_id`, `change_note`, `status`는 문서화/lifecycle 메타데이터이므로 제외한다. `parent_protocol_id`를 포함하면 링크만 추가해도 비교가 깨진다.

### 2. Protocol이 비교 가능성에 영향을 주는 모든 것을 소유한다

`ProtocolSpec`은 §15 필드 외에 `threshold{source, policy, rule, rule_param, dev_domain}`, `acer_policy(max_pai|pooled, 기본 max_pai)`, `security_gate{abs_tolerance, rel_tolerance, min_attack_samples_per_pai}`, `target_adaptation{..., source_split, selection_seed, subject_disjoint_from_test}`, `allow_image_dataset_as_clip`을 가지며 모두 hash에 들어간다. 같은 hash면 같은 ACER 정의·같은 gate 기준·같은 threshold 규칙이다. `configs/protocol/**`는 `ask` 보호 대상이다.

### 3. 커밋된 protocol의 hash를 테스트에 고정

`tests/fixtures/protocol_hashes.json`에 커밋된 각 protocol의 `protocol_hash`를 pin한다. 스키마 변경·직렬화 변경·protocol 편집은 이 테스트를 깨뜨리며, 의도한 변경이면 fixture를 함께 갱신하고 커밋 메시지에 이유를 적는다.

### 4. 비교 규칙

- **same-hash-only direct comparison**: `compare`/security gate/리포트 baseline 탐색은 `protocol_hash`가 같은 run만 직접 비교한다. 불일치 시 gate verdict는 `comparison_blocked`이고 `ProtocolMismatchError`를 낸다.
- **`--justify` 규칙**: hash가 다른 run을 비교하려면 `--justify "<이유>"`를 명시해야 한다. 이때 리포트 상단에 다음 배너를 강제한다.

  > ⚠ PROTOCOL MISMATCH — protocol_hash A ≠ B. Justification: "<이유>". 이 비교는 직접 우열 비교가 아니며 §15.1의 예외다.

  `--justify` 없이 다른 hash를 비교하는 경로는 존재하지 않는다.
- Ablation은 새 `protocol_id` + `parent_protocol_id` + `change_note`로 만든다(hash 제외 필드이므로 링크 추가 자체는 비교를 깨지 않는다).

### 5. Adaptation ↔ protocol 단방향 결합

`adaptation.enabled ⇒ protocol.target_adaptation.enabled` (**단방향**). 역방향은 요구하지 않는다. 따라서 `target_adaptation.enabled: true`인 protocol 아래에서 `adaptation: none`인 source-only 대조군(E01/E02)과 DA 실험(E03…)이 **같은 protocol_hash**를 갖고, §14.3의 security regression 비교가 직접 성립한다. 반대로 `target_adaptation.enabled: false`인 protocol에서 adaptation을 켜면 validator error다.

## Alternatives Considered

1. `protocol_id`를 hash에서 제외 — 이름 변경만으로 비교가 막히지 않는 편의성. 기각: 같은 내용을 다른 이름으로 두 번 등록해 "다른 protocol"처럼 보고하는 사고 가능성, §15.1의 literal 해석 위반.
2. `parent_protocol_id`를 hash에 포함 — 기각: 문서화 링크 추가만으로 비교 불가.
3. ACER 정의·gate tolerance를 experiment spec(`evaluation.*`)에 두기 — 기각: 같은 hash로 다른 정의를 비교할 수 있게 된다.
4. Protocol의 `target_adaptation.enabled`와 spec의 `adaptation.enabled`를 양방향 일치 강제 — 기각: source-only 대조군이 DA arm과 다른 hash를 갖게 되어 §14.3 비교가 항상 `--justify`를 요구하게 된다.
5. `--justify` 없이 경고만 출력하고 비교 허용 — 기각: §15 위반, 리포트에 섞인 비교가 검출되지 않는다.

## Why

- §15는 "가장 중요한 자동화 규칙 중 하나"이며, 비교 가능성의 모든 결정 요인이 hash 안에 있어야 자동 검사가 의미를 갖는다.
- 보수적 hash(포함 범위 넓음)는 false-negative(비교 불가인데 허용)를 없애고, 비용은 `--justify` 한 번이다.
- 단방향 결합은 실험 설계(§43: E02 vs E03 비교)가 요구하는 "같은 protocol 아래의 대조군"을 그대로 표현한다.

## Risks

- hash가 너무 보수적이라 사소한 편집(오타 수정)도 비교를 막는다 → `description`/`change_note`는 제외되어 있고, 나머지는 실제로 비교 가능성에 영향을 주는 필드다.
- Pydantic 직렬화 변경(`mode="json"` 출력 형식)이 hash를 바꿀 수 있다 → `tests/fixtures/protocol_hashes.json` pin이 검출한다.
- 사람이 `--justify`를 남용할 수 있다 → 배너가 리포트에 남고 리뷰어(§23.3)가 확인한다.

## Evidence

- 계약서 §14.3, §15, §15.1, §16, §17, §24.4, §43.
- 마스터 플랜 D5, D13; 최종 확정 설계 항목 4(단방향 결합).
- 구현: `src/pad_research/protocols/` (schema/hash/validator/compare), `tests/protocol/`, `tests/fixtures/protocol_hashes.json`.

## Date
2026-09-17
