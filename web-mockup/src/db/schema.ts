import { z } from "zod";

export const RunStatusSchema = z.enum([
  "smoke_ok",
  "success",
  "security_regression",
  "inconclusive",
]);

export const RunModeSchema = z.enum(["smoke", "full", "unknown"]);

export const ModelFamilySchema = z.enum(["frame_baseline", "video_baseline"]);

export const ExperimentGoalSchema = z.enum(["baseline", "adapt_real_only", "adapt_few_shot"]);

/**
 * Catalogue node ids, path-shaped: `aihub115/train/Light_01_High/real_01`.
 *
 * Checked as a shape rather than against the catalogue, so a draft saved before a domain was
 * renamed stays loadable and the tree shows what it can still resolve.
 */
export const DatasetSelectionSchema = z
  .object({
    train: z.array(z.string().regex(/^[A-Za-z0-9_][A-Za-z0-9_./-]*$/)).max(400),
    dev: z.array(z.string().regex(/^[A-Za-z0-9_][A-Za-z0-9_./-]*$/)).max(400),
    test: z.array(z.string().regex(/^[A-Za-z0-9_][A-Za-z0-9_./-]*$/)).max(400),
  })
  .strict();

export const AdaptationMethodSchema = z.enum([
  "none",
  "full_finetune",
  "head_only",
  "prototype",
  "spoof_preserve",
]);

export const GateVerdictSchema = z.enum([
  "pass",
  "no_gate",
  "security_regression",
  "inconclusive",
  "comparison_blocked",
  "unknown",
]);

export const PiiPolicySchema = z.enum([
  "synthetic",
  "internal_only",
  "licensed_research",
  "unknown",
]);

export const AuditSeveritySchema = z.enum(["info", "success", "warning", "danger"]);

export const AuditKindSchema = z.enum([
  "db_seeded",
  "db_recovered",
  "db_reset",
  "draft_saved",
  "command_copied",
  "report_generated",
  "paper_queued",
  "paper_status_changed",
  "paper_linked",
]);

export const LiteratureProviderSchema = z.enum([
  "openalex",
  "semantic_scholar",
  "crossref",
  "opencitations",
  "arxiv",
  "mock",
]);

export const PaperStatusSchema = z.enum([
  "discovered",
  "queued",
  "reading",
  "extracted",
  "verified",
  "excluded",
  "linked_to_experiment",
]);

export const EvidenceKindSchema = z.enum([
  "dataset",
  "method",
  "metric",
  "claim",
  "limitation",
  "protocol",
]);

export const PadMetricsSchema = z
  .object({
    apcer: z.number().min(0).max(1),
    bpcer: z.number().min(0).max(1),
    acer: z.number().min(0).max(1),
    hter: z.number().min(0).max(1),
    auc: z.number().min(0).max(1),
    tau: z.number().min(0).max(1),
  })
  .strict();

export const ClaimBlockerSchema = z.enum([
  "mode_not_full",
  "research_claim_not_allowed",
  "dataset_synthetic",
  "dataset_pii_unknown",
  "fewer_than_three_seeds",
  "insufficient_pai_support",
  "threshold_not_from_dev",
  "security_regression",
  "multiple_protocol_hashes",
]);

export const RunNoteSchema = z.enum([
  "loaded_from_export",
  "provenance_blocks_claims",
  "no_raw_media",
  "synthetic_sample",
  "smoke_budget",
  "demo_full_style",
  "pai_regression_review",
  "no_claim_made",
  "claims_need_review",
]);

export const ClaimEligibilitySchema = z
  .object({
    allowed: z.boolean(),
    blockers: z.array(ClaimBlockerSchema),
    fullMode: z.boolean(),
    researchClaimAllowed: z.boolean(),
    atLeastThreeSeeds: z.boolean(),
    enoughPaiSupport: z.boolean(),
    thresholdFromDev: z.boolean(),
    noSecurityRegression: z.boolean(),
    singleProtocolInExperiment: z.boolean(),
  })
  .strict();

export const ThresholdProvenanceSchema = z
  .object({
    rule: z.enum(["eer", "bpcer_at_apcer"]),
    fittedOn: z.string().min(1),
    tau: z.number().min(0).max(1),
    devSupport: z
      .object({
        bonaFide: z.number().int().min(0),
        attack: z.number().int().min(0),
      })
      .strict(),
  })
  .strict();

export const PerAttackMetricSchema = z
  .object({
    pai: z.string().min(1),
    apcer: z.number().min(0).max(1),
    baselineApcer: z.number().min(0).max(1),
    delta: z.number(),
    nAttack: z.number().int().min(0),
    insufficientSupport: z.boolean(),
  })
  .strict();

