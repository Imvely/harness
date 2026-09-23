---
name: adr
description: Records a decision as research/decisions/ADR-NNN-<slug>.md via the recording-adrs skill (contract §26 template, Korean, draft shown before writing, index updated).
disable-model-invocation: true
arguments: [slug]
argument-hint: "<kebab-slug>   e.g. threshold-fixed-on-source-dev"
allowed-tools: Bash(ls *) Bash(cat *) Bash(date *) Read Write Edit Grep Glob
---

# /adr $slug

Invoke the `recording-adrs` skill for the decision the user just described (or the most recent
decision in this conversation), with file name `ADR-NNN-$slug.md` where `NNN` = max existing
number in `research/decisions/` + 1.

- Show the complete draft (§26 headers: Status / Context / Decision / Alternatives Considered /
  Why / Risks / Evidence / Date) and wait for approval before writing.
- Write only the new file and the `research/decisions/README.md` index row.
- Evidence must be real run_ids / protocol_hash / claim_ids or explicitly "없음 — 설계 판단".
- Never modify an existing ADR; supersede it with a new one.
