"""Structural tests for the web dashboard mockup."""

from __future__ import annotations

import json
import re
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


def test_the_page_has_one_h1_and_a_skip_link() -> None:
    """Heading levels and keyboard order were both wrong in the same way.

    The only ``h1`` was the product name inside a button in the sidebar, so every view offered
    five to eight sibling ``h2``s under nothing, and a screen reader's outline was flat. The nav
    also had no ``aria-current`` and there was no way past seven nav items and a filter panel
    without tabbing through all of them on every view.
    """
    app = _read("src/App.tsx")
    header = _read("src/components/AppHeader.tsx")
    assert "<h1>" not in app, "the sidebar brand is an h1 again; the page's subject is the view"
    assert "<h1>{viewLabel(locale, view)}</h1>" in header
    assert 'href="#workspace"' in app and 'id="workspace"' in app, "no skip link target"
    assert 'aria-current={view === item ? "page" : undefined}' in app


def test_every_view_says_what_it_answers() -> None:
    """All seven views shared one subtitle that described the app, not the screen."""
    i18n = _read("src/i18n.ts")
    assert "viewPurposeMessages" in i18n
    for view in ("dashboard", "literature", "runs", "compare", "audit", "report", "control"):
        assert f"  {view}: {{" in i18n, f"{view} has no purpose line"
    # The two screens that compose a command have to say they do not run it.
    assert "실행하지 않습니다" in i18n
    assert "학습을 시작하지 않습니다" in i18n


def test_dashboard_headline_states_the_conditions_instead_of_claiming_safety() -> None:
    """§30: a passing gate is bounded by protocol, seeds and threshold policy.

    The slot this occupies used to hold copy about the product itself, in a heading larger than
    the page title. Now that it reports the gate, the wording matters: "no regression here" is
    not "safe", and an inconclusive verdict is not a pass.
    """
    dashboard = _read("src/components/Dashboard.tsx")
    assert "headlineState" in dashboard
    assert "protocol·이 시드·이 임계값 규칙" in dashboard
    assert "판정이 없는 것과 통과한 것은 다릅니다" in dashboard
    assert "안전합니다" not in dashboard, "the headline claims safety unconditionally"
    assert "hero-card" not in dashboard


def test_literature_view_is_split_and_its_graph_is_opt_in() -> None:
    """The biggest view was one 1,787-line file that opened on its hardest control.

    ``ResearchAtlasView.tsx`` held the view shell, a filter form, a pan-and-zoom SVG workbench, a
    minimap, a node inspector, an eight-column table, a seven-column matrix, a detail card and a
    reading queue — over half of every component in the app. The graph sat above the paper
    table, so the first thing a newcomer met was the most demanding thing on screen.
    """
    atlas = _read("src/components/ResearchAtlasView.tsx")
    assert (WEB / "src/components/literature/graphModel.ts").is_file()
    assert (WEB / "src/components/literature/LiteratureGraph.tsx").is_file()
    for path in (
        "src/components/ResearchAtlasView.tsx",
        "src/components/literature/LiteratureGraph.tsx",
        "src/components/literature/graphModel.ts",
    ):
        lines = len(_read(path).splitlines())
        assert lines < 800, f"{path} is {lines} lines; it was split to stay readable"
    # Collapsed *and* unmounted: a closed <details> still mounts its children, which would lay
    # out a graph nobody asked for, in a zero-height box.
    assert "useState(false)" in atlas
    assert "{graphOpen && (" in atlas
    assert "graphModel" in atlas, "the view no longer imports the extracted helpers"


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
    """Every chart names itself and every chart has a table behind it.

    This used to pin one literal attribute string. When the trend chart became two panels the
    attribute became a template and the test failed while the requirement was still met — so it
    was checking a spelling, not a property. It now counts: each ``<svg`` must carry
    ``aria-labelledby``, and each must have a ``<title>`` and ``<desc>`` to point at.
    """
    charts = _read("src/components/Charts.tsx")
    svg_count = charts.count("<svg")
    assert svg_count > 0
    assert charts.count("aria-labelledby=") == svg_count, "an svg is missing aria-labelledby"
    assert charts.count("<title id=") == svg_count
    assert charts.count("<desc id=") == svg_count
    for caption in (
        "Metric trend data",
        "Per-attack APCER data",
        "Seed variance data",
        "Metric delta data",
    ):
        assert caption in charts


def _token_blocks(css: str) -> tuple[str, str]:
    """Split the stylesheet into its token declarations and everything else.

    Comments are stripped from the second half: they explain *why* a colour changed and quote
    the old values, which is exactly the prose a scan for literals would trip over.
    """
    last_declaration = css.rindex(':root[data-theme="dark"]')
    end = css.index("\n}\n", last_declaration) + 3
    rules = re.sub(r"/\*.*?\*/", "", css[end:], flags=re.DOTALL)
    return css[:end], rules


