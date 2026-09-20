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
  const fabricated = database.runs.filter((run) => run.demoOnly).length;

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
          <strong>{database.runs.length}</strong>
          {locale === "ko" ? "전체 실행" : "runs total"}
        </span>
        {/* Only shown when there is something to warn about, so a clean export does not
            carry a counter that permanently reads zero. */}
        {fabricated > 0 && (
          <span className="app-header__meta--warn">
            <strong>{fabricated}</strong>
            {locale === "ko" ? "모의 행" : "mock rows"}
          </span>
        )}
      </div>
    </header>
  );
}
