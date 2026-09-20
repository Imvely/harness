import type { Locale, MockDatabaseState } from "../types";
import { t, viewLabel, viewPurpose } from "../i18n";

type View = "dashboard" | "literature" | "runs" | "compare" | "audit" | "report" | "control";

export function AppHeader({
  locale,
  view,
  database,
  filteredCount,
  onShowGuide,
}: {
  locale: Locale;
  view: View;
  database: MockDatabaseState;
  filteredCount: number;
  onShowGuide: () => void;
}) {
  const fabricated = database.runs.filter((run) => run.demoOnly).length;

  return (
    <header className="app-header">
      <div className="app-header__title">
        <p className="eyebrow">{t(locale, "overview")}</p>
        {/* The page heading. It was an h2 while the only h1 was the brand name inside a button
            in the sidebar, which left every view with five to eight sibling h2s and no level
            above them — a screen reader's heading outline was flat. */}
        <h1>{viewLabel(locale, view)}</h1>
        <span>{viewPurpose(locale, view)}</span>
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
        {/* The guide shows itself once, so without this it would be unreachable afterwards —
            including for the person who comes back to this dashboard months later. */}
        <button className="button button--secondary" onClick={onShowGuide} type="button">
          {locale === "ko" ? "읽는 법 보기" : "How to read this"}
        </button>
      </div>
    </header>
  );
}
