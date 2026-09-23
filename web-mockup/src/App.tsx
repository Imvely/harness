import { useCallback, useEffect, useMemo, useState } from "react";
import { defaultBaselineId, defaultMethodId, demoRuns } from "./data/demoRuns";
import { loadDashboardRuns } from "./data/dashboardLoader";
import { AppHeader } from "./components/AppHeader";
import { CompareView, defaultComparisonPair } from "./components/CompareView";
import { ControlView, initialControl } from "./components/ControlView";
import { Dashboard } from "./components/Dashboard";
import { FilterPanel, activeFilterCount, filterRuns } from "./components/FilterPanel";
import { GlossaryButton, GlossaryPanel } from "./components/Glossary";
import { SidePanel } from "./components/SidePanel";
import { ExperimentDrawer } from "./components/ExperimentDrawer";
import { AuditView } from "./components/AuditView";
import { MockDbPanel } from "./components/MockDbPanel";
import { Onboarding, hasSeenGuide, markGuideSeen } from "./components/Onboarding";
import { ResearchAtlasView } from "./components/ResearchAtlasView";
import { StorageView, initialStorage } from "./components/StorageView";
import { ReportView } from "./components/ReportView";
import { RunsTable } from "./components/RunsTable";
import { WarningBanner, dataOrigin } from "./components/WarningBanner";
import {
  addReadingNote,
  createInitialMockDatabase,
  linkPaperToExperiment,
  loadMockDatabase,
  queuePaperForReading,
  recordUiAudit,
  resetMockDatabase,
  saveExperimentDraft,
  updatePaperStatus,
  writeMockDatabase,
} from "./db/mockDb";
import { t, viewLabel } from "./i18n";
import { applyTheme, readTheme } from "./theme";
import type { ThemeChoice } from "./theme";
import type {
  DemoRun,
  Filters,
  Locale,
  MockDatabaseLoadResult,
  MockDatabaseState,
  MockDbSeedSource,
  PaperExperimentLink,
  PaperStatus,
  StorageDraft,
} from "./types";

type View =
  | "dashboard"
  | "literature"
  | "runs"
  | "compare"
  | "audit"
  | "report"
  | "storage"
  | "control";

/**
 * Views whose content is computed from `filteredRuns`.
 *
 * The others deliberately read the full run list: Literature has its own filter set, Compare
 * scopes by baseline/method plus its own policy switches, and Control lists every run as a
 * possible adaptation source. Keeping the set here means the sidebar can say so instead of
 * appearing to do nothing.
 */
const FILTERED_VIEWS = new Set<View>(["dashboard", "runs", "audit", "report"]);

const initialFilters: Filters = {
  query: "",
  status: "all",
  mode: "all",
  modelFamily: "all",
  adaptationMethod: "all",
  protocolId: "all",
  gateVerdict: "all",
  seed: "all",
  includeSmoke: true,
  // Off by default: on a real export every run is internal_only or licensed_research, and a
  // default-on synthetic filter rendered an empty dashboard with no hint why. Synthetic runs
  // are already marked by the banner, so showing everything is the honest default.
  syntheticOnly: false,
  maxApcer: 0.5,
  minAuc: 0,
};

const localeStorageKey = "pad-research-web-mockup-locale";

