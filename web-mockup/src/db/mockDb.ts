import type {
  AuditDetail,
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
} from "../types";
import { demoLiterature } from "../data/demoLiterature";
import {
  MockDatabaseStateSchema,
  ControlStateSchema,
  DemoRunSchema,
  LiteratureStateSchema,
} from "./schema";
import { buildLaunchCommand, buildValidationCommand, buildYamlPatch, controlWarnings } from "./controlPreview";

export const MOCK_DB_KEY = "pad-research-web-mockup-db-v1";

const maxAuditEntries = 120;

/** Tag that the removed browser run generator stamped on every row it fabricated. */
const FABRICATED_RUN_TAG = "mock-db";

/** Audit kinds that still exist; anything else is from the removed job queue. */
const AUDIT_KINDS: AuditKind[] = [
  "db_seeded",
  "db_recovered",
  "db_reset",
  "draft_saved",
  "command_copied",
  "report_generated",
  "paper_queued",
  "paper_status_changed",
  "paper_linked",
];

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
    auditLog: [
      auditEntry(
        "db_seeded",
        "info",
        "Mock DB seeded",
        `Seeded from ${seedSource} rows.`,
        seedSource === "export" ? "seeded_from_export" : "seeded_from_demo",
      ),
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
        "seed_changed_reset",
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
    "store_reset_to_seed",
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

function appendAudit(
  state: MockDatabaseState,
  kind: AuditKind,
  severity: AuditSeverity,
  title: string,
  detail: string,
  detailKey?: AuditDetail,
): MockDatabaseState {
  const now = new Date().toISOString();
  return {
    ...state,
    updatedAt: now,
    auditLog: [auditEntry(kind, severity, title, detail, detailKey), ...state.auditLog].slice(
      0,
      maxAuditEntries,
    ),
  };
}

function auditEntry(
  kind: AuditKind,
  severity: AuditSeverity,
  title: string,
  detail: string,
  detailKey?: AuditDetail,
): AuditLogEntry {
  const now = new Date().toISOString();
  return {
    entryId: makeId("audit", `${kind}:${title}:${detail}:${now}`),
    at: now,
    kind,
    severity,
    title,
    detail,
    // Spread rather than always-present: an entry with `detailKey: undefined` fails the strict
    // zod schema, and the field is meant to be absent when there is no fixed sentence.
    ...(detailKey ? { detailKey } : {}),
  };
}

function sanitizeRuns(runs: DemoRun[]): DemoRun[] {
  return runs.map((run) => DemoRunSchema.parse(run));
}

function sanitizeLiterature(literature: MockDatabaseState["literature"]): MockDatabaseState["literature"] {
  return LiteratureStateSchema.parse(literature);
}

/**
 * True when a stored row already speaks in codes rather than sentences.
 *
 * A pre-upgrade row has `claimEligibility.reasons` (prose) and free-text `notes`; a current one
 * has `blockers` and note keys. Checking the shape rather than a version counter means a store
 * written by any older build is handled, including ones that never had a version.
 */
function storesDisplayCodes(run: DemoRun): boolean {
  const eligibility = run.claimEligibility as Partial<DemoRun["claimEligibility"]> & {
    reasons?: unknown;
  };
  if (!Array.isArray(eligibility?.blockers)) return false;
  if ("reasons" in (eligibility ?? {})) return false;
  // A note key never contains a space; a sentence always does.
  return (run.notes ?? []).every((note) => typeof note === "string" && !note.includes(" "));
}

function migrateStoredState(
  raw: unknown,
  seedRuns: DemoRun[],
  seedSource: MockDbSeedSource,
): unknown {
  if (!raw || typeof raw !== "object") return raw;
  // `jobs` and browser-generated runs no longer exist. Strip both instead of letting the
  // strict schema reject the whole store: a store written before the removal still holds rows
  // whose metrics came from a formula, and those must not survive the upgrade. Audit entries
  // that announced a fabricated run go with them.
  const { jobs: _removedJobs, ...stored } = raw as Partial<MockDatabaseState> & {
    jobs?: unknown;
  };
  const partial = stored as Partial<MockDatabaseState>;
  const withoutFabricated = {
    ...partial,
    // Rows written before claim blockers and run notes became codes carry English sentences
    // where the schema now wants an enum. They are always re-derivable from the seed, so they
    // are dropped here rather than left to fail validation — a parse failure resets the whole
    // store with a raw zod error, which says nothing useful to whoever is looking at it.
    runs: partial.runs
      ?.filter((run) => !run.tags?.includes(FABRICATED_RUN_TAG))
      .filter((run) => storesDisplayCodes(run)),
    auditLog: partial.auditLog?.filter((entry) => AUDIT_KINDS.includes(entry.kind)),
  };
  if ("literature" in partial) {
    return {
      ...withoutFabricated,
      seedFingerprint: partial.seedFingerprint ?? "legacy-missing-seed-fingerprint",
    };
  }
  return {
    ...createInitialMockDatabase(seedRuns, seedSource),
    ...partial,
    seedFingerprint: partial.seedFingerprint ?? "legacy-missing-seed-fingerprint",
    runs: withoutFabricated.runs ?? seedRuns,
    literature: sanitizeLiterature(demoLiterature),
    auditLog: [
      auditEntry(
        "db_recovered",
        "info",
        "Mock DB migrated",
        "Literature tables were added to the existing browser mock DB.",
        "literature_added",
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

