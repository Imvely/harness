import type { DemoRun, Locale } from "../types";
import { t } from "../i18n";
import { formatPercent, groupByExperiment, metricAverage } from "../utils";
import { MetricTrendChart, PerAttackBarChart, SeedVarianceChart } from "./Charts";
import { ExperimentDrawer } from "./ExperimentDrawer";
import { MetricCard } from "./MetricCard";
import { RunsTable } from "./RunsTable";

export function Dashboard({
  runs,
  selectedRun,
  locale,
  onSelectRun,
  onOpenControl,
}: {
  runs: DemoRun[];
  // Optional on purpose: with an empty database there is no run to select, and reading
  // `selectedRun.runId` on undefined used to blank the whole page — the first thing a new
  // user would hit after a filter that matches nothing.
  selectedRun: DemoRun | undefined;
  locale: Locale;
  onSelectRun: (runId: string) => void;
  onOpenControl: () => void;
}) {
  const experiments = groupByExperiment(runs);
  const kpis = [
    { label: t(locale, "runs"), value: runs.length.toString(), note: t(locale, "filtered") },
    {
      label: t(locale, "securityRegressions"),
      value: runs.filter((run) => run.gateVerdict === "security_regression").length.toString(),
      note: locale === "ko" ? "검토 필요" : "needs review",
    },
    {
      label: t(locale, "claimEligible"),
      value: runs.filter((run) => run.claimEligibility.allowed).length.toString(),
      note: locale === "ko" ? "데모 데이터는 차단" : "blocked for demo data",
    },
    { label: t(locale, "meanApcer"), value: formatPercent(metricAverage(runs, "apcer")), note: locale === "ko" ? "낮을수록 안전" : "lower is safer" },
  ];

  return (
    <div className="page-grid">
      <Headline locale={locale} onOpenControl={onOpenControl} onSelectRun={onSelectRun} runs={runs} />
      <section className="kpi-grid" aria-label={locale === "ko" ? "핵심 지표" : "Key performance indicators"}>
        {kpis.map((kpi) => (
          <MetricCard key={kpi.label} {...kpi} />
        ))}
      </section>
      <section className="card card--wide">
        <div className="section-heading section-heading--row">
          <div>
            <p className="eyebrow">{t(locale, "metricTrend")}</p>
            <h2>{locale === "ko" ? "실험 평균" : "Experiment averages"}</h2>
          </div>
          <span className="subtle">{locale === "ko" ? "필터 적용 실행만" : "Filtered runs only"}</span>
        </div>
        <MetricTrendChart groups={experiments} locale={locale} />
      </section>
      <section className="card">
        <div className="section-heading">
          <p className="eyebrow">{t(locale, "paiFocus")}</p>
          <h2>{locale === "ko" ? "공격 종류별 APCER" : "Per-attack APCER"}</h2>
        </div>
        <PerAttackBarChart runs={runs} locale={locale} />
      </section>
      <section className="card">
        <div className="section-heading">
          <p className="eyebrow">{t(locale, "seedCheck")}</p>
          <h2>{locale === "ko" ? "시드 편차" : "Seed variance"}</h2>
        </div>
        <SeedVarianceChart runs={runs} locale={locale} />
      </section>
      <section className="card card--wide">
        <div className="section-heading section-heading--row">
          <div>
            <p className="eyebrow">{t(locale, "recentRuns")}</p>
            <h2>{locale === "ko" ? "행을 눌러 출처를 확인" : "Click a row for provenance"}</h2>
          </div>
          <span className="subtle">{runs.length} {locale === "ko" ? "행" : "rows"}</span>
        </div>
        <RunsTable locale={locale} runs={runs.slice(0, 8)} selectedRunId={selectedRun?.runId ?? ""} onSelectRun={onSelectRun} />
      </section>
      <ExperimentDrawer locale={locale} run={selectedRun} />
    </div>
  );
}

/**
 * The plain-language answer to "is there anything I should look at".
 *
 * This slot used to hold a card describing the product — "a W&B-style exploration flow adapted
 * for research-safe PAD review" — in a heading larger than the page title. It said nothing about
 * the reader's data, and it outranked the one line that did.
 *
 * The wording stays conditional on purpose (contract §30). "No regression in this filter" is
 * not "safe": the verdict is bounded by this protocol, these seeds and this threshold policy,
 * and saying otherwise is the false confidence the gate exists to prevent.
 */
export type HeadlineKind = "empty" | "regression" | "inconclusive" | "clear";

