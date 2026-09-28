import { useId } from "react";
import type { ReactNode } from "react";

/**
 * A "?" that explains something on hover or focus.
 *
 * The rule this enforces across the app: one short line on screen, everything else behind a ?.
 * The bubble is real text in the DOM, tied to the button with aria-describedby, so it reaches a
 * screen reader and a keyboard user (Tab onto the ?) as well as a mouse; on touch, tapping the
 * button focuses it and the bubble opens. `title` is not used: it appears late, cannot be
 * styled, and never appears on touch.
 */
export function Hint({
  children,
  label,
  align = "center",
}: {
  children: ReactNode;
  /** What the ? explains, for the button's accessible name. */
  label: string;
  /** Which way the bubble grows from the ?; "end" keeps it inside a right-hand edge. */
  align?: "center" | "start" | "end";
}) {
  const id = useId();
  return (
    <span className={`hint hint--${align}`}>
      <button aria-describedby={id} aria-label={label} className="hint__trigger" type="button">
        ?
      </button>
      <span className="hint__bubble" id={id} role="tooltip">
        {children}
      </span>
    </span>
  );
}
