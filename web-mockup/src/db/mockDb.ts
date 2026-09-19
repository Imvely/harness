import type {
  AuditKind,
  AuditLogEntry,
  AuditSeverity,
  ControlState,
  DemoRun,
  LiteraturePaper,
  PaperExperimentLink,
  PaperStatus,
  ReadingNote,
  MockDatabaseLoadResult,
  MockDatabaseState,
  MockDbSeedSource,
  MockExperimentJob,
} from "../types";
import { demoLiterature } from "../data/demoLiterature";
import { metricAverage } from "../utils";
import {
  MockDatabaseStateSchema,
  ControlStateSchema,
  DemoRunSchema,
  LiteratureStateSchema,
} from "./schema";
import { buildLaunchCommand, buildValidationCommand, buildYamlPatch, controlWarnings } from "./controlPreview";

export const MOCK_DB_KEY = "pad-research-web-mockup-db-v1";

const maxAuditEntries = 120;

type ActionResult<T> = {
  state: MockDatabaseState;
  item: T | null;
  issues: string[];
};

export function createInitialMockDatabase(
  seedRuns: DemoRun[],
  seedSource: MockDbSeedSource,
): MockDatabaseState {
  const now = new Date().toISOString();
  return {
    version: 1,
    seedSource,
    seedFingerprint: makeSeedFingerprint(seedRuns, seedSource),
    createdAt: now,
    updatedAt: now,
    runs: sanitizeRuns(seedRuns),
    literature: sanitizeLiterature(demoLiterature),
    drafts: [],
    jobs: [],
    auditLog: [
      auditEntry("db_seeded", "info", "Mock DB seeded", `Seeded from ${seedSource} rows.`),
    ],
  };
}

export function loadMockDatabase(
  seedRuns: DemoRun[],
  seedSource: MockDbSeedSource,
): MockDatabaseLoadResult {
  if (!canUseStorage()) {
    return { state: createInitialMockDatabase(seedRuns, seedSource), origin: "seeded", resetReason: null };
  }

  const raw = window.localStorage.getItem(MOCK_DB_KEY);
  if (!raw) {
    const state = createInitialMockDatabase(seedRuns, seedSource);
    writeMockDatabase(state);
    return { state, origin: "seeded", resetReason: null };
  }

  try {
    const parsed = MockDatabaseStateSchema.parse(
      migrateStoredState(JSON.parse(raw), seedRuns, seedSource),
    );
    const currentSeedFingerprint = makeSeedFingerprint(seedRuns, seedSource);
    if (parsed.seedSource !== seedSource || parsed.seedFingerprint !== currentSeedFingerprint) {
      const reason = "Seed dataset changed; persisted browser mock DB was reset to avoid mixed rows.";
      const state = appendAudit(
        createInitialMockDatabase(seedRuns, seedSource),
        "db_reset",
        "warning",
        "Mock DB reset",
        reason,
      );
      writeMockDatabase(state);
      return { state, origin: "recovered", resetReason: reason };
    }
    return { state: parsed, origin: "persisted", resetReason: null };
  } catch (error) {
    const state = appendAudit(
      createInitialMockDatabase(seedRuns, seedSource),
      "db_recovered",
      "warning",
      "Mock DB recovered",
      contractIssueMessage(error),
    );
    writeMockDatabase(state);
    return { state, origin: "recovered", resetReason: contractIssueMessage(error) };
  }
}

export function writeMockDatabase(state: MockDatabaseState): void {
  if (!canUseStorage()) return;
  const parsed = MockDatabaseStateSchema.parse(state);
  window.localStorage.setItem(MOCK_DB_KEY, JSON.stringify(parsed));
}

export function resetMockDatabase(
  seedRuns: DemoRun[],
  seedSource: MockDbSeedSource,
): MockDatabaseState {
  const state = appendAudit(
    createInitialMockDatabase(seedRuns, seedSource),
    "db_reset",
    "warning",
    "Mock DB reset",
    "Local mock records were replaced with the active seed set.",
  );
  writeMockDatabase(state);
  return state;
}

