# research/claims — 검증된 논문 주장(claim) 저장소

`claims.jsonl`은 논문/공식 코드/로컬 관측에서 얻은 **개별 주장(claim)** 을 한 줄에 하나씩(JSON Lines) 기록한다. 스키마와 검증 규칙은 `src/pad_research/research/claims.py`의 `Claim` 모델이 정의하며, 계약서(`docs/RESEARCH_CONTRACT.md`) §8 「논문 리서치 원칙」을 코드로 옮긴 것이다.

## 필드

| 필드 | 의미 |
|---|---|
| `claim_id` | 고유 ID (예: `ota_2025_oneclass_001`). 파일 내 중복 금지 |
| `claim` | 주장 한 문장 (영어) |
| `paper_id` | `research/papers/paper_index.yaml`의 `paper_id`. 로컬 관측이면 `"local"` |
| `source_type` | `primary_paper` / `official_code` / `secondary` / `local_observation` |
| `section`, `table`, `protocol` | 주장이 나온 위치·표·프로토콜. 아직 확인 전이면 `VERIFY_FROM_PDF` |
| `metric` | 수치가 가리키는 지표 (HTER, AUC, ACER …) |
| `value` | 수치. **검증 전에는 반드시 `null`** |
| `verified` | 원문 PDF/공식 페이지에서 직접 확인했는가 |
| `notes` | 자유 메모 (무엇을 아직 확인하지 못했는지 등) |
| `verified_by`, `verified_at` | 검증자·검증일 (선택) |

## 코드로 강제되는 규칙 (§8.1 / §8.2)

1. `value`가 `null`이 아니면 `verified == true`여야 하고, `source_type`은 `primary_paper` 또는 `local_observation`이어야 한다.
2. `source_type == "secondary"`(블로그, 다른 논문의 related-work 표, README, 검색 snippet)는 **절대 `verified: true`가 될 수 없다.** 원문을 확인했다면 `source_type`을 바꾼다.
3. `claim_id`는 파일 안에서 유일하다.
4. 알 수 없는 필드는 거부된다(`extra="forbid"`).

## 근거로 쓰지 않는 것 (§8.1)

- 검색 결과 snippet만 보고 성능 수치 확정
- ResearchGate 요약만 보고 세부 protocol 확정
- 다른 논문의 related work 표만 보고 원 논문의 수치 확정
- 블로그가 인용한 HTER/AUC를 원 논문 확인 없이 기록
- GitHub README만 보고 논문의 최종 성능 수치 확정

## 로컬 관측 (`local_observation`)

하네스 안에서 직접 돌린 결과에서 나온 관측은 `paper_id: "local"`로 기록한다. 이런 claim은 **해당 데이터 구성·구현·전처리·학습 조건**에 한정된 관측이며, 논문이나 방법 전체에 대한 결론으로 일반화하지 않는다(§3.1, ADR-002). 합성(synthetic) 데이터로 돌린 run은 sanity check일 뿐 연구 증거가 아니므로 claim으로 기록하지 않는다(ADR-005).

## 검증 방법

```bash
uv run --no-sync python -c "from pad_research.research.claims import validate_claims_file as v; print(v('research/claims/claims.jsonl') or 'OK')"
uv run --no-sync pytest tests/unit/test_claims.py -q
```

이 디렉터리는 `.claude/settings.json`에서 `ask` 보호 대상이다. 수정할 때는 어떤 원문에서 무엇을 확인했는지 `notes`/`verified_by`/`verified_at`에 남긴다.
