# ADR-017 — 공격 종류는 물리적 성질로 이름 짓고, 묶음 단위로 켜고 끈다

## Status
Proposed — 범위는 사용자가 결정했다(2026-09-23: "3D 추가하는데 체크로 온오프 가능하게. 일단 iBeta lv.1이 목표라서 이후에 lv.2 할 때 쓸 것"). 코드(`PAI` 목록, `pai_map.py`)는 이 변경에 포함되어 있다.

## Context

6개 도메인의 공격 종류를 실측했더니 이름 체계가 제각각이었다. CASIA-SURF는 번호(`01_e_s`), SiW-Mv2는 문장형(`Mask_TransparentMask`), aihub은 서술형(`attack_03_replay_phone`), Replay-Attack은 **클래스 이름에 공격 도구가 없다**(클래스는 거치 방식 `hand`/`fixed`이고 도구는 `extra_meta.device`에 있다).

공격 종류별 APCER는 이 이름들이 하나의 어휘로 모여야 비교가 된다(§14.2). 그리고 지금 목표는 2D 공격(iBeta Level 1을 겨냥)이지만, SiW-Mv2에는 마스크·메이크업·부분 공격이 이미 들어 있고 aihub114에도 3D mask가 45 clip 있다. 나중에 쓸 데이터를 지금 버리면 그때 다시 만들어야 한다.

## Decision

1. **`PAI` 목록을 확장한다.** 평면 공격(print, replay 계열, display)에 더해 입체 공격(`mask_3d`, `mask_paper`, `mask_transparent`, `mask_silicone`, `mannequin`)과 얼굴에 적용하는 공격(`makeup`, `partial`)을 추가한다.
2. **이름에 인증 레벨을 쓰지 않는다.** `level1`, `level2` 같은 이름 대신 공격의 물리적 성질로 부른다. iBeta/ISO 레벨과의 대응은 1차 자료로 확인하기 전이고(§33), 식별자에 넣으면 그 추측이 영구히 남는다.
3. **묶음으로 켜고 끈다.** `PAI_FLAT`(평면), `PAI_THREE_D`(입체), `PAI_ON_FACE`(얼굴 적용) 세 묶음을 정의하고, protocol의 `attack_types`가 어떤 묶음을 포함할지 고른다. 지금 기본은 `PAI_FLAT`이고, 나중에 입체 공격을 다룰 때 `PAI_THREE_D`를 더한다.
4. **데이터는 전부 담는다.** 지금 안 쓰는 공격도 manifest에는 들어간다. 켜고 끄는 일은 protocol에서 하지 데이터를 다시 만들지 않는다.
5. **원래 이름을 남긴다.** 모든 record가 데이터셋 자신의 클래스 이름을 `pai_detail`에 보존한다. 매핑 판단을 나중에 다시 읽고 다시 내릴 수 있어야 한다.
6. **모르는 클래스는 실패한다.** 표에 없는 클래스 이름을 만나면 `other`로 떨어뜨리지 않고 예외를 던진다(§27.2). 데이터셋이 새 공격을 추가하면 빌드가 멈추고 사람이 결정한다.
7. **Replay-Attack은 메타데이터에서 도구를 읽는다.** `device`(print/mobile/highdef)와 `media_type`(photo/video)으로 정한다. **화면에 띄운 정지 사진은 replay가 아니라 `display`다** — 움직이는 것이 없기 때문이다. 영상이 재생된 것만 replay로 본다.

## Alternatives Considered

- **2D만 남기고 나머지 clip을 제외**: manifest가 작아진다. 기각: 나중에 입체 공격을 다룰 때 데이터셋을 다시 만들어야 하고, `manifest_hash`가 바뀌어 이전 결과와 비교가 끊긴다.
- **모르는 클래스를 `other`로 처리**: 빌드가 멈추지 않는다. 기각: 새 공격이 조용히 `other`에 섞이면 공격별 APCER가 의미를 잃는다.
- **`level1` / `level2`로 이름 짓기**: 목표를 바로 읽을 수 있다. 기각: 결정 2.
- **`Mask_HalfMask`를 `mask_3d`가 아니라 별도 값으로**: 더 세밀하다. 보류: 세부는 `pai_detail`에 남으므로 필요해지면 나중에 값을 쪼갤 수 있다. 지금 쪼개면 표본이 잘게 흩어져 PAI별 최소 표본 조건을 넘기지 못한다.

## Why

공격 종류는 이 연구의 결과 그 자체다(§14.2: 공격별 APCER). 그러므로 어휘가 흔들리면 결론도 흔들린다. 물리적 성질로 이름 짓는 이유는 그것이 데이터에서 확인 가능한 사실이기 때문이고, 인증 레벨로 이름 짓지 않는 이유는 그것이 우리가 아직 확인하지 않은 문서의 해석이기 때문이다.

## Risks

- **입체 공격의 표본이 적다**: aihub114의 3D mask는 45 clip, SiW-Mv2의 Silicone은 17 clip, Mask_PaperMask는 17 clip이다. 입체 공격을 켜더라도 PAI별 최소 표본 조건에 걸려 `inconclusive`가 나올 수 있다. 그것이 올바른 동작이다.
- **`display` vs `replay` 구분이 문헌과 다를 수 있다**: 많은 논문이 화면 공격을 모두 replay로 부른다. 우리 구분이 더 세밀하므로, 문헌 수치와 비교할 때는 두 값을 합쳐야 한다. 이 사실을 리포트에 적는다.
- **iBeta 레벨 대응 미확인**: 어떤 공격이 Level 1이고 어떤 것이 Level 2인지는 1차 자료를 읽은 뒤에 기록한다. 그 전까지 "Level 1 달성" 같은 문장을 쓰지 않는다(§33).

## Evidence

- 2026-09-22 실측: 6개 도메인의 `sub_cls` 전체 목록과 clip 수(ADR-013).
- `src/pad_research/data/pai_map.py` — 매핑표와 해석 규칙. `tests/unit/test_pai_map.py`가 실측된 모든 클래스 이름이 매핑되는지 확인한다.
- 계약서 §14.2(공격별 APCER), §27.2(추측 금지), §33(인증 기준을 기억으로 쓰지 않기).

## Date
2026-09-23
