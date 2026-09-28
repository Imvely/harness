# Attribution — recording-adrs

- Source URL: https://github.com/affaan-m/ECC/tree/dd6ee538aee0f548d4a6b520118f875431fd749e/skills/architecture-decision-records
- Repository: affaan-m/ECC
- Path: skills/architecture-decision-records/SKILL.md
- Commit SHA: dd6ee538aee0f548d4a6b520118f875431fd749e
- License: MIT (full text below and in `LICENSE`)
- Fetched: 2026-09-17

## Modifications

- Rewritten in Korean; directory renamed to `recording-adrs`; description rewritten in third person for this repo; `metadata` (origin, license, commit) added.
- ADR template replaced by the research contract §26 template exactly (Status / Context / Decision / Alternatives Considered / Why / Risks / Evidence / Date) instead of the Nygard-style template with Consequences.
- Location changed from `docs/adr/NNNN-title.md` to `research/decisions/ADR-NNN-slug.md`; index at `research/decisions/README.md`; no `template.md` is generated.
- Kept: draft-before-write with explicit approval, index update, "read existing ADRs" flow, detection signals, what-is-worth-recording table (re-targeted to research decisions), lifecycle via Superseded.
- Added: Evidence rules (run_id / protocol_hash / seed / per-attack metrics or verified claim_id; §30 wording), data-governance prohibition (§34), protection of existing ADR files.
- Dropped: planner/code-reviewer agent integration notes.

## License text

```
MIT License

Copyright (c) 2026 Affaan Mustafa

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
