# 데이터 거버넌스 규칙 (data-governance)

전문 §6.1, §22, §34 참조. 얼굴 영상은 민감 biometric data다. 이 규칙은 데이터 파일을 만지지 않는 작업에도 항상 적용된다.

- **외부 업로드 금지**: public GitHub, 외부 클라우드(S3/GCS/Azure), Hugging Face, W&B, gist, 그리고 MCP 업로드 도구(`mcp__github__push_files`, `create_or_update_file`, Notion 첨부)와 `Artifact` 공개 페이지도 같은 정책이다(permissions.deny/ask). `git push`는 코드만, 데이터·checkpoint·mlruns는 gitignore 상태를 유지한다.
- **raw frame을 컨텍스트/로그/리포트에 넣지 않는다**: `data/raw/**`, `data/processed/**` 읽기는 ask(hook DG-13, `Read(...)` ask). 통계는 manifest와 스크립트로 계산한다. 리포트·이슈에 샘플 이미지를 넣지 않는다.
- 로그·리포트·MLflow에는 `dataset_id`, `manifest_hash`, `sample_id`만. 절대경로·사용자 경로를 남기지 않는다(spec/hash도 머신 독립).
- 데이터 경로: `PAD_DATA_ROOT` 환경변수 + manifest `relative_path`(dataset_id/…). manifest 생성은 `scripts/prepare_dataset.py --adapter <name>`만이 정식 경로이며 `data/manifests/**` 직접 편집은 ask.
- CelebA-Spoof처럼 image-only 데이터셋은 `temporal_valid: false`로 등록하고, frames>1 clip 입력으로 쓰려면 protocol의 `allow_image_dataset_as_clip: true`를 명시해야 한다(validator `IMAGE_DATASET_AS_CLIP`).
- Subject leakage 금지: 같은 subject가 train/dev/test에 동시에 있을 수 없고(validator `SUBJECT_OVERLAP_SPLITS`), adaptation sample은 test에서 제외된다(`ADAPT_TEST_*`).
- 원격 MLflow(`http(s)://`) tracking URI로 artifact(checkpoint, score csv)를 올리는 것은 외부 업로드로 간주해 hook이 ask한다(EXP-09).
- 라이선스·개인정보 정책·외부 저장 가능 여부는 데이터셋마다 `ManifestMeta.license`, `pii_policy`에 기록한다. `dvc push`/remote 설정은 정책 확인 후 사용자만.
- 실데이터 삭제(`rm -rf data/*`)는 deny. 정리는 사용자가 직접 한다.
