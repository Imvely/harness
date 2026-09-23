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
| [ADR-007](ADR-007-video-decoding-pyav.md) | 비디오 디코딩은 PyAV로 통일하고 필요한 프레임만 디코딩 | Accepted | 2026-09-21 |
| [ADR-008](ADR-008-dev-split-derivation.md) | dev split이 없는 데이터셋에서 threshold용 dev set을 만드는 규칙 | Accepted | 2026-09-21 |
| [ADR-009](ADR-009-face-crop-policy.md) | 얼굴 crop은 clip 단위로 고정하고 여백을 남긴다 | Superseded (→ ADR-015) | 2026-09-21 |
| [ADR-010](ADR-010-storage-backends.md) | LMDB·폴더·SSH를 같은 실험으로 읽는 storage 추상화 | Accepted | 2026-09-21 |
| [ADR-011](ADR-011-full-run-approval-transport.md) | Full run 승인의 붙여넣기 토큰과 파일 승인 만료 | Accepted | 2026-09-21 |
| [ADR-012](ADR-012-two-adaptation-settings.md) | Target 적응을 R(real-only)·S(few-shot supervised) 두 설정으로 병행 | Proposed | 2026-09-22 |
| [ADR-013](ADR-013-dataset-set-six-lmdb-domains.md) | 연구 데이터셋은 LMDB의 6개 도메인, leave-one-domain-out 평가 | Proposed (실측 반영) | 2026-09-22 |
| [ADR-014](ADR-014-uniform-time-grid.md) | 프레임은 "몇 초"로 고르고 도메인별 시간 간격을 기록한다 | Proposed | 2026-09-22 |
| [ADR-015](ADR-015-clip-fixed-crop.md) | 얼굴 crop은 저장된 박스의 중앙값으로 clip당 하나 (ADR-009 대체) | Proposed | 2026-09-22 |
| [ADR-016](ADR-016-own-store-in-our-space.md) | 원본은 읽기만 하고 우리 저장소에 우리 LMDB를 만든다 | Proposed | 2026-09-23 |

> 2026-09-22 사용자 검토로 007/008/010/011은 **Accepted**. 009는 사용자 저장소에 프레임별 bbox가 이미 있고 optical flow 분석이 방향에 포함되어 재작성한다(`clip_jitter` 실측 후 새 ADR로 대체). 012/013은 사용자 결정을 기록한 것이며 세부 설계 확인 후 Accepted로 바꾼다.

## 규칙

- 파일명: `ADR-NNN-<slug>.md`. `## Status` 바로 아래 줄에 `Accepted` / `Proposed` / `Superseded` 중 하나를 쓴다.
- 결정을 뒤집을 때는 기존 ADR을 편집하지 않고 새 ADR을 만들어 기존 것을 `Superseded`로 바꾸고 양쪽에 링크한다.
- 기존 `ADR-*.md` 편집은 `ask` 보호 대상이다(신규 ADR 작성은 허용). `/adr <slug>` 커맨드로 템플릿을 생성한다.
- 언어: 한국어(용어 영어 병기). `## Evidence`에는 계약서 §, claim ID, MLflow run ID 등 추적 가능한 근거만 적는다.
