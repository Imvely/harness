import type { DemoRun, Locale } from "../types";
import {
  average,
  formatMetric,
  formatPercent,
  isWorseDelta,
  metricAverage,
  metricKeys,
  unique,
} from "../utils";

/**
 * APCER and AUC over the filtered experiments, as two panels rather than one.
 *
 * They used to share a plot: one 0–1 axis, two lines, distinguished by colour alone — and the
 * APCER line wore `--danger`, a reserved status colour standing in for a series. Both problems
 * came from the same choice. The metrics have *opposite polarity*: a rising APCER is worse, a
 * rising AUC is better, so on one plot "up" has no single meaning and the reader has to hold two
 * contradictory rules at once. Small multiples give each metric its own panel, its own heading
 * and its own direction note, which leaves one series per panel — so neither needs a legend, and
 * neither needs colour to carry identity.
 */
export function MetricTrendChart({
  groups,
  locale = "en",
}: {
  groups: Array<{ id: string; runs: DemoRun[] }>;
  locale?: Locale;
}) {
  return (
    <div className="chart-shell">
      <div className="trend-grid">
        <TrendPanel
          domId="metric-trend"
          groups={groups}
          locale={locale}
          metric="apcer"
          title={locale === "ko" ? "실험별 APCER 추세" : "APCER trend by experiment"}
        />
        <TrendPanel
          domId="auc-trend"
          groups={groups}
          locale={locale}
          metric="auc"
          title={locale === "ko" ? "실험별 AUC 추세" : "AUC trend by experiment"}
        />
      </div>
      <table className="sr-only">
        <caption>Metric trend data</caption>
        <thead>
          <tr>
            <th scope="col">Experiment</th>
            <th scope="col">Mean APCER</th>
            <th scope="col">Mean AUC</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => (
            <tr key={group.id}>
              <td>{group.id}</td>
              <td>{formatMetric(metricAverage(group.runs, "apcer"))}</td>
              <td>{formatMetric(metricAverage(group.runs, "auc"))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TrendPanel({
  groups,
  metric,
  title,
  domId,
  locale,
}: {
  groups: Array<{ id: string; runs: DemoRun[] }>;
  metric: "apcer" | "auc";
  title: string;
  domId: string;
  locale: Locale;
}) {
  const width = 440;
  const height = 220;
  const padding = 40;
  // Both metrics are proportions, so both panels keep the full 0–1 range. Auto-scaling each to
  // its own data would make a 0.01 spread look like a cliff.
  const points = groups.map((group, index) => {
    const value = metricAverage(group.runs, metric);
    return {
      id: group.id,
      value,
      x: padding + (index * (width - padding * 2)) / Math.max(groups.length - 1, 1),
      y: height - padding - value * (height - padding * 2),
    };
  });
  // Axis labels were a fixed 12 characters whatever the spacing, so six experiments in one
  // panel ran into each other. Each label now gets the characters its slot can hold.
  const slot = (width - padding * 2) / Math.max(groups.length - 1, 1);
  const labelChars = Math.max(4, Math.floor(slot / 6.4));
  const direction =
    metric === "apcer"
      ? locale === "ko"
        ? "낮을수록 안전"
        : "lower is safer"
      : locale === "ko"
        ? "높을수록 좋음"
        : "higher is better";
  const description =
    metric === "apcer"
      ? locale === "ko"
        ? "필터 적용 실험별 평균 APCER입니다. 낮을수록 안전합니다."
        : "Mean APCER for each filtered experiment. Lower is safer."
      : locale === "ko"
        ? "필터 적용 실험별 평균 AUC입니다. 높을수록 좋습니다."
        : "Mean AUC for each filtered experiment. Higher is better.";

  return (
    <figure className="trend-panel">
      <figcaption>
        {/* The panel names its one series, so no legend box is needed. */}
        <strong>{metric.toUpperCase()}</strong>
        <span>{direction}</span>
      </figcaption>
      <svg role="img" aria-labelledby={`${domId}-title ${domId}-desc`} viewBox={`0 0 ${width} ${height}`}>
        <title id={`${domId}-title`}>{title}</title>
        <desc id={`${domId}-desc`}>{description}</desc>
        <line className="axis" x1={padding} x2={width - padding} y1={height - padding} y2={height - padding} />
        <line className="axis" x1={padding} x2={padding} y1={padding} y2={height - padding} />
        <polyline className="line line--series" fill="none" points={points.map((p) => `${p.x},${p.y}`).join(" ")} />
        {points.map((point) => (
          <g key={point.id}>
            {/* Hovering a point names it in full; the axis label below may be cut short. */}
            <title>{`${point.id}: ${formatMetric(point.value)}`}</title>
            {/* A surface-coloured ring so overlapping markers stay countable. */}
            <circle className="dot dot--series" cx={point.x} cy={point.y} r="5" />
            <text className="chart-value" x={point.x} y={point.y - 11} textAnchor="middle">
              {formatMetric(point.value)}
            </text>
            <text className="chart-label" x={point.x} y={height - 14} textAnchor="middle">
              {axisLabel(point.id, labelChars)}
            </text>
          </g>
        ))}
      </svg>
    </figure>
  );
}

/** An experiment id shortened to `chars`: the `exp_` and dataset prefixes go first, then the tail. */
export function axisLabel(id: string, chars: number): string {
  const bare = id.replace(/^exp_/, "").replace(/^(syn|demo)_/, "");
  return bare.length > chars ? `${bare.slice(0, Math.max(1, chars - 1))}…` : bare;
}

export function PerAttackBarChart({ runs, locale = "en" }: { runs: DemoRun[]; locale?: Locale }) {
  // The PAI list comes from the data. A hardcoded list drew absent attacks as 0.0% APCER
  // (average([]) is 0, which reads as a perfect score) and omitted PAI species the runs
  // actually contain, such as print_high_quality or a 3D mask.
  const apcerByPai = new Map<string, number[]>();
  for (const run of runs) {
    for (const item of run.perAttack) {
      const values = apcerByPai.get(item.pai) ?? [];
      values.push(item.apcer);
      apcerByPai.set(item.pai, values);
    }
  }
  const data = [...apcerByPai.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([pai, values]) => ({ pai, value: average(values) }));

  if (data.length === 0) {
    return (
      <p className="empty-note">
        {locale === "ko"
          ? "선택된 run에 공격 종류별 APCER가 없습니다."
          : "The selected runs carry no per-attack APCER."}
      </p>
    );
  }

  return (
    <div className="bar-chart" role="img" aria-label={locale === "ko" ? "공격 종류별 평균 APCER 차트" : "Mean per-attack APCER chart"}>
      {data.map((item) => (
        <div className="bar-row" key={item.pai}>
          <span>{item.pai}</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${Math.min(item.value * 100, 100)}%` }} />
          </div>
          <strong>{formatPercent(item.value)}</strong>
        </div>
      ))}
      <table className="sr-only">
        <caption>Per-attack APCER data</caption>
        <thead>
          <tr>
            <th scope="col">PAI</th>
            <th scope="col">Mean APCER</th>
          </tr>
        </thead>
        <tbody>
          {data.map((item) => (
            <tr key={item.pai}>
              <td>{item.pai}</td>
              <td>{formatMetric(item.value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SeedVarianceChart({ runs, locale = "en" }: { runs: DemoRun[]; locale?: Locale }) {
  const seeds = unique(runs.map((run) => run.seed));
  const data = seeds.map((seed) => ({
    seed,
    apcer: metricAverage(runs.filter((run) => run.seed === seed), "apcer"),
  }));
  return (
    <div className="seed-chart" role="img" aria-label={locale === "ko" ? "시드별 APCER" : "APCER by seed"}>
      {data.map((item) => (
        <div className="seed-column" key={item.seed}>
          <div className="seed-bar" style={{ height: `${Math.max(item.apcer * 360, 24)}px` }} />
          <span>seed {item.seed}</span>
          <strong>{formatMetric(item.apcer)}</strong>
        </div>
      ))}
      <table className="sr-only">
        <caption>Seed variance data</caption>
        <thead>
          <tr>
            <th scope="col">Seed</th>
            <th scope="col">APCER</th>
          </tr>
        </thead>
        <tbody>
          {data.map((item) => (
            <tr key={item.seed}>
              <td>{item.seed}</td>
              <td>{formatMetric(item.apcer)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DeltaChart({
  baseline,
  method,
  locale = "en",
}: {
  baseline: DemoRun[];
  method: DemoRun[];
  locale?: Locale;
}) {
  const data = metricKeys.map((metric) => {
    const delta = metricAverage(method, metric) - metricAverage(baseline, metric);
    return { metric, delta, worse: isWorseDelta(metric, delta) };
  });
  return (
    <div className="delta-chart" role="img" aria-label={locale === "ko" ? "지표 차이 차트" : "Metric delta chart"}>
      {data.map((item) => {
        const offset = Math.min(Math.abs(item.delta) * 400, 96);
        return (
          <div className="delta-row" key={item.metric}>
            <span>{item.metric.toUpperCase()}</span>
            <div className="delta-track">
              <i className="zero-line" />
              {/* Colour follows the safety direction, not the sign. AUC is the one metric where
                  a rise is an improvement, so colouring by sign painted an AUC gain red while
                  CompareView's delta table painted the same number green. */}
              <i
                className={item.worse ? "delta-fill delta-fill--worse" : "delta-fill delta-fill--better"}
                style={
                  item.delta >= 0 ? { left: "50%", width: `${offset}px` } : { right: "50%", width: `${offset}px` }
                }
              />
            </div>
            {/* The sign alone does not say whether the change is good, and the direction that
                means "good" flips for AUC. Name the judgement in words rather than an arrow. */}
            <strong className={item.worse ? "delta--bad" : "delta--good"}>
              {item.delta >= 0 ? "+" : ""}
              {formatMetric(item.delta)}
              <em>{item.worse ? (locale === "ko" ? "악화" : "worse") : locale === "ko" ? "개선" : "better"}</em>
            </strong>
          </div>
        );
      })}
      <table className="sr-only">
        <caption>Metric delta data</caption>
        <thead>
          <tr>
            <th scope="col">Metric</th>
            <th scope="col">Delta</th>
            <th scope="col">Direction</th>
          </tr>
        </thead>
        <tbody>
          {data.map((item) => (
            <tr key={item.metric}>
              <td>{item.metric}</td>
              <td>{formatMetric(item.delta)}</td>
              <td>{item.worse ? "worse" : "better"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
