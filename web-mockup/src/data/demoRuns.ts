import type { AdaptationMethod, DemoRun, GateVerdict, ModelFamily, RunMode, RunStatus } from "../types";

const protocolHash = "c9b36ca83c9ae3007637b08a102d227c230ea44c33295b4b13f0f66be5449b97";
const altProtocolHash = "af8e0fbd8ab255933a460b03aed8f4ad9942e06a4a46d72cb5aeba8154a08db8";
const syntheticManifestHashes = {
  synthetic_a: "b6e7f1ed3ec2f25b6af07027682fb43774b95240f15efe0e1e702ebd7f8325cf",
  synthetic_b: "4f7e8a93867d884f10f5acdf8f8fb63b060db9d63e4f505e1296db030b6529aa",
};

const titles: Record<string, string> = {
  exp_syn_e01_frame_source_only: "Frame source-only baseline",
  exp_syn_e02_video_source_only: "Video source-only baseline",
  exp_syn_e03_video_full_ft_bf_only: "Video full fine-tune, target BF only",
  exp_demo_video_head_only: "Video head-only adaptation",
  exp_demo_video_prototype: "Video prototype preservation",
  exp_demo_spoof_preserve: "Video spoof-preserving regularization",
};

function run(
  experimentId: keyof typeof titles,
  seed: number,
  status: RunStatus,
  mode: RunMode,
  modelFamily: ModelFamily,
  adaptationMethod: AdaptationMethod,
  gateVerdict: GateVerdict,
  values: {
    apcer: number;
    bpcer: number;
    acer: number;
    hter: number;
    auc: number;
    print: number;
    replayPhone: number;
    replayTablet: number;
    baselinePrint?: number;
    baselineReplayPhone?: number;
    baselineReplayTablet?: number;
    protocol?: "main" | "alt";
  },
): DemoRun {
  const hash = values.protocol === "alt" ? altProtocolHash : protocolHash;
  const runId = `${experimentId.replace("exp_", "run_")}_${seed}_${mode}`;
  const baselinePrint = values.baselinePrint ?? 0.16;
  const baselineReplayPhone = values.baselineReplayPhone ?? 0.2;
  const baselineReplayTablet = values.baselineReplayTablet ?? 0.23;
  const minAttack = mode === "smoke" ? 4 : 28;
  const claimReasons = [
    // Sentences, not field names. The drawer used to print these verbatim, so a reader met
    // `researchClaimAllowed is false` with no schema to look it up in.
    "The dataset behind this row is synthetic, so it demonstrates the pipeline rather than a detector.",
    mode === "smoke"
      ? "This was a smoke run: a handful of batches, never a performance measurement."
      : "This is full-style demo data, not a measured full run.",
    gateVerdict === "security_regression"
      ? "The security regression gate failed: at least one attack type got worse after adaptation."
      : "",
    gateVerdict === "inconclusive"
      ? "The gate could not decide: too few attack samples per PAI to tell."
      : "",
  ].filter(Boolean);
  return {
    experimentId,
    runId,
    title: titles[experimentId],
    status,
    mode,
    modelFamily,
    adaptationMethod,
    protocolId: values.protocol === "alt" ? "syn_a_to_b_v1" : "syn_a_to_b_bf_adapt_v1",
    protocolHash: hash,
    scienceHash: `${hash.slice(0, 20)}${seed}${mode}`,
    specHash: `${hash.slice(0, 18)}spec${seed}${mode}`,
    manifestHashes: syntheticManifestHashes,
    datasetPiiPolicies: { synthetic_a: "synthetic", synthetic_b: "synthetic" },
    adaptationSetHash: adaptationMethod === "none" ? null : `${hash.slice(0, 18)}adapt${seed}`,
    seed,
    metrics: {
      apcer: values.apcer,
      bpcer: values.bpcer,
      acer: values.acer,
      hter: values.hter,
      auc: values.auc,
      tau: 0.5 + seed * 0.004,
    },
    threshold: {
      rule: "eer",
      fittedOn: "source/dev",
      tau: 0.5 + seed * 0.004,
      devSupport: {
        bonaFide: mode === "smoke" ? 8 : 56,
        attack: mode === "smoke" ? 12 : 84,
      },
    },
    perAttack: [
      {
        pai: "print",
        apcer: values.print,
        baselineApcer: baselinePrint,
        delta: values.print - baselinePrint,
        nAttack: minAttack,
        insufficientSupport: mode === "smoke",
      },
      {
        pai: "replay_phone",
        apcer: values.replayPhone,
        baselineApcer: baselineReplayPhone,
        delta: values.replayPhone - baselineReplayPhone,
        nAttack: minAttack,
        insufficientSupport: mode === "smoke",
      },
      {
        pai: "replay_tablet",
        apcer: values.replayTablet,
        baselineApcer: baselineReplayTablet,
        delta: values.replayTablet - baselineReplayTablet,
        nAttack: minAttack,
        insufficientSupport: mode === "smoke",
      },
    ],
    gateVerdict,
    researchClaimAllowed: false,
    demoOnly: true,
    piiPolicy: "synthetic",
    claimEligibility: {
      allowed: false,
      reasons: claimReasons,
      fullMode: mode === "full",
      researchClaimAllowed: false,
      atLeastThreeSeeds: false,
      enoughPaiSupport: mode === "full",
      thresholdFromDev: true,
      noSecurityRegression: gateVerdict !== "security_regression",
      singleProtocolInExperiment: true,
    },
    startedAt: `2026-09-${String(10 + seed).padStart(2, "0")}T0${seed}:15:00Z`,
    durationMinutes: mode === "smoke" ? 4 + seed : 46 + seed * 3,
    notes: [
      "Synthetic sanity sample only.",
      mode === "smoke" ? "Smoke budget. Do not compare performance." : "Demo full-style sample.",
      gateVerdict === "security_regression" ? "Per-PAI APCER regression requires review." : "No claim is made from this run.",
    ],
    tags: [mode, modelFamily, adaptationMethod, gateVerdict, "synthetic"],
    artifacts: [
      { label: "Report", path: `experiments/reports/${experimentId}.md`, kind: "markdown" },
      { label: "Per-attack CSV", path: `artifacts/tables/${experimentId}_per_attack.csv`, kind: "csv" },
      { label: "Eval JSON", path: `outputs/${experimentId}/${runId}/eval_test.json`, kind: "json" },
      { label: "Checkpoint metadata", path: `outputs/${experimentId}/${runId}/checkpoint.meta.json`, kind: "checkpoint-meta" },
    ],
  };
}

