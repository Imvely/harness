"""Structural tests for the web dashboard mockup."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB = REPO_ROOT / "web-mockup"


def _read(rel: str) -> str:
    return (WEB / rel).read_text(encoding="utf-8")


def test_web_mockup_scaffold_exists() -> None:
    required = [
        "package.json",
        "index.html",
        "tsconfig.json",
        "vite.config.ts",
        "README.md",
        "src/App.tsx",
        "src/main.tsx",
        "src/styles.css",
        "src/types.ts",
        "src/data/demoRuns.ts",
        "src/data/dashboardLoader.ts",
        "src/components/Dashboard.tsx",
        "src/components/FilterPanel.tsx",
        "src/components/RunsTable.tsx",
        "src/components/CompareView.tsx",
        "src/components/AuditView.tsx",
        "src/components/ReportView.tsx",
        "src/components/ControlView.tsx",
    ]
    missing = [path for path in required if not (WEB / path).is_file()]
    assert missing == []


def test_web_mockup_package_is_vite_react() -> None:
    package = json.loads(_read("package.json"))
    deps = package["dependencies"]
    assert package["private"] is True
    assert "build" in package["scripts"]
    assert "vite" in deps
    assert "react" in deps
    assert "typescript" in deps
    assert "latest" not in json.dumps(deps)


def test_web_mockup_safety_copy_is_visible() -> None:
    combined = "\n".join(
        [
            _read("README.md"),
            _read("src/components/WarningBanner.tsx"),
            _read("src/components/ControlView.tsx"),
            _read("src/components/CompareView.tsx"),
            _read("src/data/demoRuns.ts"),
        ]
    )
    required = [
        "SYNTHETIC SANITY",
        "NOT A RESEARCH RESULT",
        "researchClaimAllowed: false",
        'piiPolicy: "synthetic"',
        "dev threshold only",
        "human full-run approval",
        "This UI does not launch training",
        "YAML patch preview",
        "mixed protocol",
    ]
    missing = [needle for needle in required if needle not in combined]
    assert missing == []


def test_web_mockup_does_not_embed_raw_media_or_approval_execution() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in (WEB / "src").rglob("*.tsx"))
    forbidden = [
        "data/raw",
        "approve_full_run.py",
        "rm -rf",
        "dvc push",
    ]
    present = [needle for needle in forbidden if needle in combined]
    assert present == []


def test_web_mockup_has_research_dashboard_views() -> None:
    app = _read("src/App.tsx")
    required = [
        '"dashboard"',
        '"runs"',
        '"compare"',
        '"audit"',
        '"report"',
        '"control"',
        "AuditView",
        "ReportView",
        "loadDashboardRuns",
    ]
    missing = [needle for needle in required if needle not in app]
    assert missing == []


def test_web_mockup_documents_dashboard_export_integration() -> None:
    combined = _read("README.md") + _read("src/data/dashboardLoader.ts")
    required = [
        "scripts/export_dashboard_data.py",
        "dashboard-demo.json",
        "loadDashboardRuns",
        'fetch("/dashboard-demo.json"',
    ]
    missing = [needle for needle in required if needle not in combined]
    assert missing == []


def test_runs_table_selection_is_keyboard_accessible() -> None:
    table = _read("src/components/RunsTable.tsx")
    assert "table-run-button" in table
    assert "<tr\n" in table
    assert "onClick={() => onSelectRun(run.runId)}" in table
    row_block = table.split("<tr", 1)[1]
    assert "onClick" not in row_block.split(">", 1)[0]


def test_charts_include_accessible_data_fallbacks() -> None:
    charts = _read("src/components/Charts.tsx")
    assert 'aria-labelledby="metric-trend-title metric-trend-desc"' in charts
    assert '<title id="metric-trend-title">' in charts
    assert '<desc id="metric-trend-desc">' in charts
    assert "Metric trend data" in charts
    assert "Per-attack APCER data" in charts
    assert "Seed variance data" in charts
    assert "Metric delta data" in charts


def test_web_command_preview_blocks_unsafe_copy_tokens() -> None:
    schema = _read("src/db/schema.ts")
    preview = _read("src/db/controlPreview.ts")
    control = _read("src/components/ControlView.tsx")

    assert "sourceRunId: z" in schema
    assert "Use a shell-safe run ID." in schema
    assert "protocolId: z" in schema
    assert "Use a protocol ID like syn_a_to_b_v1." in schema
    assert "ControlStateSchema.safeParse(control)" in preview
    assert "BLOCKED: fix validation errors before copying this command." in preview
    assert "cliToken(safe.sourceRunId)" in preview
    assert "disabled={!commandIsCopyable}" in control


def test_web_dashboard_schema_matches_python_export_unknown_states() -> None:
    types = _read("src/types.ts")
    schema = _read("src/db/schema.ts")
    loader = _read("src/data/dashboardLoader.ts")

    assert '| "unknown";' in types
    assert '| "no_gate"' in types
    assert '"no_gate"' in schema
    assert '"unknown"' in schema
    assert 'const runModes: RunMode[] = ["smoke", "full", "unknown"]' in loader
    assert '"no_gate",' in loader
    assert 'enumValue(raw.gate_verdict, gateVerdicts, "unknown")' in loader
    assert 'enumValue(raw.mode, runModes, "unknown")' in loader


def test_web_blocks_protocol_mismatch_deltas_and_stale_seed_rows() -> None:
    compare = _read("src/components/CompareView.tsx")
    report = _read("src/components/ReportView.tsx")
    db = _read("src/db/mockDb.ts")

    assert "Delta values blocked" in compare
    assert "comparable ? (" in compare
    assert "<DeltaTable baseline={baseline} method={method} locale={locale} />" in compare
    assert "<DeltaChart baseline={baseline} method={method} locale={locale} />" in compare
    assert '["pass", "no_gate"].includes(run.gateVerdict)' in compare
    assert "Report metrics blocked" in report
    assert "reportReadiness" in report
    assert "protocol hashes differ" in report
    assert "seedFingerprint" in db
    assert "Seed dataset changed; persisted browser mock DB was reset" in db
