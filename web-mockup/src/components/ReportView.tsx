import type { DemoRun, Locale, MockDatabaseState } from "../types";
import { auditKindLabel, localeDate, severityLabel, t } from "../i18n";
import { formatMetric, metricAverage, metricKeys, shortHash, unique } from "../utils";
import { MetricRow } from "./ExpandableRow";

export function ReportView({
  runs,
  database,
  locale = "en",
  onAuditEvent,
}: {
  runs: DemoRun[];
  database: MockDatabaseState;
  locale?: Locale;
  onAuditEvent: (title: string, detail: string) => void;
}) {
  const experiments = unique(runs.map((run) => run.experimentId));
  // Derived, not hardcoded. Pinning the baseline to a demo experiment id meant that on any
  // real export — where that id does not exist — the baseline side was silently empty and the
  // report blocked itself for a reason the user could not act on.
  const preferred = (...candidates: string[]) =>
    candidates.find((candidate) => experiments.includes(candidate));
  const method =
    preferred("exp_demo_spoof_preserve") ??
    experiments.find((id) => runs.some((run) => run.experimentId === id && run.adaptationMethod !== "none")) ??
    experiments[0] ??
    "";
  const baseline =
    preferred("exp_syn_e02_video_source_only") ??
    experiments.find(
      (id) =>
        id !== method && runs.some((run) => run.experimentId === id && run.adaptationMethod === "none"),
    ) ??
    experiments.find((id) => id !== method) ??
    "";
  const methodRuns = runs.filter((run) => run.experimentId === method && run.mode === "full");
  const baselineRuns = runs.filter((run) => run.experimentId === baseline && run.mode === "full");
  const readiness = reportReadiness(methodRuns, baselineRuns);
  const commandSafe = readiness.commandSafe && isCliSafe(method) && isCliSafe(baseline);
  const reportCommand = commandSafe
    ? `uv run --no-sync python scripts/summarize_experiment.py --experiment-id ${cliToken(method)} --baseline-experiment-id ${cliToken(baseline)} -o experiments/reports/${cliToken(method)}.md`
    : "BLOCKED: selected experiment IDs are not shell-safe.";
  const reportMarkdown = buildReportMarkdown(
    locale,
    method,
    baseline,
    methodRuns,
    baselineRuns,
    readiness,
  );

  const downloadDashboardJson = () => {
    downloadFile(
      "pad-mock-dashboard.json",
      "application/json",
      `${JSON.stringify(database, null, 2)}\n`,
    );
    onAuditEvent("Dashboard JSON downloaded", "The current mock DB snapshot was exported from the browser.");
  };

  const downloadReport = () => {
    downloadFile(`${method}-mock-report.md`, "text/markdown", reportMarkdown);
    onAuditEvent("Mock report downloaded", `${method} markdown preview was exported.`);
  };

  return (
    <div className="page-grid page-grid--report">
      <section className="card card--wide">
        <div className="section-heading">
          <p className="eyebrow">{t(locale, "reportStudio")}</p>
          <h2>{locale === "ko" ? "Markdown 보고서 미리보기" : "Markdown report preview"}</h2>
          <p className="subtle">{locale === "ko" ? "실제 하네스 명령은 계약 §44 보고서와 PAI별 CSV를 만듭니다." : "The real harness command produces the contract §44 report and per-attack CSV."}</p>
        </div>
        <pre className="yaml-preview">{reportCommand}</pre>
        <div className="button-row">
          <button className="button button--primary" onClick={downloadReport} type="button">
            {t(locale, "downloadReport")}
          </button>
          <button className="button button--secondary" onClick={downloadDashboardJson} type="button">
            {t(locale, "downloadMockDbJson")}
          </button>
        </div>
      </section>

      <section className="card card--wide report-preview" aria-label={locale === "ko" ? "보고서 미리보기" : "Report preview"}>
        <h2>{locale === "ko" ? "미리보기" : "Preview"}: {method}</h2>
        <blockquote>SYNTHETIC SANITY — NOT A RESEARCH RESULT</blockquote>
        <h3>{locale === "ko" ? "프로토콜" : "Protocol"}</h3>
        <p>
          {locale === "ko" ? "기준 실험과 방법은 하나의 프로토콜 해시를 공유해야 합니다. 현재 미리보기" : "Baseline and method must share one protocol hash. Current preview"}: {readiness.baselineProtocolLabel} / {readiness.methodProtocolLabel}.
        </p>
        <h3>{locale === "ko" ? "전체 지표" : "Overall"}</h3>
        {!readiness.allowed ? (
          <div className="comparison-alert" role="status">
            <strong>{locale === "ko" ? "보고서 수치 미리보기 차단" : "Report metrics blocked"}</strong>
            <ul>
              {readiness.reasons.map((reason) => (
                <li key={reason}>{localizeReadinessReason(locale, reason)}</li>
              ))}
            </ul>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="runs-table runs-table--compact">
              <thead>
                <tr>
                  <th scope="col">Metric</th>
                  <th scope="col">{t(locale, "baseline")}</th>
                  <th scope="col">{t(locale, "method")}</th>
                  <th scope="col">{locale === "ko" ? "차이" : "Delta"}</th>
                </tr>
              </thead>
              <tbody>
                {metricKeys.map((metric) => {
                  const baseValue = metricAverage(baselineRuns, metric);
                  const methodValue = metricAverage(methodRuns, metric);
                  const delta = methodValue - baseValue;
                  return (
                    <MetricRow colSpan={4} key={metric} locale={locale} metric={metric}>
                      <td>{formatMetric(baseValue)}</td>
                      <td>{formatMetric(methodValue)}</td>
                      <td>{delta >= 0 ? "+" : ""}{formatMetric(delta)}</td>
                    </MetricRow>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <h3>{t(locale, "whatThisDoesNotProve")}</h3>
        <ul>
          <li>{locale === "ko" ? "합성 데모 데이터는 연구 주장을 뒷받침할 수 없습니다." : "Synthetic demo data cannot support a research claim."}</li>
          <li>{locale === "ko" ? "스모크 또는 적은 시드 표본은 성능 결론을 뒷받침할 수 없습니다." : "Smoke or seed-light samples cannot support performance conclusions."}</li>
          <li>{locale === "ko" ? "AUC 맥락은 PAI별 APCER 회귀를 덮을 수 없습니다." : "AUC context cannot override per-PAI APCER regression."}</li>
        </ul>
      </section>

      <section className="card">
        <div className="section-heading">
          <p className="eyebrow">{t(locale, "exportPath")}</p>
          <h2>{t(locale, "dashboardJson")}</h2>
        </div>
        <pre className="yaml-preview">uv run --no-sync python scripts/export_dashboard_data.py --include-smoke -o web-mockup/public/dashboard-demo.json</pre>
        <p className="subtle">
          {t(locale, "browserExports")}
        </p>
      </section>

      <section className="card">
        <div className="section-heading">
          <p className="eyebrow">{t(locale, "auditTrail")}</p>
          <h2>{t(locale, "latestReportActions")}</h2>
        </div>
        <ol className="timeline-list">
          {database.auditLog.slice(0, 6).map((entry) => (
            <li key={entry.entryId}>
              {/* From the stored `kind`, like the audit view. Reading the stored `title` meant
                  this list stayed English whatever language the reader chose. */}
              <strong>{auditKindLabel(locale, entry.kind)}</strong>
              <span>
                {localeDate(locale, entry.at)} · {severityLabel(locale, entry.severity)}
              </span>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

function buildReportMarkdown(
  locale: Locale,
  method: string,
  baseline: string,
  methodRuns: DemoRun[],
  baselineRuns: DemoRun[],
  readiness: ReportReadiness,
): string {
  const rows = readiness.allowed
    ? metricKeys
        .map((metric) => {
          const baseValue = metricAverage(baselineRuns, metric);
          const methodValue = metricAverage(methodRuns, metric);
          const delta = methodValue - baseValue;
          return `| ${metric.toUpperCase()} | ${formatMetric(baseValue)} | ${formatMetric(methodValue)} | ${delta >= 0 ? "+" : ""}${formatMetric(delta)} |`;
        })
        .join("\n")
    : "";
  const blockedSection = readiness.allowed
    ? ""
    : readiness.reasons
        .map((reason) => `- ${localizeReadinessReason(locale, reason)}`)
        .join("\n");
  if (locale === "ko") {
    return `# Mock PAD 보고서: ${method}

> SYNTHETIC SANITY — NOT A RESEARCH RESULT

## Protocol

- 기준 실험: ${baseline}
- 방법: ${method}
- 기준 프로토콜 해시: ${readiness.baselineProtocolLabel}
- 방법 프로토콜 해시: ${readiness.methodProtocolLabel}

## 전체 지표

${readiness.allowed ? `\
| 지표 | 기준 | 방법 | 차이 |
|---|---:|---:|---:|
${rows}` : `수치 미리보기 차단:
${blockedSection}`}

## 안전 기준

- 합성 데모 데이터는 연구 주장을 뒷받침할 수 없습니다.
- 스모크 또는 적은 시드 표본은 성능 결론을 뒷받침할 수 없습니다.
- AUC 맥락은 PAI별 APCER 회귀를 덮을 수 없습니다.
`;
  }
  return `# Mock PAD Report: ${method}

> SYNTHETIC SANITY — NOT A RESEARCH RESULT

## Protocol

- Baseline: ${baseline}
- Method: ${method}
- Baseline protocol hash: ${readiness.baselineProtocolLabel}
- Method protocol hash: ${readiness.methodProtocolLabel}

## Overall metrics

${readiness.allowed ? `\
| Metric | Baseline | Method | Delta |
|---|---:|---:|---:|
${rows}` : `Metric preview blocked:
${blockedSection}`}

## Guardrails

- Synthetic demo data cannot support a research claim.
- Smoke or seed-light samples cannot support performance conclusions.
- AUC context cannot override per-PAI APCER regression.
`;
}

type ProtocolSummary = { kind: "empty" | "single" | "mixed"; label: string; hash?: string };

interface ReportReadiness {
  allowed: boolean;
  commandSafe: boolean;
  reasons: string[];
  baselineProtocolLabel: string;
  methodProtocolLabel: string;
}

function reportReadiness(methodRuns: DemoRun[], baselineRuns: DemoRun[]): ReportReadiness {
  const reasons: string[] = [];
  const baselineProtocol = protocolSummary(baselineRuns);
  const methodProtocol = protocolSummary(methodRuns);
  if (baselineRuns.length === 0) reasons.push("baseline has no full runs");
  if (methodRuns.length === 0) reasons.push("method has no full runs");
  if (baselineRuns.length > 0 && baselineRuns.length < 3) {
    reasons.push("baseline has fewer than three full seeds");
  }
  if (methodRuns.length > 0 && methodRuns.length < 3) {
    reasons.push("method has fewer than three full seeds");
  }
  if (baselineProtocol.kind !== "single") reasons.push("baseline protocol is not single");
  if (methodProtocol.kind !== "single") reasons.push("method protocol is not single");
  if (
    baselineProtocol.kind === "single" &&
    methodProtocol.kind === "single" &&
    baselineProtocol.hash !== methodProtocol.hash
  ) {
    reasons.push("protocol hashes differ");
  }
  if (!baselineRuns.every((run) => run.gateVerdict === "pass" || run.gateVerdict === "no_gate")) {
    reasons.push("baseline has unsafe gate verdicts");
  }
  if (
    !methodRuns.every(
      (run) =>
        run.gateVerdict === "pass" ||
        (run.adaptationMethod === "none" && run.gateVerdict === "no_gate"),
    )
  ) {
    reasons.push("method has unsafe gate verdicts");
  }
  return {
    allowed: reasons.length === 0,
    commandSafe: [...baselineRuns, ...methodRuns].every((run) => isCliSafe(run.experimentId)),
    reasons,
    baselineProtocolLabel: baselineProtocol.label,
    methodProtocolLabel: methodProtocol.label,
  };
}

function protocolSummary(runs: DemoRun[]): ProtocolSummary {
  const hashes = unique(runs.map((run) => run.protocolHash));
  if (hashes.length === 0) return { kind: "empty", label: "none" };
  if (hashes.length === 1) return { kind: "single", hash: hashes[0], label: shortHash(hashes[0]) };
  return { kind: "mixed", label: `mixed(${hashes.length})` };
}

function localizeReadinessReason(locale: Locale, reason: string): string {
  if (locale === "en") return reason;
  const ko: Record<string, string> = {
    "baseline has no full runs": "기준 실험에 full 실행이 없습니다.",
    "method has no full runs": "방법 실험에 full 실행이 없습니다.",
    "baseline has fewer than three full seeds": "기준 실험의 full seed가 3개 미만입니다.",
    "method has fewer than three full seeds": "방법 실험의 full seed가 3개 미만입니다.",
    "baseline protocol is not single": "기준 실험의 프로토콜 해시가 하나로 고정되지 않았습니다.",
    "method protocol is not single": "방법 실험의 프로토콜 해시가 하나로 고정되지 않았습니다.",
    "protocol hashes differ": "기준과 방법의 프로토콜 해시가 다릅니다.",
    "baseline has unsafe gate verdicts": "기준 실험에 안전하지 않은 gate verdict가 있습니다.",
    "method has unsafe gate verdicts": "방법 실험에 안전하지 않은 gate verdict가 있습니다.",
  };
  return ko[reason] ?? reason;
}

function cliToken(value: string): string {
  if (!isCliSafe(value)) throw new Error("unsafe CLI token");
  return value;
}

function isCliSafe(value: string): boolean {
  return /^[A-Za-z0-9_.:-]+$/.test(value);
}

function downloadFile(filename: string, mimeType: string, content: string): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
