# 데이터를 어떻게 읽을 것인가 — 저장소 방식 조사

> 결정은 [ADR-010](../../research/decisions/ADR-010-storage-backends.md)에 있다. 이 문서는 그 결정에 이르기까지 확인한 사실과, **지금 채택하지 않은 선택지를 왜 미뤘는지**를 남긴다. 나중에 "왜 Zarr를 안 썼지?"를 다시 묻지 않기 위한 기록이다.
>
> 조사일 2026-09-21. 버전은 PyPI JSON API로 확인했고, 동작은 이 저장소에서 직접 실행해 확인했다(아래 "실측" 표시).

## 0. 이 문제가 왜 어려운가

얼굴 PAD 데이터셋은 파일시스템에 최악의 형태다. 클립 수천 개가 프레임 수백만 개가 되고, 한 epoch은 `open`/`stat` 수백만 번이 된다. 로컬 SSD에서는 견디지만 네트워크 파일시스템에서는 **메타데이터 왕복이 지배**해 GPU가 굶는다.

그래서 이 분야에서는 데이터를 하나의 큰 컨테이너로 묶는 관행이 있고, 사용자도 LMDB로 들고 있다. 다만 사람마다 사정이 달라서, 같은 실험이 LMDB·풀어 놓은 디렉터리·SSH 너머 어디에서나 돌아야 한다.

## 1. 후보

