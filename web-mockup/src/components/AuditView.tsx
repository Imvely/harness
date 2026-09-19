import type { DemoRun, Locale, MockDatabaseState } from "../types";
import { localeDate, t } from "../i18n";
import { formatMetric, shortHash, unique } from "../utils";

export function AuditView({
  runs,
  database,
  locale = "en",
}: {
  runs: DemoRun[];
  database: MockDatabaseState;
  locale?: Locale;
}) {
  const protocols = unique(runs.map((run) => run.protocolId)).map((protocolId) => {
    const protocolRuns = runs.filter((run) => run.protocolId === protocolId);
    return {
      protocolId,
      hashes: unique(protocolRuns.map((run) => run.protocolHash)),
      runs: protocolRuns,
    };
  });
  const selected = runs[0];

  return (
    <div className="page-grid page-grid--audit">
      <section className="card card--wide">
        <div className="section-heading section-heading--row">
          <div>
            <p className="eyebrow">{locale === "ko" ? "프로토콜과 데이터 감사" : "Protocol and data audit"}</p>
            <h2>{locale === "ko" ? "주장 안전 점검표" : "Claim safety checklist"}</h2>
          </div>
          <span className="badge badge--danger">{locale === "ko" ? "데모 전용" : "demo only"}</span>
        </div>
        <div className="audit-grid" aria-label={locale === "ko" ? "연구 유효성 점검" : "Research validity checks"}>
          <AuditTile label={locale === "ko" ? "원본 매체 숨김" : "Raw media hidden"} ok detail={locale === "ko" ? "프레임 또는 얼굴 미리보기를 렌더링하지 않습니다." : "No frame or face preview is rendered."} locale={locale} />
          <AuditTile label={locale === "ko" ? "Dev 임계값" : "Dev threshold"} ok={runs.every((run) => run.threshold.fittedOn.endsWith("/dev"))} detail={locale === "ko" ? "임계값 출처는 /dev로 끝나야 합니다." : "Threshold provenance must end with /dev."} locale={locale} />
          <AuditTile label={locale === "ko" ? "합성 주장 차단" : "Synthetic blocked"} ok={runs.every((run) => !run.researchClaimAllowed)} detail={locale === "ko" ? "모든 데모 행은 연구 주장을 차단합니다." : "All demo rows block research claims."} locale={locale} />
          <AuditTile label={locale === "ko" ? "프로토콜 일관성" : "Protocol consistency"} ok={protocols.every((item) => item.hashes.length === 1)} detail={locale === "ko" ? "프로토콜 묶음마다 해시는 하나여야 합니다." : "Each protocol group should have one hash."} locale={locale} />
        </div>
      </section>

      <section className="card card--wide">
        <div className="section-heading">
          <p className="eyebrow">{t(locale, "protocolGroups")}</p>
          <h2>{locale === "ko" ? "해시 경계" : "Hash boundaries"}</h2>
        </div>
        <div className="table-wrap">
          <table className="runs-table runs-table--compact">
            <thead>
              <tr>
                <th scope="col">{t(locale, "protocol")}</th>
                <th scope="col">{locale === "ko" ? "해시 상태" : "Hash state"}</th>
                <th scope="col">{t(locale, "runs")}</th>
                <th scope="col">{t(locale, "threshold")}</th>
              </tr>
            </thead>
            <tbody>
              {protocols.map((item) => (
                <tr key={item.protocolId}>
                  <td>{item.protocolId}</td>
                  <td>{item.hashes.length === 1 ? shortHash(item.hashes[0]) : `mixed(${item.hashes.length})`}</td>
                  <td>{item.runs.length}</td>
                  <td>{unique(item.runs.map((run) => run.threshold.rule)).join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {selected && (
        <section className="card">
          <div className="section-heading">
            <p className="eyebrow">{locale === "ko" ? "매니페스트 해시" : "Manifest hashes"}</p>
            <h2>{selected.experimentId}</h2>
          </div>
          <dl className="detail-list">
            {Object.entries(selected.manifestHashes).map(([dataset, hash]) => (
              <div key={dataset}>
                <dt>{dataset}</dt>
                <dd><code>{shortHash(hash)}</code></dd>
              </div>
            ))}
            <div>
              <dt>PII policy</dt>
              <dd>{Object.values(selected.datasetPiiPolicies).join(", ")}</dd>
            </div>
            <div>
              <dt>{locale === "ko" ? "적응 세트" : "Adaptation set"}</dt>
              <dd>{selected.adaptationSetHash ? <code>{shortHash(selected.adaptationSetHash)}</code> : "none"}</dd>
            </div>
          </dl>
        </section>
      )}

      <section className="card">
        <div className="section-heading">
          <p className="eyebrow">{locale === "ko" ? "임계값 출처" : "Threshold provenance"}</p>
          <h2>{locale === "ko" ? "맞춘 split과 support" : "Fitted split and support"}</h2>
        </div>
        <div className="mini-metrics mini-metrics--stacked">
          {runs.slice(0, 5).map((run) => (
            <div key={run.runId}>
              <span>{run.experimentId}</span>
              <strong>{run.threshold.fittedOn}</strong>
              <small>tau {formatMetric(run.threshold.tau)} · dev n={run.threshold.devSupport.attack + run.threshold.devSupport.bonaFide}</small>
            </div>
          ))}
        </div>
      </section>

      <section className="card card--wide">
        <div className="section-heading section-heading--row">
          <div>
            <p className="eyebrow">{t(locale, "auditLog")}</p>
            <h2>{locale === "ko" ? "저장된 UI 이벤트" : "Persisted UI events"}</h2>
          </div>
          <span className="subtle">{database.auditLog.length} {locale === "ko" ? "개 이벤트" : "events"}</span>
        </div>
        <ol className="audit-log-list">
          {database.auditLog.slice(0, 12).map((entry) => (
            <li className={`audit-log-item audit-log-item--${entry.severity}`} key={entry.entryId}>
              <span>{entry.kind}</span>
              <strong>{entry.title}</strong>
              <p>{entry.detail}</p>
              <time dateTime={entry.at}>{localeDate(locale, entry.at)}</time>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

function AuditTile({
  label,
  ok,
  detail,
  locale,
}: {
  label: string;
  ok: boolean;
  detail: string;
  locale: Locale;
}) {
  return (
    <article className={ok ? "audit-tile audit-tile--ok" : "audit-tile audit-tile--warn"}>
      <strong>{ok ? (locale === "ko" ? "통과" : "Pass") : (locale === "ko" ? "검토" : "Review")}</strong>
      <span>{label}</span>
      <p>{detail}</p>
    </article>
  );
}
