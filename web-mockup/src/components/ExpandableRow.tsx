import { useState } from "react";
import type { ReactNode } from "react";
import type { Locale } from "../types";
import { definition, directionHint, glossaryEntry, termLabel } from "../glossary";
import { rowClick } from "./rowActivate";

/**
 * A table row that opens a detail line underneath itself when clicked anywhere.
 *
 * For tables whose rows have no page of their own to open — a metric, a protocol group — the
 * detail is shown in place. The first cell is a real disclosure button (aria-expanded), so the
 * row is reachable and operable from the keyboard as well.
 */
export function ExpandableRow({
  label,
  cells,
  colSpan,
  detail,
}: {
  label: ReactNode;
  cells: ReactNode;
  colSpan: number;
  detail: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const toggle = () => setOpen((current) => !current);
  return (
    <>
      <tr className={open ? "row-clickable table-row--active" : "row-clickable"} onClick={rowClick(toggle)}>
        <td>
          <button aria-expanded={open} className="row-toggle" onClick={toggle} type="button">
            <span aria-hidden="true" className="row-toggle__chevron">
              ›
            </span>
            {label}
          </button>
        </td>
        {cells}
      </tr>
      {open && (
        <tr className="row-detail">
          <td colSpan={colSpan}>{detail}</td>
        </tr>
      )}
    </>
  );
}

/** A metric row whose detail is the metric's plain-language definition. */
export function MetricRow({
  metric,
  locale,
  colSpan,
  children,
}: {
  metric: string;
  locale: Locale;
  colSpan: number;
  children: ReactNode;
}) {
  const entry = glossaryEntry(metric);
  const hint = entry ? directionHint(entry, locale) : null;
  return (
    <ExpandableRow
      cells={children}
      colSpan={colSpan}
      detail={
        entry ? (
          <span className="row-detail__text">
            <strong>{termLabel(entry, locale)}</strong>
            {hint && <span className="row-detail__hint">{hint}</span>}
            <span>{definition(entry, locale)}</span>
          </span>
        ) : (
          metric
        )
      }
      label={metric.toUpperCase()}
    />
  );
}
