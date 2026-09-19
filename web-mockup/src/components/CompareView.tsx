import { useMemo, useState } from "react";
import type { DemoRun, Locale } from "../types";
import { t } from "../i18n";
import { formatMetric, metricAverage, metricKeys, shortHash, unique } from "../utils";
import { DeltaChart } from "./Charts";
import { SelectBox } from "./FilterPanel";

export function CompareView({
  baselineId,
  locale = "en",
  methodId,
  onBaselineChange,
  onMethodChange,
  runs,
}: {
  baselineId: string;
  locale?: Locale;
  methodId: string;
  onBaselineChange: (value: string) => void;
  onMethodChange: (value: string) => void;
  runs: DemoRun[];
}) {
  const [includeSmoke, setIncludeSmoke] = useState(false);
  const [includeRisky, setIncludeRisky] = useState(false);
  const experiments = unique(runs.map((run) => run.experimentId));
  const baselineAll = runs.filter((run) => run.experimentId === baselineId);
  const methodAll = runs.filter((run) => run.experimentId === methodId);
  const baseline = useMemo(
    () => comparisonRuns(baselineAll, { includeSmoke, includeRisky }),
    [baselineAll, includeRisky, includeSmoke],
  );
  const method = useMemo(
    () => comparisonRuns(methodAll, { includeSmoke, includeRisky }),
    [methodAll, includeRisky, includeSmoke],
  );
  const baselineProtocol = protocolSummary(baseline);
  const methodProtocol = protocolSummary(method);
  const comparable =
    baselineProtocol.kind === "single" &&
    methodProtocol.kind === "single" &&
    baselineProtocol.hash === methodProtocol.hash;
  const blockReason = comparisonBlockReason(baselineProtocol, methodProtocol);
  const excludedCount = baselineAll.length + methodAll.length - baseline.length - method.length;

  return (
    <div className="page-grid page-grid--compare">
      <section className="card card--wide">
        <div className="section-heading">
          <p className="eyebrow">{t(locale, "compare")}</p>
          <h2>{locale === "ko" ? "기준 실험과 방법 비교" : "Baseline vs method"}</h2>
        </div>
        <div className="compare-selectors">
          <SelectBox label={t(locale, "baseline")} value={baselineId} values={experiments} onChange={onBaselineChange} />
          <SelectBox label={t(locale, "method")} value={methodId} values={experiments} onChange={onMethodChange} />
          <label className="check-field check-field--large">
            <input checked={includeSmoke} onChange={(event) => setIncludeSmoke(event.target.checked)} type="checkbox" />
            {t(locale, "includeSmoke")}
          </label>
          <label className="check-field check-field--large">
            <input checked={includeRisky} onChange={(event) => setIncludeRisky(event.target.checked)} type="checkbox" />
            {t(locale, "includeRisky")}
          </label>
          <div className={comparable ? "protocol-card protocol-card--ok" : "protocol-card protocol-card--blocked"}>
            <span>{t(locale, "protocolHash")}</span>
            <strong>{comparable ? (locale === "ko" ? "비교 가능" : "Comparable") : (locale === "ko" ? "검토 전 차단" : "Blocked until review")}</strong>
            <code>{protocolLabel(baselineProtocol)} / {protocolLabel(methodProtocol)}</code>
            {!comparable && <small>{localizeBlockReason(locale, blockReason)}</small>}
          </div>
        </div>
        <p className="subtle">
          {locale === "ko"
            ? `포함 행: 기준 ${baseline.length}, 방법 ${method.length}. 정책 제외: ${excludedCount}.`
            : `Included rows: baseline ${baseline.length}, method ${method.length}. Excluded by policy: ${excludedCount}.`}
        </p>
      </section>
      <section className="card card--wide">
        <div className="section-heading section-heading--row">
          <div>
            <p className="eyebrow">{locale === "ko" ? "차이 표" : "Delta table"}</p>
            <h2>{locale === "ko" ? "보안 우선 지표" : "Security-first metrics"}</h2>
          </div>
          <span className="subtle">{locale === "ko" ? "APCER/BPCER/ACER/HTER는 낮을수록 안전" : "Lower APCER/BPCER/ACER/HTER is safer"}</span>
        </div>
        {!comparable && (
          <div className="comparison-alert" role="status">
            {locale === "ko"
              ? "mock UI에서 비교가 차단되었습니다. 차이를 해석하기 전에 하네스 보고 흐름에서 검토자 근거를 남기세요."
              : "Comparison is blocked in the mock UI. Add a reviewer justification in the harness report flow before interpreting deltas."}
          </div>
        )}
        {comparable ? (
          <DeltaTable baseline={baseline} method={method} locale={locale} />
        ) : (
          <BlockedComparison locale={locale} reason={blockReason} />
        )}
      </section>
      <section className="card">
        <div className="section-heading">
          <p className="eyebrow">{t(locale, "metricDelta")}</p>
          <h2>{locale === "ko" ? "방법 - 기준" : "Method minus baseline"}</h2>
        </div>
        {comparable ? (
          <DeltaChart baseline={baseline} method={method} locale={locale} />
        ) : (
          <BlockedComparison locale={locale} reason={blockReason} compact />
        )}
      </section>
      <section className="card">
        <div className="section-heading">
          <p className="eyebrow">{t(locale, "guardrails")}</p>
          <h2>{t(locale, "whatThisDoesNotProve")}</h2>
        </div>
        <ul className="guardrail-list">
          <li>{locale === "ko" ? "합성 데이터는 연구 주장을 뒷받침할 수 없습니다." : "Synthetic data cannot support research claims."}</li>
          <li>{locale === "ko" ? "mixed protocol 또는 프로토콜 불일치는 `--justify`와 보이는 배너가 필요합니다." : "Protocol mismatch or mixed protocol requires `--justify` and a visible banner."}</li>
          <li>{locale === "ko" ? "시드가 세 개 미만이면 시드 편차 결론이 차단됩니다." : "Seed count below three blocks seed-variance conclusions."}</li>
          <li>{locale === "ko" ? "AUC는 PAI별 APCER 회귀를 덮을 수 없습니다." : "AUC cannot override per-PAI APCER regression."}</li>
        </ul>
      </section>
    </div>
  );
}

