import { useEffect, useState } from "react";
import type { Locale } from "../types";
import { shortHash } from "../utils";

/**
 * A hash, shown short, copyable in full.
 *
 * Every hash on screen was truncated to twelve characters with no way to reach the rest — so a
 * reader who wanted to check two runs really did share a protocol, or to paste one into
 * `summarize_experiment.py`, had to go and find it in the registry instead. Twelve characters
 * is also enough to make two different hashes look identical when they share a prefix, which is
 * precisely the case the audit view exists to catch.
 */
export function HashValue({
  value,
  locale,
  label,
}: {
  value: string;
  locale: Locale;
  /** Names what was copied, so the confirmation is not ambiguous when several sit together. */
  label: string;
}) {
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!copied && !failed) return;
    const timer = window.setTimeout(() => {
      setCopied(false);
      setFailed(false);
    }, 2000);
    return () => window.clearTimeout(timer);
  }, [copied, failed]);

  if (!value) {
    return <code className="hash-value__code">—</code>;
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
    } catch {
      // Denied permission, or an insecure origin. Say so rather than showing a false success:
      // a reader who believes they copied a hash will paste the previous one.
      setFailed(true);
    }
  };

  return (
    <span className="hash-value">
      {/* The full value is the accessible name, so it is reachable without copying at all. */}
      <code className="hash-value__code" title={value}>
        {shortHash(value)}
      </code>
      <button
        aria-label={
          locale === "ko" ? `${label} 전체 값 복사` : `Copy the full ${label}`
        }
        className="hash-value__copy"
        onClick={() => void copy()}
        type="button"
      >
        {copied
          ? locale === "ko"
            ? "복사됨"
            : "copied"
          : failed
            ? locale === "ko"
              ? "복사 실패"
              : "copy failed"
            : locale === "ko"
              ? "복사"
              : "copy"}
      </button>
    </span>
  );
}
