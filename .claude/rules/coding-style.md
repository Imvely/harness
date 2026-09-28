---
paths:
  - "src/**"
  - "tests/**"
  - "scripts/**"
  - "configs/**"
  - ".claude/hooks/**"
---
# 코딩 규칙 (coding-style)

전문 §19, §20, §27, §32 참조.

- 절차(§27.1): 해당 module 읽기 → call path 확인 → config 의존성 확인 → 테스트 확인 → 최소 수정. 새로 만들기 전에 검색.
- 도구: `uv run --no-sync ruff format . && uv run --no-sync ruff check . && uv run --no-sync pyright src scripts && uv run --no-sync pytest -m "not slow" -q`. 커밋 전 전부 통과.
- Python 3.11, 타입힌트 필수, pydantic v2, `StrEnum`. 모든 `__init__.py`는 비운다(validator·hook이 torch/mlflow 없이 import되도록). 라이브러리 코드에 `print` 금지(스크립트만).
- 이름: `bona_fide`/`spoof`, `pai`(Presentation Attack Instrument). 라벨·점수 규약은 `src/pad_research/conventions.py` 한 곳(`LABEL_SPOOF = 1`, `score = P(spoof)`, `spoof if score >= tau`).
- 실험 로직에 dataset 이름 분기 금지(`if dataset == "replay"` ✗ → `load_protocol(cfg.protocol)`). 합성 여부도 이름이 아니라 `ManifestMeta.pii_policy`로 판정.
- 단위 변환은 한 곳: latency는 `evaluation/evaluator.py::measure_latency`(`ms = seconds * 1000.0`). 모델 추론 시간과 전체 시스템 latency를 구분해 기록(§32).
- Threshold는 `metrics/threshold.py::ThresholdPolicy.fit(table)`만 사용하고 `ScoreTable.role == "dev"`가 아니면 예외. test set에서 threshold를 고르는 코드를 만들지 않는다.
- Hydra config(`configs/**.yaml`): flow mapping 안에 `${...}` 보간 금지(block style로). 실험 spec은 `configs/exp/<name>.yaml`(`# @package _global_`, `defaults: - override /model: ...`). 모델별 학습 스크립트 복제 금지.
- 테스트 매핑: `src/pad_research/<pkg>/<mod>.py` ↔ `tests/unit/test_<mod>.py`(또는 `test_<pkg>_<mod>.py`), `protocols/` ↔ `tests/protocol/`, hooks ↔ `tests/hooks/test_<hook>.py`. 통합 테스트는 `tests/integration/`(`@pytest.mark.integration`), 30초 초과는 `@pytest.mark.slow`. 실수 기대값은 `pytest.approx(abs=1e-12)`.
- 테스트 격리: 패키지 경로는 `paths.py` 함수(`PAD_REPO_ROOT`, `PAD_REGISTRY_PATH`, `PAD_OUTPUT_ROOT`, `PAD_DATA_ROOT`, `MLFLOW_TRACKING_URI` env)로만 얻는다. 통합 테스트는 tmp repo root를 만들어 실제 registry/mlruns를 오염시키지 않는다.
- Hook 스크립트(`.claude/hooks/`)는 stdlib만, Python 3.8 문법, 예외는 fail-safe(ask/deny), 환경변수 분기 없음.
- 체크포인트는 `state_dict + JSON 메타`만 저장(`torch.load(weights_only=True)`로 로드 가능해야 함). 모델 shape 계약: `PADModel.forward(clip[B,T,3,H,W]) -> ModelOutput(logits[B], clip_embedding[B,D], frame_embeddings)`.
- 커밋 메시지·코드·docstring은 영어. 문서·ADR·리포트는 한국어(용어 영어 병기).
