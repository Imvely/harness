import type { DemoRun, Locale } from "../types";
import { claimCheckKeys, claimCheckLabel, gateText, localeDate, statusText, t } from "../i18n";
import { glossaryEntry } from "../glossary";
import { Term } from "./Glossary";
import { HashValue } from "./HashValue";
import {
  classForGate,
  classForStatus,
  formatMetric,
  isFabricatedRun,
  metricKeys,
} from "../utils";

export function ExperimentDrawer({ run, locale = "en" }: { run: DemoRun | undefined; locale?: Locale }) {
  if (!run) {
    return (
      <aside className="drawer" aria-label={locale === "ko" ? "선택한 실행 상세" : "Selected run detail"}>
        <div className="section-heading">
          <p className="eyebrow">{t(locale, "selectedRun")}</p>
          <h2>{locale === "ko" ? "선택된 실행이 없습니다" : "No run selected"}</h2>
        </div>
        <p className="subtle">
          {locale === "ko"
            ? "위 표에서 행을 고르면 그 실행의 출처와 지표가 여기에 나옵니다."
            : "Pick a row above to see that run's provenance and metrics here."}
        </p>
      </aside>
    );
  }
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
        {/* Only fabricated rows carry this. It used to be hardcoded, so exported real runs
            were labelled "demo" while browser-generated rows were not labelled at all. */}
        {isFabricatedRun(run) && (
          <span className="badge badge--danger">
            {locale === "ko" ? "모의 행 (측정값 아님)" : "mock row (not measured)"}
          </span>
        )}
      </div>
      <dl className="detail-list">
        <div>
          <dt>{locale === "ko" ? "실행 ID" : "Run ID"}</dt>
          <dd>{run.runId}</dd>
        </div>
        <div>
          <dt>{t(locale, "protocol")}</dt>
          <dd>{run.protocolId}</dd>
        </div>
        {/* The three hashes used to print as three unlabelled 12-character strings, which told a
            reader nothing about what each one covers. Each carries its glossary chip now. */}
        <div>
          <dt>
            <Term id="protocol-hash" locale={locale} />
          </dt>
          <dd>
            <HashValue
              label={locale === "ko" ? "프로토콜 해시" : "protocol hash"}
              locale={locale}
              value={run.protocolHash}
            />
          </dd>
        </div>
        <div>
          <dt>
            <Term id="science-hash" locale={locale} />
          </dt>
          <dd>
            <HashValue
              label={locale === "ko" ? "과학 해시" : "science hash"}
              locale={locale}
              value={run.scienceHash}
            />
          </dd>
        </div>
        <div>
          <dt>
            <Term id="spec-hash" locale={locale} />
          </dt>
          <dd>
            <HashValue
              label={locale === "ko" ? "스펙 해시" : "spec hash"}
              locale={locale}
              value={run.specHash}
            />
          </dd>
        </div>
        <div>
          <dt>
            <Term id="tau" locale={locale}>
              {t(locale, "threshold")}
            </Term>
          </dt>
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
        {metricKeys.map((key) => {
          const entry = glossaryEntry(key);
          return (
            <div key={key}>
              <span>{key.toUpperCase()}</span>
              {entry && locale === "ko" && <small>{entry.ko}</small>}
              <strong>{formatMetric(run.metrics[key])}</strong>
            </div>
          );
        })}
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
        <h3>
          <Term id="claim-eligibility" locale={locale}>
            {t(locale, "claimEligibility")}
          </Term>
        </h3>
        <p>{run.claimEligibility.allowed ? (locale === "ko" ? "검토 후 가능." : "Eligible after review.") : t(locale, "claimBlocked")}</p>
        {/* The seven conditions, each as met or unmet. The free-text list below is the
            exporter's own wording and stays as supporting detail; on its own it printed field
            names like `researchClaimAllowed is false` at a reader who had no schema to hand. */}
        <ul className="claim-checklist">
          {claimCheckKeys.map((key) => {
            const met = run.claimEligibility[key];
            return (
              <li className={met ? "claim-check claim-check--met" : "claim-check"} key={key}>
                <span aria-hidden="true" className="claim-check__mark">
                  {met ? "✓" : "✕"}
                </span>
                <span>{claimCheckLabel(locale, key)}</span>
                <span className="sr-only">
                  {met
                    ? locale === "ko"
                      ? " — 충족"
                      : " — met"
                    : locale === "ko"
                      ? " — 미충족"
                      : " — not met"}
                </span>
              </li>
            );
          })}
        </ul>
        {run.claimEligibility.reasons.length > 0 && (
          <details className="claim-reasons">
            <summary>{locale === "ko" ? "내보내기 도구가 남긴 사유" : "Reasons recorded by the exporter"}</summary>
            <ul>
              {run.claimEligibility.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </details>
        )}
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
