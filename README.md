# pad-research — Passive Video PAD + Domain Adaptation Research Harness

Phase 0 harness MVP (work in progress). **Start here: `docs/HANDOFF_CODEX.md`** — status, how to run,
what remains and the rules to follow. Design documents live in `docs/design/`; the research
contract is `docs/RESEARCH_CONTRACT.md`; the condensed operating summary is `CLAUDE.md`.

```bash
uv sync && export PAD_DATA_ROOT=$PWD/data/processed
uv run --no-sync python scripts/prepare_dataset.py --adapter synthetic --dataset-id synthetic_a --dataset-id synthetic_b
uv run --no-sync pytest -q -m "not slow"
```
