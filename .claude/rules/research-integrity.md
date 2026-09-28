# 연구 무결성 규칙 (research-integrity)

전문 §8, §14, §15, §30, §31, §41, §46 참조. 이 파일은 전문을 재복사하지 않고 **운영 델타**만 담는다.

## 우선순위와 편차
- `docs/RESEARCH_CONTRACT.md`가 헌법. 저장소 구조·이름의 편차는 `research/decisions/ADR-005`가 우선한다.
- 전문 §25/§38과 실제 구조 편차표:

| 전문 | 실제 | 이유 |
|---|---|---|
| `scripts/prepare_dataset.py`, `make_synthetic_data.py`, `build_manifest.py` | `scripts/prepare_dataset.py --adapter <name>` 하나 | 단일 진입점 |
| `configs/dataset/` | `configs/data/` | Hydra 그룹명 |
| `model.frames` (§20) | `model.input.frames` (§16 형태) | §16이 정본 |
| `experiments/specs/` 손편집 spec | `configs/exp/<name>.yaml`이 spec, `experiments/specs/*.resolved.yaml`은 `validate_spec --freeze` 산출물 | 이중 진실 방지 |
| `train_g2v2_8frame.py` 류 | 절대 만들지 않음 | §20 |

- 계약서 전문을 승인 하에 개정하면 `conventions.CONTRACT_SHA256`과 `tests/unit/test_research_store.py`의 pin, 그리고 ADR을 함께 갱신한다.

## 비교 가능성
- `protocol_hash`가 같을 때만 metric을 직접 비교한다. 다르면 `summarize_experiment.py --justify "<이유>"`가 필요하고 리포트 상단에 `NOT DIRECTLY COMPARABLE` 배너가 붙는다.
- `adaptation.method: none`은 해당 protocol의 control arm이다. Source-only baseline은 DA 실험과 **같은 protocol**(같은 adaptation 예산·같은 test 제외 규칙) 아래에서 돌려 hash를 공유한다.
- 합성 데이터 run(`research_claim_allowed=false` 태그)은 연구 주장에 쓰지 않는다. 리포트에 자동 배너가 붙는다.

## 표현 규칙
- §30: 결과 문장에는 dataset, protocol, seed, metric, threshold policy를 포함한다. "성공했다"는 `research-reviewer` 리뷰 전에는 쓰지 않는다.
- §46: 아이디어는 `[Established]` / `[Adaptation]` / `[Hypothesis]`로 표시하고 섞지 않는다.
- §8.1: 검색 snippet, ResearchGate 요약, 블로그, GitHub README, 다른 논문의 related-work 표로 수치를 확정하지 않는다. `claims.jsonl`의 `value`는 primary PDF 표에서 읽기 전까지 `null`.

## 위임 정책
- 논문 질문 → `paper-researcher`(병렬 2개 이하). 비-arXiv PDF는 main agent가 `research/papers/pdf/<paper_id>.pdf`(gitignore)로 받아 경로를 넘긴다.
- 파일 3개 이상 신규 구현 → `experiment-engineer`.
- full run 결과 해석 전 → `research-reviewer`(`/review-run`). 리뷰 verdict가 `SECURITY_REGRESSION`/`REJECT`면 결론 문장을 쓰지 않는다.
- 파일 기록(`research/claims/**`, `research/papers/reviews/**`)은 main agent가 한다(서브에이전트는 read-only).
