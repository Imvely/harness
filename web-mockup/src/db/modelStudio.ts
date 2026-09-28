/**
 * A model as a composition, and what has to exist before one can run.
 *
 * Picking from a list is the easy half. The real work is a backbone with something else on top:
 * a frame encoder pooled over time, a clip encoder with a pixel-wise head, somebody's own
 * architecture dropped in. So a choice here is three parts — backbone, what happens to time,
 * what the head predicts — and any of them can come from the catalogue, from a search, or from
 * a class in this repository.
 *
 * Two things keep that honest:
 *
 * **A combination can be wrong, and the wrongness is stated.** A clip backbone already reads
 * time, so pooling on top of it discards what it computed. A pixel-wise head needs a spatial map,
 * which a pooled clip vector no longer has. These are checked, not left to be discovered in a
 * loss curve.
 *
 * **Nothing claims to run that cannot.** A composition is runnable only when its backbone has an
 * adapter here. Everything else produces the config draft *and* the one command that would
 * scaffold the adapter, so trying a new model is a copy-paste rather than a project.
 */

import type { ModelEntry } from "../data/modelCatalog";
import { MODEL_CATALOG, modelById } from "../data/modelCatalog";
import type { ControlState, CustomModel, HeadKind, Locale, ModelSpec, TemporalOp } from "../types";

export type { CustomModel, HeadKind, ModelSpec, TemporalOp };

export const TEMPORAL_OPS: TemporalOp[] = ["none", "mean", "max", "diff", "lstm", "attention"];
export const HEAD_KINDS: HeadKind[] = ["linear", "mlp", "pixelwise", "prototype"];

export const TEMPORAL_LABELS: Record<TemporalOp, { ko: string; en: string }> = {
  none: { ko: "그대로 (백본이 처리)", en: "As-is (the backbone handles it)" },
  mean: { ko: "프레임 평균", en: "Average over frames" },
  max: { ko: "프레임 최대", en: "Max over frames" },
  diff: { ko: "프레임 차이", en: "Frame differences" },
  lstm: { ko: "LSTM으로 순서 읽기", en: "Read the order with an LSTM" },
  attention: { ko: "주의로 프레임 가중", en: "Weigh frames with attention" },
};

export const TEMPORAL_WHY: Record<TemporalOp, { ko: string; en: string }> = {
  none: {
    ko: "백본이 이미 시간축을 봅니다. 클립 모델에는 이것이 기본입니다.",
    en: "The backbone already reads time. For a clip model this is the default.",
  },
  mean: {
    ko: "가장 단순하고 안정적입니다. 순서를 버리므로, 순서가 신호인지 확인하는 기준선이 됩니다.",
    en: "The simplest and most stable. It discards order, so it is the line that tells you whether order was the signal.",
  },
  max: {
    ko: "한 프레임에서만 드러나는 단서(반사, 모아레)를 살립니다. 잡음에 민감합니다.",
    en: "Keeps a cue that shows in one frame only (a reflection, a moire). Sensitive to noise.",
  },
  diff: {
    ko: "인접 프레임의 차이를 봅니다. 화면 재생의 깜빡임이나 종이의 정지성을 노립니다.",
    en: "Looks at what changed between frames: a screen's flicker, or paper holding perfectly still.",
  },
  lstm: {
    ko: "프레임 순서를 학습합니다. 표본이 작으면 과적합하기 쉽습니다.",
    en: "Learns the order of frames. With a small sample it overfits easily.",
  },
  attention: {
    ko: "어떤 프레임이 중요한지 학습합니다. 어디를 봤는지 확인할 수 있습니다.",
    en: "Learns which frames matter, and lets you see which it used.",
  },
};

export const HEAD_LABELS: Record<HeadKind, { ko: string; en: string }> = {
  linear: { ko: "선형 한 층", en: "One linear layer" },
  mlp: { ko: "작은 MLP", en: "A small MLP" },
  pixelwise: { ko: "화소별 진짜/가짜", en: "Real or fake per pixel" },
  prototype: { ko: "프로토타입 거리", en: "Distance to a prototype" },
};

export const HEAD_WHY: Record<HeadKind, { ko: string; en: string }> = {
  linear: {
    ko: "기본값입니다. 성능 차이가 백본에서 왔다고 말할 수 있게 머리를 최소로 둡니다.",
    en: "The default. Keeping the head minimal is what lets a difference be attributed to the backbone.",
  },
  mlp: {
    ko: "비선형을 조금 더 줍니다. 파라미터가 늘어 적응 단계에서 과적합 위험이 커집니다.",
    en: "A little more non-linearity, and more parameters to overfit with during adaptation.",
  },
  pixelwise: {
    ko: "어느 영역이 가짜인지까지 학습합니다. 근거를 보여 줄 수 있고, 공간 정보가 남아 있어야 합니다.",
    en: "Learns which region is fake, so it can show evidence — but it needs the spatial map intact.",
  },
  prototype: {
    ko: "진짜 얼굴 분포의 중심에서 얼마나 먼지를 봅니다. 목표 환경에 진짜만 있을 때 쓰는 방식입니다.",
    en: "Measures distance from the centre of the bona fide distribution — the method for a target with real faces only.",
  },
};

