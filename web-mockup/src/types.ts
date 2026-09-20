export type RunStatus = "smoke_ok" | "success" | "security_regression" | "inconclusive";
export type RunMode = "smoke" | "full" | "unknown";
export type ModelFamily = "frame_baseline" | "video_baseline";
export type AdaptationMethod = "none" | "full_finetune" | "head_only" | "prototype" | "spoof_preserve";
export type GateVerdict =
  | "pass"
  | "no_gate"
  | "security_regression"
  | "inconclusive"
  | "comparison_blocked"
  | "unknown";
export type PiiPolicy = "synthetic" | "internal_only" | "licensed_research" | "unknown";
export type Locale = "ko" | "en";
export type MockDbSeedSource = "demo" | "export";
export type MockDbLoadOrigin = "seeded" | "persisted" | "recovered";
export type AuditSeverity = "info" | "success" | "warning" | "danger";
export type LiteratureProvider = "openalex" | "semantic_scholar" | "crossref" | "opencitations" | "arxiv" | "mock";
export type PaperStatus = "discovered" | "queued" | "reading" | "extracted" | "verified" | "excluded" | "linked_to_experiment";
export type EvidenceKind = "dataset" | "method" | "metric" | "claim" | "limitation" | "protocol";
export type GraphNodeKind = "paper" | "author" | "dataset" | "method" | "task" | "venue" | "experiment";
export type GraphEdgeKind =
  | "cites"
  | "cited_by"
  | "uses_dataset"
  | "evaluates_on"
  | "reports_metric"
  | "shares_author"
  | "published_in"
  | "defines_protocol"
  | "states_claim"
  | "notes_limitation"
  | "related_method"
  | "linked_experiment";
export type AuditKind =
  | "db_seeded"
  | "db_recovered"
  | "db_reset"
  | "draft_saved"
  | "command_copied"
  | "report_generated"
  | "paper_queued"
  | "paper_status_changed"
  | "paper_linked";

export interface PadMetrics {
  apcer: number;
  bpcer: number;
  acer: number;
  hter: number;
  auc: number;
  tau: number;
}

export interface ClaimEligibility {
  allowed: boolean;
  reasons: string[];
  fullMode: boolean;
  researchClaimAllowed: boolean;
  atLeastThreeSeeds: boolean;
  enoughPaiSupport: boolean;
  thresholdFromDev: boolean;
  noSecurityRegression: boolean;
  singleProtocolInExperiment: boolean;
}

export interface ThresholdProvenance {
  rule: "eer" | "bpcer_at_apcer";
  fittedOn: "source/dev" | "target/dev" | string;
  tau: number;
  devSupport: {
    bonaFide: number;
    attack: number;
  };
}

export interface PerAttackMetric {
  pai: string;
  apcer: number;
  baselineApcer: number;
  delta: number;
  nAttack: number;
  insufficientSupport: boolean;
}

export interface DemoArtifact {
  label: string;
  path: string;
  kind: "markdown" | "csv" | "json" | "yaml" | "image" | "checkpoint-meta" | "unknown";
}

export interface DemoRun {
  experimentId: string;
  runId: string;
  title: string;
  status: RunStatus;
  mode: RunMode;
  modelFamily: ModelFamily;
  adaptationMethod: AdaptationMethod;
  protocolId: string;
  protocolHash: string;
  scienceHash: string;
  specHash: string;
  manifestHashes: Record<string, string>;
  datasetPiiPolicies: Record<string, PiiPolicy>;
  adaptationSetHash: string | null;
  seed: number;
  metrics: PadMetrics;
  threshold: ThresholdProvenance;
  perAttack: PerAttackMetric[];
  gateVerdict: GateVerdict;
  researchClaimAllowed: boolean;
  demoOnly: boolean;
  piiPolicy: PiiPolicy;
  claimEligibility: ClaimEligibility;
  startedAt: string;
  durationMinutes: number;
  notes: string[];
  tags: string[];
  artifacts: DemoArtifact[];
}

export interface ControlState {
  experimentId: string;
  modelFamily: ModelFamily;
  frames: number;
  batchSize: number;
  epochs: number;
  learningRate: string;
  adaptationMethod: AdaptationMethod;
  sourceRunId: string;
  protocolId: string;
  thresholdRule: "eer" | "bpcer_at_apcer";
  smokeMode: boolean;
  seed: number;
}

