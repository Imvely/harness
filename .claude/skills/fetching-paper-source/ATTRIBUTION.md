# Attribution — fetching-paper-source

Two MIT sources were combined.

## Primary: K-Dense-AI/scientific-agent-skills (paper-lookup)

- Source URL: https://github.com/K-Dense-AI/scientific-agent-skills/tree/330c8e764435a731eff571e3efdda70b363d0792/skills/paper-lookup
- Repository: K-Dense-AI/scientific-agent-skills
- Path: skills/paper-lookup/ (SKILL.md; scripts/_common.py, arxiv_atom.py, jats_to_text.py, openalex_abstract.py, paginate.py; references/arxiv.md, semantic-scholar.md, openalex.md, crossref.md, unpaywall.md, core.md)
- Commit SHA: 330c8e764435a731eff571e3efdda70b363d0792
- License: MIT (full text below and in `LICENSE`; upstream file name `LICENSE.md`)
- Fetched: 2026-09-17

## Secondary: davila7/claude-code-templates (literature-review / verify_citations.py)

- Source URL: https://github.com/davila7/claude-code-templates/tree/d400d5d49415dc032e6cfff4716548a600e5b975/cli-tool/components/skills/scientific/literature-review
- Repository: davila7/claude-code-templates
- Path: cli-tool/components/skills/scientific/literature-review/scripts/verify_citations.py
- Commit SHA: d400d5d49415dc032e6cfff4716548a600e5b975
- License: MIT (full text below and in `LICENSE-davila7-verify-citations`)
- Fetched: 2026-09-17

## Modifications

- SKILL.md rewritten for this repo: kept the "APIs fail with HTTP 200" hazard framing, core workflow (define → select → read reference → bounded calls → untrusted data → auditable provenance), selection table, bundled-scripts table and provenance rules; reduced the 18-database guide to the six relevant to CS/biometrics (arXiv, Semantic Scholar, OpenAlex, Crossref, Unpaywall, CORE). Dropped the biomedical-only references (PubMed, PMC, Europe PMC, bioRxiv, medRxiv, PubTator3, BioStudies, DOAJ, Zenodo, Figshare, ROR, OpenCitations) and the "Citing Scientific Agent Skills" section.
- Added contract §8 evidence hierarchy and prohibitions (no snippets / ResearchGate / README / related-work numbers), the §23.1 Paper Review 16-header template written to `research/papers/reviews/<paper_id>.md`, the claims.jsonl row schema (§8.2) with `verified:false` / `value:null` default, protected-file rules, and the `pdf` skill route for non-arXiv PDFs.
- `scripts/*.py`: formatting-only changes so the files pass this repo's ruff configuration (PEP 585 annotations, `collections.abc` imports, import sorting, removed unused `noqa`, `raise … from error` in `paginate.py`). `_common.py` also had an unused variable and redundant open mode fixed by ruff. Behaviour unchanged.
- `verify_citations.py` (davila7): only the SKILL.md-independent script was taken (the literature-review SKILL.md, PDF generation, and schematic-generation parts were not vendored); ruff fixes applied (typing imports, unused loop variable). It depends on `requests`, which is available transitively via mlflow.
- `metadata` (origins, licenses, commits) added to the frontmatter; `allowed-tools` narrowed to curl, the bundled scripts, and read tools.

## License text — K-Dense-AI/scientific-agent-skills

```
MIT License

Copyright (c) 2025 K-Dense Inc.

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

## License text — davila7/claude-code-templates

```
MIT License

Copyright (c) 2025 Daniel (San) Ávila

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
