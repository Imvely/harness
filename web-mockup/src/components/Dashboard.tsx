import type { DemoRun, Locale } from "../types";
import { t } from "../i18n";
import { formatMetric, formatPercent, groupByExperiment, metricAverage } from "../utils";
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
      <section className="hero-card">
        <div className="hero-orb hero-orb--blue" aria-hidden="true" />
        <div className="hero-orb hero-orb--amber" aria-hidden="true" />
        <div>
          <p className="eyebrow">{t(locale, "researchDashboard")}</p>
          <h2>{locale === "ko" ? "실험 실행, gate, metric, PAI별 위험을 한 화면에서 봅니다." : "Explore runs, gates, metrics, and PAI-specific risk in one focused view."}</h2>
          <p>
            {locale === "ko"
              ? "W&B 스타일 탐색 경험을 연구 안전 규칙에 맞게 재구성했습니다. 표, SVG chart, detail drawer, compare panel은 모두 mock DB로 동작합니다."
              : "This workspace adapts a W&B-style exploration flow for research-safe PAD review. Tables, SVG charts, drawers, and compare panels are backed by the mock DB."}
          </p>
        </div>
        <button className="button button--primary" onClick={onOpenControl} type="button">
          {t(locale, "openControlLab")}
        </button>
      </section>
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
          <h2>Per-attack APCER</h2>
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
          <span className="subtle">{runs.length} rows</span>
        </div>
        <RunsTable locale={locale} runs={runs.slice(0, 8)} selectedRunId={selectedRun?.runId ?? ""} onSelectRun={onSelectRun} />
      </section>
      <ExperimentDrawer locale={locale} run={selectedRun} />
    </div>
  );
}
