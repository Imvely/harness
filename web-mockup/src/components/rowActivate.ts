import type { MouseEvent } from "react";

/** Elements that already do something when clicked; a click on one is not a row click. */
const INTERACTIVE = "button, a, input, select, textarea, summary, label, [role='button']";

/**
 * Make a whole table row open its detail, not only the title inside it.
 *
 * Every clickable table keeps a real button in its first cell, so a keyboard user can still
 * Tab to a row and press Enter; this adds the mouse path on top. A click that lands on that
 * button, or on any other control in the row (a copy button, a "queue" button), is left to the
 * control: handling it here too would run the action twice, which for a toggle means undoing it.
 * A click that ends a text selection is ignored as well, so a row stays copyable.
 */
export function rowClick(onActivate: () => void) {
  return (event: MouseEvent<HTMLElement>) => {
    const target = event.target;
    if (target instanceof Element && target.closest(INTERACTIVE)) return;
    if (typeof window !== "undefined" && window.getSelection()?.toString()) return;
    onActivate();
  };
}
