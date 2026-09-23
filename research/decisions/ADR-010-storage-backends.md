# ADR-010 — 데이터가 어디에 있든 같은 실험이 되도록, 저장소 접근을 추상화한다

## Status
Accepted (2026-09-22, 사용자 검토) — 코드는 `6179078`에 포함되어 있다. 단, 사용자 저장소의 프레임 키는 `<video_id>#<index>`이고 이 ADR의 `frames_dir`는 `/` 자식을 가정하므로, 그 저장소를 읽으려면 키 구분자 지원이 추가로 필요하다(`scripts/inspect_lmdb_layout.py` 실측 후).

## Context

사용자 환경 사실(2026-09-21): **데이터는 LMDB로 들고 있고**, 디렉터리 구조와 위치는 추후 알려주기로 했다. 그리고 사람마다 사정이 다르다 — 어떤 사람은 LMDB, 어떤 사람은 풀어 놓은 디렉터리, 어떤 사람은 SSH 너머의 서버. 같은 실험을 이 셋 위에서 모두 돌릴 수 있어야 한다.

여기서 조용한 함정이 하나 있다. 저장 방식을 실험 설정(spec) 안에 그냥 넣으면 그것이 `science_hash`에 들어간다. `science_hash`는 "이 실험의 과학적 내용"을 나타내는 지문이고, 계약서 §14.3은 **같은 protocol·같은 science_hash 아래에서만 metric을 직접 비교**하도록 요구한다. 저장 방식이 hash에 섞이면:

- A는 LMDB로, B는 디렉터리로 같은 실험을 돌렸는데 **hash가 달라 비교가 막힌다**.
- 데이터셋을 LMDB로 옮기는 순간 **이전 run 전체가 소급해서 비교 불가**가 된다.

반대로 저장 방식을 완전히 기록하지 않으면, 나중에 "이 run은 어떤 경로로 읽었나"를 답할 수 없다.

또 하나. `configs/`도 `experiments/specs/*.resolved.yaml`(`validate_spec --freeze` 산출물)도 **커밋된다**. 여기에 `/mnt/nas/faces/oulu`나 `gpu03.lab.internal` 같은 값이 들어가면 계약서 §34가 금지하는 머신 경로·호스트명이 공개 git 히스토리에 남고, 동시에 그 spec은 다음 사람의 머신에서 쓸 수 없게 된다.

## Decision

### 1. 저장소 백엔드 추상화 (`src/pad_research/data/storage/`)

`relative_path` → 바이트. 세 가지 구현:

| kind | 무엇을 읽는가 | `local_path()` |
|---|---|---|
| `local` | 디렉터리 트리. NFS·SMB·컨테이너 볼륨·**sshfs 마운트**를 전부 포함한다 | 실제 경로 반환 |
| `lmdb` | 메모리 매핑 key/value 스토어 | `None` (바이트로 읽음) |
| `sftp` | SSH 너머의 원격 디렉터리 | `None` (바이트로 읽음) |

`local_path()`가 둘로 갈리는 이유가 이 설계의 핵심이다. 경로를 받은 디코더는 파일을 **스트리밍**한다(`np.load`는 mmap하고, PyAV는 필요한 프레임만 읽는다). 바이트를 받은 디코더는 **객체 전체를 worker 메모리에** 올린다. 200 MB짜리 비디오면 worker마다 200 MB다. 그래서 경로가 있으면 항상 경로를 쓴다.

### 2. 저장 방식은 과학이 아니다 — `science_hash`에서 제외한다

`ExperimentSpec.storage`를 추가하고 `SCIENCE_EXCLUDE`에 넣는다. 결과:

```
storage=local  science d1853fb82a5d   spec 3d71f0a8b9c8
storage=lmdb   science d1853fb82a5d   spec 0fb66b7f8ca6
storage=sftp   science d1853fb82a5d   spec 1c9930922470
```

`science_hash`는 셋이 동일하고 `spec_hash`만 다르다. 즉 **세 사람이 서로 다른 저장 방식으로 돌린 run이 직접 비교 가능**하면서, 어떤 경로로 읽었는지는 `spec_hash`와 MLflow 태그에 남는다.

부수 효과로, `storage`는 `execution.*`와 달리 **CLI에서 바꿔도 된다**: `train.py +exp=<name> storage=lmdb`. 게이트의 `SPEC_FROZEN`은 `science_hash`만 비교하므로 full run에서도 통과한다. 이것이 "사용자마다 다른 방식"을 실험 파일 수정 없이 지원하는 방법이다.

