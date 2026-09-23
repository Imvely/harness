# 저장소의 문제를 우리 코드에서 감당하는 방법

> 원칙: **빌드 스크립트와 LMDB 저장소는 건드리지 않는다.** 둘 다 이 저장소 밖에 있고 팀원과 공유된다. 문제는 harness 쪽에서 감지하고 보정하며, 보정했다는 사실을 manifest에 남긴다.
>
> 근거는 2026-09-22 실측(`scripts/inspect_lmdb_layout.py`, 6개 도메인 전체 스캔)이다. 수치는 [ADR-013](../../research/decisions/ADR-013-dataset-set-six-lmdb-domains.md)에 있다.

이 문서는 Phase 1 adapter가 무엇을 해야 하는지의 명세다. 각 항목은 "저장소가 이러하다 → adapter가 이렇게 한다 → manifest에 이렇게 남는다"의 형태다.

## 1. Idiap 키 충돌 — 중복 키는 한 행만 채택한다

**저장소 상태**: 목차는 프레임 키 215,252개를 말하지만 저장소에는 136,161개뿐이다. 공격 clip 700개 중 **350쌍이 같은 키를 공유**한다. 빌드가 키를 파일 이름만으로 만드는데, 이 데이터셋은 같은 파일 이름을 `attack/fixed/`와 `attack/hand/`에 두기 때문이다. 나중에 쓰인 쪽이 앞의 것을 덮어썼다.

**adapter 동작**:
1. parquet를 읽은 뒤 프레임 키 집합이 같은 행들을 묶는다.
2. 각 묶음에서 **한 행만** manifest에 넣는다. 선택은 결정적으로 한다(`sub_cls`, `video_id` 순 정렬의 첫 행).
3. 채택한 행에 `key_collision_group: <n>`과 `support_ambiguous: true`를 남긴다.
4. 버린 행 수를 `ManifestMeta`에 기록하고, 빌드 로그에 경고를 남긴다.

**왜 이것으로 충분한가**: 쌍을 이루는 두 행은 client·session·매체(print/mobile/highdef)·조명이 같고 **거치 방식만 다르다.** 따라서 PAI 수준(print/replay) 라벨은 어느 쪽을 남겨도 정확하다. 포기하는 것은 "손으로 든 공격 vs 고정한 공격" 비교 하나뿐이고, 그것은 애초에 저장소에서 소실된 정보다.

**결과**: Idiap 공격 clip 700 → 350, bona-fide 140은 그대로. PAI별 표본이 줄어 security gate의 최소 표본 조건에 걸릴 수 있으므로, 이 도메인이 target일 때 `inconclusive` 판정이 나오면 그 이유가 여기임을 리포트에 적는다.

## 2. devel 세트 없음 — 파생한다

**저장소 상태**: Idiap은 `train`/`test`만 빌드돼 있다. 원 데이터셋에는 공식 devel(360 영상)이 있지만 저장소에 없다. SiW-Mv2는 split 자체가 `all` 하나다.

**adapter 동작**: [ADR-008](../../research/decisions/ADR-008-dev-split-derivation.md)의 규칙 그대로 — train에서 subject의 20%(최소 2명)를 `sha256(dataset_id:subject_id)` 순서로 dev로 옮기고, 그 record에 `official_protocol: null`을 남긴다. 저장소를 다시 만들 필요가 없다.

**주의**: SiW-Mv2는 공격 clip마다 subject_id가 다르다(1,656 clip에 subject 1,656). 이 도메인에서 "subject 분리"는 사실상 clip 분리이며, 같은 인물이 양쪽에 들어가는 것을 막을 방법이 없다. 결과 해석에 명시한다.

## 3. 프레임 시각 미기록 — 원본 헤더에서 읽어 manifest에 넣는다

**저장소 상태**: 프레임이 언제 찍혔는지 어디에도 없다. `extra_meta.target_fps`는 빌드 설정값(30.0)이지 원본 fps가 아니다.

**adapter 동작**(영상 도메인 = Idiap, SiW-Mv2):
1. clip의 원본 영상 경로를 캐시 폴더 구조로 역산한다(`_frames/<domain>/<rel>/<stem>/` ↔ `<data_root>/<domain>/<rel>/<stem>.<ext>`).
2. 컨테이너 헤더에서 fps를 읽어 `extra.source_fps`, `extra.dt_seconds = hop / source_fps`, `extra.time_source = "header"`로 기록한다.
3. 원본을 찾지 못하면 `time_source = "unknown"`으로 남기고 시간 기반 분석에서 제외되게 한다([ADR-014](../../research/decisions/ADR-014-uniform-time-grid.md) 결정 3).

