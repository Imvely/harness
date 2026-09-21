import { useEffect, useMemo, useState } from "react";
import { defaultBaselineId, defaultMethodId, demoRuns } from "./data/demoRuns";
import { loadDashboardRuns } from "./data/dashboardLoader";
import { AppHeader } from "./components/AppHeader";
import { CompareView } from "./components/CompareView";
import { ControlView, initialControl } from "./components/ControlView";
import { Dashboard } from "./components/Dashboard";
import { FilterPanel, filterRuns } from "./components/FilterPanel";
import { GlossaryPanel } from "./components/Glossary";
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
      setBaselineId(nextLoad.state.runs[0]?.experimentId ?? defaultBaselineId);
      setMethodId(nextLoad.state.runs[1]?.experimentId ?? nextLoad.state.runs[0]?.experimentId ?? defaultMethodId);
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

  return (
    <div className="app-shell">
      {/* First focusable element on the page, so a keyboard user can pass the seven nav items
          and the whole filter panel instead of tabbing through them on every view. */}
      <a className="skip-link" href="#workspace">
        {locale === "ko" ? "본문으로 건너뛰기" : "Skip to main content"}
      </a>
      <aside className="sidebar" aria-label={locale === "ko" ? "대시보드 탐색과 필터" : "Dashboard navigation and filters"}>
        <button
          aria-label={locale === "ko" ? "대시보드로 이동" : "Go to dashboard"}
          className={view === "dashboard" ? "brand-lockup brand-lockup--active" : "brand-lockup"}
          onClick={() => setView("dashboard")}
          type="button"
        >
          <span className="brand-mark" aria-hidden="true">
            <span className="brand-mark__lens">P</span>
          </span>
          <span className="brand-copy">
            <p className="eyebrow">pad-research</p>
            {/* Not an h1: the product name is not this page's subject, the current view is. */}
            <p className="brand-name">Experiment Lens</p>
          </span>
        </button>
        <nav className="nav-tabs" aria-label={locale === "ko" ? "기본 화면" : "Primary views"}>
          {(
            [
              "dashboard",
              "literature",
              "runs",
              "compare",
              "audit",
              "report",
              "storage",
              "control",
            ] as View[]
          ).map((item) => (
            <button
              // Colour and weight were the only signal for which view is open; aria-current is
              // how that reaches a screen reader.
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
        </nav>
        <FilterPanel
          appliesToCurrentView={FILTERED_VIEWS.has(view)}
          availableRuns={runs}
          filters={filters}
          locale={locale}
          onChange={setFilters}
          onReset={() => setFilters(initialFilters)}
        />
        <GlossaryPanel locale={locale} />
        <MockDbPanel
          database={database}
          locale={locale}
          loadResult={loadResult}
          onReset={resetDatabase}
        />
        <div className="sidebar-language" aria-label={locale === "ko" ? "화면 모드" : "Appearance"}>
          <span className="sidebar-language__label">{locale === "ko" ? "화면 모드" : "Appearance"}</span>
          <div className="language-switch language-switch--sidebar">
            {(["light", "dark", "system"] as ThemeChoice[]).map((choice) => (
              <button
                aria-pressed={theme === choice}
                className={theme === choice ? "language-switch__button language-switch__button--active" : "language-switch__button"}
                key={choice}
                onClick={() => setTheme(choice)}
                type="button"
              >
                {themeLabel(locale, choice)}
              </button>
            ))}
          </div>
        </div>
        <div className="sidebar-language sidebar-language--footer" aria-label={t(locale, "language")}>
          <span className="sidebar-language__label">{t(locale, "language")}</span>
          <div className="language-switch language-switch--sidebar">
            <button
              aria-pressed={locale === "ko"}
              className={locale === "ko" ? "language-switch__button language-switch__button--active" : "language-switch__button"}
              onClick={() => setLocale("ko")}
              type="button"
            >
              한국어
            </button>
            <button
              aria-pressed={locale === "en"}
              className={locale === "en" ? "language-switch__button language-switch__button--active" : "language-switch__button"}
              onClick={() => setLocale("en")}
              type="button"
            >
              English
            </button>
          </div>
        </div>
      </aside>

      <main
        aria-busy={resolvingOrigin}
        className={resolvingOrigin ? "workspace workspace--resolving" : "workspace"}
        id="workspace"
      >
        <AppHeader
          database={database}
          filteredCount={filteredRuns.length}
          locale={locale}
          onShowGuide={() => setShowGuide(true)}
          view={view}
        />
        {showGuide && (
          <Onboarding
            locale={locale}
            onDismiss={() => {
              markGuideSeen();
              setShowGuide(false);
            }}
          />
        )}
        {/* Always first in the content column: every number below means something different
            depending on where the rows came from. */}
        <WarningBanner
          locale={locale}
          loadOrigin={loadResult.origin}
          origin={origin}
          resolving={resolvingOrigin}
        />
        {view === "dashboard" && (
          <Dashboard
            locale={locale}
            runs={filteredRuns}
            onSelectRun={setSelectedRunId}
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
                <div>
                  <p className="eyebrow">{t(locale, "runTable")}</p>
                  <h2>{t(locale, "metricFirstTable")}</h2>
                </div>
                <span className="subtle">{t(locale, "filterNote")}</span>
              </div>
              <RunsTable locale={locale} runs={filteredRuns} selectedRunId={selectedRun?.runId ?? ""} onSelectRun={setSelectedRunId} />
            </section>
            <ExperimentDrawer locale={locale} run={selectedRun} />
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
    </div>
  );
}

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
