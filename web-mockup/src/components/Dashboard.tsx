import type { DemoRun, Locale } from "../types";
import { t } from "../i18n";
import { formatPercent, groupByExperiment, metricAverage } from "../utils";
import { MetricTrendChart, PerAttackBarChart, SeedVarianceChart } from "./Charts";
import { Hint } from "./Hint";
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
  const ko = locale === "ko";
  const experiments = groupByExperiment(runs);
  const kpis = [
    { label: t(locale, "runs"), value: runs.length.toString(), note: ko ? "필터 적용" : "filtered" },
    {
      label: t(locale, "securityRegressions"),
      value: runs.filter((run) => run.gateVerdict === "security_regression").length.toString(),
      note: ko ? "검토 필요" : "needs review",
    },
    {
      label: t(locale, "claimEligible"),
      value: runs.filter((run) => run.claimEligibility.allowed).length.toString(),
      note: ko ? "연구에 쓸 수 있음" : "may back a claim",
    },
    { label: t(locale, "meanApcer"), value: formatPercent(metricAverage(runs, "apcer")), note: ko ? "낮을수록 안전" : "lower is safer" },
  ];

  return (
    <div className="page-grid">
      <Headline locale={locale} onOpenControl={onOpenControl} onSelectRun={onSelectRun} runs={runs} />
      <section className="kpi-grid" aria-label={ko ? "핵심 지표" : "Key performance indicators"}>
        {kpis.map((kpi) => (
          <MetricCard key={kpi.label} {...kpi} />
        ))}
      </section>
      <section className="card card--wide">
        <div className="section-heading section-heading--row">
          <h2>
            {ko ? "실험별 평균" : "Averages by experiment"}
            <Hint label={ko ? "그래프 읽는 법" : "How to read this chart"}>
              {ko
                ? "실험마다 APCER과 AUC의 평균입니다. APCER은 낮을수록, AUC는 높을수록 좋습니다. 둘은 방향이 반대라 따로 그렸습니다."
                : "Mean APCER and AUC per experiment. Lower APCER and higher AUC are better; their directions are opposite, so they are drawn apart."}
            </Hint>
          </h2>
        </div>
        <MetricTrendChart groups={experiments} locale={locale} />
      </section>
      <section className="card">
        <div className="section-heading">
          <h2>
            {ko ? "공격 종류별 APCER" : "APCER by attack type"}
            <Hint label={ko ? "공격 종류별 APCER 설명" : "About per-attack APCER"}>
              {ko
                ? "공격 종류마다 가짜를 진짜로 통과시킨 비율입니다. 평균이 괜찮아도 한 종류만 크게 나쁠 수 있어 따로 봅니다."
                : "How often each attack type got through. The average can look fine while one type is much worse."}
            </Hint>
          </h2>
        </div>
        <PerAttackBarChart runs={runs} locale={locale} />
      </section>
      <section className="card">
        <div className="section-heading">
          <h2>
            {ko ? "시드별 차이" : "Across seeds"}
            <Hint label={ko ? "시드 설명" : "About seeds"}>
              {ko
                ? "같은 실험을 난수 시드만 바꿔 돌린 결과입니다. 막대 차이가 크면 결과가 운에 좌우된다는 뜻입니다."
                : "The same experiment with only the random seed changed. Large differences mean the result depends on luck."}
            </Hint>
          </h2>
        </div>
        <SeedVarianceChart runs={runs} locale={locale} />
      </section>
      <section className="card card--wide">
        <div className="section-heading section-heading--row">
          <h2>{ko ? "최근 실행" : "Recent runs"}</h2>
          <span className="subtle">{ko ? "행을 누르면 상세가 열립니다" : "Click a row for detail"}</span>
        </div>
        <RunsTable locale={locale} runs={runs.slice(0, 8)} selectedRunId={selectedRun?.runId ?? ""} onSelectRun={onSelectRun} />
      </section>
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

  // `message` is the one line on screen; `detail` is what the ? adds. The short line stays
  // conditional too: it names the verdict, never "safe", and the condition line under it is
  // always visible (contract §30).
  let tone = "headline-card--calm";
  let message: string;
  let detail: string;
  if (kind === "empty") {
    message = ko ? "필터와 맞는 실행이 없습니다" : "No run matches the filters";
    detail = ko ? "헤더의 필터에서 조건을 넓히거나 초기화하세요." : "Widen or reset the filters from the header.";
  } else if (kind === "regression") {
    tone = "headline-card--alert";
    message = ko ? `보안 회귀 ${regressions}건 / 실행 ${runs.length}개` : `${regressions} security regressions in ${runs.length} runs`;
    detail = ko
      ? "적응 뒤 어떤 공격 종류의 APCER가 허용치를 넘어 나빠졌다는 뜻입니다. BPCER가 좋아졌더라도 이 판정은 뒤집히지 않습니다."
      : "After adaptation at least one attack type got worse beyond the allowed tolerance. A better BPCER does not overturn that.";
  } else if (kind === "inconclusive") {
    tone = "headline-card--watch";
    message = ko ? `판정 불가 ${inconclusive}건 · 회귀 없음` : `${inconclusive} not judged · no regression`;
    detail = ko
      ? "공격 종류별 표본이 모자라 판정을 내리지 못했습니다. 판정이 없는 것과 통과한 것은 다릅니다."
      : 'There were too few attack samples per PAI to judge. "Not judged" is not "passed".';
  } else {
    message = ko ? `실행 ${runs.length}개 모두 보안 게이트 통과` : `All ${runs.length} runs passed the gate`;
    detail = ko
      ? '"안전하다"는 뜻이 아닙니다. 이 protocol·이 시드·이 임계값 규칙 아래에서 공격 종류별 APCER가 악화되지 않았다는 뜻입니다.'
      : 'That is not "safe": per-PAI APCER did not worsen under this protocol, these seeds and this threshold policy.';
  }

  return (
    <section aria-label={ko ? "지금 봐야 할 것" : "What to look at"} className={`headline-card ${tone}`}>
      <div className="headline-card__text">
        <p className="headline-card__message">
          <span aria-hidden="true" className="headline-card__dot" />
          {message}
          <Hint align="start" label={ko ? "이 판정의 뜻" : "What this verdict means"}>
            {detail}
          </Hint>
        </p>
        <p className="headline-card__sub">
          {ko
            ? `이 protocol·시드·임계값 기준 · 연구에 쓸 수 있는 실행 ${claimable}/${runs.length}`
            : `Under this protocol, seeds and threshold · ${claimable}/${runs.length} may back a claim`}
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
