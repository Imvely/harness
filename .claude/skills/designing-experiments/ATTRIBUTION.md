# Attribution — designing-experiments

- Source URL: https://github.com/obra/superpowers/tree/b36e0829c6d0140e93cfef2ca599b1b07d4a7797/skills/brainstorming
- Repository: obra/superpowers
- Path: skills/brainstorming/SKILL.md
- Commit SHA: b36e0829c6d0140e93cfef2ca599b1b07d4a7797
- License: MIT (full text below and in `LICENSE`)
- Fetched: 2026-09-17

## Modifications

- Rewritten for research-experiment design: the hard approval gate, the "classify the path out loud", one-question-at-a-time dialogue, 2–3 approaches with a recommendation, YAGNI, and the red-flag table are kept in spirit; the software spec / writing-plans flow is replaced.
- Paths renamed Spike/Bounded/Architectural → Question/Ablation/Method.
- Output target changed from `docs/superpowers/specs/*.md` to `research/hypotheses/<id>.md`, followed by `/new-exp` for `configs/exp/<name>.yaml`.
- Added contract §11 order enforcement (baseline → observed failure mode → minimal hypothesis → minimal ablation; never implement Proposed first), §46 idea tagging ([Established]/[Adaptation]/[Hypothesis]), §14.2/§14.3 per-attack prediction requirement, §15.1 protocol_hash comparison rule.
- Dropped the browser "visual companion" and its `scripts/` (server.cjs, helper.js, frame-template.html, start/stop-server.sh), `visual-companion.md`, and `spec-document-reviewer-prompt.md`.
- Added `metadata` (origin, license, commit) to the frontmatter.

## License text

```
MIT License

Copyright (c) 2025 Jesse Vincent

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