export const SOURCE_LABELS: Record<CustomModel["source"], string> = {
  timm: "timm",
  huggingface: "huggingface",
  torchvision: "torchvision",
  pytorchvideo: "pytorchvideo",
  local: "this repository",
};

export const DEFAULT_SPEC: ModelSpec = {
  backboneId: "video_baseline",
  temporal: "none",
  head: "linear",
  frames: 8,
};

/** A custom model as a catalogue entry, so one list can hold both. */
export function asEntry(custom: CustomModel): ModelEntry {
  return {
    id: custom.id,
    label: custom.label,
    group: "custom",
    status: "user_added",
    frames: custom.frames,
    paramsM: custom.paramsM,
    library: SOURCE_LABELS[custom.source],
    pretrain: "—",
    // The searchable name, not the note: a note like "from the Hugging Face hub" as a search
    // query is how every link ended up returning nothing.
    paper: custom.label,
    why: {
      ko: `직접 추가한 모델입니다 (${SOURCE_LABELS[custom.source]}: ${custom.ref}).`,
      en: `Added here (${SOURCE_LABELS[custom.source]}: ${custom.ref}).`,
    },
  };
}

export function allModels(custom: CustomModel[] = []): ModelEntry[] {
  return [...MODEL_CATALOG, ...custom.map(asEntry)];
}

export function entryFor(id: string, custom: CustomModel[] = []): ModelEntry | undefined {
  return modelById(id) ?? custom.filter((model) => model.id === id).map(asEntry)[0];
}

/** A stable id for a composition, usable as a config name and as a run tag. */
export function specId(spec: ModelSpec): string {
  const parts = [spec.backboneId];
  if (spec.temporal !== "none") parts.push(spec.temporal);
  if (spec.head !== "linear") parts.push(spec.head);
  if (spec.frames > 1) parts.push(`t${spec.frames}`);
  return parts.join("_");
}

export interface SpecIssue {
  level: "blocking" | "warning";
  code:
    | "unknown_backbone"
    | "frame_backbone_needs_time"
    | "clip_backbone_time_twice"
    | "pixelwise_after_pooling"
    | "prototype_needs_real_only"
    | "no_adapter";
  /** The part of the composition at fault. */
  part: "backbone" | "temporal" | "head";
}

/**
 * What is wrong with a composition, before anything is trained.
 *
 * Each of these is a silent failure otherwise: a frame encoder fed eight frames with no temporal
 * operator trains on frame one and ignores the rest; a pixel-wise head after a pooled vector
 * learns from a map that no longer exists.
 */
export function specIssues(spec: ModelSpec, custom: CustomModel[] = []): SpecIssue[] {
  const backbone = entryFor(spec.backboneId, custom);
  if (!backbone) {
    return [{ level: "blocking", code: "unknown_backbone", part: "backbone" }];
  }
  const issues: SpecIssue[] = [];
  const readsTimeItself = backbone.frames > 1;
  if (!readsTimeItself && spec.frames > 1 && spec.temporal === "none") {
    issues.push({ level: "blocking", code: "frame_backbone_needs_time", part: "temporal" });
  }
  if (readsTimeItself && spec.temporal !== "none" && spec.temporal !== "attention") {
    issues.push({ level: "warning", code: "clip_backbone_time_twice", part: "temporal" });
  }
  if (spec.head === "pixelwise" && (readsTimeItself || spec.temporal !== "none")) {
    issues.push({ level: "warning", code: "pixelwise_after_pooling", part: "head" });
  }
  if (spec.head === "prototype") {
    issues.push({ level: "warning", code: "prototype_needs_real_only", part: "head" });
  }
  if (backbone.status !== "implemented") {
    issues.push({ level: "blocking", code: "no_adapter", part: "backbone" });
  }
  return issues;
}

export function specIsRunnable(spec: ModelSpec, custom: CustomModel[] = []): boolean {
  return specIssues(spec, custom).every((issue) => issue.level !== "blocking");
}

