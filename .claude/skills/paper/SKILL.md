---
name: paper
description: Runs the paper-researcher subagent on a reference (arXiv id, DOI, URL, title, or paper_id) using the fetching-paper-source skill and returns the contract §23.1 Paper Review text plus proposed claims rows. The subagent writes nothing; the main agent writes research/papers/reviews/<paper_id>.md and proposes claims edits, because research/claims is protected.
disable-model-invocation: true
arguments: [reference]
argument-hint: "<arXiv id | DOI | URL | title | paper_id>"
context: fork
agent: paper-researcher
background: false
disallowed-tools: [Write, Edit, NotebookEdit]
---

# /paper $reference

Apply the `fetching-paper-source` skill to `$reference` end to end and **return text only**.

## What to return

1. `paper_id` proposal (`<firstauthor><year><keyword>`, e.g. `li2025ota`) — check
   `research/papers/paper_index.yaml` and `research/papers/reviews/` for an existing id first and
   reuse it.
2. The full `# Paper Review` (§23.1, all 16 headers in order) ready to be saved as
   `research/papers/reviews/<paper_id>.md`.
3. Proposed `claims.jsonl` rows (§8.2 schema) — `verified:false`, `value:null` unless the number
   was read from the primary PDF table; then `table`/`protocol` name the exact table.
4. Provenance: endpoints + parameters, PDF URL and version read, official code repo + commit or
   "none found", access date, and anything that returned empty.
5. Relevance: which RQ this paper informs, ideas tagged [Established]/[Adaptation]/[Hypothesis].

## Rules

- Primary PDF first; abstract/snippet/README/related-work numbers are never evidence (§8).
- Do not write any file, modify code, or run training; you are read-only in this fork.
- If the paper cannot be located or the PDF cannot be read, return what was found, mark every
  number `VERIFY_FROM_PDF`, and say exactly which step failed.
- Unverified numbers stay `null`. Say "unknown", never guess.
