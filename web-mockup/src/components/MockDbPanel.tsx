import type { Locale, MockDatabaseLoadResult, MockDatabaseState } from "../types";
import { t } from "../i18n";

export function MockDbPanel({
  database,
  locale,
  loadResult,
  onCompleteQueued,
  onReset,
}: {
  database: MockDatabaseState;
  locale: Locale;
  loadResult: Pick<MockDatabaseLoadResult, "origin" | "resetReason">;
  onCompleteQueued: () => void;
  onReset: () => void;
}) {
  const queued = database.jobs.filter((job) => job.status === "queued").length;
  const completed = database.jobs.filter((job) => job.status === "completed").length;

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
        <div>
          <dt>{locale === "ko" ? "대기" : "Queued"}</dt>
          <dd>{queued}</dd>
        </div>
        <div>
          <dt>{locale === "ko" ? "완료" : "Completed"}</dt>
          <dd>{completed}</dd>
        </div>
      </dl>
      <p className="subtle">
        {t(locale, "source")}: {database.seedSource}. {t(locale, "databaseState")}: {loadResult.origin}.
        {loadResult.resetReason ? (locale === "ko" ? " 저장 상태를 복구했습니다." : " Stored state was recovered.") : ""}
      </p>
      <div className="mock-db-actions">
        <button className="button button--secondary" disabled={queued === 0} onClick={onCompleteQueued} type="button">
          {locale === "ko" ? "대기 작업 완료" : "Complete queued"}
        </button>
        <button className="button button--secondary" onClick={onReset} type="button">
          {t(locale, "resetDb")}
        </button>
      </div>
    </details>
  );
}
