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

## 화면에 보이는 데이터가 무엇인지 (상단 배너)

모든 화면 맨 위 배너가 지금 보고 있는 숫자의 출처를 먼저 말한다. 네 가지 상태가 있다.

| 상태 | 뜻 |
|---|---|
| **합성 예시 데이터** | 번들된 `demoRuns.ts`. UI를 둘러보기 위한 예시이며 측정값이 아니다 |
| **실제 실행이지만 데이터가 합성** | MLflow에서 내보낸 진짜 run이나 데이터셋이 synthetic이라 성능 주장 불가 |
| **실제 데이터로 측정된 결과** | 내보낸 run이고 `research_claim_allowed`가 true |
| **실제 + 모의 행 혼재** | Control 화면이 브라우저에서 만든 행이 섞여 있다 |

Control 화면의 "mock 실행"이 만드는 행은 지표를 **공식으로 계산**한 것이라 측정값이 아니다.
이런 행은 표에서 빗금 배경과 `모의 · 측정값 아님` 태그로 표시되고, **Compare 계산에서는 토글과 무관하게 항상 제외**된다.

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
