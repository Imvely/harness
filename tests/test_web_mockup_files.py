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


def test_safety_banner_is_actually_rendered() -> None:
    """The copy above has to reach the screen, not just exist in a file.

    ``WarningBanner`` carried the synthetic-data warning and the data-origin disclosure for
    weeks while never being imported, so the test above passed on a banner no user could see.
    A string check over source text cannot catch that; asserting the component is mounted can.
    """
    app = _read("src/App.tsx")
    assert "WarningBanner" in app, "WarningBanner is not imported into App"
    assert "<WarningBanner" in app, "WarningBanner is imported but never rendered"


def test_fabricated_rows_are_marked_in_the_ui() -> None:
    """``demoOnly`` must reach a component.

    Rows generated in the browser by the control lab get their metrics from a formula in
    ``mockDb.createMockRun``. They carry ``demoOnly: true``, but for a long time no component
    read that flag, so a fabricated APCER was indistinguishable from a measured one.
    """
    readers = [
        path
        for path in (WEB / "src" / "components").glob("*.tsx")
        if "demoOnly" in path.read_text(encoding="utf-8")
        or "isFabricatedRun" in path.read_text(encoding="utf-8")
    ]
    assert readers, "no component distinguishes fabricated rows from measured ones"


def test_metric_delta_polarity_is_shared() -> None:
    """One rule decides whether a delta is an improvement.

    ``CompareView`` knew that a falling AUC is bad while a falling APCER is good; ``DeltaChart``
    coloured by raw sign and therefore painted the same AUC delta the opposite colour. The rule
    now lives in utils and both read it from there.
    """
    utils = _read("src/utils.ts")
    assert "export function isWorseDelta" in utils
    for component in ("Charts.tsx", "CompareView.tsx"):
        source = _read(f"src/components/{component}")
        assert "isWorseDelta" in source, f"{component} does not use the shared polarity rule"
        assert 'metric === "auc" ?' not in source, f"{component} still has its own polarity copy"


def test_glossary_exists_and_reaches_the_screen() -> None:
    """Acronyms need somewhere to be looked up, inside the product.

    APCER, BPCER, tau, PAI and the three hashes were printed bare on every view with no
    expansion, tooltip or glossary anywhere in the repository. A reader meeting them for the
    first time could not learn what they meant without leaving the dashboard.
    """
    glossary = _read("src/glossary.ts")
    for term in ("APCER", "BPCER", "tau", "PAI", "protocol_hash", "research_claim_allowed"):
        assert f'"{term}"' in glossary, f"{term} has no glossary entry"
    # A definition alone is not a feature; it has to be mounted and openable.
    assert "GlossaryProvider" in _read("src/main.tsx")
    assert "<GlossaryPanel" in _read("src/App.tsx")
    assert "TermMark" in _read("src/components/RunsTable.tsx")


def test_claim_eligibility_is_shown_as_checks_not_field_names() -> None:
    """The drawer used to print ``researchClaimAllowed is false`` at the reader.

    The seven conditions were already computed per run; only the exporter's free text was
    rendered, so a field name stood in for "no synthetic dataset behind it" and the other six
    conditions were invisible.
    """
    drawer = _read("src/components/ExperimentDrawer.tsx")
    assert "claimCheckKeys" in drawer
    assert "claim-checklist" in drawer
    i18n = _read("src/i18n.ts")
    for key in (
        "fullMode",
        "researchClaimAllowed",
        "atLeastThreeSeeds",
        "enoughPaiSupport",
        "thresholdFromDev",
        "noSecurityRegression",
        "singleProtocolInExperiment",
    ):
        assert f"{key}:" in i18n, f"{key} has no human-readable label"


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
    # Seven, not six: `literature` (ResearchAtlasView) shipped without being listed here or in
    # the README, which is how the largest view in the app stayed undocumented.
    app = _read("src/App.tsx")
    required = [
        '"dashboard"',
        '"literature"',
        '"runs"',
        '"compare"',
        '"audit"',
        '"report"',
        '"control"',
        "AuditView",
        "ReportView",
        "ResearchAtlasView",
        "loadDashboardRuns",
    ]
    missing = [needle for needle in required if needle not in app]
    assert missing == []


def test_readme_documents_every_view() -> None:
    """A view that no document mentions is a view nobody can find."""
    readme = _read("README.md")
    for view in ("Dashboard", "Literature", "Runs", "Compare", "Audit", "Report", "Control"):
        assert view in readme, f"README does not mention the {view} view"


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
