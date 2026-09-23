# 데이터셋 manifest

이 디렉터리는 **커밋되는** 데이터셋 manifest를 담는다. manifest는 실제 미디어(얼굴 영상)를
포함하지 않으며, 미디어는 `PAD_DATA_ROOT`(또는 meta의 `root_env_var`)가 가리키는 로컬 경로에만
존재한다(연구 계약 §22, §34). `data/manifests/adaptation/`은 프로토콜별 adaptation set이 실체화되는
곳으로 커밋되지 않는다.

## 파일 구성

| 파일 | 내용 |
| --- | --- |
| `<dataset_id>.jsonl` | 샘플 1개 = 1줄. `sample_id` 오름차순 정렬, 각 줄은 canonical JSON(정렬된 키, 공백 없음, ASCII). |
| `<dataset_id>.meta.json` | `ManifestMeta` 사이드카. `manifest_hash`, 분할/PAI 집계, 생성 정보. |

`manifest_hash = sha256("\n".join(canonical_json(record) for record in sorted(records, key=sample_id)))`.
레코드에는 **상대 경로만** 들어가므로 해시는 머신에 독립적이며, 모든 run의 provenance에 그대로 기록된다(§17).
`load_manifest()`는 로드 시 해시를 다시 계산해 `.meta.json`과 다르면 `ManifestTamperedError`를 던진다.

## 레코드 스키마 (`pad_research.data.manifest.ManifestRecord`)

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `dataset_id` | str | `^[a-z0-9_]+$`. 입력은 소문자로 정규화된다(`REPLAY_ATTACK` → `replay_attack`). |
| `sample_id` | str | `^[A-Za-z0-9_\-.]+$`, 데이터셋 내 유일. |
| `subject_id` | str | 피험자 식별자. **같은 subject가 두 split에 있으면 안 된다**(subject leakage, §6.1). 합성 데이터는 `subj0000` 형식이며 synthetic_b는 1000 offset을 써 a/b가 겹치지 않는다. |
| `split` | `train` / `dev` / `test` | adaptation set은 split이 아니라 프로토콜이 선택한다. |
| `label` | `bona_fide` / `spoof` | |
| `pai` | `none`, `print`, `replay`, `replay_phone`, `replay_tablet`, `replay_display`, `display`, `mask_3d`, `other` | `label == bona_fide` ⇔ `pai == none` (모델 validator가 강제). |
| `pai_detail` | str \| null | 자유 형식 세부 정보(예: `"ipad_pro_2020"`). |
| `relative_path` | str | 데이터 루트 기준 POSIX 상대 경로. 절대 경로, 드라이브 문자, `..`, 역슬래시 거부. |
| `media_type` | `video` / `frames_dir` / `image` / `npy_clip` | 확장자가 타입과 맞아야 한다(`npy_clip` → `.npy`). |
| `fps`, `n_frames`, `width`, `height` | 선택 | 클립 메타. |
| `capture_device`, `session`, `environment`, `official_protocol` | 선택 | 도메인 분석/공식 프로토콜 매핑용. |
| `extra` | dict[str, str\|int\|float\|bool] | 어댑터별 부가 정보(중첩 불가). |

추가 필드는 거부(`extra="forbid"`)되고 레코드는 불변(frozen)이다.

## 메타 스키마 (`ManifestMeta`)

`dataset_id`, `version`, `adapter`, `license`, `pii_policy`(`synthetic` | `internal_only` | `licensed_research`),
`root_env_var`(기본 `PAD_DATA_ROOT`), `temporal_valid`(단일 이미지를 반복한 가짜 클립이면 `false`, §6.1 CelebA-Spoof 주의),
`manifest_hash`, `n_records`, `n_subjects`, `splits`(split별 `n_records / n_subjects / n_bona_fide / n_attack`),
`pai_counts`, `created_at`(UTC ISO), `generator_commit`.
`pii_policy == "synthetic"`이면 `research_grade == False`이며 그 결과는 연구 주장의 근거가 될 수 없다.

## manifest 만들기

```bash
# 합성 데이터 (미디어는 data/processed/<dataset_id>/*.npy 로 생성, gitignore 대상)
PAD_DATA_ROOT=$PWD/data/processed uv run --no-sync python scripts/prepare_dataset.py \
    --adapter synthetic --dataset-id synthetic_a --dataset-id synthetic_b
```

옵션: `--root PATH`(기본 `$PAD_DATA_ROOT`, 없으면 `<repo>/data/processed`), `--manifests-dir PATH`(기본 이 디렉터리).
출력은 데이터셋마다 한 줄 `dataset_id=<id> n_records=<n> manifest_hash=<hash>`.
스크립트는 **멱등**이다: 같은 커밋에서 두 번 실행하면 `.jsonl`, `.meta.json`, `.npy` 모두 바이트 동일하다
(내용 해시가 같으면 기존 `created_at`을 유지한다). manifest 변경은 반드시 이 스크립트로 다시 생성해서 커밋한다 —
손으로 고치면 `ManifestTamperedError`로 로드가 실패한다.

## Phase 1: 실제 데이터셋 어댑터 작성법

1. `src/pad_research/data/adapters/<name>.py`에 `DatasetAdapter`를 상속한다.
   - 클래스 속성: `adapter_name`, `version`(데이터셋 배포 버전/프로토콜 버전), `license`, `pii_policy`
     (`internal_only` 또는 `licensed_research`), `temporal_valid`.
   - `build(self, root: Path) -> list[ManifestRecord]`: `root` 아래의 **원본 위치를 읽기만** 하고
     상대 경로를 기록한다. 얼굴 데이터를 복사/변환해 다른 곳에 쓰지 않는다(§34).
   - 공식 프로토콜의 train/dev/test 분할을 그대로 `split`에 매핑하고 `official_protocol`에 이름을 남긴다.
     공식 분할이 없으면 subject 단위로만 나눈다 — 프레임/클립 단위 무작위 분할 금지.
   - `pai`는 위 enum 중 가장 구체적인 값으로 매핑하고 원문 명칭은 `pai_detail`에 보존한다.
2. `data/adapters/base.py`의 `ADAPTERS`에 팩토리를 등록한다(예: `"replay_attack": _make_replay_attack`).
   base 모듈은 무거운 의존성을 import하면 안 되므로 팩토리 안에서 lazy import한다.
3. `PAD_DATA_ROOT=/path/to/root uv run --no-sync python scripts/prepare_dataset.py --adapter <name> --dataset-id <id>`
   로 manifest를 생성한다. `write_manifest()`가 `validate_records()`를 호출해 중복 `sample_id`, subject leakage,
   label/pai 불일치, 확장자 불일치를 거부한다.
4. `tests/unit/`에 어댑터 테스트를 추가한다: 작은 가짜 디렉터리 트리를 `tmp_path`에 만들고
   레코드 수, split별 subject 분리, PAI 매핑, `validate_records() == []`을 확인한다.
5. 프로토콜 spec의 `source_datasets` / `target_dataset`에 `dataset_id`를 넣고
   `scripts/validate_protocol.py`로 검증한 뒤 manifest 두 파일을 커밋한다.

실험 로직에서 `dataset_id`를 하드코딩하지 않는다(§27.3). 데이터셋별 특이사항은 어댑터와 manifest에만 존재해야 한다.
