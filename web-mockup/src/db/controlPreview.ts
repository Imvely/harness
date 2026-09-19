import type { ControlState } from "../types";
import { ControlStateSchema } from "./schema";

const blockedCommand = "BLOCKED: fix validation errors before copying this command.";

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
  const parsed = ControlStateSchema.safeParse(control);
  if (!parsed.success) return blockedCommand;
  const safe = parsed.data;
  const expName = cliToken(experimentName(safe));
  if (safe.adaptationMethod === "none") {
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
  const expName = experimentName(safe);
  const executionBlock = safe.smokeMode
    ? "  mode: smoke\n  allow_full_gpu_run: false\n  require_gpu: false\n  expected_gpu: null"
    : "  mode: full\n  allow_full_gpu_run: true\n  require_gpu: true\n  expected_gpu: H100";
  const adaptationBlock =
    safe.adaptationMethod === "none"
      ? "adaptation:\n  enabled: false\n  method: none"
      : `adaptation:\n  method: ${safe.adaptationMethod}\n  epochs: ${safe.epochs}\n  learning_rate: ${safe.learningRate}\n  batch_size: ${safe.batchSize}`;
  return `# Draft only. Edit configs/exp/${expName}.yaml after review.
# Do not paste execution.* overrides into a launch CLI.
defaults:
  - override /model: ${safe.modelFamily}
  - override /protocol: ${safe.protocolId}
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
