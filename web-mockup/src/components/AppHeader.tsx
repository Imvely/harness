import type { Locale, MockDatabaseState } from "../types";
import { t, viewLabel } from "../i18n";

type View = "dashboard" | "literature" | "runs" | "compare" | "audit" | "report" | "control";

export function AppHeader({
  locale,
  view,
  database,
  filteredCount,
}: {
  locale: Locale;
  view: View;
  database: MockDatabaseState;
  filteredCount: number;
}) {
  const queued = database.jobs.filter((job) => job.status === "queued").length;
  const generated = database.runs.filter((run) => run.tags.includes("mock-db")).length;

  return (
    <header className="app-header">
      <div className="app-header__title">
        <p className="eyebrow">{t(locale, "overview")}</p>
        <h2>{viewLabel(locale, view)}</h2>
        <span>{t(locale, "researchSubtitle")}</span>
      </div>
      <div className="app-header__meta" aria-label={t(locale, "databaseState")}>
        <span>
          <strong>{filteredCount}</strong>
          {t(locale, "filtered")}
        </span>
        <span>
          <strong>{queued}</strong>
          {t(locale, "queuedJobs")}
        </span>
        <span>
          <strong>{generated}</strong>
          {t(locale, "generatedRows")}
        </span>
      </div>
    </header>
  );
}
