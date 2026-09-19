import type {
  AdaptationMethod,
  ClaimEligibility,
  DemoArtifact,
  DemoRun,
  GateVerdict,
  ModelFamily,
  PadMetrics,
  PiiPolicy,
  RunMode,
  RunStatus,
  ThresholdProvenance,
} from "../types";

interface DashboardBundleJson {
  schema_version?: string;
  runs?: DashboardRunJson[];
}

interface DashboardRunJson {
  run_id: string;
  experiment_id: string;
  title?: string | null;
  status: string;
  gate_verdict?: string;
  mode: string;
  seed?: number | null;
  started_at?: string;
  duration_seconds?: number | null;
  model_family?: string;
  adaptation_method?: string;
  protocol_id?: string;
  protocol_hash?: string;
  science_hash?: string;
  spec_hash?: string;
  manifest_hashes?: Record<string, string>;
  dataset_pii_policies?: Record<string, string>;
  adaptation_set_hash?: string | null;
  research_claim_allowed?: boolean;
  claim_eligibility?: ClaimEligibilityJson;
  threshold?: ThresholdJson;
  metrics?: MetricsJson;
  per_attack?: PerAttackJson[];
  tags?: Record<string, string>;
  artifacts?: ArtifactJson[];
}

interface ClaimEligibilityJson {
  allowed?: boolean;
  reasons?: string[];
  full_mode?: boolean;
  research_claim_allowed?: boolean;
  at_least_three_seeds?: boolean;
  enough_pai_support?: boolean;
  threshold_from_dev?: boolean;
  no_security_regression?: boolean;
  single_protocol_in_experiment?: boolean;
}

interface ThresholdJson {
  rule?: string;
  fitted_on?: string | null;
  tau?: number | null;
  dev_n_bona_fide?: number | null;
  dev_n_attack?: number | null;
}

interface MetricsJson {
  apcer?: number;
  bpcer?: number;
  acer?: number;
  hter?: number;
  auc?: number;
  tau?: number;
}

interface PerAttackJson {
  pai?: string;
  apcer?: number;
  baseline_apcer?: number | null;
  delta?: number | null;
  n_attack?: number;
  insufficient_support?: boolean;
  regressed?: boolean | null;
}

interface ArtifactJson {
  label?: string;
  relative_path?: string;
  kind?: string;
}

const runStatuses: RunStatus[] = ["smoke_ok", "success", "security_regression", "inconclusive"];
const runModes: RunMode[] = ["smoke", "full", "unknown"];
const modelFamilies: ModelFamily[] = ["frame_baseline", "video_baseline"];
const adaptationMethods: AdaptationMethod[] = ["none", "full_finetune", "head_only", "prototype", "spoof_preserve"];
const gateVerdicts: GateVerdict[] = [
  "pass",
  "no_gate",
  "security_regression",
  "inconclusive",
  "comparison_blocked",
  "unknown",
];
const artifactKinds: DemoArtifact["kind"][] = ["markdown", "csv", "json", "yaml", "image", "checkpoint-meta", "unknown"];

export async function loadDashboardRuns(): Promise<DemoRun[] | null> {
  try {
    const response = await fetch("/dashboard-demo.json", { cache: "no-store" });
    if (!response.ok) return null;
    const payload = (await response.json()) as DashboardBundleJson;
    if (!Array.isArray(payload.runs)) return null;
    const runs = payload.runs.map(toDemoRun).filter((run): run is DemoRun => run !== null);
    return runs.length > 0 ? runs : null;
  } catch {
    return null;
  }
}

function toDemoRun(raw: DashboardRunJson): DemoRun | null {
  if (!raw.run_id || !raw.experiment_id) return null;
  const metrics = toMetrics(raw.metrics);
  const threshold = toThreshold(raw.threshold, metrics.tau);
  const piiPolicies = toPiiPolicies(raw.dataset_pii_policies ?? {});
  const researchClaimAllowed = Boolean(raw.research_claim_allowed);
  const gateVerdict = enumValue(raw.gate_verdict, gateVerdicts, "unknown");
  const mode = enumValue(raw.mode, runModes, "unknown");
  return {
    experimentId: raw.experiment_id,
    runId: raw.run_id,
    title: raw.title ?? raw.experiment_id,
    status: enumValue(raw.status, runStatuses, "inconclusive"),
    mode,
    modelFamily: enumValue(raw.model_family, modelFamilies, "video_baseline"),
    adaptationMethod: enumValue(raw.adaptation_method, adaptationMethods, "none"),
    protocolId: raw.protocol_id ?? "unknown",
    protocolHash: raw.protocol_hash ?? "unknown",
    scienceHash: raw.science_hash ?? "unknown",
    specHash: raw.spec_hash ?? "unknown",
    manifestHashes: raw.manifest_hashes ?? {},
    datasetPiiPolicies: piiPolicies,
    adaptationSetHash: raw.adaptation_set_hash ?? null,
    seed: raw.seed ?? 0,
    metrics,
    threshold,
    perAttack: toPerAttack(raw.per_attack ?? []),
    gateVerdict,
    researchClaimAllowed,
    demoOnly: false,
    piiPolicy: runPiiPolicy(piiPolicies),
    claimEligibility: toClaimEligibility(raw.claim_eligibility, mode, researchClaimAllowed, gateVerdict),
    startedAt: raw.started_at ?? new Date(0).toISOString(),
    durationMinutes: raw.duration_seconds ? Math.round(raw.duration_seconds / 60) : 0,
    notes: [
      researchClaimAllowed ? "Loaded from dashboard export." : "Run provenance blocks research claims.",
      "No raw media is displayed in this UI.",
    ],
    tags: Object.values(raw.tags ?? {}),
    artifacts: toArtifacts(raw.artifacts ?? []),
  };
}

