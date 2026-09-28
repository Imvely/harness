# ADR-007 — 비디오 디코딩은 PyAV로 통일하고, 필요한 프레임만 디코딩한다

## Status
Accepted (2026-09-22, 사용자 검토) — 코드는 `48a5dd1`에 구현되어 있다. 이 ADR은 그 결정을 사후에 기록한 것이다.

## Context

Phase 0의 하네스는 `npy_clip` 하나만 읽을 수 있었다. 합성(synthetic) 데이터는 전부 `.npy`이기 때문에 그걸로 충분했지만, 정작 `configs/protocol/ocim_target_i_v1.yaml`이 이름을 대고 있는 실제 데이터셋 네 개(Replay-Attack, CASIA-FASD, MSU-MFSD, OULU-NPU)는 **전부 비디오**다. 즉 하네스는 자기 프로토콜이 지정한 데이터를 단 한 프레임도 읽지 못하는 상태였다.

비디오를 읽으려면 디코더를 하나 골라야 하는데, PyTorch 생태계의 사정이 2026년 기준으로 다음과 같다(2026-09-17 PyPI/공식 문서 확인).

| 후보 | 상태 |
|---|---|
| `torchvision.io.read_video` | **0.26에서 제거됨**. 더 이상 존재하지 않는다 |
| `decord` | 2021년 이후 사실상 방치. Python 3.11+ wheel 없음 |
| `opencv-python` | `VideoCapture`는 순차 읽기 전용이고, 프레임 단위 seek 정확도가 빌드에 따라 다르다 |
| **PyAV (`av`)** | 활발히 유지, FFmpeg를 wheel에 번들, Python 3.11+ 지원 |

두 번째 문제는 "얼마나 읽느냐"다. Phase 0 리더는 클립 전체를 디코딩한 뒤 `frames`개만 남기고 버렸다. 16프레임짜리 합성 `.npy`에서는 공짜지만, 수백 프레임짜리 1080p 비디오에서는 **DataLoader worker마다 완전히 디코딩된 비디오 한 편을 메모리에 들고 있게 된다**. worker 8개면 그만큼 곱해진다.

## Decision

1. **디코더는 PyAV(`av>=13,<19`)로 통일한다.** `opencv-python-headless`는 이후 face crop 단계에서만 쓰고, 컨테이너 디코딩에는 쓰지 않는다.
2. **읽기를 `probe_n_frames()`와 `read_frames(indices)`로 분리한다.** 샘플러가 먼저 인덱스를 고르고, 디코더는 그 인덱스만 만진다.
3. **`ManifestRecord.n_frames`가 채워져 있으면 그것을 신뢰한다.** manifest는 한 번 만들고 매 epoch 읽으므로, adapter가 빌드 시점에 프레임 수를 기록해 두면 probe 비용이 0이 된다. 비어 있을 때만 컨테이너를 연다.
4. **seek하지 않고 앞에서부터 디코딩한다.** 가장 높은 인덱스에 도달하면 멈춘다.
5. **manifest가 주장하는 것보다 파일이 짧으면 예외를 던진다.** 짧은 클립을 조용히 반환하지 않는다.
6. `frames_dir`의 파일명은 **자연 정렬**한다(`frame_2` < `frame_10`).

## Alternatives Considered

- **`decord`**: 랜덤 액세스 API가 이 용도에 가장 잘 맞지만 유지되지 않는다. 2021년 이후 커밋이 없고 현행 Python wheel이 없다. 연구 기간이 수년 단위인 프로젝트에서 빌드가 깨지면 되돌릴 방법이 없다.
- **비디오를 미리 프레임으로 풀어 두기(pre-extraction)**: 디코딩 비용이 사라지는 대신 수백만 개의 작은 파일이 생기고, 이는 ADR-010이 다루는 파일시스템 문제를 그대로 만든다. 다만 이 선택지는 **배제되지 않았다** — `media_type: frames_dir`로 이미 지원되므로 사용자가 원하면 그렇게 쓸 수 있다.
- **seek 후 디코딩**: 훨씬 빠르다. 그러나 seek는 가장 가까운 keyframe에 착지하고, 거기서 목표 프레임까지는 어차피 디코딩해야 정확하다. 이 계산을 틀리면 **조용히 잘못된 프레임을 반환**한다. temporal cue를 연구하는 모델에게 이것은 느린 것보다 훨씬 나쁜 실패다.

## Why

핵심은 "느린 것"과 "틀린 것"의 비대칭이다. temporal PAD 모델에서 프레임 순서나 위치가 어긋나면 모델이 학습하는 신호 자체가 달라지고, 그 오류는 metric에 이상값으로 나타나지 않는다(그냥 성능이 조금 나쁠 뿐이다). 반면 디코딩이 느린 것은 눈에 보이고, 측정되고, 나중에 최적화할 수 있다. 그래서 정확성 쪽으로 기울여 결정했다.

`n_frames`를 신뢰하는 것도 같은 이유다. manifest는 `manifest_hash`로 봉인되어 있어 내용이 바뀌면 hash가 달라진다. 즉 "신뢰"의 근거가 관례가 아니라 검증 가능한 해시다.

## Risks

- **`n_frames`가 잘못 기록된 manifest**: adapter의 버그가 조용히 전파된다. 완화: 파일이 manifest보다 짧으면 예외(결정 5). 반대 방향(파일이 더 김)은 잡히지 않으므로, adapter를 쓸 때 몇 개 샘플의 프레임 수를 손으로 확인해야 한다.
- **앞에서부터 디코딩의 비용**: 긴 비디오의 뒤쪽 프레임을 샘플링하면 매번 앞부분을 전부 디코딩한다. Phase 1에서 실제 데이터로 epoch 시간을 측정하고, 병목이면 그때 keyframe 정확도를 검증한 seek 경로를 **별도 ADR로** 추가한다. 지금 추측으로 최적화하지 않는다.
- **FFmpeg 번들의 라이선스**: PyAV wheel이 번들하는 FFmpeg의 빌드 구성(LGPL vs GPL)은 배포 형태에 영향을 줄 수 있다. 연구용 내부 사용에서는 문제되지 않지만, 모델을 제품에 넣을 때 확인이 필요하다.

## Evidence

- `torchvision` 0.26 릴리스 노트에서 `io.read_video` 제거 확인(2026-09-17).
- PyPI JSON API: `av` 최신 버전이 Python 3.11+ wheel을 제공하고 FFmpeg를 번들함.
- `decord` PyPI 최신 릴리스 날짜가 2021년, Python 3.11 classifier 없음.
- 이 저장소에서 실측: `av.open(io.BytesIO(...))`는 동작하지만 seek 불가능한 스트림에서는 `NotImplementedError`를 던진다(ADR-010이 이 사실에 의존한다).
- `tests/unit/test_media.py`가 네 가지 `media_type`을 실제 인코딩된 비디오·실제 PNG로 검증한다.

## Date
2026-09-21