function App() {
  const [view, setView] = useState<View>("dashboard");
  const [locale, setLocale] = useState<Locale>(() => readInitialLocale());
  const [database, setDatabase] = useState<MockDatabaseState>(() => createInitialMockDatabase(demoRuns, "demo"));
  const [seedRuns, setSeedRuns] = useState<DemoRun[]>(demoRuns);
  const [seedSource, setSeedSource] = useState<MockDbSeedSource>("demo");
  const [loadResult, setLoadResult] = useState<Pick<MockDatabaseLoadResult, "origin" | "resetReason">>({
    origin: "seeded",
    resetReason: null,
  });
  const [filters, setFilters] = useState<Filters>(initialFilters);
  const [storage, setStorage] = useState<StorageDraft>(initialStorage);
  const [selectedRunId, setSelectedRunId] = useState<string>(demoRuns[0]?.runId ?? "");
  const [selectedPaperId, setSelectedPaperId] = useState<string>("");
  const [baselineId, setBaselineId] = useState(defaultBaselineId);
  const [methodId, setMethodId] = useState(defaultMethodId);
  const [control, setControl] = useState(initialControl);
  const [showGuide, setShowGuide] = useState(() => !hasSeenGuide());
  const [theme, setTheme] = useState<ThemeChoice>(() => readTheme());
  // True until the export fetch settles. Until then the rows on screen are the bundled demo
  // rows, and they may be replaced — the banner says so rather than asserting an origin it
  // does not yet know.
  const [resolvingOrigin, setResolvingOrigin] = useState(true);

  useEffect(() => {
    document.documentElement.lang = locale;
    window.localStorage.setItem(localeStorageKey, locale);
  }, [locale]);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  useEffect(() => {
    let mounted = true;
    void loadDashboardRuns().then((loadedRuns) => {
      if (!mounted) return;
      const nextSeedRuns = loadedRuns ?? demoRuns;
      const nextSeedSource: MockDbSeedSource = loadedRuns === null ? "demo" : "export";
      const nextLoad = loadMockDatabase(nextSeedRuns, nextSeedSource);
      setSeedRuns(nextSeedRuns);
      setSeedSource(nextSeedSource);
      setDatabase(nextLoad.state);
      setLoadResult({ origin: nextLoad.origin, resetReason: nextLoad.resetReason });
      setSelectedRunId(nextLoad.state.runs[0]?.runId ?? "");
      setSelectedPaperId(nextLoad.state.literature.papers[0]?.paperId ?? "");
      // A pair that actually compares, when the data has one; otherwise the first two rows.
      const pair = defaultComparisonPair(nextLoad.state.runs);
      setBaselineId(pair?.baseline ?? nextLoad.state.runs[0]?.experimentId ?? defaultBaselineId);
      setMethodId(
        pair?.method ?? nextLoad.state.runs[1]?.experimentId ?? nextLoad.state.runs[0]?.experimentId ?? defaultMethodId,
      );
      setResolvingOrigin(false);
    });
    return () => {
      mounted = false;
    };
  }, []);

  const runs = database.runs;
  const filteredRuns = useMemo(() => filterRuns(runs, filters), [filters, runs]);
  // May be undefined when the database is empty; every consumer handles that rather than
  // dereferencing it (an empty database used to blank the page).
  const selectedRun: DemoRun | undefined =
    runs.find((run) => run.runId === selectedRunId) ?? filteredRuns[0] ?? runs[0];
  const origin = dataOrigin(seedSource, runs);

  useEffect(() => {
    if (!runs.some((run) => run.runId === selectedRunId)) {
      setSelectedRunId(runs[0]?.runId ?? "");
    }
  }, [runs, selectedRunId]);

  useEffect(() => {
    if (!database.literature.papers.some((paper) => paper.paperId === selectedPaperId)) {
      setSelectedPaperId(database.literature.papers[0]?.paperId ?? "");
    }
  }, [database.literature.papers, selectedPaperId]);

  // Which right-hand panel is open. The run detail is separate because it follows the selection.
  const [panel, setPanel] = useState<"none" | "filters" | "settings">("none");
  const [detailOpen, setDetailOpen] = useState(false);
  const closePanel = useCallback(() => setPanel("none"), []);
  const closeDetail = useCallback(() => setDetailOpen(false), []);
  const selectRun = useCallback((runId: string) => {
    setSelectedRunId(runId);
    setDetailOpen(true);
  }, []);

  const persistDatabase = (next: MockDatabaseState) => {
    writeMockDatabase(next);
    setDatabase(next);
  };

  const saveDraft = () => {
    const outcome = saveExperimentDraft(database, control);
    persistDatabase(outcome.state);
    return {
      ok: outcome.item !== null,
      message: outcome.item
        ? locale === "ko"
          ? "초안을 mock DB에 저장했습니다."
          : "Draft saved in the mock DB."
        : locale === "ko"
          ? "초안을 저장하지 못했습니다."
          : "Draft was not saved.",
      issues: outcome.issues,
    };
  };

  const resetDatabase = () => {
    const next = resetMockDatabase(seedRuns, seedSource);
    setDatabase(next);
    setSelectedRunId(next.runs[0]?.runId ?? "");
    setSelectedPaperId(next.literature.papers[0]?.paperId ?? "");
    setLoadResult({ origin: "seeded", resetReason: null });
  };

  const recordCommandCopied = (command: string) => {
    const next = recordUiAudit(
      database,
      "command_copied",
      "info",
      "Command copied",
      command,
    );
    setDatabase(next);
  };

  const queuePaper = (paperId: string) => {
    const outcome = queuePaperForReading(database, paperId);
    persistDatabase(outcome.state);
    return {
      ok: outcome.item !== null,
      message: outcome.item
        ? locale === "ko"
          ? "논문을 읽기 큐에 추가했습니다."
          : "Paper was added to the reading queue."
        : locale === "ko"
          ? "논문을 읽기 큐에 추가하지 못했습니다."
          : "Paper was not added to the reading queue.",
      item: outcome.item,
      issues: outcome.issues,
    };
  };

  const setPaperStatus = (paperId: string, status: PaperStatus) => {
    const outcome = updatePaperStatus(database, paperId, status);
    persistDatabase(outcome.state);
    return {
      ok: outcome.item !== null,
      message: outcome.item
        ? locale === "ko"
          ? "논문 상태를 바꿨습니다."
          : "Paper status was updated."
        : locale === "ko"
          ? "논문 상태를 바꾸지 못했습니다."
          : "Paper status was not updated.",
      item: outcome.item,
      issues: outcome.issues,
    };
  };

  const linkPaper = (
    paperId: string,
    experimentId: string,
    relation: PaperExperimentLink["relation"],
  ) => {
    const outcome = linkPaperToExperiment(database, paperId, experimentId, relation);
    persistDatabase(outcome.state);
    return {
      ok: outcome.item !== null,
      message: outcome.item
        ? locale === "ko"
          ? "논문과 실험을 연결했습니다."
          : "Paper was linked to the experiment."
        : locale === "ko"
          ? "논문과 실험을 연결하지 못했습니다."
          : "Paper was not linked to the experiment.",
      item: outcome.item,
      issues: outcome.issues,
    };
  };

  const saveReadingNote = (paperId: string, text: string) => {
    const outcome = addReadingNote(database, paperId, text);
    persistDatabase(outcome.state);
    return {
      ok: outcome.item !== null,
      message: outcome.item
        ? locale === "ko"
          ? "읽기 메모를 저장했습니다."
          : "Reading note was saved."
        : locale === "ko"
          ? "읽기 메모를 저장하지 못했습니다."
          : "Reading note was not saved.",
      item: outcome.item,
      issues: outcome.issues,
    };
  };

  const ko = locale === "ko";
  const filterCount = activeFilterCount(filters, initialFilters);
  const showsRunDetail = view === "dashboard" || view === "runs";

  return (
    <div className="app-shell">
      {/* First focusable element on the page, so a keyboard user can pass the nav items instead
          of tabbing through them on every view. */}
      <a className="skip-link" href="#workspace">
        {ko ? "본문으로 건너뛰기" : "Skip to main content"}
      </a>
      <aside className="sidebar" aria-label={ko ? "화면 이동" : "Navigation"}>
        <button
          aria-label={ko ? "대시보드로 이동" : "Go to dashboard"}
          className="brand-lockup"
          onClick={() => setView("dashboard")}
          type="button"
        >
          <span className="brand-mark" aria-hidden="true" />
          {/* Not an h1: the product name is not this page's subject, the current view is. */}
          <span className="brand-name">Experiment Lens</span>
        </button>
        <nav className="nav-tabs" aria-label={ko ? "기본 화면" : "Primary views"}>
          {NAV_GROUPS.map((group) => (
            <div className="nav-group" key={group.id}>
              <span className="nav-group__label">{ko ? group.ko : group.en}</span>
              {group.views.map((item) => (
                <button
                  // Colour and weight were the only signal for which view is open; aria-current
                  // is how that reaches a screen reader.
                  aria-current={view === item ? "page" : undefined}
                  className={view === item ? "nav-item nav-item--active" : "nav-item"}
                  key={item}
                  onClick={() => setView(item)}
                  type="button"
                >
                  <span className="nav-item__icon" aria-hidden="true">{navIcon(item)}</span>
                  <span>{viewLabel(locale, item)}</span>
                </button>
              ))}
            </div>
          ))}
        </nav>
        <button className="nav-item nav-item--settings" onClick={() => setPanel("settings")} type="button">
          <span className="nav-item__icon" aria-hidden="true">⚙</span>
          <span>{ko ? "설정" : "Settings"}</span>
        </button>
      </aside>

      <main
        aria-busy={resolvingOrigin}
        className={resolvingOrigin ? "workspace workspace--resolving" : "workspace"}
        id="workspace"
      >
        <AppHeader
          actions={
            <>
              {FILTERED_VIEWS.has(view) && (
                <button
                  aria-label={ko ? `필터, ${filterCount}개 적용 중` : `Filters, ${filterCount} active`}
                  className={filterCount > 0 ? "button button--ghost button--active" : "button button--ghost"}
                  onClick={() => setPanel("filters")}
                  type="button"
                >
                  {ko ? "필터" : "Filters"}
                  {filterCount > 0 && <span className="count-badge">{filterCount}</span>}
                </button>
              )}
              <GlossaryButton locale={locale} />
              {/* The guide shows itself once, so without this it would be unreachable afterwards —
                  including for the person who comes back to this dashboard months later. */}
              <button className="button button--ghost" onClick={() => setShowGuide(true)} type="button">
                {ko ? "읽는 법" : "How to read"}
              </button>
            </>
          }
          locale={locale}
          view={view}
        >
          {/* Right under the title on every view: every number below means something different
              depending on where the rows came from. */}
          <WarningBanner
            locale={locale}
            loadOrigin={loadResult.origin}
            origin={origin}
            resolving={resolvingOrigin}
          />
        </AppHeader>
        {showGuide && (
          <Onboarding
            locale={locale}
            onDismiss={() => {
              markGuideSeen();
              setShowGuide(false);
            }}
          />
        )}
        {view === "dashboard" && (
          <Dashboard
            locale={locale}
            runs={filteredRuns}
            onSelectRun={selectRun}
            selectedRun={selectedRun}
            onOpenControl={() => setView("control")}
          />
        )}
        {view === "literature" && (
          <ResearchAtlasView
            database={database}
            locale={locale}
            onAddNote={saveReadingNote}
            onLinkPaper={linkPaper}
            onQueuePaper={queuePaper}
            onSelectPaper={setSelectedPaperId}
            onSetPaperStatus={setPaperStatus}
            runs={runs}
            selectedPaperId={selectedPaperId}
          />
        )}
        {view === "runs" && (
          <div className="page-grid page-grid--runs">
            <section className="card card--wide">
              <div className="section-heading section-heading--row">
                <h2>{t(locale, "metricFirstTable")}</h2>
                <span className="subtle">
                  {ko ? `${filteredRuns.length}개 / 전체 ${runs.length}개` : `${filteredRuns.length} of ${runs.length}`}
                </span>
              </div>
              <RunsTable locale={locale} runs={filteredRuns} selectedRunId={selectedRun?.runId ?? ""} onSelectRun={selectRun} />
            </section>
          </div>
        )}
        {view === "compare" && (
          <CompareView
            baselineId={baselineId}
            locale={locale}
            methodId={methodId}
            onBaselineChange={setBaselineId}
            onMethodChange={setMethodId}
            runs={runs}
          />
        )}
        {view === "audit" && <AuditView runs={filteredRuns} database={database} locale={locale} />}
        {view === "report" && <ReportView database={database} runs={filteredRuns} onAuditEvent={(title, detail) => {
          const next = recordUiAudit(database, "report_generated", "info", title, detail);
          setDatabase(next);
        }} locale={locale} />}
        {view === "storage" && (
          <StorageView draft={storage} locale={locale} onChange={setStorage} />
        )}
        {view === "control" && (
          <ControlView
            control={control}
            database={database}
            locale={locale}
            sourceRuns={runs}
            onChange={setControl}
            onSaveDraft={saveDraft}
            onCommandCopied={recordCommandCopied}
          />
        )}
      </main>

      <SidePanel
        closeLabel={ko ? "실행 상세 닫기" : "Close run detail"}
        onClose={closeDetail}
        open={detailOpen && showsRunDetail && selectedRun !== undefined}
        title={ko ? "실행 상세" : "Run detail"}
      >
        <ExperimentDrawer locale={locale} run={selectedRun} />
      </SidePanel>
      <SidePanel
        closeLabel={ko ? "필터 닫기" : "Close filters"}
        onClose={closePanel}
        open={panel === "filters"}
        title={ko ? "필터" : "Filters"}
      >
        <FilterPanel
          appliesToCurrentView={FILTERED_VIEWS.has(view)}
          availableRuns={runs}
          filters={filters}
          locale={locale}
          onChange={setFilters}
          onReset={() => setFilters(initialFilters)}
        />
      </SidePanel>
      <SidePanel
        closeLabel={ko ? "설정 닫기" : "Close settings"}
        onClose={closePanel}
        open={panel === "settings"}
        title={ko ? "설정" : "Settings"}
      >
        <section className="settings-group" aria-label={ko ? "화면 모드" : "Appearance"}>
          <h3>{ko ? "화면 모드" : "Appearance"}</h3>
          <div className="segmented">
            {(["light", "dark", "system"] as ThemeChoice[]).map((choice) => (
              <button
                aria-pressed={theme === choice}
                className={theme === choice ? "segmented__button segmented__button--active" : "segmented__button"}
                key={choice}
                onClick={() => setTheme(choice)}
                type="button"
              >
                {themeLabel(locale, choice)}
              </button>
            ))}
          </div>
        </section>
        <section className="settings-group" aria-label={t(locale, "language")}>
          <h3>{t(locale, "language")}</h3>
          <div className="segmented">
            {(["ko", "en"] as Locale[]).map((choice) => (
              <button
                aria-pressed={locale === choice}
                className={locale === choice ? "segmented__button segmented__button--active" : "segmented__button"}
                key={choice}
                onClick={() => setLocale(choice)}
                type="button"
              >
                {choice === "ko" ? "한국어" : "English"}
              </button>
            ))}
          </div>
        </section>
        <MockDbPanel database={database} locale={locale} loadResult={loadResult} onReset={resetDatabase} />
      </SidePanel>
      <GlossaryPanel locale={locale} />
    </div>
  );
}

