# Attribution — handoff

Two MIT sources were combined.

## Primary: REMvisual/claude-handoff

- Source URL: https://github.com/REMvisual/claude-handoff/tree/c407845e4c571f355b48901828f9cb0ad82272ec
- Repository: REMvisual/claude-handoff
- Path: skills/handoff/SKILL.md, skills/handoff/references/output-template.md, skills/handoff/references/validation.md
- Commit SHA: c407845e4c571f355b48901828f9cb0ad82272ec
- License: MIT (full text below and in `LICENSE`)
- Fetched: 2026-09-17

## Secondary: pedrohcgs/claude-code-my-workflow (checkpoint)

- Source URL: https://github.com/pedrohcgs/claude-code-my-workflow/tree/9d371f0bf8a8bc99569feca3210ef5133af28d33/.claude/skills
- Repository: pedrohcgs/claude-code-my-workflow
- Path: .claude/skills/checkpoint/SKILL.md
- Commit SHA: 9d371f0bf8a8bc99569feca3210ef5133af28d33
- License: MIT (full text below and in `LICENSE-pedrohcgs-checkpoint`)
- Fetched: 2026-09-17

## Modifications

- From REMvisual/claude-handoff kept: guards, "gather external state with cheap Bash, never agents", conversation-mining checklist, chronological "What we tried" with failures, evidence-with-real-numbers rule, user-feedback section, self-validation checklist, report step. Dropped: beads/epic chain tracking, chain tags and seq numbers, mining-deep-chunked map-reduce, multi-file splitting, 150–800 line targets (replaced by a ≤120-line cap), hooks/precompact-handoff.sh, handoffplan skill, close-session flow, bd memory writes.
- From pedrohcgs checkpoint kept: "In flight" table (what is running / artifacts / check with / ends when), "Next 1–3 actions", "Open questions" numbering, "Resume/Quick-start" block, propose-then-apply idea for memory (moved to `/end-day` as [LEARN] lines). Dropped: quality_reports paths, MEMORY.md writes, plan-file coupling.
- Output relocated to `research/handoffs/YYYY-MM-DD.md` + copy to `research/handoffs/LATEST.md`; Evidence table keyed by experiment_id / run_id / protocol_hash; data-governance rule (§34: logical dataset_id only, no frames/paths) and §8/§30 wording rule added.
- Frontmatter rewritten to the current skill format (`argument-hint`, `allowed-tools`, `metadata` with origins, licenses, commits).

## License text — REMvisual/claude-handoff

```
MIT License

Copyright (c) 2026 REMvisual

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## License text — pedrohcgs/claude-code-my-workflow

```
MIT License

Copyright (c) 2026 Pedro H. C. Sant'Anna

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