| 방식 | 최신 버전 (2026-09-21) | Python 요구 | 이 프로젝트에서 |
|---|---|---|---|
| 디렉터리 트리 (+ NFS/SMB/**sshfs** 마운트) | — | — | **채택** (`local`) |
| LMDB (`lmdb`) | 2.3.0 | ≥3.9 | **채택** (`lmdb`) |
| SFTP (`paramiko`) | 5.0.0 | ≥3.9 | **채택, optional extra** (`sftp`) |
| `fsspec` | 2026.9.0 | ≥3.10 | 기각 — 아래 §4 |
| HDF5 (`h5py`) | 3.16.0 | ≥3.10 | 보류 |
| Zarr | 3.4.0 | **≥3.12** | 보류 — 이 프로젝트는 3.11 고정이라 설치조차 안 된다 |
| WebDataset | 1.0.2 | ≥3.10 | 보류 |
| S3/GCS | — | — | 정책 문제 — 아래 §5 |

## 2. 실측으로 확인한 사실

### 2.1 LMDB는 fork를 건너면 안 되고, 그 사실이 조용히 드러나지 않는다

py-lmdb 공식 문서는 분명히 말한다: *"LMDB environments must not be used across a `fork()` call"*, 그리고 fork 가능성이 있으면 `max_spare_txns=0`을 쓰라고 권고한다. DataLoader worker는 Linux에서 정확히 fork다.

그런데 **문서만 따라 "자식에서 다시 열면 된다"로 구현하면 동작하지 않는다.** 실측:

```
부모가 연 상태에서 자식이 같은 경로를 open
  → lmdb.Error: The environment '...' is already open in this process.
```

py-lmdb는 열린 환경의 **프로세스 전역 레지스트리**를 갖고 같은 경로의 두 번째 open을 거절하는데, 이 레지스트리가 fork를 건너 상속된다. 자식 입장에서 "this process"는 실은 부모다. 자식은 상속받은 객체를 **먼저 close** 해야 레지스트리가 비고 자기 것을 열 수 있다. 실측으로 확인:

```
자식: inherited.close() → lmdb.open(...) → 읽기 성공 (worker 4개 모두)
부모: 이후에도 정상 읽기
```

`lock=False`일 때만 안전하다. reader lock table이 없으므로 자식의 close가 자식의 매핑과 디스크립터만 해제한다. `lock=True`면 `lock.mdb`의 reader slot이 공유되므로 같은 조작이 부모의 슬롯을 놓아 버릴 수 있다 — 그래서 그 조합은 거절한다.

> 이것을 문서만 읽고 넘어갔다면 multi-worker 학습이 첫 배치에서 전부 죽었을 것이다. 회귀 테스트가 있다: `tests/unit/test_storage_lmdb_store.py::test_forked_workers_read_while_the_parent_still_holds_the_store`.

### 2.2 PyAV는 seek 가능한 스트림만 받는다

LMDB나 SFTP에서 온 바이트를 디코딩하려면 파일 객체로 감싸야 한다. 실측:

```python
av.open(io.BytesIO(data))        # 동작. header frame count도 읽힘
av.open(<seek 불가능한 스트림>)   # NotImplementedError
```

그래서 가져온 바이트는 반드시 `BytesIO`로 감싼다. 반대로 **실제 파일이 있으면 경로를 넘겨야 한다** — 경로를 받은 PyAV는 필요한 프레임까지만 읽지만, 바이트를 받으면 객체 전체가 worker 메모리에 올라간다. 200 MB 비디오면 worker마다 200 MB다. 이것이 `StorageBackend.local_path()`가 `Path | None`을 반환하는 이유다.

### 2.3 `np.load`의 mmap도 경로를 요구한다

`mmap_mode="r"`은 헤더만 읽고 픽셀은 디스크에 둔다. 파일 객체에는 쓸 수 없으므로, 경로가 없는 백엔드에서는 일반 로드로 떨어진다. 같은 비대칭이다.

## 3. 채택한 것

### `local` — 디렉터리 트리

가장 단순하면서 **가장 많은 경우를 덮는다.** OS가 이미 디렉터리로 보이게 만들어 둔 것은 전부 여기로 들어온다: NFS, SMB, 컨테이너 볼륨, 그리고 `sshfs`.

원격 데이터에 대해 SFTP보다 마운트를 권하는 이유가 여기 있다. 커널이 페이지 캐시와 readahead를 주고, PyAV가 스트리밍할 수 있는 진짜 파일 디스크립터를 준다. 그리고 **자격증명이 이 저장소에 전혀 들어오지 않는다.**

### `lmdb` — 메모리 매핑 key/value

수백만 개 작은 파일 문제에 대한 직접적인 답이다. 읽기가 syscall 폭풍이 아니라 page fault가 된다.

핵심 설계: **manifest의 `relative_path`가 곧 키다.** 그러면 LMDB가 가질 수 있는 모든 레이아웃이 이미 `media_type`으로 표현된다(비디오 한 편 / 프레임들의 키 접두사 / 스틸 / `.npy`). 사용자의 LMDB 구조를 추측할 필요가 없다는 뜻이고, 계약서 §27.2를 지키는 방법이기도 하다.

읽기 플래그와 이유: `readonly=True`(쓰지 않는다), `lock=False`(읽기 전용 마운트에서도 열리고 worker가 reader slot을 고갈시키지 않는다 — 대신 아무도 쓰지 않는 동안만 옳다), `readahead=False`(RAM보다 큰 스토어에 랜덤 액세스), `meminit=False`(어차피 덮어쓸 페이지를 0으로 채우지 않는다), `max_spare_txns=0`(fork 권고).

### `sftp` — SSH 너머

성능도 보안도 마운트가 낫고 문서도 그렇게 권한다. 그럼에도 넣은 이유는, FUSE 권한이 없는 공용 서버가 실제로 존재하고 그 경우 "느린 읽기"가 "못 읽음"보다 낫기 때문이다. **optional extra**(`uv sync --extra sftp`)로 두어 기본 설치에는 들어가지 않는다.

자격증명은 설정 파일에 절대 넣지 않는다. 호스트·계정·비밀번호는 전부 **환경변수 이름**으로만 적고 값은 셸에 있다. 알 수 없는 host key는 TOFU(trust on first use)하지 않고 거절한다 — 그 주소에 응답하는 무엇이든 얼굴 데이터를 받아갈 수 있게 되기 때문이다.

## 4. `fsspec`을 쓰지 않은 이유

s3/sftp/http/local을 한 인터페이스로 묶어 주므로 매력적이다. 두 가지로 기각했다.

1. **파일 추상화이지 key/value 추상화가 아니다.** 우리에게 필요한 핵심 매핑 — "LMDB에서 `frames_dir`은 키 범위다" — 가 `fsspec`의 모델에 자연스럽게 앉지 않는다. `AbstractFileSystem`을 LMDB 위에 억지로 구현하면 `ls`/`info`/`open`을 전부 흉내 내야 하는데, 우리가 실제로 쓰는 것은 `read_bytes`와 `list_children` 둘뿐이다.
2. **의존성 대비 이득이 없다.** 백엔드 세 개를 직접 쓰는 비용이 크지 않았고, 대신 각 백엔드가 자기 함정(§2.1의 fork 레지스트리 같은)을 자기 자리에서 문서화할 수 있다.

나중에 백엔드가 대여섯 개로 늘면 재검토할 가치가 있다. 지금은 아니다.

## 5. 보류한 것들과 그 조건

- **HDF5**: LMDB와 같은 문제를 푸는 다른 답. 병렬 읽기에서 SWMR 설정이 까다롭고, LMDB가 이미 사용자의 현실이다. LMDB로 표현하기 어려운 레이아웃이 나오면 검토.
- **Zarr**: 3.x가 **Python ≥3.12**를 요구한다. 이 프로젝트는 hydra-core 호환 때문에 3.11 고정(ADR-005)이라 설치 자체가 안 된다. Python을 올리는 별도 결정이 선행되어야 한다.
- **WebDataset / tar shard**: 순차 읽기에 최적화되어 있어 대규모 분산 학습에 강하다. 우리는 샘플러가 **랜덤 인덱스**를 고르는 구조(ADR-007)라 강점이 살지 않는다. 학습 규모가 커지고 순차 스트리밍으로 갈 수 있게 되면 재검토.
- **S3 / GCS / MinIO**: 기술 문제가 아니라 **정책 문제**다. 계약서 §34는 얼굴 데이터의 외부 클라우드 업로드를 금지한다. 읽기 전용이고 사내 MinIO라면 다른 이야기일 수 있으나, 그 판단은 데이터 라이선스와 개인정보 정책 확인이 먼저다. 백엔드 등록만 하면 추가되는 구조이므로, 필요해지면 ADR과 함께 넣는다.

## 6. 결정이 만든 성질

이 조사에서 가장 중요한 결론은 어느 라이브러리를 쓰느냐가 아니다. **저장 방식이 과학이 아니라는 것**이다.

백엔드는 바이트가 어디서 오는지만 바꾸고, 그것이 무엇인지는 바꾸지 않는다. 그래서 `storage` 블록은 `science_hash`에서 제외되고, 세 사람이 세 가지 방식으로 읽어도 결과가 직접 비교된다(계약서 §14.3). 이 전제는 테스트로 고정되어 있다:

- `tests/unit/test_media_over_storage.py` — 같은 비디오·프레임·`.npy`를 LMDB와 파일에서 읽어 픽셀이 동일한지 비교한다.
- `tests/unit/test_spec_schema.py::test_the_storage_backend_does_not_change_science_hash` — `storage=local|lmdb|sftp` 세 경우의 `science_hash`가 같은지 확인한다.

전제가 깨지면 나머지 결정이 전부 근거를 잃는다.
