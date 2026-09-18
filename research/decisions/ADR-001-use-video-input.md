# ADR-001 — RGB Video(multi-frame clip)를 기본 입력으로 사용한다

## Status
Accepted

## Context

최종 목표는 안면인식 서비스 환경에 적용할 **Passive Face PAD**다(계약서 §0). 사용자가 고개를 크게 돌리거나 문장을 말하거나 의도적으로 눈을 깜빡이게 하는 능동(active) 방식은 지양하고, 짧은 비디오의 **미세한 temporal cue**를 활용하는 방향을 선호한다. 설치 환경(카메라, 조명, 거리, 배경, 영상 품질)은 다양하며 향후 RGB + ToF fusion으로 확장할 계획이다(§3.3).

RQ1(§4)은 "Video가 frame-only PAD보다 실제로 도움이 되는가?"이며, 특히 사용자가 거의 움직이지 않는 low-motion 상황에서도 작은 landmark movement, local facial motion, display flicker, moiré/reflection 변화, temporal compression artifact, frame timing, rPPG 유사 cue가 유효한지가 핵심이다.

## Decision

- 하네스의 정본 입력 단위는 **RGB video clip**(`[T, H, W, 3]`, `model.input.frames = T`)이다. Frame baseline은 `T = 1`인 특수 경우로 같은 파이프라인(manifest → ClipDataset → model → evaluator)을 탄다.
- 1차 실험 매트릭스(§43)에서 E01(1 frame)과 E02(8 frames)를 **같은 protocol_hash** 아래에서 비교해 temporal gain을 측정한다(가설 H1).
- ToF/depth는 Phase 0에 넣지 않되, `model.input.modality` 필드로 config schema만 확장 가능하게 둔다(§3.3).
- Low-motion protocol(§28)을 별도 evaluation 축으로 유지한다.

## Alternatives Considered

1. **Frame-only PAD**(단일 이미지 texture 기반, CDCN 계열 등) — 구현·추론이 단순하고 강한 baseline이지만 replay의 temporal artifact와 rPPG 유사 cue를 사용할 수 없다. baseline으로 **유지**하되 정본 입력으로는 채택하지 않는다(§9.1).
2. **Active liveness**(고개 돌리기, 문장 읽기, 의도적 깜빡임) — 보안 단서는 강하지만 사용자 경험 요구사항(§0)과 충돌해 기각.
3. **RGB + ToF fusion 즉시 도입** — 최종 방향이지만 RGB 우선 원칙(§3.3)에 따라 후속 Phase로 이연.

## Why

- 제품 요구사항(passive, 무동작)과 연구 질문(RQ1, RQ4)이 모두 video 입력을 전제로 한다.
- Frame baseline을 같은 파이프라인의 `T = 1`로 두면 §14.2의 공격 유형별 비교가 protocol_hash 동일성 위에서 성립한다.
- Target 환경 적응(§0, RQ3)에서 "Replay Attack도 같은 target 카메라로 촬영된다"(§5.3)는 사실이 video-specific cue 보존을 요구한다.

## Risks

- Low-motion 환경에서는 temporal gain이 작거나 없을 수 있다. H1이 기각되면 frame baseline이 더 적합할 수 있으므로 E01을 항상 함께 보고한다.
- 비디오 디코딩·프레임 샘플링(§28)이 결과에 영향을 준다. Phase 0은 `.npy` clip만 읽고 실제 디코딩(PyAV)은 Phase 1로 이연(ADR-005).
- 추론 지연(§32)이 frame 모델보다 크다. latency 측정을 evaluation에 포함한다.

## Evidence

- 계약서 §0, §3.2, §4 RQ1, §9.2, §28, §43(E01/E02).
- 문헌: `research/papers/paper_index.yaml`의 `wang2022ttn`(TTN), `yang2025g2v2former`(G²V²former) — 수치는 `claims.jsonl`에 검증 후 기록한다.
- 실험 증거는 아직 없음(H1 untested). 합성 데이터 run은 증거가 아니다.

## Date
2026-09-17
