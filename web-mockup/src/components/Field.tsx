import { useId } from "react";
import type { ReactNode } from "react";
import { Hint } from "./Hint";

/**
 * A labelled input with an optional ? beside the label.
 *
 * The ? cannot live inside a <label>: a label labels its first labelable descendant, so a
 * button inside it would take the label away from the input, and clicking the label text would
 * press the ? instead of focusing the field. The label and the ? sit side by side instead, and
 * the input is tied to the label by id.
 */
export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: ReactNode;
  /** Renders the control; spread `{ id }` onto it. */
  children: (id: string) => ReactNode;
}) {
  const id = useId();
  return (
    <div className="field">
      <span className="field__head">
        <label htmlFor={id}>{label}</label>
        {hint && (
          <Hint align="start" label={label}>
            {hint}
          </Hint>
        )}
      </span>
      {children(id)}
    </div>
  );
}