type ProtocolSummary =
  | { kind: "empty"; hashes: string[] }
  | { kind: "single"; hash: string; hashes: string[] }
  | { kind: "mixed"; hashes: string[] };

function comparisonRuns(
  runs: DemoRun[],
  policy: { includeSmoke: boolean; includeRisky: boolean },
): DemoRun[] {
  return runs.filter((run) => {
    if (!policy.includeSmoke && run.mode === "smoke") return false;
    if (!policy.includeRisky && !["pass", "no_gate"].includes(run.gateVerdict)) return false;
    return true;
  });
}

function BlockedComparison({
  compact = false,
  locale,
  reason,
}: {
  compact?: boolean;
  locale: Locale;
  reason: string;
}) {
  return (
    <div className="comparison-alert" role="status">
      <strong>{locale === "ko" ? "비교 수치 차단됨" : "Delta values blocked"}</strong>
      {!compact && (
        <p>
          {locale === "ko"
            ? "프로토콜 해시가 하나로 일치하기 전에는 표/차트를 계산하지 않습니다."
            : "Tables and charts are not computed until both selections share exactly one protocol hash."}
        </p>
      )}
      <small>{localizeBlockReason(locale, reason)}</small>
    </div>
  );
}

function protocolSummary(runs: DemoRun[]): ProtocolSummary {
  const hashes = unique(runs.map((run) => run.protocolHash));
  if (hashes.length === 0) return { kind: "empty", hashes };
  if (hashes.length === 1) return { kind: "single", hash: hashes[0], hashes };
  return { kind: "mixed", hashes };
}

function protocolLabel(summary: ProtocolSummary): string {
  if (summary.kind === "single") return shortHash(summary.hash);
  if (summary.kind === "mixed") return `mixed(${summary.hashes.length})`;
  return "none";
}

function comparisonBlockReason(baseline: ProtocolSummary, method: ProtocolSummary): string {
  if (baseline.kind === "empty" || method.kind === "empty") return "No eligible rows under the active policy.";
  if (baseline.kind === "mixed" || method.kind === "mixed") return "One selected experiment has mixed protocol hashes.";
  if (baseline.hash !== method.hash) return "Protocol hashes differ.";
  return "";
}

function DeltaTable({
  baseline,
  method,
  locale,
}: {
  baseline: DemoRun[];
  method: DemoRun[];
  locale: Locale;
}) {
  return (
    <div className="table-wrap">
      <table className="runs-table runs-table--compact">
        <thead>
          <tr>
            <th>Metric</th>
            <th>{locale === "ko" ? "기준 평균" : "Baseline mean"}</th>
            <th>{locale === "ko" ? "방법 평균" : "Method mean"}</th>
            <th>{locale === "ko" ? "차이" : "Delta"}</th>
            <th>{locale === "ko" ? "검토 신호" : "Review signal"}</th>
          </tr>
        </thead>
        <tbody>
          {metricKeys.map((metric) => {
            const b = metricAverage(baseline, metric);
            const m = metricAverage(method, metric);
            const delta = m - b;
            const bad = metric === "auc" ? delta < 0 : delta > 0;
            const noData = baseline.length === 0 || method.length === 0;
            return (
              <tr key={metric}>
                <td>{metric.toUpperCase()}</td>
                <td>{noData ? "—" : formatMetric(b)}</td>
                <td>{noData ? "—" : formatMetric(m)}</td>
                <td className={bad ? "delta delta--bad" : "delta delta--good"}>
                  {noData ? "—" : `${delta >= 0 ? "+" : ""}${formatMetric(delta)}`}
                </td>
                <td>{noData ? (locale === "ko" ? "적격 행 부족" : "not enough eligible rows") : bad ? (locale === "ko" ? "검토" : "review") : (locale === "ko" ? "데모 범위 내" : "within demo range")}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function localizeBlockReason(locale: Locale, reason: string): string {
  if (locale === "en") return reason;
  if (reason === "No eligible rows under the active policy.") return "활성 정책에서 적격 행이 없습니다.";
  if (reason === "One selected experiment has mixed protocol hashes.") return "선택한 실험 중 하나에 mixed protocol 해시가 있습니다.";
  if (reason === "Protocol hashes differ.") return "프로토콜 해시가 다릅니다.";
  return reason;
}