**이미지 시퀀스 도메인**(aihub114/115, CASIA-SURF/CeFA): 원본 영상이 없거나 배포본이 이미 솎아진 프레임이라 헤더를 읽을 대상이 없다. `time_source = "unknown"`으로 두고, 데이터셋 1차 자료에서 fps가 확인되면 `documented`로 올린다.

**비용**: clip당 영상 헤더 한 번 읽기. 프레임을 디코딩하지 않으므로 manifest 빌드 시간에 큰 영향이 없다.

## 4. 버려진 프레임 — 복원은 못 하고, 표시한다

**저장소 상태**: 얼굴이 하나로 검출되지 않은 프레임을 빌드가 버렸고 위치를 남기지 않았다(SiW-Mv2 183 clip에서 5,174 프레임, Idiap 7 clip에서 86 프레임).

**adapter 동작**(선택 단계, 기본 off): 캐시 폴더의 프레임과 저장된 프레임을 지문으로 대조해 원본 순번을 복원하고, 간격이 공칭의 1.5배를 넘는 clip에 `irregular_gap: true`를 남긴다. `inspect_lmdb_layout.py`가 이미 하는 계산과 같고, adapter에서는 전체 clip을 대상으로 한 번 돌린다.

**비용이 크다**: 도메인 전체의 캐시 파일과 LMDB 값을 한 번씩 읽는다. 그래서 기본은 꺼 두고, 시간 기반 실험을 돌리기 전에 한 번만 켠다. 캐시가 지워졌다면 이 정보는 영구히 복원 불가이며 그때는 `irregular_gap: null`(모름)이다.

## 5. aihub114 카메라 교란 — protocol에서 다룬다

**저장소 상태**: 공격 6,789개는 전부 GoPro, bona-fide 1,686개는 전부 스마트폰으로 촬영됐다. 카메라만으로 라벨이 완전히 결정된다.

**adapter 동작**: 라벨을 바꾸거나 행을 버리지 않는다. 촬영 장비를 `extra.capture_device`에 그대로 남기고, 이 사실을 `ManifestMeta`에 경고로 기록한다.

**protocol 동작**(사용자 결정 필요): 세 선택지 중 하나를 protocol 파일에 명시한다.
- 이 도메인을 source/target 어느 쪽으로도 쓰지 않는다(5개 도메인으로 진행).
- source로만 쓰고 target으로는 쓰지 않는다.
- 카메라가 같은 부분집합이 존재한다면 그 부분만 쓴다.

어느 쪽이든 `inspect_lmdb_layout.py`의 `LABEL_PREDICTED_BY_METADATA` 검사가 다음에도 같은 문제를 자동으로 잡는다.

## 6. 재인코딩 이력 — 사실로 기록만 한다

SiW-Mv2와 Idiap의 프레임은 `cv2.imwrite`로 다시 JPEG 압축된 것이고 나머지는 원본 JPEG이다. adapter는 이 사실을 도메인 단위 상수로 `ManifestMeta`에 남긴다. 공간 FFT 결과를 도메인 간에 비교할 때 이 항목을 조건으로 함께 보고한다.

## 7. 3fps 그리드 — 재빌드 없이 가능하다

빌드가 `--target-fps 30`으로 돌았기 때문에 영상 도메인은 원본 프레임을 거의 다 갖고 있다(Idiap 최대 375프레임 = 25fps × 15초). 3fps는 **읽는 쪽에서 시간 기준으로 고르면** 된다(ADR-014 결정 1). 저장소를 다시 만들 이유가 없다.

## adapter가 manifest에 남기는 항목 요약

| 키 | 값 | 출처 |
|---|---|---|
| `source_fps` | 원본 fps 또는 없음 | 영상 헤더 |
| `dt_seconds` | 프레임 간 공칭 간격 | `hop / source_fps` |
| `time_source` | `header` / `documented` / `unknown` | 위 3번 |
| `irregular_gap` | `true` / `false` / 없음 | 위 4번 |
| `crop_x/y/w/h`, `box_jitter`, `crop_source` | clip 고정 박스 | [ADR-015](../../research/decisions/ADR-015-clip-fixed-crop.md) |
| `capture_device` | 촬영 장비 | parquet `extra_meta` |
| `key_collision_group`, `support_ambiguous` | 중복 키 처리 흔적 | 위 1번 |
| `reencoded` | JPEG 재압축 여부 | 도메인 상수 |