export const DemoArtifactSchema = z
  .object({
    path: z.string().min(1),
    kind: z.enum(["markdown", "csv", "json", "yaml", "image", "checkpoint-meta", "unknown"]),
  })
  .strict();

export const DemoRunSchema = z
  .object({
    experimentId: z
      .string()
      .min(3)
      .max(80)
      .regex(/^exp_[a-z0-9_]+$/, "Use an experiment ID like exp_demo_name."),
    runId: z
      .string()
      .min(1)
      .max(128)
      .regex(/^[A-Za-z0-9][A-Za-z0-9_.:-]*$/, "Run IDs must be shell-safe."),
    title: z.string().min(1),
    status: RunStatusSchema,
    mode: RunModeSchema,
    modelFamily: ModelFamilySchema,
    adaptationMethod: AdaptationMethodSchema,
    protocolId: z
      .string()
      .min(1)
      .max(120)
      .regex(/^([a-z0-9_]+_v\d+|unknown)$/, "Protocol IDs must match the protocol schema."),
    protocolHash: z.string().min(1),
    scienceHash: z.string().min(1),
    specHash: z.string().min(1),
    manifestHashes: z.record(z.string(), z.string()),
    datasetPiiPolicies: z.record(z.string(), PiiPolicySchema),
    adaptationSetHash: z.string().nullable(),
    seed: z.number().int().min(0),
    metrics: PadMetricsSchema,
    threshold: ThresholdProvenanceSchema,
    perAttack: z.array(PerAttackMetricSchema),
    gateVerdict: GateVerdictSchema,
    researchClaimAllowed: z.boolean(),
    demoOnly: z.boolean(),
    piiPolicy: PiiPolicySchema,
    claimEligibility: ClaimEligibilitySchema,
    startedAt: z.string().min(1),
    durationMinutes: z.number().min(0),
    notes: z.array(RunNoteSchema),
    tags: z.array(z.string()),
    artifacts: z.array(DemoArtifactSchema),
  })
  .strict();

export const ControlStateSchema = z
  .object({
    experimentId: z
      .string()
      .min(3)
      .max(80)
      .regex(/^exp_[a-z0-9_]+$/, "Use an experiment ID like exp_demo_name."),
    goal: ExperimentGoalSchema,
    modelId: z
      .string()
      .min(1)
      .max(64)
      .regex(/^[a-z0-9_]+$/, "Use a model id from the catalogue."),
    datasets: DatasetSelectionSchema,
    modelFamily: ModelFamilySchema,
    frames: z.number().int().min(1).max(16),
    batchSize: z.number().int().min(1).max(64),
    epochs: z.number().int().min(1).max(20),
    learningRate: z
      .string()
      .regex(/^(0|[1-9]\d*)(\.\d+)?(e-\d+)?$/i, "Use a positive numeric learning rate."),
    adaptationMethod: AdaptationMethodSchema,
    sourceRunId: z
      .string()
      .min(1)
      .max(128)
      .regex(/^[A-Za-z0-9][A-Za-z0-9_.:-]*$/, "Use a shell-safe run ID."),
    protocolId: z
      .string()
      .min(1)
      .max(120)
      .regex(/^[a-z0-9_]+_v\d+$/, "Use a protocol ID like syn_a_to_b_v1."),
    thresholdRule: z.enum(["eer", "bpcer_at_apcer"]),
    smokeMode: z.boolean(),
    seed: z.number().int().min(1).max(999),
  })
  .strict()
  .superRefine((control, context) => {
    if (control.smokeMode && control.epochs !== 1) {
      context.addIssue({
        code: "custom",
        path: ["epochs"],
        message: "Smoke mode requires epochs to stay at 1.",
      });
    }
  });

export const ExperimentDraftSchema = z
  .object({
    draftId: z.string().min(1),
    experimentId: z
      .string()
      .min(3)
      .max(80)
      .regex(/^exp_[a-z0-9_]+$/, "Use an experiment ID like exp_demo_name."),
    createdAt: z.string().min(1),
    updatedAt: z.string().min(1),
    control: ControlStateSchema,
    yamlPatch: z.string().min(1),
    validationCommand: z.string().min(1),
    command: z.string().min(1),
    warnings: z.array(z.string()),
  })
  .strict();

export const AuditDetailSchema = z.enum([
  "seeded_from_demo",
  "seeded_from_export",
  "store_reset_to_seed",
  "seed_changed_reset",
  "literature_added",
]);

export const AuditLogEntrySchema = z
  .object({
    entryId: z.string().min(1),
    at: z.string().min(1),
    kind: AuditKindSchema,
    severity: AuditSeveritySchema,
    title: z.string().min(1),
    detail: z.string().min(1),
    // Optional and additive: entries written before this existed keep validating and keep
    // rendering their stored `detail`, so no store has to be thrown away for a log line.
    detailKey: AuditDetailSchema.optional(),
    detailParam: z.string().optional(),
  })
  .strict();

