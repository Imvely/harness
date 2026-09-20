import type { Locale, MockDatabaseLoadResult, MockDatabaseState } from "../types";
import { t } from "../i18n";

export function MockDbPanel({
  database,
  locale,
  loadResult,
  onReset,
}: {
  database: MockDatabaseState;
  locale: Locale;
  loadResult: Pick<MockDatabaseLoadResult, "origin" | "resetReason">;
  onReset: () => void;
}) {

  return (
    <details className="mock-db-panel sidebar-section" aria-label="Mock database status">
      <summary className="sidebar-section__summary">
        <span>
          <span className="eyebrow">{t(locale, "mockDb")}</span>
          <strong>{t(locale, "mockDbPanelTitle")}</strong>
        </span>
        <span className="sidebar-section__count">{database.runs.length}</span>
      </summary>
      <dl>
        <div>
          <dt>{t(locale, "runs")}</dt>
          <dd>{database.runs.length}</dd>
        </div>
        <div>
          <dt>{locale === "ko" ? "초안" : "Drafts"}</dt>
          <dd>{database.drafts.length}</dd>
        </div>
      </dl>
      <p className="subtle">
        {t(locale, "source")}: {database.seedSource}. {t(locale, "databaseState")}: {loadResult.origin}.
        {loadResult.resetReason ? (locale === "ko" ? " 저장 상태를 복구했습니다." : " Stored state was recovered.") : ""}
      </p>
      <div className="mock-db-actions">
        <button className="button button--secondary" onClick={onReset} type="button">
          {t(locale, "resetDb")}
        </button>
      </div>
    </details>
  );
}
