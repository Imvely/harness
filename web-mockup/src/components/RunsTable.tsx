import type { DemoRun, Locale } from "../types";
import { useMemo, useState } from "react";
import { gateText, modeText, statusText, t } from "../i18n";
import type { GlossaryId } from "../glossary";
import { glossaryEntry } from "../glossary";
import { TermMark } from "./Glossary";
import {
  classForGate,
  classForStatus,
  formatMetric,
  isFabricatedRun,
  shortHash,
} from "../utils";

type SortKey =
  | "experimentId"
  | "status"
  | "mode"
  | "modelFamily"
  | "adaptationMethod"
  | "apcer"
  | "bpcer"
  | "acer"
  | "hter"
  | "auc"
  | "gateVerdict"
  | "protocolHash"
  | "seed";

type SortState = {
  key: SortKey;
  direction: "asc" | "desc";
};

export function RunsTable({
  runs,
  selectedRunId,
  locale = "en",
  onSelectRun,
}: {
  runs: DemoRun[];
  selectedRunId: string;
  locale?: Locale;
  onSelectRun: (runId: string) => void;
}) {
  const [sort, setSort] = useState<SortState>({ key: "apcer", direction: "asc" });
  const sortedRuns = useMemo(() => {
    return [...runs].sort((a, b) => {
      const av = sortValue(a, sort.key);
      const bv = sortValue(b, sort.key);
      const base =
        typeof av === "number" && typeof bv === "number"
          ? av - bv
          : String(av).localeCompare(String(bv));
      return sort.direction === "asc" ? base : -base;
    });
  }, [runs, sort]);
  const requestSort = (key: SortKey) => {
    setSort((current) => ({
      key,
      direction: current.key === key && current.direction === "asc" ? "desc" : "asc",
    }));
  };
  const th = (key: SortKey, label: string, termId?: GlossaryId) => (
    <SortableTh
      active={sort.key === key}
      direction={sort.direction}
      label={label}
      locale={locale}
      onSort={() => requestSort(key)}
      termId={termId}
    />
  );
  /**
   * A column whose header is a bare acronym.
   *
   * In Korean the acronym stays the headline and the Korean name sits under it in smaller type.
   * Putting the Korean name first would widen five columns at once, and the acronym is what the
   * reports, the registry and the papers all print — the reader has to learn it either way.
   */
  const metricTh = (key: SortKey, acronym: string, termId: GlossaryId) => (
    <SortableTh
      active={sort.key === key}
      direction={sort.direction}
      label={acronym}
      locale={locale}
      onSort={() => requestSort(key)}
      sublabel={locale === "ko" ? (glossaryEntry(termId)?.ko ?? null) : null}
      termId={termId}
    />
  );

  return (
    <div className="table-wrap">
      <table className="runs-table">
        <thead>
          <tr>
            {th("experimentId", t(locale, "experiment"))}
            {th("status", t(locale, "status"))}
            {th("mode", t(locale, "mode"), "smoke")}
            {th("modelFamily", t(locale, "model"))}
            {th("adaptationMethod", t(locale, "adaptation"), "adaptation")}
            {metricTh("apcer", "APCER", "apcer")}
            {metricTh("bpcer", "BPCER", "bpcer")}
            {metricTh("acer", "ACER", "acer")}
            {metricTh("hter", "HTER", "hter")}
            {metricTh("auc", "AUC", "auc")}
            {th("gateVerdict", t(locale, "gate"), "gate-verdict")}
            {th("protocolHash", t(locale, "protocol"), "protocol-hash")}
            {th("seed", t(locale, "seed"), "seed")}
          </tr>
        </thead>
        <tbody>
          {sortedRuns.map((run) => (
            <tr
              className={[
                "table-row",
                run.runId === selectedRunId ? "table-row--active" : "",
                // A fabricated row's metrics came from a formula, not a measurement. It has to
                // be distinguishable at a glance, not only in the drawer.
                isFabricatedRun(run) ? "table-row--mock" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              key={run.runId}
            >
              <td>
                <button
                  className="table-run-button"
                  onClick={() => onSelectRun(run.runId)}
                  type="button"
                >
                  <strong>{run.experimentId}</strong>
                  <span>{run.title}</span>
                  {isFabricatedRun(run) && (
                    <span className="mock-tag">
                      {locale === "ko" ? "모의 · 측정값 아님" : "mock · not measured"}
                    </span>
                  )}
                </button>
              </td>
              <td>
                <span className={classForStatus(run.status)}>{statusText(locale, run.status)}</span>
              </td>
              <td>{modeText(locale, run.mode)}</td>
              <td>{run.modelFamily}</td>
              <td>{run.adaptationMethod}</td>
              <td>{formatMetric(run.metrics.apcer)}</td>
              <td>{formatMetric(run.metrics.bpcer)}</td>
              <td>{formatMetric(run.metrics.acer)}</td>
              <td>{formatMetric(run.metrics.hter)}</td>
              <td>{formatMetric(run.metrics.auc)}</td>
              <td>
                <span className={classForGate(run.gateVerdict)}>{gateText(locale, run.gateVerdict)}</span>
              </td>
              <td>
                <code>{shortHash(run.protocolHash)}</code>
              </td>
              <td>{run.seed}</td>
            </tr>
          ))}
          {sortedRuns.length === 0 && (
            <tr>
              <td colSpan={13}>{t(locale, "noRows")}</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function SortableTh({
  label,
  sublabel = null,
  termId,
  active,
  direction,
  locale = "en",
  onSort,
}: {
  label: string;
  sublabel?: string | null;
  termId?: GlossaryId;
  active: boolean;
  direction: SortState["direction"];
  locale?: Locale;
  onSort: () => void;
}) {
  const nextDirection = active && direction === "asc" ? "descending" : "ascending";
  return (
    <th
      // Without this a screen reader reads thirteen identical-looking buttons and never says
      // which column the table is currently ordered by.
      aria-sort={active ? (direction === "asc" ? "ascending" : "descending") : "none"}
      scope="col"
    >
      <span className="th-inner">
        <button
          aria-label={locale === "ko" ? `${label} ${nextDirection === "ascending" ? "오름차순" : "내림차순"} 정렬` : `Sort by ${label} ${nextDirection}`}
          className="sort-button"
          onClick={onSort}
          type="button"
        >
          <span className="th-label">
            <span className="th-label__term">{label}</span>
            {sublabel && <span className="th-label__ko">{sublabel}</span>}
          </span>
          <span aria-hidden="true">{active ? (direction === "asc" ? "↑" : "↓") : "↕"}</span>
        </button>
        {/* Outside the sort button: a button cannot contain another button. */}
        {termId && <TermMark id={termId} locale={locale} />}
      </span>
    </th>
  );
}

function sortValue(run: DemoRun, key: SortKey): string | number {
  if (key in run.metrics) {
    return run.metrics[key as keyof typeof run.metrics];
  }
  return run[key as keyof Pick<
    DemoRun,
    | "experimentId"
    | "status"
    | "mode"
    | "modelFamily"
    | "adaptationMethod"
    | "gateVerdict"
    | "protocolHash"
    | "seed"
  >];
}