export function validateControlState(control: ControlState): string[] {
  const parsed = ControlStateSchema.safeParse(control);
  if (parsed.success) return controlWarnings(control);
  return [
    ...parsed.error.issues.map((issue) => `${issue.path.join(".") || "control"}: ${issue.message}`),
    ...controlWarnings(control),
  ];
}

export function saveExperimentDraft(
  state: MockDatabaseState,
  control: ControlState,
): ActionResult<MockDatabaseState["drafts"][number]> {
  const issues = validateControlState(control);
  if (!ControlStateSchema.safeParse(control).success) {
    return { state, item: null, issues };
  }

  const now = new Date().toISOString();
  const existing = state.drafts.find((draft) => draft.experimentId === control.experimentId);
  const draft = {
    draftId: existing?.draftId ?? makeId("draft", `${control.experimentId}:${now}`),
    experimentId: control.experimentId,
    createdAt: existing?.createdAt ?? now,
    updatedAt: now,
    control,
    yamlPatch: buildYamlPatch(control),
    validationCommand: buildValidationCommand(control),
    command: buildLaunchCommand(control),
    warnings: controlWarnings(control),
  };
  const drafts = existing
    ? state.drafts.map((item) => (item.draftId === existing.draftId ? draft : item))
    : [draft, ...state.drafts];
  const next = appendAudit(
    { ...state, drafts, updatedAt: now },
    "draft_saved",
    "success",
    "Draft saved",
    `${control.experimentId} was saved in the mock DB.`,
  );
  return { state: next, item: draft, issues };
}

export function queueMockExperiment(
  state: MockDatabaseState,
  control: ControlState,
): ActionResult<MockExperimentJob> {
  const issues = validateControlState(control);
  if (!ControlStateSchema.safeParse(control).success) {
    return { state, item: null, issues };
  }

  const now = new Date().toISOString();
  const job: MockExperimentJob = {
    jobId: makeId("job", `${control.experimentId}:${control.seed}:${now}`),
    experimentId: control.experimentId,
    sourceRunId: control.sourceRunId,
    control,
    status: "queued",
    createdAt: now,
    updatedAt: now,
    command: buildLaunchCommand(control),
    validationCommand: buildValidationCommand(control),
    seed: control.seed,
    progress: 0,
    warnings: controlWarnings(control),
    runId: null,
  };
  const next = appendAudit(
    { ...state, jobs: [job, ...state.jobs], updatedAt: now },
    "job_queued",
    control.smokeMode ? "success" : "warning",
    "Mock job queued",
    `${control.experimentId} seed ${control.seed} is queued in the browser mock DB.`,
  );
  return { state: next, item: job, issues };
}

export function completeNextQueuedJob(
  state: MockDatabaseState,
): ActionResult<{ job: MockExperimentJob; run: DemoRun }> {
  const queued = state.jobs.find((job) => job.status === "queued");
  if (!queued) {
    return { state, item: null, issues: ["No queued mock job is available."] };
  }
  return completeJob(state, queued.jobId);
}

export function runMockExperimentNow(
  state: MockDatabaseState,
  control: ControlState,
): ActionResult<{ job: MockExperimentJob; run: DemoRun }> {
  const queued = queueMockExperiment(state, control);
  if (!queued.item) {
    return { state: queued.state, item: null, issues: queued.issues };
  }
  const completed = completeJob(queued.state, queued.item.jobId);
  return { ...completed, issues: [...queued.issues, ...completed.issues] };
}

export function recordUiAudit(
  state: MockDatabaseState,
  kind: AuditKind,
  severity: AuditSeverity,
  title: string,
  detail: string,
): MockDatabaseState {
  const next = appendAudit(state, kind, severity, title, detail);
  writeMockDatabase(next);
  return next;
}

export function queuePaperForReading(
  state: MockDatabaseState,
  paperId: string,
): ActionResult<LiteraturePaper> {
  return updatePaperStatus(state, paperId, "queued", "Paper queued", "paper_queued");
}

