# research/papers — 논문 인덱스와 리뷰

- `paper_index.yaml`: 계약서 §7의 핵심 논문 9편(이해 순서, 연도순 아님)과 Appendix C의 URL. 스키마는 `src/pad_research/research/claims.py`의 `PaperEntry`.
  - `code_status`는 초기값 `verify`. 구현 착수 시점에 공식 코드 공개 여부를 다시 확인해 `available` / `unavailable` / `partial`로 갱신한다(§7 주의, §53 Q1·Q2).
  - `review`는 `reviews/<paper_id>.md`가 작성되면 그 경로를 적는다.
- `reviews/`: `paper-researcher` 서브에이전트의 §23.1 「Paper Review」 템플릿 결과를 저장한다. 서브에이전트는 read-only이므로 파일 기록은 main agent가 한다.

수치가 포함된 주장은 여기가 아니라 `research/claims/claims.jsonl`에 기록하며, 원문 확인 전에는 `value: null`을 유지한다(§8.2).
