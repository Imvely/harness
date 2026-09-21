# research/decisions — Architecture Decision Records (ADR)

중요한 연구/엔지니어링 결정은 계약서 §26 템플릿(`ADR-000-template.md`)으로 여기에 기록한다. 목적: 나중에 Claude나 사람이 과거에 버린 아이디어를 이유도 모르고 다시 도입하지 않게 하는 것.

| ADR | 제목 | Status | Date |
|---|---|---|---|
| [ADR-000](ADR-000-template.md) | 템플릿 (§26 그대로) | — | — |
| [ADR-001](ADR-001-use-video-input.md) | RGB Video(multi-frame clip)를 기본 입력으로 사용한다 | Accepted | 2026-09-17 |
| [ADR-002](ADR-002-switch-dg-to-da.md) | 연구 중심을 DG에서 DA로 전환한다 (§3.1 "정확한 표현" 포함) | Accepted | 2026-09-17 |
| [ADR-003](ADR-003-real-only-target-setting.md) | 기본 DA 설정은 Real-only(Bona-fide-only) Target Adaptation이다 | Accepted | 2026-09-17 |
| [ADR-004](ADR-004-protocol-lock.md) | Protocol Lock: `protocol_hash` 정의와 비교 규칙 | Accepted | 2026-09-17 |
| [ADR-005](ADR-005-harness-phase0-scope-and-conventions.md) | Harness Phase 0 범위와 규약(환경, torch, spec/hash, 승인, 이연 목록) | Accepted | 2026-09-17 |
| [ADR-006](ADR-006-readonly-dashboard-exception.md) | 읽기 전용 로컬 대시보드를 §39 예외로 허용하고 계약서를 개정 | Accepted | 2026-09-19 |
| [ADR-007](ADR-007-video-decoding-pyav.md) | 비디오 디코딩은 PyAV로 통일하고 필요한 프레임만 디코딩 | Proposed | 2026-09-21 |
| [ADR-008](ADR-008-dev-split-derivation.md) | dev split이 없는 데이터셋에서 threshold용 dev set을 만드는 규칙 | Proposed | 2026-09-21 |
| [ADR-009](ADR-009-face-crop-policy.md) | 얼굴 crop은 clip 단위로 고정하고 여백을 남긴다 | Proposed | 2026-09-21 |
| [ADR-010](ADR-010-storage-backends.md) | LMDB·폴더·SSH를 같은 실험으로 읽는 storage 추상화 | Proposed | 2026-09-21 |
| [ADR-011](ADR-011-full-run-approval-transport.md) | Full run 승인의 붙여넣기 토큰과 파일 승인 만료 | Proposed | 2026-09-21 |

> ADR-007~011은 **Proposed**다. 007/010/011은 코드가 이미 있고(각각 `48a5dd1`, 이번 변경), 008/009는 Phase 1 adapter를 쓰기 전에 결정되어야 한다. 사용자가 검토해 `Accepted`로 바꾸거나 반려하면 그에 맞춰 코드를 되돌린다.

## 규칙

- 파일명: `ADR-NNN-<slug>.md`. `## Status` 바로 아래 줄에 `Accepted` / `Proposed` / `Superseded` 중 하나를 쓴다.
- 결정을 뒤집을 때는 기존 ADR을 편집하지 않고 새 ADR을 만들어 기존 것을 `Superseded`로 바꾸고 양쪽에 링크한다.
- 기존 `ADR-*.md` 편집은 `ask` 보호 대상이다(신규 ADR 작성은 허용). `/adr <slug>` 커맨드로 템플릿을 생성한다.
- 언어: 한국어(용어 영어 병기). `## Evidence`에는 계약서 §, claim ID, MLflow run ID 등 추적 가능한 근거만 적는다.
