import { demoRuns } from "../data/demoRuns";
import type { DemoRun, Filters, Locale } from "../types";
import { t } from "../i18n";
import { formatMetric, formatPercent, unique } from "../utils";

export function filterRuns(runs = demoRuns, filters: Filters) {
  return runs.filter((run) => {
    const query = filters.query.trim().toLowerCase();
    const matchesQuery =
      query.length === 0 ||
      [
        run.experimentId,
        run.runId,
        run.title,
        run.protocolId,
        run.protocolHash,
        run.scienceHash,
        run.specHash,
        run.modelFamily,
        run.adaptationMethod,
        ...run.tags,
      ]
        .join(" ")
        .toLowerCase()
        .includes(query);
    return (
      matchesQuery &&
      (filters.status === "all" || run.status === filters.status) &&
      (filters.mode === "all" || run.mode === filters.mode) &&
      (filters.modelFamily === "all" || run.modelFamily === filters.modelFamily) &&
      (filters.adaptationMethod === "all" || run.adaptationMethod === filters.adaptationMethod) &&
      (filters.protocolId === "all" || run.protocolId === filters.protocolId) &&
      (filters.gateVerdict === "all" || run.gateVerdict === filters.gateVerdict) &&
      (filters.seed === "all" || String(run.seed) === filters.seed) &&
      (filters.includeSmoke || run.mode !== "smoke") &&
      (!filters.syntheticOnly || run.piiPolicy === "synthetic") &&
      run.metrics.apcer <= filters.maxApcer &&
      run.metrics.auc >= filters.minAuc
    );
  });
}

export function FilterPanel({
  availableRuns = demoRuns,
  filters,
  locale,
  onChange,
  onReset,
}: {
  availableRuns?: DemoRun[];
  filters: Filters;
  locale: Locale;
  onChange: (filters: Filters) => void;
  onReset: () => void;
}) {
  const statuses = unique(availableRuns.map((run) => run.status));
  const modes = unique(availableRuns.map((run) => run.mode));
  const families = unique(availableRuns.map((run) => run.modelFamily));
  const methods = unique(availableRuns.map((run) => run.adaptationMethod));
  const protocols = unique(availableRuns.map((run) => run.protocolId));
  const gates = unique(availableRuns.map((run) => run.gateVerdict));
  const seeds = unique(availableRuns.map((run) => run.seed)).map(String);

  return (
    <details className="sidebar-section sidebar-filter-section">
      <summary className="sidebar-section__summary">
        <span>
          <span className="eyebrow">{t(locale, "viewFilters")}</span>
          <strong>{locale === "ko" ? "실행 걸러보기" : "Slice runs"}</strong>
        </span>
        <span className="sidebar-section__chevron" aria-hidden="true">⌄</span>
      </summary>
      <section className="filter-panel" aria-label={locale === "ko" ? "실행 필터" : "Run filters"}>
      <label className="field">
        {t(locale, "search")}
        <input
          value={filters.query}
          onChange={(event) => onChange({ ...filters, query: event.target.value })}
          placeholder={locale === "ko" ? "실험, 실행, 방법" : "experiment, run, method"}
          type="search"
        />
      </label>
      <SelectField label={t(locale, "status")} locale={locale} value={filters.status} values={statuses} onChange={(value) => onChange({ ...filters, status: value as Filters["status"] })} />
      <SelectField label="Mode" locale={locale} value={filters.mode} values={modes} onChange={(value) => onChange({ ...filters, mode: value as Filters["mode"] })} />
      <SelectField label={t(locale, "model")} locale={locale} value={filters.modelFamily} values={families} onChange={(value) => onChange({ ...filters, modelFamily: value as Filters["modelFamily"] })} />
      <SelectField label={t(locale, "adaptation")} locale={locale} value={filters.adaptationMethod} values={methods} onChange={(value) => onChange({ ...filters, adaptationMethod: value as Filters["adaptationMethod"] })} />
      <SelectField label={t(locale, "protocol")} locale={locale} value={filters.protocolId} values={protocols} onChange={(value) => onChange({ ...filters, protocolId: value })} />
      <SelectField label={t(locale, "gate")} locale={locale} value={filters.gateVerdict} values={gates} onChange={(value) => onChange({ ...filters, gateVerdict: value as Filters["gateVerdict"] })} />
      <SelectField label={t(locale, "seed")} locale={locale} value={filters.seed} values={seeds} onChange={(value) => onChange({ ...filters, seed: value })} />
      <label className="range-field">
        <span>Max APCER: {formatPercent(filters.maxApcer)}</span>
        <input max="0.5" min="0" step="0.01" type="range" value={filters.maxApcer} onChange={(event) => onChange({ ...filters, maxApcer: Number(event.target.value) })} />
      </label>
      <label className="range-field">
        <span>Min AUC: {formatMetric(filters.minAuc)}</span>
        <input max="1" min="0" step="0.01" type="range" value={filters.minAuc} onChange={(event) => onChange({ ...filters, minAuc: Number(event.target.value) })} />
      </label>
      <label className="check-field">
        <input checked={filters.includeSmoke} onChange={(event) => onChange({ ...filters, includeSmoke: event.target.checked })} type="checkbox" />
        {t(locale, "includeSmoke")}
      </label>
      <label className="check-field">
        <input checked={filters.syntheticOnly} onChange={(event) => onChange({ ...filters, syntheticOnly: event.target.checked })} type="checkbox" />
        {locale === "ko" ? "합성 데이터만" : "Synthetic only"}
      </label>
      <button className="button button--secondary" onClick={onReset} type="button">
        {locale === "ko" ? "필터 초기화" : "Reset filters"}
      </button>
      </section>
    </details>
  );
}

export function SelectField({
  label,
  value,
  values,
  locale = "en",
  onChange,
}: {
  label: string;
  value: string;
  values: string[];
  locale?: Locale;
  onChange: (value: string) => void;
}) {
  return (
    <label className="field">
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="all">{locale === "ko" ? "전체" : "All"}</option>
        {values.map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </select>
    </label>
  );
}

export function SelectBox({
  label,
  value,
  values,
  onChange,
}: {
  label: string;
  value: string;
  values: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="field field--inline">
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {values.map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </select>
    </label>
  );
}