export interface ExperimentDraft {
  draftId: string;
  experimentId: string;
  createdAt: string;
  updatedAt: string;
  control: ControlState;
  yamlPatch: string;
  validationCommand: string;
  command: string;
  warnings: string[];
}

export interface AuditLogEntry {
  entryId: string;
  at: string;
  kind: AuditKind;
  severity: AuditSeverity;
  title: string;
  detail: string;
}

export interface LiteratureAuthor {
  authorId: string;
  name: string;
  affiliation: string;
}

export interface LiteratureVenue {
  venueId: string;
  name: string;
  type: "conference" | "journal" | "preprint" | "workshop" | "unknown";
}

export interface LiteratureDataset {
  datasetId: string;
  name: string;
  domain: string;
  modality: "image" | "video" | "mixed" | "unknown";
  piiPolicy: PiiPolicy;
  notes: string[];
}

export interface LiteratureMethod {
  methodId: string;
  name: string;
  family: string;
  adaptationType: AdaptationMethod | "other";
  notes: string[];
}

export interface LiteraturePaper {
  paperId: string;
  title: string;
  abstract: string;
  year: number;
  venueId: string;
  authorIds: string[];
  doi: string | null;
  arxivId: string | null;
  semanticScholarId: string | null;
  openAlexId: string | null;
  citationCount: number;
  influentialCitationCount: number;
  fieldsOfStudy: string[];
  keywords: string[];
  providerIds: LiteratureProvider[];
  retrievedAt: string;
  providerPayloadHash: string;
  status: PaperStatus;
  relevanceScore: number;
  notes: string[];
}

export interface LiteratureCitation {
  sourcePaperId: string;
  targetPaperId: string;
  provider: LiteratureProvider;
}

export interface LiteratureEvidenceItem {
  evidenceId: string;
  paperId: string;
  kind: EvidenceKind;
  label: string;
  value: string;
  confidence: number;
  extractedBy: "mock" | "api" | "human";
  verified: boolean;
}

export interface PaperExperimentLink {
  paperId: string;
  experimentId: string;
  relation: "motivates" | "baseline" | "dataset" | "metric" | "limitation";
}

export interface ReadingNote {
  noteId: string;
  paperId: string;
  createdAt: string;
  text: string;
}

export interface ResearchQuery {
  queryId: string;
  text: string;
  provider: LiteratureProvider;
  createdAt: string;
  resultPaperIds: string[];
}

export interface LiteratureState {
  papers: LiteraturePaper[];
  authors: LiteratureAuthor[];
  venues: LiteratureVenue[];
  datasets: LiteratureDataset[];
  methods: LiteratureMethod[];
  citations: LiteratureCitation[];
  evidenceItems: LiteratureEvidenceItem[];
  paperExperimentLinks: PaperExperimentLink[];
  readingNotes: ReadingNote[];
  researchQueries: ResearchQuery[];
}

export interface LiteratureFilters {
  query: string;
  yearMin: number;
  yearMax: number;
  provider: "all" | LiteratureProvider;
  status: "all" | PaperStatus;
  datasetId: "all" | string;
  methodId: "all" | string;
  minCitations: number;
  openAccessOnly: boolean;
}

export interface LiteratureGraphNode {
  id: string;
  label: string;
  kind: GraphNodeKind;
  score: number;
}

export interface LiteratureGraphEdge {
  id: string;
  source: string;
  target: string;
  kind: GraphEdgeKind;
}

export interface MockDatabaseState {
  version: 1;
  seedSource: MockDbSeedSource;
  seedFingerprint: string;
  createdAt: string;
  updatedAt: string;
  runs: DemoRun[];
  literature: LiteratureState;
  drafts: ExperimentDraft[];
  auditLog: AuditLogEntry[];
}

export interface MockDatabaseLoadResult {
  state: MockDatabaseState;
  origin: MockDbLoadOrigin;
  resetReason: string | null;
}

export interface Filters {
  query: string;
  status: "all" | RunStatus;
  mode: "all" | RunMode;
  modelFamily: "all" | ModelFamily;
  adaptationMethod: "all" | AdaptationMethod;
  protocolId: "all" | string;
  gateVerdict: "all" | GateVerdict;
  seed: "all" | string;
  includeSmoke: boolean;
  syntheticOnly: boolean;
  maxApcer: number;
  minAuc: number;
}

export type MetricKey = keyof PadMetrics;