export const LiteratureAuthorSchema = z
  .object({
    authorId: z.string().min(1),
    name: z.string().min(1),
    affiliation: z.string().min(1),
  })
  .strict();

export const LiteratureVenueSchema = z
  .object({
    venueId: z.string().min(1),
    name: z.string().min(1),
    type: z.enum(["conference", "journal", "preprint", "workshop", "unknown"]),
  })
  .strict();

export const LiteratureDatasetSchema = z
  .object({
    datasetId: z.string().min(1),
    name: z.string().min(1),
    domain: z.string().min(1),
    modality: z.enum(["image", "video", "mixed", "unknown"]),
    piiPolicy: PiiPolicySchema,
    notes: z.array(z.string()),
  })
  .strict();

export const LiteratureMethodSchema = z
  .object({
    methodId: z.string().min(1),
    name: z.string().min(1),
    family: z.string().min(1),
    adaptationType: z.union([AdaptationMethodSchema, z.literal("other")]),
    notes: z.array(z.string()),
  })
  .strict();

export const LiteraturePaperSchema = z
  .object({
    paperId: z.string().min(1),
    title: z.string().min(1),
    abstract: z.string().min(1),
    year: z.number().int().min(1980).max(2100),
    venueId: z.string().min(1),
    authorIds: z.array(z.string().min(1)),
    doi: z.string().nullable(),
    arxivId: z.string().nullable(),
    semanticScholarId: z.string().nullable(),
    openAlexId: z.string().nullable(),
    citationCount: z.number().int().min(0),
    influentialCitationCount: z.number().int().min(0),
    fieldsOfStudy: z.array(z.string()),
    keywords: z.array(z.string()),
    providerIds: z.array(LiteratureProviderSchema),
    retrievedAt: z.string().min(1),
    providerPayloadHash: z.string().min(1),
    status: PaperStatusSchema,
    relevanceScore: z.number().min(0).max(1),
    notes: z.array(z.string()),
  })
  .strict();

export const LiteratureCitationSchema = z
  .object({
    sourcePaperId: z.string().min(1),
    targetPaperId: z.string().min(1),
    provider: LiteratureProviderSchema,
  })
  .strict();

export const LiteratureEvidenceItemSchema = z
  .object({
    evidenceId: z.string().min(1),
    paperId: z.string().min(1),
    kind: EvidenceKindSchema,
    label: z.string().min(1),
    value: z.string().min(1),
    confidence: z.number().min(0).max(1),
    extractedBy: z.enum(["mock", "api", "human"]),
    verified: z.boolean(),
  })
  .strict();

export const PaperExperimentLinkSchema = z
  .object({
    paperId: z.string().min(1),
    experimentId: z
      .string()
      .min(3)
      .max(80)
      .regex(/^exp_[a-z0-9_]+$/, "Use an experiment ID like exp_demo_name."),
    relation: z.enum(["motivates", "baseline", "dataset", "metric", "limitation"]),
  })
  .strict();

export const ReadingNoteSchema = z
  .object({
    noteId: z.string().min(1),
    paperId: z.string().min(1),
    createdAt: z.string().min(1),
    text: z.string().min(1),
  })
  .strict();

export const ResearchQuerySchema = z
  .object({
    queryId: z.string().min(1),
    text: z.string().min(1),
    provider: LiteratureProviderSchema,
    createdAt: z.string().min(1),
    resultPaperIds: z.array(z.string().min(1)),
  })
  .strict();

export const LiteratureStateSchema = z
  .object({
    papers: z.array(LiteraturePaperSchema),
    authors: z.array(LiteratureAuthorSchema),
    venues: z.array(LiteratureVenueSchema),
    datasets: z.array(LiteratureDatasetSchema),
    methods: z.array(LiteratureMethodSchema),
    citations: z.array(LiteratureCitationSchema),
    evidenceItems: z.array(LiteratureEvidenceItemSchema),
    paperExperimentLinks: z.array(PaperExperimentLinkSchema),
    readingNotes: z.array(ReadingNoteSchema),
    researchQueries: z.array(ResearchQuerySchema),
  })
  .strict();

export const MockDatabaseStateSchema = z
  .object({
    version: z.literal(1),
    seedSource: z.enum(["demo", "export"]),
    seedFingerprint: z.string().min(1),
    createdAt: z.string().min(1),
    updatedAt: z.string().min(1),
    runs: z.array(DemoRunSchema),
    literature: LiteratureStateSchema,
    drafts: z.array(ExperimentDraftSchema),
    auditLog: z.array(AuditLogEntrySchema),
  })
  .strict();