export function updatePaperStatus(
  state: MockDatabaseState,
  paperId: string,
  status: PaperStatus,
  title = "Paper status changed",
  kind: AuditKind = "paper_status_changed",
): ActionResult<LiteraturePaper> {
  const paper = state.literature.papers.find((item) => item.paperId === paperId);
  if (!paper) return { state, item: null, issues: ["Paper was not found in the mock literature DB."] };

  const updatedPaper: LiteraturePaper = { ...paper, status };
  const now = new Date().toISOString();
  const next = appendAudit(
    {
      ...state,
      updatedAt: now,
      literature: {
        ...state.literature,
        papers: state.literature.papers.map((item) => (item.paperId === paperId ? updatedPaper : item)),
      },
    },
    kind,
    status === "excluded" ? "warning" : "success",
    title,
    `${paper.title} is now ${status}.`,
  );
  return { state: next, item: updatedPaper, issues: [] };
}

export function linkPaperToExperiment(
  state: MockDatabaseState,
  paperId: string,
  experimentId: string,
  relation: PaperExperimentLink["relation"] = "motivates",
): ActionResult<PaperExperimentLink> {
  const paper = state.literature.papers.find((item) => item.paperId === paperId);
  const experimentExists = state.runs.some((run) => run.experimentId === experimentId);
  if (!paper) return { state, item: null, issues: ["Paper was not found in the mock literature DB."] };
  if (!experimentExists) return { state, item: null, issues: ["Experiment was not found in the mock DB."] };

  const link: PaperExperimentLink = { paperId, experimentId, relation };
  const alreadyLinked = state.literature.paperExperimentLinks.some(
    (item) =>
      item.paperId === paperId &&
      item.experimentId === experimentId &&
      item.relation === relation,
  );
  const links = alreadyLinked
    ? state.literature.paperExperimentLinks
    : [link, ...state.literature.paperExperimentLinks];
  const statusResult = updatePaperStatus(
    {
      ...state,
      literature: {
        ...state.literature,
        paperExperimentLinks: links,
      },
    },
    paperId,
    "linked_to_experiment",
    "Paper linked",
    "paper_linked",
  );
  return { state: statusResult.state, item: link, issues: statusResult.issues };
}

export function addReadingNote(
  state: MockDatabaseState,
  paperId: string,
  text: string,
): ActionResult<ReadingNote> {
  const paper = state.literature.papers.find((item) => item.paperId === paperId);
  const cleanText = text.trim();
  if (!paper) return { state, item: null, issues: ["Paper was not found in the mock literature DB."] };
  if (!cleanText) return { state, item: null, issues: ["Reading note cannot be empty."] };

  const now = new Date().toISOString();
  const note: ReadingNote = {
    noteId: makeId("note", `${paperId}:${cleanText}:${now}`),
    paperId,
    createdAt: now,
    text: cleanText,
  };
  const next = appendAudit(
    {
      ...state,
      updatedAt: now,
      literature: {
        ...state.literature,
        readingNotes: [note, ...state.literature.readingNotes],
      },
    },
    "paper_status_changed",
    "info",
    "Reading note saved",
    `${paper.title} received a mock reading note.`,
  );
  return { state: next, item: note, issues: [] };
}

function completeJob(
  state: MockDatabaseState,
  jobId: string,
): ActionResult<{ job: MockExperimentJob; run: DemoRun }> {
  const target = state.jobs.find((job) => job.jobId === jobId);
  if (!target) return { state, item: null, issues: ["Queued job was not found."] };

  const now = new Date().toISOString();
  const run = createMockRun(state.runs, target.control);
  const completedJob: MockExperimentJob = {
    ...target,
    status: "completed",
    updatedAt: now,
    progress: 100,
    runId: run.runId,
  };
  const nextJobs = state.jobs.map((job) => (job.jobId === jobId ? completedJob : job));
  const nextRuns = [run, ...state.runs.filter((item) => item.runId !== run.runId)];
  const next = appendAudit(
    { ...state, runs: nextRuns, jobs: nextJobs, updatedAt: now },
    "run_completed",
    run.gateVerdict === "security_regression" ? "warning" : "success",
    "Mock run completed",
    `${run.runId} was generated from synthetic mock metrics.`,
  );
  return { state: next, item: { job: completedJob, run }, issues: [] };
}