/** The views, in the order a reader uses them: look at results, then prepare the next run. */
const NAV_GROUPS: { id: string; ko: string; en: string; views: View[] }[] = [
  { id: "results", ko: "결과 보기", en: "Results", views: ["dashboard", "runs", "compare", "report"] },
  { id: "check", ko: "확인", en: "Checks", views: ["audit", "literature"] },
  { id: "setup", ko: "준비", en: "Setup", views: ["storage", "control"] },
];

export default App;

function readInitialLocale(): Locale {
  if (typeof window === "undefined") return "ko";
  const stored = window.localStorage.getItem(localeStorageKey);
  if (stored === "ko" || stored === "en") return stored;
  return "ko";
}

function themeLabel(locale: Locale, choice: ThemeChoice): string {
  if (choice === "light") return locale === "ko" ? "밝게" : "Light";
  if (choice === "dark") return locale === "ko" ? "어둡게" : "Dark";
  return locale === "ko" ? "시스템" : "System";
}

function navIcon(view: View): string {
  if (view === "dashboard") return "⌁";
  if (view === "literature") return "◎";
  if (view === "runs") return "▦";
  if (view === "compare") return "⇄";
  if (view === "storage") return "⛁";
  if (view === "audit") return "✓";
  if (view === "report") return "◱";
  return "⚙";
}
