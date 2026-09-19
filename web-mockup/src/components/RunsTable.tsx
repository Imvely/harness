import type { DemoRun, Locale } from "../types";
import { useMemo, useState } from "react";
import { gateText, modeText, statusText, t } from "../i18n";
import {
  classForGate,
  classForStatus,
  formatMetric,
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

  return (
    <div className="table-wrap">
      <table className="runs-table">
        <thead>
          <tr>
            <SortableTh active={sort.key === "experimentId"} direction={sort.direction} label={t(locale, "experiment")} locale={locale} onSort={() => requestSort("experimentId")} />
            <SortableTh active={sort.key === "status"} direction={sort.direction} label={t(locale, "status")} locale={locale} onSort={() => requestSort("status")} />
            <SortableTh active={sort.key === "mode"} direction={sort.direction} label="Mode" onSort={() => requestSort("mode")} />
            <SortableTh active={sort.key === "modelFamily"} direction={sort.direction} label={t(locale, "model")} locale={locale} onSort={() => requestSort("modelFamily")} />
            <SortableTh active={sort.key === "adaptationMethod"} direction={sort.direction} label={t(locale, "adaptation")} locale={locale} onSort={() => requestSort("adaptationMethod")} />
            <SortableTh active={sort.key === "apcer"} direction={sort.direction} label="APCER" onSort={() => requestSort("apcer")} />
            <SortableTh active={sort.key === "bpcer"} direction={sort.direction} label="BPCER" onSort={() => requestSort("bpcer")} />
            <SortableTh active={sort.key === "acer"} direction={sort.direction} label="ACER" onSort={() => requestSort("acer")} />
            <SortableTh active={sort.key === "hter"} direction={sort.direction} label="HTER" onSort={() => requestSort("hter")} />
            <SortableTh active={sort.key === "auc"} direction={sort.direction} label="AUC" onSort={() => requestSort("auc")} />
            <SortableTh active={sort.key === "gateVerdict"} direction={sort.direction} label={t(locale, "gate")} locale={locale} onSort={() => requestSort("gateVerdict")} />
            <SortableTh active={sort.key === "protocolHash"} direction={sort.direction} label={t(locale, "protocol")} locale={locale} onSort={() => requestSort("protocolHash")} />
            <SortableTh active={sort.key === "seed"} direction={sort.direction} label={t(locale, "seed")} locale={locale} onSort={() => requestSort("seed")} />
          </tr>
        </thead>
        <tbody>
          {sortedRuns.map((run) => (
            <tr
              className={run.runId === selectedRunId ? "table-row table-row--active" : "table-row"}
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
  active,
  direction,
  locale = "en",
  onSort,
}: {
  label: string;
  active: boolean;
  direction: SortState["direction"];
  locale?: Locale;
  onSort: () => void;
}) {
  const nextDirection = active && direction === "asc" ? "descending" : "ascending";
  return (
    <th scope="col">
      <button
        aria-label={locale === "ko" ? `${label} ${nextDirection === "ascending" ? "오름차순" : "내림차순"} 정렬` : `Sort by ${label} ${nextDirection}`}
        className="sort-button"
        onClick={onSort}
        type="button"
      >
        {label}
        <span aria-hidden="true">{active ? (direction === "asc" ? "↑" : "↓") : "↕"}</span>
      </button>
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