function createMockRun(existingRuns: DemoRun[], control: ControlState): DemoRun {
  const now = new Date().toISOString();
  const source =
    existingRuns.find((run) => run.runId === control.sourceRunId) ??
    existingRuns.find((run) => run.experimentId === "exp_syn_e02_video_source_only") ??
    existingRuns[0];
  const familyRuns = existingRuns.filter((run) => run.modelFamily === control.modelFamily);
  const baseApcer = (source?.metrics.apcer ?? metricAverage(familyRuns, "apcer")) || 0.22;
  const baseBpcer = (source?.metrics.bpcer ?? metricAverage(familyRuns, "bpcer")) || 0.18;
  const baseAcer = (source?.metrics.acer ?? metricAverage(familyRuns, "acer")) || 0.2;
  const baseHter = (source?.metrics.hter ?? metricAverage(familyRuns, "hter")) || 0.2;
  const baseAuc = (source?.metrics.auc ?? metricAverage(familyRuns, "auc")) || 0.82;
  const jitter = centeredNoise(`${control.experimentId}:${control.seed}:${control.learningRate}`);
  const method = methodOffsets(control.adaptationMethod);
  const framePenalty = control.modelFamily === "frame_baseline" ? 0.025 : 0;
  const smokePenalty = control.smokeMode ? 0.025 : 0;
  const epochFactor = control.smokeMode ? 0 : Math.min(control.epochs - 1, 12) * 0.0015;
  const apcer = clamp01(baseApcer + method.apcer + framePenalty + smokePenalty - epochFactor + jitter * 0.015);
  const bpcer = clamp01(baseBpcer + method.bpcer + smokePenalty / 2 - epochFactor / 2 - jitter * 0.01);
  const acer = clamp01((apcer + bpcer) / 2 || baseAcer);
  const hter = clamp01((acer + baseHter) / 2 + jitter * 0.006);
  const auc = clamp01(baseAuc + method.auc - smokePenalty + epochFactor + jitter * 0.012);
  const paiBaseline = source?.perAttack.length
    ? source.perAttack
    : [
        { pai: "print", apcer: 0.16, baselineApcer: 0.16, delta: 0, nAttack: 28, insufficientSupport: false },
        { pai: "replay_phone", apcer: 0.2, baselineApcer: 0.2, delta: 0, nAttack: 28, insufficientSupport: false },
        { pai: "replay_tablet", apcer: 0.23, baselineApcer: 0.23, delta: 0, nAttack: 28, insufficientSupport: false },
      ];
  const perAttack = paiBaseline.map((item, index) => {
    const value = clamp01(item.apcer + method.perAttack + smokePenalty + centeredNoise(`${item.pai}:${control.seed}`) * 0.02 + index * 0.003);
    return {
      pai: item.pai,
      apcer: value,
      baselineApcer: item.apcer,
      delta: value - item.apcer,
      nAttack: control.smokeMode ? 6 : 36,
      insufficientSupport: control.smokeMode,
    };
  });
  const hasSecurityRegression =
    control.adaptationMethod !== "none" &&
    (perAttack.some((item) => item.delta > 0.05) || apcer > 0.32);
  const mode = control.smokeMode ? "smoke" : "full";
  const gateVerdict =
    control.adaptationMethod === "none"
      ? "no_gate"
      : hasSecurityRegression
        ? "security_regression"
        : control.smokeMode
          ? "inconclusive"
          : "pass";
  const status = control.smokeMode
    ? "smoke_ok"
    : hasSecurityRegression
      ? "security_regression"
      : "success";
  const protocolHash = stableHash(`protocol:${control.protocolId}:${control.thresholdRule}`);
  const scienceHash = stableHash(`science:${control.experimentId}:${control.modelFamily}:${control.adaptationMethod}:${control.frames}`);
  const specHash = stableHash(`spec:${control.experimentId}:${control.batchSize}:${control.epochs}:${control.learningRate}`);
  const runId = `${control.experimentId.replace("exp_", "run_")}_${control.seed}_${mode}_${stableHash(now).slice(0, 6)}`;

  return DemoRunSchema.parse({
    experimentId: control.experimentId,
    runId,
    title: `${control.experimentId.replace(/^exp_/, "").replaceAll("_", " ")} mock run`,
    status,
    mode,
    modelFamily: control.modelFamily,
    adaptationMethod: control.adaptationMethod,
    protocolId: control.protocolId,
    protocolHash,
    scienceHash,
    specHash,
    manifestHashes: {
      synthetic_a: stableHash("synthetic_a"),
      synthetic_b: stableHash("synthetic_b"),
    },
    datasetPiiPolicies: { synthetic_a: "synthetic", synthetic_b: "synthetic" },
    adaptationSetHash: control.adaptationMethod === "none" ? null : stableHash(`adapt:${control.sourceRunId}`),
    seed: control.seed,
    metrics: {
      apcer,
      bpcer,
      acer,
      hter,
      auc,
      tau: clamp01(0.5 + control.seed * 0.004 + jitter * 0.01),
    },
    threshold: {
      rule: control.thresholdRule,
      fittedOn: control.adaptationMethod === "none" ? "source/dev" : "target/dev",
      tau: clamp01(0.5 + control.seed * 0.004 + jitter * 0.01),
      devSupport: {
        bonaFide: control.smokeMode ? 8 : 64,
        attack: control.smokeMode ? 12 : 96,
      },
    },
    perAttack,
    gateVerdict,
    researchClaimAllowed: false,
    demoOnly: true,
    piiPolicy: "synthetic",
    claimEligibility: {
      allowed: false,
      reasons: [
        "mock database row",
        "synthetic data",
        "researchClaimAllowed is false",
        control.smokeMode ? "mode is smoke" : "demo row needs reviewer approval",
        hasSecurityRegression ? "security regression gate failed" : "",
      ].filter(Boolean),
      fullMode: !control.smokeMode,
      researchClaimAllowed: false,
      atLeastThreeSeeds:
        new Set(
          existingRuns
            .filter((run) => run.experimentId === control.experimentId)
            .map((run) => run.seed),
        ).size >= 3,
      enoughPaiSupport: !control.smokeMode,
      thresholdFromDev: true,
      noSecurityRegression: !hasSecurityRegression,
      singleProtocolInExperiment: true,
    },
    startedAt: now,
    durationMinutes: control.smokeMode ? 5 : 48 + Math.min(control.epochs, 20),
    notes: [
      "Generated by the browser mock database.",
      "Synthetic demo data cannot support research claims.",
      hasSecurityRegression ? "Per-PAI APCER regression requires review." : "No raw media is stored or rendered.",
    ],
    tags: [mode, control.modelFamily, control.adaptationMethod, gateVerdict, "synthetic", "mock-db"],
    artifacts: [
      { label: "Mock report", path: `mock-db/reports/${control.experimentId}.md`, kind: "markdown" },
      { label: "Mock per-attack CSV", path: `mock-db/tables/${control.experimentId}_per_attack.csv`, kind: "csv" },
      { label: "Mock eval JSON", path: `mock-db/runs/${runId}/eval_test.json`, kind: "json" },
      { label: "Checkpoint metadata", path: `mock-db/runs/${runId}/checkpoint.meta.json`, kind: "checkpoint-meta" },
    ],
  });
}

