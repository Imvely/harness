# ADR-013 — 연구 데이터셋은 사용자 LMDB의 6개 도메인이며, leave-one-domain-out으로 평가한다

## Status
Proposed — 데이터셋 구성은 사용자가 확인했다(2026-09-22, "LMDB에 있는 게 진짜 데이터셋이야. 그거만 있어"). 아래 표의 빌드 사실은 빌드 코드를 **읽고** 정리한 것이며, 서버에서 `scripts/inspect_lmdb_layout.py`로 실측한 뒤 이 ADR에 수치를 추가하고 Accepted로 바꾼다.

## Context

지금까지 이 저장소는 OCIM(OULU-NPU, CASIA-FASD, Replay-Attack, MSU-MFSD)을 가정했다. 초안 protocol `configs/protocol/ocim_target_i_v1.yaml`이 그 예다. 실제로 연구에 쓸 수 있는 데이터는 사용자 서버의 LMDB에 있는 6개 도메인뿐이고, OCIM과 겹치는 것은 Replay-Attack 하나다.

저장소 구조는 빌드 스크립트 `lmdb_dataset_video.py`(이 저장소 밖, 읽기만 함)에서 확인했다. `DIST_ROOT` 아래에 도메인마다 LMDB 디렉터리 `<domain>/`와 `<domain>_meta.parquet`가 짝을 이룬다. parquet가 목차이고 한 행이 clip 하나다. 프레임은 키 `<video_id>#<index:05d>` 하나에 인코딩된 이미지 하나로 들어 있고, 행의 `lmdb_key` 열이 그 clip의 키 목록(JSON)이다.

**도메인마다 빌드 방식이 다르다.** 이 차이가 곧 도메인 간 차이(domain shift)의 일부가 되므로 기록해 둔다.

| 도메인 | 원본 | 프레임 | 시간 간격 | split | 얼굴 box | 비고 |
|---|---|---|---|---|---|---|
| aihub114 | 이미지 시퀀스 | 30장(예상) | 원 촬영 간격, **fps 미기록** | train / val | 라벨 JSON | `Light_01_High`만 |
| aihub115 | 이미지 시퀀스 | 30장(예상) | 원 촬영 간격, **fps 미기록** | train / val | 라벨 JSON | 8개 클래스, 3D mask 포함 |
| SiW-Mv2 | 영상 | 3fps 추출 후 **얼굴이 정확히 1개인 프레임만** | **불균일 가능**(버린 자리 미기록) | `all`(split 없음) | 프레임별 검출 | 공격 clip마다 subject_id 별도 |
| Idiap_ReplayAttack | 영상 | 3fps 추출 후 **얼굴 1개 프레임만** | **불균일 가능** | train / test(**devel 미빌드**) | 프레임별 검출 | 공격: `fixed` / `hand` |
| CASIA-SURF | 프레임 폴더(color) | 전부 | 원 촬영 간격, **fps 미기록** | train / test / dev | 없음 | 촬영 시 얼굴 영역으로 잘림 |
| CASIA-CeFA | 프레임 폴더(color) | 전부 | 원 촬영 간격, **fps 미기록** | train / dev(test 없음) | 없음 | 촬영 시 얼굴 영역으로 잘림 |

SiW-Mv2와 Idiap의 프레임은 `cv2.imwrite`로 **JPEG 재인코딩**된 것이다. 나머지는 원본 JPEG 그대로다.

## Decision

1. **데이터셋은 위 6개 도메인이다.** `ocim_target_i_v1`은 사용하지 않는다. 파일은 작성 이력으로 남기고, 상태 표시는 protocol 파일을 수정할 때 함께 바꾼다(보호 파일).
2. **평가는 leave-one-domain-out이다.** 각 도메인을 한 번씩 target으로 두고, 나머지 5개를 source로 쓴다. 이 도메인 루프가 ADR-012의 두 설정(R, S) 각각에 적용된다.
3. **adapter는 parquet를 유일한 목차로 읽는다.** manifest의 `relative_path`는 `video_id`이고, 프레임은 `#` 키로 찾는다. harness의 LMDB 백엔드에 키 구분자 지원을 추가해야 한다(ADR-010 Status 참고).
4. **도메인 간 빌드 차이를 manifest에 남긴다.** 얼굴 영역으로 잘려 있는지, 프레임을 버렸는지, fps가 기록돼 있는지, 재인코딩했는지를 `ManifestRecord.extra`에 기록해 결과 해석 때 조건으로 쓸 수 있게 한다.
5. **빌드 코드와 LMDB는 harness가 수정하지 않는다.** 시간 간격 균일화처럼 재빌드가 필요한 결정이 나오면 사양을 제안하고, 재빌드는 사용자가 한다.

## Alternatives Considered

- **OCIM 유지**: 논문 수치와 비교하기 쉽다. 기각: 데이터가 없다.
- **6개 도메인을 합쳐 하나의 source로 쓰고 별도 target 없이 평가**: DA 연구 질문(target 적응)에 답하지 못한다. 기각.
- **얼굴 영역으로 잘린 도메인(CASIA-SURF/CeFA) 제외**: 다른 도메인과 이미지 통계가 달라 교란 요인이 된다(사용자가 이미 지적함). 기각(지금은): 제외하면 도메인이 4개로 줄어든다. 대신 Decision 4로 조건을 기록하고, 필요하면 "제외한 5-도메인 / 4-도메인" 부분 실험을 따로 둔다.

## Why

데이터셋 구성은 모든 protocol, 모든 hash, 모든 수치의 전제다. 가정한 데이터셋과 실제 데이터셋이 다른 채로 adapter를 쓰면, 그 불일치가 코드 곳곳에 조용히 묻힌다. 빌드 방식의 차이를 표로 남기는 이유도 같다. 도메인 간 성능 차이의 일부는 얼굴이나 공격이 아니라 **빌드 방식**(잘림 여부, 재인코딩, 프레임 간격)에서 온다. 그 사실이 기록돼 있지 않으면 결과를 해석할 때 드러나지 않는다.

## Risks

- **시간 간격**: 6개 중 어느 도메인도 "3fps로 균일한 간격"이 보장되지 않는다(표 참고). 연구 방향(3fps 균일 샘플링, FFT, optical flow)과 충돌하며, 별도 ADR에서 다룬다.
- **공격 분류 체계가 도메인마다 다르다**: sub_cls 이름과 종류가 제각각이라 PAI 매핑표가 필요하다. 매핑은 연구 판단이므로 사용자가 확인한다.
- **라이선스·개인정보 정책 미기록**: aihub 등 각 데이터셋의 `license`, `pii_policy`를 manifest에 기록해야 한다(데이터 거버넌스). 값은 사용자가 확인한다.
- **아직 실측 전**: 표는 코드에서 읽은 의도이며, 실제 저장소가 다를 수 있다(예: CeFA는 버그 수정 후 재빌드됨).

## Evidence

- 빌드 스크립트 `lmdb_dataset_video.py`, `da_dataset.py`, `CODEBASE_NOTES.md`(사용자 제공, 읽기만 함).
- `scripts/inspect_lmdb_layout.py` — 실측 도구(`88dadbc`). 서버 실행 결과는 아직 없다.
- ADR-008(dev split 파생: Idiap의 devel 미빌드, SiW-Mv2의 split 없음에 적용), ADR-010(storage), ADR-012(두 적응 설정).

## Date
2026-09-22
