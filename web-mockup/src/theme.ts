/**
 * Light / dark / follow-the-system, as a stamp on <html>.
 *
 * Three choices, not two. "System" has to be a real option rather than the absence of a choice:
 * a viewer whose machine switches at sunset should be able to say "follow that" *and* be able to
 * say "no, always light" — and the second is only expressible if the first is a stored value.
 *
 * The stamp is an attribute rather than a class because the CSS reads it twice: once inside the
 * `prefers-color-scheme` query (guarded by `:not([data-theme="light"])`, so an explicit light
 * choice beats an OS set to dark) and once as `[data-theme="dark"]`.
 */

export type ThemeChoice = "light" | "dark" | "system";

const storageKey = "pad-research-web-mockup-theme";

export function readTheme(): ThemeChoice {
  try {
    const stored = window.localStorage.getItem(storageKey);
    if (stored === "light" || stored === "dark" || stored === "system") return stored;
  } catch {
    // Private browsing or blocked site data. Following the system is the safe default.
  }
  return "system";
}

export function applyTheme(choice: ThemeChoice): void {
  const root = document.documentElement;
  if (choice === "system") {
    // Removing the attribute is what hands control back to the media query.
    root.removeAttribute("data-theme");
  } else {
    root.setAttribute("data-theme", choice);
  }
  try {
    window.localStorage.setItem(storageKey, choice);
  } catch {
    // The stamp is already applied; only the memory of it is lost.
  }
}
