# ADR-014 — 프레임은 "몇 번째"가 아니라 "몇 초"로 고르고, 도메인마다 간격을 기록한다

## Status
Proposed — 2026-09-22 실측(`scripts/inspect_lmdb_layout.py`, 6개 도메인 전체) 근거. 코드는 아직 없다. Phase 1 adapter와 sampling 코드가 이 규칙을 구현한다.

## Context

연구 방향은 3fps로 **일정하게** 뽑은 프레임에서 temporal FFT와 optical flow를 보는 것이다. 두 분석 모두 "프레임 사이 시간 간격이 일정하고, 도메인 간에도 같다"를 전제한다. 실측 결과 그 전제는 지금 어디에서도 성립하지 않는다.

| 도메인 | 저장된 프레임의 원본 간격 | 근거 |
|---|---|---|
| Idiap_ReplayAttack | 25fps, 간격 0.04s (40 clip 표본, hop 1) | `timing.source_fps {25: 40}`, `seconds_between_frames p50 0.04` |
| SiW-Mv2 | **원본이 30·25·60·29.97fps 혼재**, 저장 간격 0.0333s가 대부분이나 최대 0.433s | `source_fps {30:24, 25:6, 60:5, 29.97:5}`, `hop {1:35, 2:5}` |
| CASIA-CeFA | fps 기록 없음 | `FRAME_RATE_NOT_RECORDED` 1800/1800 |
| CASIA-SURF | fps 기록 없음. 배포본이 이미 10프레임 중 1장 | 같은 finding + 1차 자료(Zhang et al., CVPR 2019 §3.3) |
| aihub114 / aihub115 | fps 기록 없음, clip당 30프레임 고정 | 같은 finding, `num_frames min=max=30` |

두 번째 사실: **간격이 중간에 끊긴다.** 얼굴이 하나로 검출되지 않은 프레임을 빌드가 버렸고, 어디를 버렸는지는 저장되지 않았다. 표본에서 Idiap 40개 중 2개, SiW-Mv2 40개 중 3개가 불규칙했고, SiW-Mv2에서는 한 번에 13스텝(0.43초)이 비는 구간도 있었다.

세 번째 사실은 좋은 소식이다. 빌드가 `--target-fps 30`으로 돌아서 **영상 도메인은 원본 프레임을 거의 다 갖고 있다**(Idiap 최대 375프레임 = 25fps × 15초). 3fps 그리드는 재빌드 없이 지금 저장소에서 만들 수 있다.

## Decision

1. **샘플링은 시간으로 한다.** clip에서 `t_k = k / 3` 초(k = 0..N-1)에 **가장 가까운** 저장 프레임을 고른다. "몇 번째 프레임마다"로 고르지 않는다. 원본이 25fps면 3fps는 정수 간격이 아니므로(25/3 ≈ 8.33), 정수 간격 규칙은 도메인마다 다른 실제 fps를 만들어낸다.
2. **프레임의 시각은 adapter가 알아내 manifest에 기록한다.** 저장소에는 없으므로 원본 영상 헤더에서 읽는다. `ManifestRecord.extra`에 `dt_seconds`(프레임 간 공칭 간격)와 `time_source`를 넣는다. `time_source`는 값의 출처다: `header`(원본 영상 헤더에서 읽음), `documented`(데이터셋 1차 자료에 기재), `unknown`.
3. **`time_source: unknown`인 clip은 시간 기반 분석에서 제외한다.** temporal FFT, optical flow, 그리고 "초당 움직임"을 쓰는 모든 feature가 대상이다. 지금 기준으로 CASIA-CeFA, CASIA-SURF, aihub114, aihub115가 여기 해당한다. 이 도메인들은 프레임 단위(공간) 분석과 clip 분류에는 그대로 쓴다.
4. **간격이 불규칙한 구간은 표시한다.** 고른 두 프레임의 실제 간격이 공칭 간격의 1.5배를 넘으면 그 clip에 `irregular_gap: true`를 남긴다. 버린 자리를 복원할 수는 없지만, 결과를 해석할 때 걸러낼 수는 있다.
5. **optical flow는 초당 이동량으로 정규화한다.** 프레임 쌍의 flow를 그 쌍의 실제 `Δt`로 나눈다. 정규화하지 않으면 25fps 도메인과 30fps 도메인의 "움직임"이 20% 차이 나고, 모델은 그 차이를 도메인 단서로 쓸 수 있다.
6. **3fps에서 temporal FFT로 말할 수 있는 것은 1.5Hz 이하로 한정한다.** 표본 정리(Nyquist)에 따라 초당 3장으로는 1.5Hz까지만 구분된다. 맥박(약 1~2Hz)과 화면 주사율은 이 한계를 넘으므로 **다른 주파수로 접혀 들어온다(aliasing)**. rPPG류 주장은 이 그리드에서 하지 않는다. 필요하면 원본 fps로 따로 뽑아 별도 실험으로 다룬다.
7. **공간 FFT는 이 규칙과 무관하다.** 한 프레임 안의 무늬(모아레, 인쇄 망점)는 fps와 상관없다. 다만 JPEG 재압축 이력이 도메인마다 다르므로 그 사실을 `extra`에 남긴다(ADR-013).

