from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "validate_protocol.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, cwd=ROOT, check=False
    )


@pytest.mark.integration
def test_validate_protocol_cli_exit_codes(tmp_path: Path) -> None:
    ok = _run("--protocol", "syn_a_to_b_v1", "--json")
    assert ok.returncode == 0, ok.stderr
    payload = json.loads(ok.stdout)
    assert payload["ok"] is True and payload["protocol_id"] == "syn_a_to_b_v1"

    bad = tmp_path / "bad_v1.yaml"
    bad.write_text("protocol_id: bad_v1\nsource_datasets: []\n")
    assert _run("--path", str(bad)).returncode == 2

    missing = _run("--protocol", "syn_a_to_b_v1", "--manifests-dir", str(tmp_path))
    assert missing.returncode == 3 and "MISSING_MANIFEST" in missing.stdout

    schema_only = _run("--protocol", "ocim_target_i_v1", "--schema-only")
    assert schema_only.returncode == 0


@pytest.mark.integration
def test_materialize_writes_adaptation_file(tmp_path: Path) -> None:
    import shutil

    mdir = tmp_path / "manifests"
    shutil.copytree(ROOT / "data" / "manifests", mdir, ignore=shutil.ignore_patterns("adaptation"))
    r = _run("--protocol", "syn_a_to_b_bf_adapt_v1", "--manifests-dir", str(mdir), "--materialize")
    assert r.returncode == 0, r.stderr + r.stdout
    files = list((mdir / "adaptation").glob("syn_a_to_b_bf_adapt_v1.*.jsonl"))
    assert len(files) == 1 and len(files[0].read_text().splitlines()) == 24
