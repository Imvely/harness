import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

/**
 * A panel that slides in from the right, over the page.
 *
 * The run detail used to be appended below the table, so clicking a row changed something a
 * screen-height away and the reader had to scroll to find out what. Opening it beside the row
 * keeps the table in view, so the next row is one click away rather than a scroll back up.
 *
 * Escape and the close button both close it, focus moves into it when it opens and back to
 * what opened it when it closes, and the backdrop closes it on click.
 */
export function SidePanel({
  open,
  onClose,
  title,
  closeLabel,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  closeLabel: string;
  children: ReactNode;
}) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const returnFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    panelRef.current?.focus({ preventScroll: true });
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      returnFocus.current?.focus({ preventScroll: true });
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="side-panel-layer">
      <div aria-hidden="true" className="side-panel-backdrop" onClick={onClose} />
      <div aria-label={title} aria-modal="true" className="side-panel" ref={panelRef} role="dialog" tabIndex={-1}>
        <div className="side-panel__bar">
          <span className="side-panel__title">{title}</span>
          <button aria-label={closeLabel} className="side-panel__close" onClick={onClose} type="button">
            ×
          </button>
        </div>
        <div className="side-panel__body">{children}</div>
      </div>
    </div>
  );
}
