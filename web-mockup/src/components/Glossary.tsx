import { createContext, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { Locale } from "../types";
import type { GlossaryId } from "../glossary";
import {
  definition,
  directionHint,
  glossary,
  glossaryEntry,
  glossaryGroups,
  termLabel,
} from "../glossary";

/**
 * The glossary surface: a sidebar panel plus the small chips that open it.
 *
 * Splitting it this way is deliberate. A tooltip alone would carry the definition to a mouse
 * user and to nobody else — `title` is unreachable on touch and unreliable for screen readers —
 * so the definition lives in a panel that is keyboard-reachable and readable on a phone, and the
 * chip is a real button that opens it. The chip still carries `title` as a convenience, never as
 * the only route to the text.
 */

interface GlossaryControls {
  /** The entry the panel should scroll to and highlight, if any. */
  focusedId: string | null;
  /**
   * Bumped on every request, including a repeat of the same term.
   *
   * Without it, clicking a chip, scrolling away, then clicking the same chip again changes no
   * state at all, so the panel never scrolls back — the button would look broken.
   */
  focusNonce: number;
  open: boolean;
  openTerm: (id: string) => void;
  setOpen: (open: boolean) => void;
}

const GlossaryContext = createContext<GlossaryControls>({
  focusedId: null,
  focusNonce: 0,
  open: false,
  openTerm: () => {},
  setOpen: () => {},
});

export function GlossaryProvider({ children }: { children: ReactNode }) {
  const [focus, setFocus] = useState<{ id: string | null; nonce: number }>({ id: null, nonce: 0 });
  const [open, setOpen] = useState(false);
  return (
    <GlossaryContext.Provider
      value={{
        focusedId: focus.id,
        focusNonce: focus.nonce,
        open,
        openTerm: (id: string) => {
          setFocus((current) => ({ id, nonce: current.nonce + 1 }));
          setOpen(true);
        },
        setOpen,
      }}
    >
      {children}
    </GlossaryContext.Provider>
  );
}

export function useGlossary(): GlossaryControls {
  return useContext(GlossaryContext);
}

/**
 * A term as it should appear in body copy: `공격 통과율 (APCER)` in Korean, `APCER` in English.
 *
 * `children` overrides the label for places that already print the term their own way and only
 * want the chip attached to it.
 */
export function Term({
  id,
  locale,
  children,
}: {
  id: GlossaryId;
  locale: Locale;
  children?: ReactNode;
}) {
  const { openTerm } = useGlossary();
  const entry = glossaryEntry(id);
  if (!entry) return <>{children ?? id}</>;
  const label = children ?? termLabel(entry, locale);
  return (
    <button
      aria-label={
        locale === "ko"
          ? `${termLabel(entry, locale)} 용어 설명 열기`
          : `Open the glossary entry for ${entry.term}`
      }
      className="term-chip"
      onClick={() => openTerm(entry.id)}
      title={definition(entry, locale)}
      type="button"
    >
      <span className="term-chip__label">{label}</span>
      <span aria-hidden="true" className="term-chip__mark">
        ?
      </span>
    </button>
  );
}

/**
 * The chip on its own, for spots where the term is already printed by something that cannot
 * contain a button — a sort header, for instance, whose label is itself a button.
 */
export function TermMark({ id, locale }: { id: GlossaryId; locale: Locale }) {
  const { openTerm } = useGlossary();
  const entry = glossaryEntry(id);
  if (!entry) return null;
  return (
    <button
      aria-label={
        locale === "ko"
          ? `${termLabel(entry, locale)} 용어 설명 열기`
          : `Open the glossary entry for ${entry.term}`
      }
      className="term-chip term-chip--bare"
      onClick={() => openTerm(entry.id)}
      title={definition(entry, locale)}
      type="button"
    >
      <span aria-hidden="true" className="term-chip__mark">
        ?
      </span>
    </button>
  );
}

export function GlossaryPanel({ locale }: { locale: Locale }) {
  const { focusedId, focusNonce, open, setOpen } = useGlossary();
  const listRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open || !focusedId) return;
    const node = listRef.current?.querySelector(`#glossary-${focusedId}`);
    if (node instanceof HTMLElement) {
      node.scrollIntoView({ block: "nearest" });
      // Moving focus is what makes the chip useful with a keyboard or a screen reader: the
      // definition is announced instead of silently appearing somewhere off-screen.
      node.focus({ preventScroll: true });
    }
  }, [focusedId, focusNonce, open]);

  return (
    <details
      className="glossary-panel sidebar-section"
      onToggle={(event) => setOpen((event.currentTarget as HTMLDetailsElement).open)}
      open={open}
    >
      <summary className="sidebar-section__summary">
        <span>
          <span className="eyebrow">{locale === "ko" ? "용어" : "Glossary"}</span>
          <strong>{locale === "ko" ? "이 화면의 용어" : "Terms on this screen"}</strong>
        </span>
        <span className="sidebar-section__count">{glossary.length}</span>
      </summary>
      <p className="glossary-panel__lead">
        {locale === "ko"
          ? "숫자 옆의 ? 를 누르면 그 용어가 여기에서 열립니다."
          : "The ? beside a number opens that term here."}
      </p>
      <div className="glossary-list" ref={listRef}>
        {glossaryGroups.map((group) => {
          const entries = glossary.filter((entry) => entry.group === group.group);
          if (entries.length === 0) return null;
          return (
            <section className="glossary-group" key={group.group}>
              <h3>{locale === "ko" ? group.ko : group.en}</h3>
              <dl>
                {entries.map((entry) => {
                  const hint = directionHint(entry, locale);
                  return (
                    <div
                      className={
                        entry.id === focusedId ? "glossary-item glossary-item--focused" : "glossary-item"
                      }
                      id={`glossary-${entry.id}`}
                      key={entry.id}
                      tabIndex={-1}
                    >
                      <dt>
                        {termLabel(entry, locale)}
                        {/* The space is load-bearing: margin-left separates these visually, but
                            without it a screen reader runs "…(APCER)낮을수록 안전" together. */}
                        {hint && <> <span className="glossary-item__hint">{hint}</span></>}
                      </dt>
                      {entry.expansion && <p className="glossary-item__expansion">{entry.expansion}</p>}
                      <dd>{definition(entry, locale)}</dd>
                    </div>
                  );
                })}
              </dl>
            </section>
          );
        })}
      </div>
    </details>
  );
}
