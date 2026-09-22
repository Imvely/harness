import { useMemo, useState } from "react";
import type { DemoRun, Locale } from "../types";
import { t } from "../i18n";
import {
  formatMetric,
  isFabricatedRun,
  isWorseDelta,
  metricAverage,
  metricKeys,
  shortHash,
  unique,
} from "../utils";
import { DeltaChart } from "./Charts";
import { MetricRow } from "./ExpandableRow";
import { SelectBox } from "./FilterPanel";
import { Hint } from "./Hint";

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
  // Fabricated rows never enter a comparison (see comparisonRuns), so on the bundled sample
  // data every comparison is blocked. That is correct, and the screen says so in one line
  // rather than as three warnings that read like something is broken.
  const selected = [...baselineAll, ...methodAll];
  const onlyFabricated = selected.length > 0 && selected.every(isFabricatedRun);
  const blockReason = onlyFabricated ? SAMPLE_ONLY : comparisonBlockReason(baselineProtocol, methodProtocol);
  const excludedCount = baselineAll.length + methodAll.length - baseline.length - method.length;

  return (
    <div className="page-grid page-grid--compare">
      <section className="card card--wide">
        <div className="section-heading">
          <h2>
            {locale === "ko" ? "무엇과 무엇을 비교할까요?" : "What to compare"}
            <Hint label={locale === "ko" ? "비교 규칙" : "Comparison rules"}>
              {locale === "ko"
                ? "두 실험의 protocol hash가 같을 때만 차이를 계산합니다. 모의 값은 어떤 설정에서도 평균에 넣지 않습니다."
                : "Deltas are computed only when both share one protocol hash. Mock values never enter an average, under any setting."}
            </Hint>
          </h2>
        </div>
        <div className="compare-selectors">
          <SelectBox label={t(locale, "baseline")} value={baselineId} values={experiments} onChange={onBaselineChange} />
          <SelectBox label={t(locale, "method")} value={methodId} values={experiments} onChange={onMethodChange} />
          {/* Worded apart from the sidebar's "include smoke rows", which starts on. This one
              starts off and means something stricter: whether smoke runs may enter an average
              that a delta is computed from. Identical labels with opposite defaults read as a
              bug. */}
          <label className="check-field check-field--large">
            <input checked={includeSmoke} onChange={(event) => setIncludeSmoke(event.target.checked)} type="checkbox" />
            {locale === "ko" ? "비교 계산에 스모크 실행도 포함" : "Average smoke runs into the comparison"}
          </label>
          <label className="check-field check-field--large">
            <input checked={includeRisky} onChange={(event) => setIncludeRisky(event.target.checked)} type="checkbox" />
            {locale === "ko"
              ? "게이트가 통과가 아닌 실행도 포함"
              : "Include runs whose gate did not pass"}
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
          <h2>{locale === "ko" ? "지표 차이" : "Metric deltas"}</h2>
          <span className="subtle">
            {locale === "ko" ? "APCER·BPCER·ACER·HTER 낮을수록, AUC 높을수록 좋음" : "Lower APCER·BPCER·ACER·HTER, higher AUC is better"}
          </span>
        </div>
        {comparable ? (
          <DeltaTable baseline={baseline} method={method} locale={locale} />
        ) : (
          <BlockedComparison locale={locale} reason={blockReason} />
        )}
      </section>
      <section className="card">
        <div className="section-heading">
          <h2>{locale === "ko" ? "방법 - 기준" : "Method minus baseline"}</h2>
        </div>
        {comparable ? (
          <DeltaChart baseline={baseline} method={method} locale={locale} />
        ) : (
          <p className="empty-note">{locale === "ko" ? "비교가 성립하면 여기에 그려집니다." : "Drawn here once the comparison holds."}</p>
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

export function comparisonRuns(
  runs: DemoRun[],
  policy: { includeSmoke: boolean; includeRisky: boolean },
): DemoRun[] {
  return runs.filter((run) => {
    // Never, under any toggle. A fabricated row's metrics were computed by the browser from
    // methodOffsets() and a seeded jitter, so averaging one into a baseline or a method makes
    // the delta a statement about mockDb's arithmetic rather than about either experiment.
    // The smoke and risky switches are policy choices; this one is not offered.
    if (isFabricatedRun(run)) return false;
    if (!policy.includeSmoke && run.mode === "smoke") return false;
    if (!policy.includeRisky && !["pass", "no_gate"].includes(run.gateVerdict)) return false;
    return true;
  });
}

const SAMPLE_ONLY = "Sample rows are never compared. Export real runs to see deltas here.";

function BlockedComparison({ locale, reason }: { locale: Locale; reason: string }) {
  return (
    <div className="comparison-alert" role="status">
      <strong>{locale === "ko" ? "비교 수치 차단됨" : "Delta values blocked"}</strong>
      <span>{localizeBlockReason(locale, reason)}</span>
    </div>
  );
}

/**
 * A baseline and a method that compare under the default policy, for the first render.
 *
 * Opening the screen on two identical experiments, or on a pair that shares no protocol hash,
 * greeted a new reader with "blocked". The baseline is the first eligible source-only
 * experiment; the method is another eligible experiment under the same protocol hash.
 */
export function defaultComparisonPair(runs: DemoRun[]): { baseline: string; method: string } | null {
  const eligible = comparisonRuns(runs, { includeSmoke: false, includeRisky: false });
  const baseline = eligible.find((run) => run.adaptationMethod === "none") ?? eligible[0];
  if (!baseline) return null;
  const method = eligible.find(
    (run) => run.experimentId !== baseline.experimentId && run.protocolHash === baseline.protocolHash,
  );
  return method ? { baseline: baseline.experimentId, method: method.experimentId } : null;
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
            const bad = isWorseDelta(metric, delta);
            const noData = baseline.length === 0 || method.length === 0;
            return (
              <MetricRow colSpan={5} key={metric} locale={locale} metric={metric}>
                <td>{noData ? "—" : formatMetric(b)}</td>
                <td>{noData ? "—" : formatMetric(m)}</td>
                <td className={bad ? "delta delta--bad" : "delta delta--good"}>
                  {noData ? "—" : `${delta >= 0 ? "+" : ""}${formatMetric(delta)}`}
                </td>
                <td>{noData ? (locale === "ko" ? "적격 행 부족" : "not enough eligible rows") : bad ? (locale === "ko" ? "검토" : "review") : (locale === "ko" ? "데모 범위 내" : "within demo range")}</td>
              </MetricRow>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function localizeBlockReason(locale: Locale, reason: string): string {
  if (locale === "en") return reason;
  if (reason === SAMPLE_ONLY) return "예시 데이터로는 차이를 계산하지 않습니다. 실제 실행 결과를 내보내면 여기에 나옵니다.";
  if (reason === "No eligible rows under the active policy.") return "활성 정책에서 적격 행이 없습니다.";
  if (reason === "One selected experiment has mixed protocol hashes.") return "선택한 실험 중 하나에 mixed protocol 해시가 있습니다.";
  if (reason === "Protocol hashes differ.") return "프로토콜 해시가 다릅니다.";
  return reason;
}
