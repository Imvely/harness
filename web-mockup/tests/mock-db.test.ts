import { describe, expect, test } from "bun:test";
import { demoRuns } from "../src/data/demoRuns";
import {
  completeNextQueuedJob,
  createInitialMockDatabase,
  queueMockExperiment,
  saveExperimentDraft,
  validateControlState,
} from "../src/db/mockDb";
import { initialControl } from "../src/components/ControlView";
import { buildLiteratureGraph, filterLiteraturePapers } from "../src/components/ResearchAtlasView";

describe("mock database", () => {
  test("seeds valid demo runs", () => {
    const state = createInitialMockDatabase(demoRuns, "demo");
    expect(state.runs.length).toBeGreaterThan(0);
    expect(state.literature.papers.length).toBeGreaterThan(0);
    expect(state.auditLog[0]?.kind).toBe("db_seeded");
  });

  test("persists drafts and completes queued synthetic jobs", () => {
    const state = createInitialMockDatabase(demoRuns, "demo");
    const draft = saveExperimentDraft(state, initialControl);
    expect(draft.item?.experimentId).toBe(initialControl.experimentId);

    const queued = queueMockExperiment(draft.state, initialControl);
    expect(queued.item?.status).toBe("queued");

    const completed = completeNextQueuedJob(queued.state);
    expect(completed.item?.job.status).toBe("completed");
    expect(completed.item?.run.tags).toContain("mock-db");
    expect(completed.state.runs[0]?.runId).toBe(completed.item?.run.runId);
  });

  test("blocks smoke epoch increases", () => {
    const issues = validateControlState({ ...initialControl, epochs: 2 });
    expect(issues.join("\n")).toContain("Smoke mode requires epochs to stay at 1.");
  });

  test("filters literature by method evidence and builds a selected graph", () => {
    const state = createInitialMockDatabase(demoRuns, "demo");
    const papers = filterLiteraturePapers(state, {
      query: "spoof",
      yearMin: 2019,
      yearMax: 2026,
      provider: "all",
      status: "all",
      datasetId: "all",
      methodId: "method_spoof_preserve",
      minCitations: 0,
      openAccessOnly: false,
    });
    expect(papers.map((paper) => paper.paperId)).toContain("paper_spoof_preserve");

    const graph = buildLiteratureGraph(state, "paper_spoof_preserve");
    expect(graph.nodes.some((node) => node.kind === "method")).toBe(true);
    expect(graph.edges.some((edge) => edge.kind === "cites")).toBe(true);
  });
});