function methodOffsets(method: ControlState["adaptationMethod"]): {
  apcer: number;
  bpcer: number;
  auc: number;
  perAttack: number;
} {
  if (method === "full_finetune") return { apcer: 0.08, bpcer: -0.05, auc: -0.005, perAttack: 0.07 };
  if (method === "head_only") return { apcer: 0.01, bpcer: -0.025, auc: 0.008, perAttack: 0.005 };
  if (method === "prototype") return { apcer: -0.005, bpcer: -0.015, auc: 0.006, perAttack: -0.005 };
  if (method === "spoof_preserve") return { apcer: -0.018, bpcer: -0.012, auc: 0.015, perAttack: -0.015 };
  return { apcer: 0, bpcer: 0, auc: 0, perAttack: 0 };
}

function appendAudit(
  state: MockDatabaseState,
  kind: AuditKind,
  severity: AuditSeverity,
  title: string,
  detail: string,
): MockDatabaseState {
  const now = new Date().toISOString();
  return {
    ...state,
    updatedAt: now,
    auditLog: [auditEntry(kind, severity, title, detail), ...state.auditLog].slice(0, maxAuditEntries),
  };
}

function auditEntry(
  kind: AuditKind,
  severity: AuditSeverity,
  title: string,
  detail: string,
): AuditLogEntry {
  const now = new Date().toISOString();
  return {
    entryId: makeId("audit", `${kind}:${title}:${detail}:${now}`),
    at: now,
    kind,
    severity,
    title,
    detail,
  };
}