def test_every_colour_in_the_stylesheet_is_a_token() -> None:
    """Dark mode is a second set of values, so a literal colour has no dark value to take.

    A hard-coded ``#ffffff`` renders white on a dark surface and nothing catches it: the build
    passes, the types pass, and it is only visible to someone who opens the page in dark mode.
    Ninety-six raw hex values and thirty rgba literals were removed to make this hold; the test
    is what keeps them out.
    """
    tokens, rules = _token_blocks(_read("src/styles.css"))
    assert "--series-1" in tokens and "prefers-color-scheme: dark" in tokens
    stray_hex = sorted(set(re.findall(r"#[0-9a-fA-F]{3,8}\b", rules)))
    assert stray_hex == [], f"literal colours outside the token blocks: {stray_hex}"
    stray_rgba = sorted(set(re.findall(r"rgba\([^)]*\)", rules)))
    assert stray_rgba == [], f"literal rgba outside the token blocks: {stray_rgba}"


def test_dark_mode_is_declared_for_both_the_system_and_the_viewer() -> None:
    """Either alone leaves a viewer stuck.

    The media query follows the operating system; the attribute follows an explicit choice. The
    ``:not([data-theme="light"])`` guard is what lets someone on a dark machine pick light and
    have it hold — without it the media query would keep winning.
    """
    tokens, _ = _token_blocks(_read("src/styles.css"))
    assert "@media (prefers-color-scheme: dark)" in tokens
    assert ':root:not([data-theme="light"])' in tokens
    assert ':root[data-theme="dark"]' in tokens

    app = _read("src/App.tsx")
    for choice in ('"light"', '"dark"', '"system"'):
        assert choice in app, f"the appearance control is missing {choice}"
    # Applied before first paint, or a viewer who chose light on a dark machine sees a flash.
    assert "pad-research-web-mockup-theme" in _read("index.html")


def test_the_banner_does_not_name_an_origin_it_does_not_yet_know() -> None:
    """While the export fetch is in flight the rows are the bundled samples and may be replaced.

    Asserting "sample data" in that window would put the wrong label on numbers that are a
    moment from being real measurements, and a reader who looked then would carry it away.
    """
    banner = _read("src/components/WarningBanner.tsx")
    assert "resolving" in banner
    assert "safety-banner--resolving" in banner
    app = _read("src/App.tsx")
    assert "aria-busy={resolvingOrigin}" in app


def test_hashes_are_reachable_in_full() -> None:
    """Twelve characters is not the hash.

    Every hash on screen was truncated with no way to reach the rest, so a reader who wanted to
    check that two runs really did share a protocol, or to paste one into
    ``summarize_experiment.py``, had to go dig it out of the registry. Twelve characters is also
    enough for two different hashes to look identical when they share a prefix — precisely the
    case the audit view exists to catch.
    """
    hash_value = _read("src/components/HashValue.tsx")
    assert "navigator.clipboard.writeText(value)" in hash_value
    # The full value is the accessible name too, so it is readable without copying at all.
    assert "title={value}" in hash_value
    # A denied clipboard must not render as success: a reader who believes they copied will
    # paste whatever was there before.
    assert "copy failed" in hash_value
    for view in ("ExperimentDrawer", "AuditView"):
        assert "HashValue" in _read(f"src/components/{view}.tsx"), f"{view} still truncates"


def test_the_exporter_sends_codes_not_display_prose() -> None:
    """A sentence on the wire is a sentence the dashboard cannot translate.

    The exporter emitted English for the two things the drawer shows a human: why a claim is
    blocked ("research claim is not allowed by run provenance") and what each artifact is
    ("Resolved spec"). The Korean-first UI printed both verbatim, because there was nothing else
    to print. The wire carries codes and paths now; the wording is chosen at render time.
    """
    schema = (REPO_ROOT / "src/pad_research/dashboard/schema.py").read_text(encoding="utf-8")
    export = (REPO_ROOT / "src/pad_research/dashboard/export.py").read_text(encoding="utf-8")
    assert "ClaimBlocker = Literal[" in schema
    assert "blockers: list[ClaimBlocker]" in schema
    assert "reasons" not in schema, "the prose field is back on the export contract"
    # The artifact table is (path, kind); a three-tuple means a label crept back in.
    assert "_SAFE_ARTIFACTS: tuple[tuple[str, str], ...]" in export

    # And the UI has a translation for every code it can receive.
    i18n = _read("src/i18n.ts")
    for blocker in re.findall(r'^\s+"(\w+)",$', schema.split("ClaimBlocker = Literal[")[1].split("]")[0], re.M):
        assert f"{blocker}: {{" in i18n, f"no translation for the {blocker} blocker"


def test_status_colours_are_never_used_as_series_colours() -> None:
    """A reserved status colour must not stand in for a series.

    The APCER trend line wore ``--danger`` and every per-PAI bar was filled with it, which told
    the reader that an APCER of 0.000 was alarming. Whether a number is alarming is the gate's
    verdict, and the row beside it already states that. A judgement colour (the compare view's
    better/worse fills, a status badge) is a different job and keeps them.
    """
    css = _read("src/styles.css")
    series_rules = re.findall(
        r"\.(?:line|dot|bar-fill|seed-bar|graph-node__circle|graph-legend__dot)[^{]*\{[^}]*\}",
        css,
    )
    assert series_rules, "no series mark rules found; the selectors moved"
    for rule in series_rules:
        for reserved in ("var(--danger)", "var(--success)", "var(--warning)", "var(--status-"):
            assert reserved not in rule, f"a status colour is doing series duty:\n{rule}"


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
