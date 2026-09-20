import type { ReactNode } from "react";
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

interface Column {
  key: SortKey;
  /** The header text. For a metric this is the bare acronym. */
  label: string;
  termId?: GlossaryId;
  /** True for the acronym columns, which print the Korean name under the acronym. */
  acronym?: boolean;
  /** Hidden until the reader asks for the full table. */
  detail?: boolean;
  cell: (run: DemoRun, locale: Locale, onSelectRun: (runId: string) => void) => ReactNode;
}

/**
 * One definition per column, used for both the header and the body.
 *
 * They used to be two hand-maintained parallel lists — thirteen `<SortableTh>` elements and
 * thirteen `<td>`s in the same order — which is a silent-drift hazard: insert a column in one
 * list and every value to its right shifts under the wrong heading.
 *
 * Six columns show by default. Thirteen at `min-width: 980px` meant that on a laptop the
 * experiment name scrolled out of view while the reader was looking at the numbers, so they
 * were reading metrics with no idea whose they were. The other seven are one click away, and
 * the first column is now pinned so it stays put whatever is showing.
 */
function columns(locale: Locale): Column[] {
  return [
    {
      key: "experimentId",
      label: t(locale, "experiment"),
      cell: (run, loc, onSelectRun) => (
        <button className="table-run-button" onClick={() => onSelectRun(run.runId)} type="button">
          <strong>{run.experimentId}</strong>
          <span>{run.title}</span>
          {isFabricatedRun(run) && (
            <span className="mock-tag">{loc === "ko" ? "모의 · 측정값 아님" : "mock · not measured"}</span>
          )}
        </button>
      ),
    },
    {
      key: "status",
      label: t(locale, "status"),
      cell: (run, loc) => <span className={classForStatus(run.status)}>{statusText(loc, run.status)}</span>,
    },
    {
      key: "gateVerdict",
      label: t(locale, "gate"),
      termId: "gate-verdict",
      cell: (run, loc) => <span className={classForGate(run.gateVerdict)}>{gateText(loc, run.gateVerdict)}</span>,
    },
    {
      key: "apcer",
      label: "APCER",
      termId: "apcer",
      acronym: true,
      cell: (run) => formatMetric(run.metrics.apcer),
    },
    { key: "auc", label: "AUC", termId: "auc", acronym: true, cell: (run) => formatMetric(run.metrics.auc) },
    { key: "seed", label: t(locale, "seed"), termId: "seed", cell: (run) => run.seed },

    // --- behind the toggle ---
    {
      key: "mode",
      label: t(locale, "mode"),
      termId: "smoke",
      detail: true,
      cell: (run, loc) => modeText(loc, run.mode),
    },
    { key: "modelFamily", label: t(locale, "model"), detail: true, cell: (run) => run.modelFamily },
    {
      key: "adaptationMethod",
      label: t(locale, "adaptation"),
      termId: "adaptation",
      detail: true,
      cell: (run) => run.adaptationMethod,
    },
    {
      key: "bpcer",
      label: "BPCER",
      termId: "bpcer",
      acronym: true,
      detail: true,
      cell: (run) => formatMetric(run.metrics.bpcer),
    },
    {
      key: "acer",
      label: "ACER",
      termId: "acer",
      acronym: true,
      detail: true,
      cell: (run) => formatMetric(run.metrics.acer),
    },
    {
      key: "hter",
      label: "HTER",
      termId: "hter",
      acronym: true,
      detail: true,
      cell: (run) => formatMetric(run.metrics.hter),
    },
    {
      key: "protocolHash",
      label: t(locale, "protocol"),
      termId: "protocol-hash",
      detail: true,
      cell: (run) => <code>{shortHash(run.protocolHash)}</code>,
    },
  ];
}

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
  const [showDetail, setShowDetail] = useState(false);
  const visible = useMemo(
    () => columns(locale).filter((column) => showDetail || !column.detail),
    [locale, showDetail],
  );
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
  const hiddenCount = columns(locale).filter((column) => column.detail).length;

  return (
    <div className="table-block">
      <div className="table-block__actions">
        <button
          aria-expanded={showDetail}
          className="button button--secondary button--small"
          onClick={() => setShowDetail((current) => !current)}
          type="button"
        >
          {showDetail
            ? locale === "ko"
              ? "기본 열만 보기"
              : "Show fewer columns"
            : locale === "ko"
              ? `열 ${hiddenCount}개 더 보기`
              : `Show ${hiddenCount} more columns`}
        </button>
      </div>
      <div className="table-wrap">
        <table className={showDetail ? "runs-table runs-table--detail" : "runs-table"}>
          <thead>
            <tr>
              {visible.map((column) => (
                <SortableTh
                  active={sort.key === column.key}
                  direction={sort.direction}
                  key={column.key}
                  label={column.label}
                  locale={locale}
                  onSort={() => requestSort(column.key)}
                  // The acronym stays the headline and the Korean name sits under it: the
                  // registry, the reports and the papers all print the acronym, so the reader
                  // has to learn it either way.
                  sublabel={
                    column.acronym && locale === "ko"
                      ? (glossaryEntry(column.termId ?? "")?.ko ?? null)
                      : null
                  }
                  termId={column.termId}
                />
              ))}
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
                {visible.map((column) => (
                  <td key={column.key}>{column.cell(run, locale, onSelectRun)}</td>
                ))}
              </tr>
            ))}
            {sortedRuns.length === 0 && (
              <tr>
                <td colSpan={visible.length}>{t(locale, "noRows")}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
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
      // Without this a screen reader reads a row of identical-looking buttons and never says
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
