#!/usr/bin/env python
"""Validate a protocol YAML against the dataset manifests (contract §15).

Exit codes: 0 ok, 2 schema error (YAML / pydantic), 3 validation errors, 5 internal.
Never imports torch or mlflow.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from pad_research import paths
from pad_research.data.manifest import load_manifest
from pad_research.protocols.adaptation_set import materialize_adaptation_set, select_adaptation_set
from pad_research.protocols.hashing import protocol_hash
from pad_research.protocols.loader import ProtocolNotFoundError, load_protocol
from pad_research.protocols.validator import ProtocolValidation, validate_protocol
from pad_research.utils.redaction import redact_text


def _parse() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--protocol", help="protocol name under configs/protocol/")
    g.add_argument("--path", help="explicit protocol YAML path")
    ap.add_argument("--manifests-dir", type=Path, default=None)
    ap.add_argument("--frames", type=int, default=1)
    ap.add_argument("--schema-only", action="store_true", help="skip manifest checks")
    ap.add_argument("--materialize", action="store_true", help="write the adaptation set file")
    ap.add_argument("--json", action="store_true")
    return ap.parse_args()


def main() -> int:
    args = _parse()
    manifests_dir = args.manifests_dir or paths.manifests_dir()
    try:
        spec = load_protocol(args.protocol or args.path)
    except ProtocolNotFoundError as exc:
        print(f"error: {redact_text(exc, paths.repo_root())}", file=sys.stderr)
        return 2
    except (ValidationError, ValueError) as exc:
        print(f"schema error: {redact_text(exc, paths.repo_root())}", file=sys.stderr)
        return 2
    if args.schema_only:
        result = ProtocolValidation(
            protocol_id=spec.protocol_id,
            protocol_hash=protocol_hash(spec),
            status=spec.status,
            manifest_hashes={},
            adaptation_set_hash=None,
            research_claim_allowed=True,
            issues=[],
        )
    else:
        result = validate_protocol(spec, manifests_dir, frames=args.frames)
    materialized: Path | None = None
    if args.materialize and result.ok and spec.target_adaptation.enabled:
        target = load_manifest(spec.target_dataset[0], manifests_dir)
        sel = select_adaptation_set(spec, target)
        materialized = materialize_adaptation_set(sel, manifests_dir / "adaptation", target)
    if args.json:
        payload = result.model_dump()
        for issue in payload.get("issues", []):
            if isinstance(issue, dict) and "message" in issue:
                issue["message"] = redact_text(issue["message"], paths.repo_root())
        payload["ok"] = result.ok
        payload["errors"] = [i.code for i in result.errors()]
        payload["warnings"] = [i.code for i in result.warnings()]
        payload["materialized_path"] = materialized.name if materialized else None
        print(json.dumps(payload, ensure_ascii=False, indent=1))
    else:
        print(
            f"protocol_id={result.protocol_id} hash={result.protocol_hash} status={result.status} "
            f"ok={result.ok} errors={len(result.errors())} warnings={len(result.warnings())}"
        )
        for issue in result.issues:
            print(
                f"  [{issue.severity}] {issue.code}: "
                f"{redact_text(issue.message, paths.repo_root())}"
            )
        if materialized:
            print(f"  materialized: {materialized.name}")
    return 0 if result.ok else 3


if __name__ == "__main__":
    sys.exit(main())
