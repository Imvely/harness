# PAD Research Web Mockup

이 목업은 Passive Video Face PAD + Domain Adaptation 하네스 결과를 W&B처럼 탐색하는 데모 화면이다.
모든 샘플 데이터는 합성 데모 데이터이며 연구 결과가 아니다.

## 실행

이 환경에는 `node`와 `npm`이 없어서 Bun으로 검증했다.

```powershell
cd C:\Harness\PAD\web-mockup
bun install
bun run build
bun run dev
```

Node 환경에서는 다음 명령도 사용할 수 있다.

```powershell
npm install
npm run build
npm run dev
```

## 포함 화면

- Dashboard: run 요약, metric trend, seed variance, per-attack overview
- Runs: 필터와 정렬 가능한 실험 table, keyboard-accessible run selection
- Compare: baseline/method 비교, mixed protocol 차단, smoke/risky row 포함 옵션
- Audit: protocol hash, manifest hash, threshold provenance, claim eligibility 확인
- Report: `summarize_experiment.py`와 `export_dashboard_data.py` 명령 미리보기
- Control: 실제 실행 없이 YAML patch preview와 safe command preview만 생성

## 실제 하네스 연동

목업 데이터 대신 로컬 MLflow/registry 결과를 JSON으로 내보낼 수 있다.

```powershell
cd C:\Harness\PAD
uv run --no-sync python scripts/export_dashboard_data.py --include-smoke -o web-mockup/public/dashboard-demo.json
```

현재 React 화면은 데모 `demoRuns.ts`를 기본으로 사용한다.
다음 단계에서는 위 JSON을 fetch하여 같은 화면 계약에 연결한다.

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
