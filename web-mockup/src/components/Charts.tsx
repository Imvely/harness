import type { DemoRun, Locale } from "../types";
import { average, formatMetric, formatPercent, metricAverage, metricKeys, unique } from "../utils";

export function MetricTrendChart({
  groups,
  locale = "en",
}: {
  groups: Array<{ id: string; runs: DemoRun[] }>;
  locale?: Locale;
}) {
  const width = 900;
  const height = 260;
  const padding = 48;
  const points = groups.map((group, index) => {
    const x = padding + (index * (width - padding * 2)) / Math.max(groups.length - 1, 1);
    const apcer = metricAverage(group.runs, "apcer");
    const auc = metricAverage(group.runs, "auc");
    return {
      id: group.id,
      x,
      apcerY: height - padding - apcer * (height - padding * 2),
      aucY: height - padding - auc * (height - padding * 2),
    };
  });
  const line = (selector: "apcerY" | "aucY") =>
    points.map((point) => `${point.x},${point[selector]}`).join(" ");

  return (
    <div className="chart-shell">
      <svg role="img" aria-labelledby="metric-trend-title metric-trend-desc" viewBox={`0 0 ${width} ${height}`}>
        <title id="metric-trend-title">{locale === "ko" ? "실험별 APCER와 AUC 추세" : "APCER and AUC trend by experiment"}</title>
        <desc id="metric-trend-desc">
          {locale === "ko"
            ? "선은 필터 적용 실험별 평균 APCER와 평균 AUC를 보여줍니다. 낮은 APCER가 더 안전합니다."
            : "Lines show mean APCER and mean AUC for each filtered experiment. Lower APCER is safer."}
        </desc>
        <line className="axis" x1={padding} x2={width - padding} y1={height - padding} y2={height - padding} />
        <line className="axis" x1={padding} x2={padding} y1={padding} y2={height - padding} />
        <polyline className="line line--danger" fill="none" points={line("apcerY")} />
        <polyline className="line line--blue" fill="none" points={line("aucY")} />
        {points.map((point) => (
          <g key={point.id}>
            <circle className="dot dot--danger" cx={point.x} cy={point.apcerY} r="5" />
            <circle className="dot dot--blue" cx={point.x} cy={point.aucY} r="5" />
            <text className="chart-label" x={point.x} y={height - 16} textAnchor="middle">
              {point.id.replace("exp_", "").slice(0, 14)}
            </text>
          </g>
        ))}
      </svg>
      <div className="legend">
        <span><i className="legend-dot legend-dot--danger" /> APCER</span>
        <span><i className="legend-dot legend-dot--blue" /> AUC</span>
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
  const data = metricKeys.map((metric) => ({
    metric,
    delta: metricAverage(method, metric) - metricAverage(baseline, metric),
  }));
  return (
    <div className="delta-chart" role="img" aria-label={locale === "ko" ? "지표 차이 차트" : "Metric delta chart"}>
      {data.map((item) => {
        const offset = Math.min(Math.abs(item.delta) * 400, 96);
        return (
          <div className="delta-row" key={item.metric}>
            <span>{item.metric.toUpperCase()}</span>
            <div className="delta-track">
              <i className="zero-line" />
              <i
                className={item.delta >= 0 ? "delta-fill delta-fill--positive" : "delta-fill delta-fill--negative"}
                style={
                  item.delta >= 0 ? { left: "50%", width: `${offset}px` } : { right: "50%", width: `${offset}px` }
                }
              />
            </div>
            <strong>{item.delta >= 0 ? "+" : ""}{formatMetric(item.delta)}</strong>
          </div>
        );
      })}
      <table className="sr-only">
        <caption>Metric delta data</caption>
        <thead>
          <tr>
            <th scope="col">Metric</th>
            <th scope="col">Delta</th>
          </tr>
        </thead>
        <tbody>
          {data.map((item) => (
            <tr key={item.metric}>
              <td>{item.metric}</td>
              <td>{formatMetric(item.delta)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