export function specIssueText(locale: Locale, issue: SpecIssue): string {
  switch (issue.code) {
    case "unknown_backbone":
      return locale === "ko"
        ? "백본을 찾을 수 없습니다. 목록에서 고르거나 새로 추가하세요."
        : "That backbone is not in the list. Pick one or add it.";
    case "frame_backbone_needs_time":
      return locale === "ko"
        ? "한 장씩 보는 백본에 여러 프레임을 넣었습니다. 시간 처리를 고르지 않으면 첫 프레임만 쓰이고 나머지는 버려집니다."
        : "A frame backbone is being fed several frames. Without a temporal step it trains on the first frame and throws the rest away.";
    case "clip_backbone_time_twice":
      return locale === "ko"
        ? "이 백본은 이미 시간축을 봅니다. 위에 평균이나 최대를 얹으면 백본이 계산한 시간 정보를 눌러 버립니다."
        : "This backbone already reads time; pooling on top of it flattens what it computed.";
    case "pixelwise_after_pooling":
      return locale === "ko"
        ? "화소별 머리는 공간 지도가 남아 있어야 합니다. 시간·공간을 합친 뒤에는 위치 정보가 없습니다."
        : "A pixel-wise head needs the spatial map; after pooling there is no position left to supervise.";
    case "prototype_needs_real_only":
      return locale === "ko"
        ? "프로토타입 머리는 진짜만으로 학습하는 설정을 전제합니다. 공격도 함께 쓸 거라면 선형이나 MLP가 맞습니다."
        : "A prototype head assumes training on bona fide only. If attacks are used too, linear or MLP is the fit.";
    case "no_adapter":
      return locale === "ko"
        ? "이 백본은 이 저장소에 adapter가 없습니다. 아래 명령으로 만들면 바로 쓸 수 있습니다."
        : "This backbone has no adapter here. The command below creates one, and then it runs.";
  }
}

/**
 * The one command that makes a chosen model runnable.
 *
 * "Search for a model and try it" fails at exactly one point: the repository has to learn to
 * build it. Printing that step as a command turns a blocked choice into a next action.
 */
export function scaffoldCommand(spec: ModelSpec, custom: CustomModel[] = []): string {
  const backbone = entryFor(spec.backboneId, custom);
  const own = custom.find((model) => model.id === spec.backboneId);
  const source = own ? own.source : guessSource(backbone?.library ?? "");
  const ref = own ? own.ref : spec.backboneId;
  return [
    "uv run --no-sync python scripts/new_model.py",
    `--id ${specId(spec)}`,
    `--backbone ${source}:${ref}`,
    `--temporal ${spec.temporal}`,
    `--head ${spec.head}`,
    `--frames ${spec.frames}`,
    // The hub holds image and video models under one source, so the side that knows says which.
    `--reads-clip ${(backbone?.frames ?? 1) > 1 ? "yes" : "no"}`,
  ].join(" ");
}

function guessSource(library: string): CustomModel["source"] {
  const lower = library.toLowerCase();
  if (lower.includes("timm")) return "timm";
  if (lower.includes("huggingface")) return "huggingface";
  if (lower.includes("pytorchvideo")) return "pytorchvideo";
  if (lower.includes("torchvision")) return "torchvision";
  return "local";
}

/** The model block a composition writes into a config file. */
export function specYaml(spec: ModelSpec, custom: CustomModel[] = []): string {
  const own = custom.find((model) => model.id === spec.backboneId);
  const lines = [
    "model:",
    `  name: ${specId(spec)}`,
    "  backbone:",
    `    source: ${own ? own.source : guessSource(entryFor(spec.backboneId, custom)?.library ?? "")}`,
    `    ref: ${own ? own.ref : spec.backboneId}`,
    `  temporal: ${spec.temporal}`,
    `  head: ${spec.head}`,
    "  input:",
    `    frames: ${spec.frames}`,
  ];
  return lines.join("\n");
}

/** Turn a searched-for model into a registry entry. Ids stay config-safe. */
export function customFromRef(
  source: CustomModel["source"],
  ref: string,
  options: { label?: string; frames?: number; paramsM?: number | null; note?: string; now?: string } = {},
): CustomModel {
  const trimmed = ref.trim();
  if (trimmed.length === 0) throw new Error("a model needs a reference");
  const id = `own_${trimmed
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")}`.slice(0, 60);
  return {
    id,
    label: options.label?.trim() || trimmed.split("/").slice(-1)[0].split(".").slice(-1)[0],
    source,
    ref: trimmed,
    frames: options.frames ?? 1,
    paramsM: options.paramsM ?? null,
    note: options.note ?? "",
    addedAt: options.now ?? new Date().toISOString(),
  };
}

/** The composition a control state stands for: the control keeps the parts flat, this joins them. */
export function specOf(control: ControlState): ModelSpec {
  return {
    backboneId: control.modelId,
    temporal: control.temporal,
    head: control.head,
    frames: control.frames,
  };
}

export function describeSpec(spec: ModelSpec, locale: Locale, custom: CustomModel[] = []): string {
  const backbone = entryFor(spec.backboneId, custom);
  const name = backbone?.label ?? spec.backboneId;
  const time = TEMPORAL_LABELS[spec.temporal][locale];
  const head = HEAD_LABELS[spec.head][locale];
  return locale === "ko"
    ? `${name} → ${time} → ${head} (프레임 ${spec.frames})`
    : `${name} → ${time} → ${head} (${spec.frames} frames)`;
}
