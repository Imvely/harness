import { describe, expect, test } from "bun:test";
import { demoRuns } from "../src/data/demoRuns";
import { createInitialMockDatabase } from "../src/db/mockDb";
import { comparisonRuns } from "../src/components/CompareView";
import { dataOrigin } from "../src/components/WarningBanner";
import { isFabricatedRun, isWorseDelta, lowerIsBetter } from "../src/utils";

describe("metric polarity", () => {
  test("a rising error rate is worse, a rising AUC is better", () => {
    // The whole point of the shared rule: four metrics agree that up is bad, AUC disagrees.
    for (const metric of ["apcer", "bpcer", "acer", "hter"] as const) {
      expect(lowerIsBetter(metric)).toBe(true);
      expect(isWorseDelta(metric, 0.05)).toBe(true);
      expect(isWorseDelta(metric, -0.05)).toBe(false);
    }
    expect(lowerIsBetter("auc")).toBe(false);
    expect(isWorseDelta("auc", 0.05)).toBe(false);
    expect(isWorseDelta("auc", -0.05)).toBe(true);
  });

  test("no change is never reported as worse", () => {
    for (const metric of ["apcer", "bpcer", "acer", "hter", "auc"] as const) {
      expect(isWorseDelta(metric, 0)).toBe(false);
    }
  });
});

describe("fabricated rows", () => {
  test("bundled demo rows are marked as not measured", () => {
    // These ship with the app so the UI has something to render. They are not measurements,
    // and every surface that shows a metric has to be able to say so.
    expect(demoRuns.every((run) => isFabricatedRun(run))).toBe(true);
    expect(demoRuns.every((run) => !run.researchClaimAllowed)).toBe(true);
  });

  test("the mock database exposes no way to generate a run", async () => {
    // The control lab used to synthesise APCER/AUC from methodOffsets() and a seeded jitter
    // and insert the result alongside exported runs. Nothing may bring that back: a browser
    // cannot measure a detector, so any row it invents is indistinguishable fiction.
    const mockDb = await import("../src/db/mockDb");
    for (const gone of [
      "queueMockExperiment",
      "runMockExperimentNow",
      "completeNextQueuedJob",
      "createMockRun",
    ]) {
      expect(Object.keys(mockDb)).not.toContain(gone);
    }
  });
});

describe("data origin", () => {
  test("bundled demo rows read as demo even before any export loads", () => {
    expect(dataOrigin("demo", demoRuns)).toBe("demo");
  });

  test("a real export on synthetic data is not called a real result", () => {
    // The synthetic sanity datasets export cleanly, so provenance alone would read "real".
    // research_claim_allowed is what separates a usable result from a pipeline demonstration.
    const exported = demoRuns.map((run) => ({
      ...run,
      demoOnly: false,
      researchClaimAllowed: false,
    }));
    expect(dataOrigin("export", exported)).toBe("export_synthetic");
  });

  test("an export whose rows allow claims reads as a real result", () => {
    const exported = demoRuns.map((run) => ({
      ...run,
      demoOnly: false,
      researchClaimAllowed: true,
    }));
    expect(dataOrigin("export", exported)).toBe("export_real");
  });

  test("one fabricated row downgrades a real export to mixed", () => {
    const exported = demoRuns.map((run) => ({
      ...run,
      demoOnly: false,
      researchClaimAllowed: true,
    }));
    const withMock = [...exported, { ...exported[0]!, runId: "mock_1", demoOnly: true }];
    expect(dataOrigin("export", withMock)).toBe("mixed");
  });

  test("an empty database does not claim to show exported results", () => {
    expect(dataOrigin("export", [])).toBe("demo");
  });
});

describe("comparison eligibility", () => {
  test("rows that are not measurements never enter a comparison", () => {
    const state = createInitialMockDatabase(demoRuns, "demo");
    const experimentId = state.runs[0]!.experimentId;

    // Both permissive switches on: smoke and non-passing rows are allowed back in, rows that
    // were never measured still are not.
    const eligible = comparisonRuns(
      state.runs.filter((run) => run.experimentId === experimentId),
      { includeSmoke: true, includeRisky: true },
    );
    expect(eligible.length).toBe(0);
  });

  test("measured rows do pass the same filter", () => {
    const measured = demoRuns
      .filter((run) => run.experimentId === demoRuns[0]!.experimentId)
      .map((run) => ({ ...run, demoOnly: false }));

    const eligible = comparisonRuns(measured, { includeSmoke: true, includeRisky: true });
    expect(eligible.length).toBe(measured.length);
  });
});
