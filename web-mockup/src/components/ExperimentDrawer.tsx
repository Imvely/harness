import type { DemoRun, Locale } from "../types";
import { gateText, localeDate, statusText, t } from "../i18n";
import {
  classForGate,
  classForStatus,
  formatMetric,
  metricKeys,
  shortHash,
} from "../utils";

export function ExperimentDrawer({ run, locale = "en" }: { run: DemoRun; locale?: Locale }) {
  return (
    <aside className="drawer" aria-label={locale === "ko" ? "선택한 실행 상세" : "Selected run detail"}>
      <div className="section-heading">
        <p className="eyebrow">{t(locale, "selectedRun")}</p>
        <h2>{run.experimentId}</h2>
      </div>
      <div className="drawer-badges">
        <span className={classForStatus(run.status)}>{statusText(locale, run.status)}</span>
        <span className={classForGate(run.gateVerdict)}>{gateText(locale, run.gateVerdict)}</span>
        <span className="badge badge--muted">{t(locale, "seed")} {run.seed}</span>
        <span className="badge badge--danger">{locale === "ko" ? "데모" : "demo"}</span>
      </div>
      <dl className="detail-list">
        <div>
          <dt>Run ID</dt>
          <dd>{run.runId}</dd>
        </div>
        <div>
          <dt>{t(locale, "protocol")}</dt>
          <dd>{run.protocolId}</dd>
        </div>
        <div>
          <dt>{t(locale, "protocolHash")}</dt>
          <dd>
            <code>{shortHash(run.protocolHash)}</code>
          </dd>
        </div>
        <div>
          <dt>Science hash</dt>
          <dd>
            <code>{shortHash(run.scienceHash)}</code>
          </dd>
        </div>
        <div>
          <dt>Spec hash</dt>
          <dd>
            <code>{shortHash(run.specHash)}</code>
          </dd>
        </div>
        <div>
          <dt>{t(locale, "threshold")}</dt>
          <dd>{run.threshold.rule} on {run.threshold.fittedOn}</dd>
        </div>
        <div>
          <dt>{t(locale, "started")}</dt>
          <dd>{localeDate(locale, run.startedAt)}</dd>
        </div>
        <div>
          <dt>{t(locale, "duration")}</dt>
          <dd>{run.durationMinutes} {locale === "ko" ? "분" : "min"}</dd>
        </div>
      </dl>
      <div className="mini-metrics">
        {metricKeys.map((key) => (
          <div key={key}>
            <span>{key.toUpperCase()}</span>
            <strong>{formatMetric(run.metrics[key])}</strong>
          </div>
        ))}
      </div>
      <section className="note-panel">
        <h3>{t(locale, "whatThisDoesNotProve")}</h3>
        <ul>
          {run.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
          <li>{locale === "ko" ? "연구 주장은 실제 데이터, 호환 프로토콜, 검토자 승인이 필요합니다." : "Research claims require real data, compatible protocols, and reviewer approval."}</li>
        </ul>
      </section>
      <section className="note-panel">
        <h3>{t(locale, "claimEligibility")}</h3>
        <p>{run.claimEligibility.allowed ? (locale === "ko" ? "검토 후 가능." : "Eligible after review.") : t(locale, "claimBlocked")}</p>
        <ul>
          {run.claimEligibility.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      </section>
      <section className="artifact-list">
        <h3>{t(locale, "artifacts")}</h3>
        {run.artifacts.map((artifact) => (
          <div className="artifact-row" key={artifact.path}>
            <span>{artifact.label}</span>
            <code>{artifact.kind}</code>
          </div>
        ))}
      </section>
    </aside>
  );
}