export interface HeadlineState {
  kind: HeadlineKind;
  regressions: number;
  inconclusive: number;
  claimable: number;
  /** The run the primary button opens, or null when nothing is owed attention. */
  urgent: DemoRun | null;
}

/**
 * Which of the four things the dashboard has to say, and which run to point at.
 *
 * Separated from the copy so the precedence can be tested. The order matters and is not
 * arbitrary: a regression outranks an inconclusive verdict, and an inconclusive verdict outranks
 * a clear one, because "could not be judged" must never be presented as "passed".
 */
export function headlineState(runs: DemoRun[]): HeadlineState {
  const regressions = runs.filter((run) => run.gateVerdict === "security_regression");
  const inconclusive = runs.filter((run) => run.gateVerdict === "inconclusive");
  const claimable = runs.filter((run) => run.claimEligibility.allowed);
  // Worst first within the most serious category, so the button goes where attention is owed.
  const byApcer = (rows: DemoRun[]) => [...rows].sort((a, b) => b.metrics.apcer - a.metrics.apcer)[0] ?? null;
  const kind: HeadlineKind =
    runs.length === 0
      ? "empty"
      : regressions.length > 0
        ? "regression"
        : inconclusive.length > 0
          ? "inconclusive"
          : "clear";
  return {
    kind,
    regressions: regressions.length,
    inconclusive: inconclusive.length,
    claimable: claimable.length,
    urgent: byApcer(regressions) ?? byApcer(inconclusive),
  };
}

function Headline({
  runs,
  locale,
  onSelectRun,
  onOpenControl,
}: {
  runs: DemoRun[];
  locale: Locale;
  onSelectRun: (runId: string) => void;
  onOpenControl: () => void;
}) {
  const ko = locale === "ko";
  const { kind, regressions, inconclusive, claimable, urgent } = headlineState(runs);

  let tone = "headline-card--calm";
  let message: string;
  if (kind === "empty") {
    message = ko
      ? "지금 필터와 맞는 실행이 없습니다. 왼쪽 필터를 넓히거나 초기화해 보세요."
      : "No run matches the current filters. Widen or reset them on the left.";
  } else if (kind === "regression") {
    tone = "headline-card--alert";
    message = ko
      ? `실행 ${runs.length}개 중 ${regressions}개에서 보안 회귀가 잡혔습니다. 적응 뒤 어떤 공격 종류의 APCER가 허용치를 넘어 나빠졌다는 뜻이고, BPCER가 좋아졌더라도 이 판정은 뒤집히지 않습니다.`
      : `${regressions} of ${runs.length} runs came back with a security regression: after adaptation at least one attack type got worse beyond the allowed tolerance. A better BPCER does not overturn that.`;
  } else if (kind === "inconclusive") {
    tone = "headline-card--watch";
    message = ko
      ? `보안 회귀 판정은 없지만, ${inconclusive}개는 공격 종류별 표본이 모자라 판정을 내리지 못했습니다. 판정이 없는 것과 통과한 것은 다릅니다.`
      : `No run came back as a regression, but ${inconclusive} could not be judged for lack of attack samples per PAI. "Not judged" is not "passed".`;
  } else {
    message = ko
      ? `실행 ${runs.length}개 모두 보안 회귀 판정 없이 통과했습니다. 이것은 "안전하다"는 뜻이 아니라, 이 protocol·이 시드·이 임계값 규칙 아래에서 공격 종류별 APCER가 악화되지 않았다는 뜻입니다.`
      : `All ${runs.length} runs passed the gate. That is not "safe": it means per-PAI APCER did not worsen under this protocol, these seeds and this threshold policy.`;
  }

  return (
    <section aria-label={ko ? "지금 봐야 할 것" : "What to look at"} className={`headline-card ${tone}`}>
      <div>
        <p className="eyebrow">{ko ? "지금 봐야 할 것" : "What to look at"}</p>
        <p className="headline-card__message">{message}</p>
        <p className="headline-card__sub">
          {ko
            ? `연구 주장에 쓸 수 있는 실행 ${claimable}개 / ${runs.length}개.`
            : `${claimable} of ${runs.length} runs may back a research claim.`}
        </p>
      </div>
      <div className="button-row">
        {urgent && (
          <button className="button button--primary" onClick={() => onSelectRun(urgent.runId)} type="button">
            {ko ? "가장 시급한 실행 보기" : "Open the most urgent run"}
          </button>
        )}
        <button className="button button--secondary" onClick={onOpenControl} type="button">
          {t(locale, "openControlLab")}
        </button>
      </div>
    </section>
  );
}
