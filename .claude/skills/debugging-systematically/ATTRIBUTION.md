# Attribution — debugging-systematically

- Source URL: https://github.com/obra/superpowers/tree/b36e0829c6d0140e93cfef2ca599b1b07d4a7797/skills/systematic-debugging
- Repository: obra/superpowers
- Path: skills/systematic-debugging/ (SKILL.md, root-cause-tracing.md, defense-in-depth.md, condition-based-waiting.md)
- Commit SHA: b36e0829c6d0140e93cfef2ca599b1b07d4a7797
- License: MIT (full text below and in `LICENSE`)
- Fetched: 2026-09-17

## Modifications

- Renamed the skill directory to `debugging-systematically`; description rewritten in third person for this repo; `metadata` (origin, license, commit) added.
- Removed the two cross-references to other skills of the original plugin (test-driven-development, verification-before-completion) and replaced them with plain instructions / a reference to this repo's `verifying-before-completion` skill.
- Added "Phase 1b: ML Pipeline Checks (pad-research)" (seed/deterministic flags, dataloader order/drop_last, protocol_hash, manifest_hash, NaN/inf, batch_first, device, smoke vs full, threshold source, adaptation/test overlap, label convention).
- Dropped files not used by this repo: `CREATION-LOG.md`, `test-academic.md`, `test-pressure-1..3.md`, `condition-based-waiting-example.ts`, `find-polluter.sh`.
- `root-cause-tracing.md`: replaced the `find-polluter.sh` usage block with a pytest bisection instruction.
- `condition-based-waiting.md`: replaced the reference to the dropped `.ts` example with a Python polling note.

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