### 3. 위치는 **환경변수 이름**으로만 적는다

`configs/storage/*.yaml`은 `root_env_var: PAD_DATA_ROOT`, `path_env_var: PAD_LMDB_PATH`, `host_env_var: PAD_SFTP_HOST`처럼 **이름**만 담는다. 값은 실행하는 셸에 있다. 이는 `PAD_DATA_ROOT`가 원래 갖고 있던 계약(§34, manifest의 머신 독립성)을 LMDB와 SFTP로 확장한 것이다.

### 4. LMDB 레이아웃은 manifest가 이미 기술하고 있다

`relative_path`가 곧 키다(선택적 `key_prefix`/`key_suffix` 적용 후). 그러면 LMDB가 가질 수 있는 모든 형태가 **`media_type`만으로 표현된다**:

| LMDB가 담은 것 | `media_type` | `relative_path`는 |
|---|---|---|
| 샘플당 인코딩된 비디오 1개 | `video` | 그 키 |
| 프레임당 JPEG/PNG | `frames_dir` | 프레임들의 키 **접두사** |
| 샘플당 스틸 1장 | `image` | 그 키 |
| 직렬화된 `.npy` 클립 | `npy_clip` | 그 키 |

즉 **사용자의 LMDB 구조를 추측할 필요가 없다**(계약서 §27.2). 구조를 알려주면 그것을 encode하는 것은 adapter이고, storage 계층은 바뀌지 않는다.

### 5. 핸들은 fork를 건너지 않는다

DataLoader worker는 fork(Linux) 또는 spawn(Windows/macOS)된 프로세스다. LMDB 환경과 SSH 채널은 둘 다 프로세스를 건너 공유하면 안 된다. 연결은 지연 생성하고 pid가 바뀌면 다시 만든다.

**LMDB는 여기에 함정이 하나 더 있었고, 실제로 버그를 만들었다.** py-lmdb는 같은 경로를 한 프로세스에서 두 번 열지 못하게 하는 **프로세스 전역 레지스트리**를 갖고 있는데, 이 레지스트리가 fork를 건너 자식에게 상속된다. 그래서 자식이 그냥 다시 열면 *"The environment is already open in this process"* 로 거절당한다 — 여기서 말하는 "this process"는 실은 부모다. 자식은 상속받은 객체를 **먼저 close** 해서 레지스트리 항목을 지워야 자기 것을 열 수 있다. `lock=False`에서는 reader lock table이 없으므로 이 close가 자식의 매핑과 파일 디스크립터만 해제하고 부모는 멀쩡하다. `lock=True`에서는 `lock.mdb`의 reader slot이 공유되므로 안전하지 않고, 그 조합은 **설명과 함께 거절**한다.

### 6. 연결 진단 명령

```bash
uv run --no-sync python scripts/check_storage.py --storage lmdb --dataset-id oulu_npu
uv run --no-sync python scripts/check_storage.py --exp <name>     # 프로토콜의 모든 데이터셋
```

`BACKEND_REACHABLE` → `MANIFEST_READABLE` → `MEDIA_READABLE` 순으로 확인하고 첫 실패에서 멈춘다. 특히 **"스토어는 열리는데 키가 manifest와 안 맞는다"** 를 "스토어에 접근 불가"와 구분해서 보고한다 — 이것이 LMDB에서 가장 흔한 실수이고, 구분하지 않으면 증상이 샘플마다 반복되는 `FileNotFoundError` 수천 개일 뿐이다.

## Alternatives Considered

