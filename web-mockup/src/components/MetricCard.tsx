import type { ReactNode } from "react";
import { Hint } from "./Hint";

/**
 * One number with its name, and — where the number is not self-explanatory — the ? that says
 * what would change it. "주장 가능 0" is the case that needs it: a zero there reads as a failure
 * when it is usually just the demo data, and nothing on screen said which.
 */
export function MetricCard({
  label,
  value,
  note,
  hint,
}: {
  label: string;
  value: string;
  note: string;
  hint?: ReactNode;
}) {
  return (
    <article className="metric-card">
      <p>
        {label}
        {hint && (
          <Hint align="start" label={label}>
            {hint}
          </Hint>
        )}
      </p>
      <strong>{value}</strong>
      <span>{note}</span>
    </article>
  );
}