/**
 * Collapse the per-dataset policies into one policy for the run, most restrictive first.
 *
 * Mapping everything that is not synthetic to "unknown" erased internal_only and
 * licensed_research, and the synthetic-only filter then hid every row of a real export.
 */
function runPiiPolicy(policies: Record<string, PiiPolicy>): PiiPolicy {
  const values = Object.values(policies);
  if (values.length === 0 || values.includes("unknown")) return "unknown";
  if (values.includes("synthetic")) return "synthetic";
  if (values.includes("internal_only")) return "internal_only";
  return "licensed_research";
}

function toMetrics(raw?: MetricsJson): PadMetrics {
  return {
    apcer: numberValue(raw?.apcer),
    bpcer: numberValue(raw?.bpcer),
    acer: numberValue(raw?.acer),
    hter: numberValue(raw?.hter),
    auc: numberValue(raw?.auc),
    tau: numberValue(raw?.tau),
  };
}

function toThreshold(raw: ThresholdJson | undefined, fallbackTau: number): ThresholdProvenance {
  return {
    rule: raw?.rule === "bpcer_at_apcer" ? "bpcer_at_apcer" : "eer",
    fittedOn: raw?.fitted_on ?? "unknown",
    tau: raw?.tau ?? fallbackTau,
    devSupport: {
      bonaFide: raw?.dev_n_bona_fide ?? 0,
      attack: raw?.dev_n_attack ?? 0,
    },
  };
}

function toPerAttack(rows: PerAttackJson[]) {
  return rows.map((row) => ({
    pai: row.pai ?? "unknown",
    apcer: numberValue(row.apcer),
    baselineApcer: numberValue(row.baseline_apcer),
    delta: numberValue(row.delta),
    nAttack: row.n_attack ?? 0,
    insufficientSupport: Boolean(row.insufficient_support),
  }));
}

function toClaimEligibility(
  raw: ClaimEligibilityJson | undefined,
  mode: RunMode,
  researchClaimAllowed: boolean,
  gateVerdict: GateVerdict,
): ClaimEligibility {
  return {
    allowed: Boolean(raw?.allowed),
    reasons: raw?.reasons ?? [],
    fullMode: raw?.full_mode ?? mode === "full",
    researchClaimAllowed: raw?.research_claim_allowed ?? researchClaimAllowed,
    atLeastThreeSeeds: Boolean(raw?.at_least_three_seeds),
    enoughPaiSupport: Boolean(raw?.enough_pai_support),
    thresholdFromDev: Boolean(raw?.threshold_from_dev),
    noSecurityRegression: raw?.no_security_regression ?? gateVerdict !== "security_regression",
    singleProtocolInExperiment: Boolean(raw?.single_protocol_in_experiment),
  };
}

function toArtifacts(rows: ArtifactJson[]): DemoArtifact[] {
  return rows.map((row) => ({
    label: row.label ?? "Artifact",
    path: row.relative_path ?? "unknown",
    kind: enumValue(row.kind, artifactKinds, "unknown"),
  }));
}

function toPiiPolicies(raw: Record<string, string>): Record<string, PiiPolicy> {
  const out: Record<string, PiiPolicy> = {};
  for (const [key, value] of Object.entries(raw)) {
    out[key] = enumValue(value, ["synthetic", "internal_only", "licensed_research", "unknown"], "unknown");
  }
  return out;
}

function enumValue<T extends string>(value: string | undefined, allowed: T[], fallback: T): T {
  return value && allowed.includes(value as T) ? (value as T) : fallback;
}

function numberValue(value: number | null | undefined): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}