## Alternatives Considered

- **정수 간격(매 N번째 프레임)**: 구현이 간단하다. 기각: 25fps에서 3fps를 만들 수 없고(8 또는 9로 반올림), 그 반올림이 도메인마다 다른 실제 fps를 만든다. 빌드 코드의 `hop = max(1, round(fps/target))`가 정확히 이 문제를 갖고 있다.
- **모든 도메인을 최저 공통 fps로 맞추기**: fps가 미기록인 도메인이 4개라 최저값을 알 수 없다. 기각.
- **fps 미기록 도메인을 버리기**: 6개 중 4개가 사라진다. 기각. 대신 결정 3으로 **분석 종류를 제한**한다.
- **저장소를 다시 만들어 타임스탬프를 넣기**: 가장 깨끗하다. 기각: 빌드 스크립트와 LMDB는 팀원과 공유되는 저장소 밖 자산이라 harness가 고치지 않는다(ADR-013 결정 5). 필요한 정보는 **읽는 쪽에서** 얻는다 — fps는 원본 영상 헤더에서, 버려진 자리는 프레임 캐시와 대조해서(`docs/design/store-workarounds.md` §3, §4).

## Why

프레임 번호는 시간이 아니다. 지금 저장소에서 "16프레임 clip"은 도메인에 따라 0.53초(30fps)일 수도, 0.64초(25fps)일 수도 있다. 그 차이는 optical flow의 크기에 그대로 들어가고, **라벨이 아니라 도메인과 상관관계를 갖는 단서**가 된다. Domain adaptation 연구에서 이런 단서는 적응이 "흡수"해 버려서, 측정하려던 것 대신 촬영 장비 차이를 측정하게 만든다.

결정 3이 데이터를 버리는 것처럼 보이지만 그 반대다. 시간을 모르는 clip에 시간 기반 feature를 계산하면 숫자는 나오지만 그 숫자가 무엇인지 말할 수 없다. 쓸 수 있는 분석을 명시하는 편이 결과를 살린다.

## Risks

- **`time_source: header`도 추정이 섞인다**: 컨테이너 헤더의 fps는 가변 프레임률 영상에서 평균값일 수 있다. 표본에서 SiW-Mv2에 29.97fps가 5개 있었다(NTSC 계열). 0.1% 수준의 오차이므로 3fps 그리드에서는 무시할 수 있으나, 기록은 `header`로 남겨 구분한다.
- **버려진 프레임의 위치는 복원 불가**: 결정 4는 "간격이 벌어졌다"만 알려 준다. 정확한 시각은 재빌드로만 얻을 수 있다.
- **16프레임 × 3fps = 5.3초**: clip이 그보다 짧으면 앞뒤를 반복하거나 clip을 버려야 한다. CASIA-SURF는 프레임 1장짜리 clip도 있다(`num_frames min 1`). 이 처리 규칙은 sampling 코드에서 정하고 manifest에 `padded: true`로 남긴다.
- **Nyquist 제한이 연구 범위를 좁힌다**: 3fps에서는 맥박 기반 단서를 쓸 수 없다. 이 방향이 중요해지면 별도 고fps 프로토콜이 필요하다.

## Evidence

- `scripts/inspect_lmdb_layout.py` 실측(2026-09-22, 6개 도메인). 위 표의 모든 수치는 `timing`, `frame_cache`, `index.frame_rate` 섹션에서 그대로 옮긴 것이다.
- 1차 자료: Replay-Attack 25fps(Chingovska et al., BIOSIG 2012 §III), CASIA-SURF 10프레임 중 1장 배포(Zhang et al., CVPR 2019 §3.3), CeFA 30fps 촬영(Liu et al., arXiv 2003.05136 §3). `verified: false` — 출판본 대조 전.
- 계약서 §28(video sampling), §53 열린 질문 12(low-motion 정의).
- ADR-013(도메인별 빌드 차이), ADR-009/ADR-015(crop과 flow).

## Date
2026-09-22
