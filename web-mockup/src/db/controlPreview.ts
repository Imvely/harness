import type { ControlState } from "../types";
import { ControlStateSchema } from "./schema";
import { isRunnableModel, modelById } from "../data/modelCatalog";
import { findingText, review, selectionYaml } from "./datasetSelection";

const blockedCommand = "BLOCKED: fix validation errors before copying this command.";
const blockedByData =
  "BLOCKED: the data selection has a problem that would make the result meaningless.";
const blockedByModel =
  "BLOCKED: this architecture is a research candidate; no adapter runs it in this repository yet.";

/** Why a run cannot be launched as configured, or null when it can. */
export function launchBlocker(control: ControlState): string | null {
  if (!ControlStateSchema.safeParse(control).success) return blockedCommand;
  if (review(control.datasets).some((finding) => finding.level === "blocking")) return blockedByData;
  if (!isRunnableModel(control.modelId)) return blockedByModel;
  return null;
}

export function experimentName(control: ControlState): string {
  return control.experimentId.replace(/^exp_/, "");
}

export function buildValidationCommand(control: ControlState): string {
  const parsed = ControlStateSchema.safeParse(control);
  if (!parsed.success) return blockedCommand;
  return `uv run --no-sync python scripts/validate_spec.py --exp ${cliToken(
    experimentName(parsed.data),
  )} --for-launch --json`;
}

export function buildLaunchCommand(control: ControlState): string {
  const blocker = launchBlocker(control);
  if (blocker) return blocker;
  const safe = ControlStateSchema.parse(control);
  const expName = cliToken(experimentName(safe));
  if (safe.goal === "baseline" || safe.adaptationMethod === "none") {
    return `uv run --no-sync python scripts/train.py +exp=${expName} execution.mode=smoke`;
  }
  return `uv run --no-sync python scripts/adapt.py +exp=${expName} adaptation.source_run_id=${cliToken(safe.sourceRunId)}${
    safe.smokeMode ? " execution.mode=smoke" : " # full requires config-file gate"
  }`;
}

export function buildYamlPatch(control: ControlState): string {
  const parsed = ControlStateSchema.safeParse(control);
  if (!parsed.success) return "# BLOCKED: fix validation errors before drafting YAML.";
  const safe = parsed.data;
  const model = modelById(safe.modelId);
  // A candidate architecture has no adapter here, so the line that would select it is written
  // as a comment: the draft records the intent without pretending the run exists.
  const modelLine = model && model.status === "implemented"
    ? `  - override /model: ${safe.modelId}`
    : `  # - override /model: ${safe.modelId}   # ${model?.label ?? safe.modelId}: no adapter yet`;
  const expName = experimentName(safe);
  const executionBlock = safe.smokeMode
    ? "  mode: smoke\n  allow_full_gpu_run: false\n  require_gpu: false\n  expected_gpu: null"
    : "  mode: full\n  allow_full_gpu_run: true\n  require_gpu: true\n  expected_gpu: H100";
  const adaptationBlock =
    safe.adaptationMethod === "none"
      ? "adaptation:\n  enabled: false\n  method: none"
      : `adaptation:\n  method: ${safe.adaptationMethod}\n  epochs: ${safe.epochs}\n  learning_rate: ${safe.learningRate}\n  batch_size: ${safe.batchSize}`;
  // The tree's selection travels as comments: this screen drafts, and a reviewed protocol file
  // is what a run actually reads.
  const selectionComment = selectionYaml(safe.datasets)
    .split("\n")
    .map((line) => `# ${line}`)
    .join("\n");
  return `# Draft only. Edit configs/exp/${expName}.yaml after review.
# Do not paste execution.* overrides into a launch CLI.
# goal: ${safe.goal}
defaults:
${modelLine}
  - override /protocol: ${safe.protocolId}
# The protocol file is what a run reads. These are the splits this screen selected;
# they belong in configs/protocol/${safe.protocolId}.yaml, reviewed, before a run uses them.
${selectionComment}
training:
  epochs: ${safe.epochs}
  batch_size: ${safe.batchSize}
  learning_rate: ${safe.learningRate}
model:
  input:
    frames: ${safe.frames}
${adaptationBlock}
execution:
${executionBlock}
# threshold.rule=${safe.thresholdRule} belongs to a protocol design review.`;
}

export function controlWarnings(control: ControlState): string[] {
  const warnings: string[] = [];
  // The data findings come first: they are the ones that decide whether a number means anything.
  for (const finding of review(control.datasets)) {
    warnings.push(findingText("en", finding));
  }
  const model = modelById(control.modelId);
  if (model === undefined) {
    warnings.push(`Unknown model id ${control.modelId}; pick one from the catalogue.`);
  } else if (model.status !== "implemented") {
    warnings.push(
      `${model.label} is a research candidate. This screen can draft a config for it, but no adapter runs it yet.`,
    );
  }
  if (!control.smokeMode) {
    warnings.push("Full mode is a config preview only. It does not approve a full run.");
  }
  if (control.thresholdRule !== "eer") {
    warnings.push("Threshold rule changes require protocol design review.");
  }
  if (control.smokeMode && control.epochs !== 1) {
    warnings.push("Smoke mode must keep max_epochs at 1.");
  }
  if (control.adaptationMethod !== "none" && control.sourceRunId.trim().length === 0) {
    warnings.push("Adaptation requires a source run ID.");
  }
  return warnings;
}

function cliToken(value: string): string {
  if (!/^[A-Za-z0-9_.:-]+$/.test(value)) {
    throw new Error("unsafe CLI token reached command builder after schema validation");
  }
  return value;
}