export const demoRuns: DemoRun[] = [
  run("exp_syn_e01_frame_source_only", 1, "success", "full", "frame_baseline", "none", "no_gate", {
    apcer: 0.29,
    bpcer: 0.22,
    acer: 0.255,
    hter: 0.25,
    auc: 0.76,
    print: 0.22,
    replayPhone: 0.31,
    replayTablet: 0.34,
  }),
  run("exp_syn_e01_frame_source_only", 2, "success", "full", "frame_baseline", "none", "no_gate", {
    apcer: 0.27,
    bpcer: 0.24,
    acer: 0.255,
    hter: 0.26,
    auc: 0.75,
    print: 0.2,
    replayPhone: 0.28,
    replayTablet: 0.32,
  }),
  run("exp_syn_e01_frame_source_only", 3, "smoke_ok", "smoke", "frame_baseline", "none", "no_gate", {
    apcer: 0.33,
    bpcer: 0.2,
    acer: 0.265,
    hter: 0.28,
    auc: 0.71,
    print: 0.25,
    replayPhone: 0.35,
    replayTablet: 0.38,
  }),
  run("exp_syn_e02_video_source_only", 1, "success", "full", "video_baseline", "none", "no_gate", {
    apcer: 0.21,
    bpcer: 0.19,
    acer: 0.2,
    hter: 0.205,
    auc: 0.82,
    print: 0.16,
    replayPhone: 0.2,
    replayTablet: 0.23,
  }),
  run("exp_syn_e02_video_source_only", 2, "success", "full", "video_baseline", "none", "no_gate", {
    apcer: 0.19,
    bpcer: 0.18,
    acer: 0.185,
    hter: 0.19,
    auc: 0.84,
    print: 0.15,
    replayPhone: 0.18,
    replayTablet: 0.22,
  }),
  run("exp_syn_e02_video_source_only", 3, "smoke_ok", "smoke", "video_baseline", "none", "no_gate", {
    apcer: 0.24,
    bpcer: 0.2,
    acer: 0.22,
    hter: 0.215,
    auc: 0.78,
    print: 0.17,
    replayPhone: 0.25,
    replayTablet: 0.29,
  }),
  run("exp_syn_e03_video_full_ft_bf_only", 1, "security_regression", "full", "video_baseline", "full_finetune", "security_regression", {
    apcer: 0.31,
    bpcer: 0.12,
    acer: 0.215,
    hter: 0.23,
    auc: 0.81,
    print: 0.19,
    replayPhone: 0.34,
    replayTablet: 0.39,
  }),
  run("exp_syn_e03_video_full_ft_bf_only", 2, "security_regression", "full", "video_baseline", "full_finetune", "security_regression", {
    apcer: 0.34,
    bpcer: 0.11,
    acer: 0.225,
    hter: 0.235,
    auc: 0.8,
    print: 0.21,
    replayPhone: 0.38,
    replayTablet: 0.43,
  }),
  run("exp_syn_e03_video_full_ft_bf_only", 3, "smoke_ok", "smoke", "video_baseline", "full_finetune", "security_regression", {
    apcer: 0.38,
    bpcer: 0.1,
    acer: 0.24,
    hter: 0.26,
    auc: 0.77,
    print: 0.25,
    replayPhone: 0.42,
    replayTablet: 0.48,
  }),
  run("exp_demo_video_head_only", 1, "success", "full", "video_baseline", "head_only", "pass", {
    apcer: 0.22,
    bpcer: 0.15,
    acer: 0.185,
    hter: 0.19,
    auc: 0.85,
    print: 0.17,
    replayPhone: 0.21,
    replayTablet: 0.24,
  }),
  run("exp_demo_video_head_only", 2, "success", "full", "video_baseline", "head_only", "pass", {
    apcer: 0.2,
    bpcer: 0.16,
    acer: 0.18,
    hter: 0.18,
    auc: 0.86,
    print: 0.16,
    replayPhone: 0.2,
    replayTablet: 0.22,
  }),
  run("exp_demo_video_prototype", 1, "inconclusive", "full", "video_baseline", "prototype", "inconclusive", {
    apcer: 0.2,
    bpcer: 0.17,
    acer: 0.185,
    hter: 0.19,
    auc: 0.84,
    print: 0.15,
    replayPhone: 0.19,
    replayTablet: 0.25,
  }),
  run("exp_demo_video_prototype", 2, "success", "full", "video_baseline", "prototype", "pass", {
    apcer: 0.18,
    bpcer: 0.18,
    acer: 0.18,
    hter: 0.18,
    auc: 0.86,
    print: 0.14,
    replayPhone: 0.17,
    replayTablet: 0.21,
  }),
  run("exp_demo_spoof_preserve", 1, "success", "full", "video_baseline", "spoof_preserve", "pass", {
    apcer: 0.18,
    bpcer: 0.16,
    acer: 0.17,
    hter: 0.17,
    auc: 0.87,
    print: 0.14,
    replayPhone: 0.18,
    replayTablet: 0.2,
  }),
  run("exp_demo_spoof_preserve", 2, "success", "full", "video_baseline", "spoof_preserve", "pass", {
    apcer: 0.17,
    bpcer: 0.15,
    acer: 0.16,
    hter: 0.165,
    auc: 0.88,
    print: 0.13,
    replayPhone: 0.16,
    replayTablet: 0.19,
  }),
  run("exp_demo_spoof_preserve", 3, "smoke_ok", "smoke", "video_baseline", "spoof_preserve", "inconclusive", {
    apcer: 0.23,
    bpcer: 0.14,
    acer: 0.185,
    hter: 0.2,
    auc: 0.8,
    print: 0.2,
    replayPhone: 0.22,
    replayTablet: 0.27,
    protocol: "alt",
  }),
];

export const defaultBaselineId = "exp_syn_e02_video_source_only";
export const defaultMethodId = "exp_demo_spoof_preserve";
