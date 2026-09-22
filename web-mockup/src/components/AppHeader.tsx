import type { ReactNode } from "react";
import type { Locale } from "../types";
import { viewLabel, viewPurpose } from "../i18n";

// Mirrors the App shell's view union; `viewLabel`/`viewPurpose` key off the same names.
type View =
  | "dashboard"
  | "literature"
  | "runs"
  | "compare"
  | "audit"
  | "report"
  | "storage"
  | "control";

/**
 * The page title, what this screen answers in one line, the screen's tools on the right, and
 * the data-origin line underneath. Nothing else: counters and explanations moved to where they
 * are needed (the filter button's badge, the ? on each section).
 */
export function AppHeader({
  locale,
  view,
  actions,
  children,
}: {
  locale: Locale;
  view: View;
  /** Buttons for this screen, right-aligned. */
  actions?: ReactNode;
  /** The data-origin line. */
  children?: ReactNode;
}) {
  return (
    <header className="app-header">
      <div className="app-header__row">
        <div className="app-header__title">
          {/* The page heading. It was an h2 while the only h1 was the brand name inside a button
              in the sidebar, which left every view with five to eight sibling h2s and no level
              above them — a screen reader's heading outline was flat. */}
          <h1>{viewLabel(locale, view)}</h1>
          <span>{viewPurpose(locale, view)}</span>
        </div>
        {actions && <div className="app-header__actions">{actions}</div>}
      </div>
      {children}
    </header>
  );
}
