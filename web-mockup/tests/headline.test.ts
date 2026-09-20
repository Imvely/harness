import { describe, expect, test } from "bun:test";
import { demoRuns } from "../src/data/demoRuns";
import { headlineState } from "../src/components/Dashboard";
import type { DemoRun, GateVerdict } from "../src/types";

function withGate(gateVerdict: GateVerdict, apcer: number, runId: string): DemoRun {
  return { ...demoRuns[0]!, runId, gateVerdict, metrics: { ...demoRuns[0]!.metrics, apcer } };
}

describe("dashboard headline precedence", () => {
  test("a regression outranks everything else on screen", () => {
    const state = headlineState([
      withGate("pass", 0.01, "a"),
      withGate("inconclusive", 0.9, "b"),
      withGate("security_regression", 0.2, "c"),
    ]);
    expect(state.kind).toBe("regression");
    expect(state.urgent?.runId).toBe("c");
  });

  test("an inconclusive verdict is never folded into a pass", () => {
    // "Could not be judged" and "passed" are different states. Collapsing them would let a run
    // with too few attack samples per PAI read as a clean result.
    const state = headlineState([withGate("pass", 0.01, "a"), withGate("inconclusive", 0.4, "b")]);
    expect(state.kind).toBe("inconclusive");
    expect(state.urgent?.runId).toBe("b");
  });

  test("all passing points at no run in particular", () => {
    const state = headlineState([withGate("pass", 0.01, "a"), withGate("no_gate", 0.02, "b")]);
    expect(state.kind).toBe("clear");
    expect(state.urgent).toBeNull();
  });

  test("an empty filter result is its own state, not a clean bill of health", () => {
    const state = headlineState([]);
    expect(state.kind).toBe("empty");
    expect(state.urgent).toBeNull();
  });

  test("the worst run of the most serious category is the one offered", () => {
    const state = headlineState([
      withGate("security_regression", 0.3, "low"),
      withGate("security_regression", 0.8, "high"),
      withGate("inconclusive", 0.99, "worse-but-less-serious"),
    ]);
    expect(state.urgent?.runId).toBe("high");
  });

  test("counts report what they say they report", () => {
    const state = headlineState([
      withGate("security_regression", 0.3, "a"),
      withGate("inconclusive", 0.2, "b"),
      withGate("pass", 0.1, "c"),
    ]);
    expect(state.regressions).toBe(1);
    expect(state.inconclusive).toBe(1);
    // Every bundled demo row blocks claims, so this stays 0 whatever the gate says.
    expect(state.claimable).toBe(0);
  });
});