- **fsspec 하나로 통일**: 매력적이다(s3/sftp/http/local을 한 인터페이스로). 기각 이유 두 가지. ⒜ fsspec은 파일 추상화이지 key/value 추상화가 아니라, LMDB의 `frames_dir = 키 범위` 매핑이 자연스럽지 않다. ⒝ 의존성이 크고, 우리가 실제로 필요한 것은 `bytes`와 `list_children` 두 개뿐이다.
- **SFTP를 아예 넣지 않고 "마운트하세요"라고만 하기**: 성능·보안 면에서는 이쪽이 낫고 문서에도 그렇게 권고한다. 그래도 넣은 이유는, FUSE 권한이 없는 공용 서버가 실제로 존재하고 그 경우 "느린 읽기"가 "못 읽음"보다 낫기 때문이다. 대신 **optional extra**(`uv sync --extra sftp`)로 두어 기본 설치에는 들어가지 않는다.
- **S3/GCS 백엔드**: 지금 만들지 않는다. 계약서 §34는 얼굴 데이터의 외부 클라우드 업로드를 금지하고, 사내 MinIO 같은 예외는 정책 확인이 먼저다. 등록만 하면 추가되는 구조이므로 필요할 때 ADR과 함께 넣는다.
- **HDF5 / Zarr / WebDataset**: 같은 문제(작은 파일 수백만 개)에 대한 다른 답이다. 지금 필요 없고, Zarr 3.x는 Python ≥3.12를 요구해 이 프로젝트의 3.11 고정과 충돌한다.
- **storage를 spec 밖의 머신 로컬 파일에 두기**: hash 문제는 똑같이 해결되지만, run이 무엇으로 읽었는지 기록이 남지 않는다. spec 안에 두고 `science_hash`에서만 빼는 편이 provenance를 지킨다.

## Why

이 ADR의 모든 결정은 하나의 문장에서 나온다: **백엔드는 바이트가 어디서 오는지만 바꾸고, 그것이 무엇인지는 바꾸지 않는다.** 그래서 `science_hash`에서 빠지고, 그래서 CLI에서 바꿔도 되고, 그래서 `tests/unit/test_media_over_storage.py`가 "같은 미디어를 LMDB와 파일에서 읽어 픽셀이 동일한지"를 검증한다. 이 전제가 깨지면 나머지 결정이 전부 근거를 잃는다.

## Risks

- **`lock=False`의 전제**: 아무도 스토어에 쓰지 않는 동안만 올바르다. 데이터셋 LMDB는 한 번 만들고 끝이므로 성립하지만, 스토어를 채우는 중에 읽으면 잘못된 데이터를 볼 수 있다. 완화: `lock: true` 옵션을 남겨 두고, 그 경우 multi-worker를 거절한다.
- **SFTP의 메모리**: worker마다 객체 하나가 통째로 올라간다. 큰 비디오 + 많은 worker면 OOM이 난다. 완화: 문서에서 마운트를 권고. 추가 완화(청크 읽기)는 필요해지면 그때.
- **`key_prefix` 추측**: 사용자의 LMDB 키 구조를 아직 모른다. 잘못 넣으면 전량 miss한다. 완화: `check_storage.py`가 바로 이 경우를 지목한다.
- **프로세스 전역 LMDB 캐시**: 같은 스토어를 다른 읽기 옵션으로 두 번 설정하면 두 번째가 거절된다. 드문 구성이고 에러 메시지가 명확하지만, 한 스토어에 한 설정이라는 제약은 실재한다.

## Evidence

- `lmdb` 2.3.0, Python ≥3.9 (PyPI JSON, 2026-09-21).
- py-lmdb 공식 문서: *"LMDB environments must not be used across a `fork()` call"*, 그리고 fork 가능성이 있으면 `max_spare_txns=0`을 쓰라는 권고.
- 이 저장소에서 실측한 fork 동작: 부모가 연 상태에서 자식이 같은 경로를 열면 `lmdb.Error: The environment ... is already open in this process`. 자식이 상속받은 환경을 close한 뒤 열면 성공하고, 부모의 읽기는 그대로 동작한다(worker 4개로 확인).
- `av.open(io.BytesIO(...))`는 동작하고, seek 불가능한 스트림에서는 `NotImplementedError`를 던진다 → 가져온 바이트는 반드시 `BytesIO`로 감싼다.
- `science_hash` 불변성: `storage=local|lmdb|sftp` 세 경우 모두 `d1853fb82a5d`, `spec_hash`는 각각 다름(`validate_spec` 실행 결과).
- 회귀 방지: `tests/unit/test_storage_lmdb_store.py::test_forked_workers_read_while_the_parent_still_holds_the_store`, `tests/unit/test_media_over_storage.py`, `tests/unit/test_spec_schema.py::test_the_storage_backend_does_not_change_science_hash`.
- 동작 보존: `syn_e02_video_source_only` smoke를 리팩터링 후 재실행해 metric이 비트 단위로 동일함(`auc 0.91796875`, `tau 0.11499344557523727`, `bpcer 1.0`, `apcer_per_pai` 전부 `0.0`, `n_test 32`).

## Date
2026-09-21
