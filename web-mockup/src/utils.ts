import type { DemoRun, GateVerdict, MetricKey, RunStatus } from "./types";

export const metricKeys: MetricKey[] = ["apcer", "bpcer", "acer", "hter", "auc"];

export function unique<T extends string | number>(values: T[]): T[] {
  return Array.from(new Set(values)).sort((a, b) => String(a).localeCompare(String(b)));
}

export function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function formatMetric(value: number): string {
  return value.toFixed(3);
}

export function shortHash(value: string): string {
  return value.slice(0, 12);
}

export function average(values: number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

export function metricAverage(runs: DemoRun[], metric: MetricKey): number {
  return average(runs.map((run) => run.metrics[metric]));
}

export function groupByExperiment(runs: DemoRun[]): Array<{ id: string; runs: DemoRun[] }> {
  return unique(runs.map((run) => run.experimentId)).map((id) => ({
    id,
    runs: runs.filter((run) => run.experimentId === id),
  }));
}

/**
 * Does a lower value of this metric mean a safer detector?
 *
 * True for every error rate (APCER, BPCER, ACER, HTER) and false for AUC, which is a ranking
 * quality score. Keeping the rule here is the point: it used to live only inside CompareView's
 * delta table, so DeltaChart coloured by raw sign and painted an AUC *gain* red while the table
 * two cards above painted the same number green.
 */
export function lowerIsBetter(metric: MetricKey): boolean {
  return metric !== "auc";
}

/** Is this change in the unsafe direction for ``metric``? */
export function isWorseDelta(metric: MetricKey, delta: number): boolean {
  return lowerIsBetter(metric) ? delta > 0 : delta < 0;
}

/**
 * Was this row fabricated in the browser rather than exported from a real run?
 *
 * ``demoOnly`` is set by the bundled demo rows and by the mock-run generator, and cleared by
 * ``dashboardLoader`` for rows that came out of ``export_dashboard_data.py``. Until now nothing
 * read it, so a row whose APCER came from an arithmetic formula looked exactly like a measured
 * one. Every surface that shows a metric has to be able to ask this question.
 */
export function isFabricatedRun(run: DemoRun): boolean {
  return run.demoOnly;
}

export function statusLabel(status: RunStatus): string {
  return status.replace("_", " ");
}

export function gateLabel(gate: GateVerdict): string {
  return gate.replace("_", " ");
}

export function classForStatus(status: RunStatus): string {
  if (status === "success") return "badge badge--success";
  if (status === "security_regression") return "badge badge--danger";
  if (status === "inconclusive") return "badge badge--warning";
  return "badge badge--muted";
}

export function classForGate(gate: GateVerdict): string {
  if (gate === "pass") return "badge badge--success";
  if (gate === "no_gate") return "badge badge--muted";
  if (gate === "security_regression" || gate === "comparison_blocked") {
    return "badge badge--danger";
  }
  return "badge badge--warning";
}
