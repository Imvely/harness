# PAD Research Web Mockup

이 목업은 Passive Video Face PAD + Domain Adaptation 하네스 결과를 W&B처럼 탐색하는 데모 화면이다.
모든 샘플 데이터는 합성 데모 데이터이며 연구 결과가 아니다.

## 실행

```bash
cd web-mockup
npm install && npm run dev          # 또는: bun install && bun run dev
```

테스트는 `bun test`로 돈다(테스트 파일이 `bun:test`를 import하므로 vitest로는 실행되지 않는다).
타입 검사는 `npx tsc --noEmit`, 빌드는 `npm run build`.

## 포함 화면 (7개)

- **Dashboard**: run 요약, metric trend, seed variance, per-attack overview
- **Literature**(문헌 지도): 논문·데이터셋·방법·실험을 잇는 관계도, 증거 행렬, 읽기 큐
- **Runs**: 필터와 정렬 가능한 실험 table, keyboard-accessible run selection
- **Compare**: baseline/method 비교, mixed protocol 차단, smoke/risky row 포함 옵션
- **Audit**: protocol hash, manifest hash, threshold provenance, claim eligibility 확인
- **Report**: `summarize_experiment.py`와 `export_dashboard_data.py` 명령 미리보기
- **Control**: 실제 실행 없이 YAML patch preview와 safe command preview만 생성

## 용어 사전 (사이드바)

지표 옆의 작은 **?** 를 누르면 사이드바의 `이 화면의 용어` 패널이 열리면서 그 용어로 이동한다.
24개 항목이 지표 / 임계값 / 공격 / 실행 / 보안 판정 / 출처 추적 여섯 묶음으로 들어 있고,
각 항목은 한국어 이름·영어 원어·한두 문장 정의를 갖는다. 지표에는 `낮을수록 안전`,
`높을수록 좋음` 방향 표시가 붙는다 — "0.2는 좋은 값인가"가 처음 보는 사람의 첫 질문이고,
그 답이 APCER와 AUC에서 서로 뒤집히기 때문이다.

정의 문구는 계약서 §14(지표)와 §16(실행 어휘)을 따른다. `src/glossary.ts` 한 곳에만 있고,
`tests/glossary.test.ts`가 ⒜ 화면에 나오는 모든 지표에 항목이 있는지 ⒝ 방향 표시가
`utils.ts`의 `lowerIsBetter`와 일치하는지를 검사한다. 둘이 어긋나면 사전이 "낮을수록 안전"이라
말하는 지표를 차트가 올라갈 때 초록으로 칠하게 된다.

툴팁(`title`)은 편의로만 붙어 있다. 터치와 스크린리더에서 읽히지 않으므로 정의의 유일한
경로가 되어서는 안 된다.

## 화면에 보이는 데이터가 무엇인지 (상단 배너)

모든 화면 맨 위 배너가 지금 보고 있는 숫자의 출처를 먼저 말한다. 네 가지 상태가 있다.

| 상태 | 뜻 |
|---|---|
| **합성 예시 데이터** | 번들된 `demoRuns.ts`. UI를 둘러보기 위한 예시이며 측정값이 아니다 |
| **실제 실행이지만 데이터가 합성** | MLflow에서 내보낸 진짜 run이나 데이터셋이 synthetic이라 성능 주장 불가 |
| **실제 데이터로 측정된 결과** | 내보낸 run이고 `research_claim_allowed`가 true |
| **실제 + 모의 행 혼재** | Control 화면이 브라우저에서 만든 행이 섞여 있다 |

번들된 데모 행은 표에서 빗금 배경과 `모의 · 측정값 아님` 태그로 표시되고,
**Compare 계산에서는 토글과 무관하게 항상 제외**된다.

> **2026-09-20**: Control 화면에 있던 `mock 실행 대기열 추가` / `mock 즉시 실행` 버튼을 제거했다.
> 이 버튼들은 `methodOffsets()`와 시드 jitter로 APCER·AUC를 **계산해 만든** 행을 실제 run과 같은
> 목록에 넣었다. 브라우저는 탐지기를 측정할 수 없으므로 그렇게 만든 숫자는 구분 불가능한 허구다.
> 초안 저장(`Save draft`)과 명령 미리보기는 그대로 남는다 — 둘 다 입력값을 보관하고 보여줄 뿐이다.

## 실제 하네스 연동

목업 데이터 대신 로컬 MLflow/registry 결과를 JSON으로 내보낸다.

```bash
uv run --no-sync python scripts/export_dashboard_data.py --include-smoke -o web-mockup/public/dashboard-demo.json
```

앱은 시작할 때 `/dashboard-demo.json`을 fetch한다. 파일이 있으면 그 행으로 교체하고 배너가
"실제 …"로 바뀌며, 없으면 조용히 `demoRuns.ts`로 남는다(배너는 "합성 예시 데이터"). 이 JSON은
`.gitignore`에 있으므로 커밋되지 않는다 — 내보낸 결과를 저장소나 외부에 올리지 않는다(계약 §34).

## 안전 규칙

- synthetic 결과는 연구 주장으로 사용하지 않는다.
- smoke run은 성능 주장으로 사용하지 않는다.
- threshold는 dev split에서만 fit한다.
- protocol hash가 다르면 직접 비교하지 않는다.
- 한 실험 안에 protocol hash가 섞이면 비교를 차단한다.
- full run approval token은 사람만 만든다.
- raw frame이나 실제 얼굴 이미지는 표시하지 않는다.
- Control 화면은 실험을 실행하지 않는다.
- `execution.*`는 config patch preview로만 제안한다.