function sanitizeRuns(runs: DemoRun[]): DemoRun[] {
  return runs.map((run) => DemoRunSchema.parse(run));
}

function sanitizeLiterature(literature: MockDatabaseState["literature"]): MockDatabaseState["literature"] {
  return LiteratureStateSchema.parse(literature);
}

function migrateStoredState(
  raw: unknown,
  seedRuns: DemoRun[],
  seedSource: MockDbSeedSource,
): unknown {
  if (!raw || typeof raw !== "object") return raw;
  const partial = raw as Partial<MockDatabaseState>;
  if ("literature" in partial) {
    return {
      ...partial,
      seedFingerprint: partial.seedFingerprint ?? "legacy-missing-seed-fingerprint",
    };
  }
  return {
    ...createInitialMockDatabase(seedRuns, seedSource),
    ...partial,
    seedFingerprint: partial.seedFingerprint ?? "legacy-missing-seed-fingerprint",
    runs: partial.runs ?? seedRuns,
    literature: sanitizeLiterature(demoLiterature),
    auditLog: [
      auditEntry(
        "db_recovered",
        "info",
        "Mock DB migrated",
        "Literature tables were added to the existing browser mock DB.",
      ),
      ...(partial.auditLog ?? []),
    ].slice(0, maxAuditEntries),
  };
}

function canUseStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function contractIssueMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Stored mock DB failed contract validation.";
}

function makeId(prefix: string, input: string): string {
  return `${prefix}_${stableHash(input).slice(0, 14)}`;
}

function makeSeedFingerprint(seedRuns: DemoRun[], seedSource: MockDbSeedSource): string {
  return stableHash(
    JSON.stringify({
      seedSource,
      runs: seedRuns.map((run) => ({
        runId: run.runId,
        experimentId: run.experimentId,
        protocolHash: run.protocolHash,
        scienceHash: run.scienceHash,
        specHash: run.specHash,
      })),
    }),
  );
}

function stableHash(input: string): string {
  const salts = [0x811c9dc5, 0x9e3779b1, 0x85ebca77, 0xc2b2ae3d];
  return salts
    .map((salt) => {
      let hash = salt;
      for (let index = 0; index < input.length; index += 1) {
        hash ^= input.charCodeAt(index);
        hash = Math.imul(hash, 16777619);
      }
      return (hash >>> 0).toString(16).padStart(8, "0");
    })
    .join("")
    .repeat(2);
}

function centeredNoise(input: string): number {
  const value = Number.parseInt(stableHash(input).slice(0, 8), 16) / 0xffffffff;
  return value - 0.5;
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, Number(value.toFixed(6))));
}
