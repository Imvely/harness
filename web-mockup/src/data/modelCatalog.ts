/**
 * The models a run can use, and which of them this repository can actually run today.
 *
 * Two entries used to be the whole list — `frame_baseline` and `video_baseline` — which is fine
 * as a contract between the trainer and a config, and useless as a research choice: the
 * question is which video architecture reads a spoof cue, and that list is long. So the
 * catalogue holds the candidates, grouped by what they do to time, and each one says plainly
 * whether an adapter exists (`status`).
 *
 * `status` is the honest part. `implemented` means this repository has an adapter and a smoke
 * test. `candidate` means the architecture is on the research list and nothing here runs it
 * yet; selecting one produces a config draft and a note saying so, never a launch command.
 * Parameter counts are the reference implementation's, for ordering the list by cost — they are
 * not measured here, and the UI says so.
 */

export type ModelGroup = "frame" | "clip_3d" | "clip_transformer" | "pad_specific";
export type ModelStatus = "implemented" | "candidate";

export interface ModelEntry {
  id: string;
  label: string;
  group: ModelGroup;
  status: ModelStatus;
  /** Frames the reference setup reads at once. 1 means it never sees motion. */
  frames: number;
  /** Reference-implementation parameter count in millions, or null when not established. */
  paramsM: number | null;
  /** Where a working implementation comes from. */
  library: string;
  /** Pretraining the reference weights carry. Kinetics for video, ImageNet for frames. */
  pretrain: string;
  /** The paper title, used verbatim to search for it rather than hardcoding an id. */
  paper: string;
  /** One line on why it is on the list, ko/en. Not marketing: what it does to the input. */
  why: { ko: string; en: string };
}

export const MODEL_CATALOG: ModelEntry[] = [
  // -- what the repository can run today --------------------------------------------
  {
    id: "frame_baseline",
    label: "Frame baseline (ResNet-18)",
    group: "frame",
    status: "implemented",
    frames: 1,
    paramsM: 11.7,
    library: "torchvision",
    pretrain: "ImageNet-1k",
    paper: "Deep Residual Learning for Image Recognition",
    why: {
      ko: "한 장만 봅니다. 움직임을 쓰지 않으므로, 비디오 모델이 정말 움직임으로 이기는지 판단하는 기준선입니다.",
      en: "Sees one frame. It uses no motion, so it is the line a video model has to beat with motion.",
    },
  },
  {
    id: "video_baseline",
    label: "Video baseline (R(2+1)D-18)",
    group: "clip_3d",
    status: "implemented",
    frames: 8,
    paramsM: 33.4,
    library: "torchvision",
    pretrain: "Kinetics-400",
    paper: "A Closer Look at Spatiotemporal Convolutions for Action Recognition",
    why: {
      ko: "공간 합성곱과 시간 합성곱을 분리해 3D보다 학습이 안정적입니다. 비디오 쪽 첫 기준선입니다.",
      en: "Splits spatial and temporal convolution, which trains more stably than full 3D. The first video baseline.",
    },
  },

  // -- 3D / motion-first candidates --------------------------------------------------
  {
    id: "x3d_m",
    label: "X3D-M",
    group: "clip_3d",
    status: "candidate",
    frames: 16,
    paramsM: 3.8,
    library: "pytorchvideo",
    pretrain: "Kinetics-400",
    paper: "X3D: Expanding Architectures for Efficient Video Recognition",
    why: {
      ko: "같은 정확도를 10배 적은 파라미터로 냅니다. 표본이 작은 PAD에서 과적합을 줄이는 쪽으로 먼저 볼 후보입니다.",
      en: "Reaches comparable accuracy with about ten times fewer parameters — the first thing to try when a PAD set is small.",
    },
  },
  {
    id: "slowfast_r50",
    label: "SlowFast R50",
    group: "clip_3d",
    status: "candidate",
    frames: 32,
    paramsM: 34.6,
    library: "pytorchvideo",
    pretrain: "Kinetics-400",
    paper: "SlowFast Networks for Video Recognition",
    why: {
      ko: "느린 경로가 모양을, 빠른 경로가 움직임을 봅니다. 화면 재생 공격의 깜빡임처럼 빠른 신호에 유리할 수 있습니다.",
      en: "A slow path for appearance and a fast one for motion, which may suit fast cues like a screen's flicker.",
    },
  },
  {
    id: "i3d_r50",
    label: "I3D R50",
    group: "clip_3d",
    status: "candidate",
    frames: 32,
    paramsM: 28.0,
    library: "pytorchvideo",
    pretrain: "Kinetics-400",
    paper: "Quo Vadis, Action Recognition? A New Model and the Kinetics Dataset",
    why: {
      ko: "비디오 전이학습의 기준점입니다. 새 결과를 기존 문헌과 맞춰 볼 때 비교 대상이 됩니다.",
      en: "The reference point for video transfer learning, and so the thing a new result is compared against.",
    },
  },
  {
    id: "tsm_r50",
    label: "TSM ResNet-50",
    group: "clip_3d",
    status: "candidate",
    frames: 8,
    paramsM: 24.3,
    library: "official repo",
    pretrain: "ImageNet-1k",
    paper: "TSM: Temporal Shift Module for Efficient Video Understanding",
    why: {
      ko: "2D 연산량으로 시간 정보를 씁니다. 추론 지연이 제약일 때(실시간 PAD) 유력합니다.",
      en: "Uses temporal information at 2D cost, which matters when inference latency is the constraint.",
    },
  },

  // -- transformer candidates --------------------------------------------------------
  {
    id: "videomae_b",
    label: "VideoMAE ViT-B",
    group: "clip_transformer",
    status: "candidate",
    frames: 16,
    paramsM: 87.0,
    library: "huggingface transformers",
    pretrain: "Kinetics-400 (self-supervised)",
    paper: "VideoMAE: Masked Autoencoders are Data-Efficient Learners for Self-Supervised Video Pre-Training",
    why: {
      ko: "라벨 없이 사전학습해 작은 데이터셋에서 상대적으로 강합니다. 도메인 적응과 결이 맞습니다.",
      en: "Pretrained without labels, so it holds up better on small sets — which is the situation adaptation is for.",
    },
  },
  {
    id: "mvitv2_s",
    label: "MViTv2-S",
    group: "clip_transformer",
    status: "candidate",
    frames: 16,
    paramsM: 34.5,
    library: "torchvision",
    pretrain: "Kinetics-400",
    paper: "MViTv2: Improved Multiscale Vision Transformers for Classification and Detection",
    why: {
      ko: "여러 해상도를 함께 봅니다. 인쇄물의 미세한 질감과 전체 움직임을 같이 써야 할 때 후보입니다.",
      en: "Looks at several scales at once, for when a fine print texture and a whole-clip motion both matter.",
    },
  },
  {
    id: "video_swin_t",
    label: "Video Swin-T",
    group: "clip_transformer",
    status: "candidate",
    frames: 32,
    paramsM: 28.2,
    library: "official repo",
    pretrain: "Kinetics-400",
    paper: "Video Swin Transformer",
    why: {
      ko: "국소 윈도 주의로 계산을 줄인 transformer입니다. 파라미터 대비 성능이 좋습니다.",
      en: "A transformer with local window attention, which keeps compute down for its accuracy.",
    },
  },
  {
    id: "timesformer_b",
    label: "TimeSformer-B",
    group: "clip_transformer",
    status: "candidate",
    frames: 8,
    paramsM: 121.0,
    library: "huggingface transformers",
    pretrain: "Kinetics-400",
    paper: "Is Space-Time Attention All You Need for Video Understanding?",
    why: {
      ko: "시간과 공간 주의를 분리합니다. 크고 느려서, 작은 PAD 데이터에서는 과적합을 먼저 확인해야 합니다.",
      en: "Separates time and space attention. It is large and slow, so overfitting is the first thing to check.",
    },
  },

  // -- PAD-specific candidates -------------------------------------------------------
  {
    id: "cdcn",
    label: "CDCN (central difference conv.)",
    group: "pad_specific",
    status: "candidate",
    frames: 1,
    paramsM: 2.3,
    library: "official repo",
    pretrain: "none",
    paper: "Searching Central Difference Convolutional Networks for Face Anti-Spoofing",
    why: {
      ko: "합성곱 자체를 국소 차분으로 바꿔 질감 경계를 강조합니다. PAD 전용 설계의 대표입니다.",
      en: "Replaces the convolution itself with a local difference, emphasising texture edges. The representative PAD-specific design.",
    },
  },
  {
    id: "deep_pixbis",
    label: "DeepPixBiS",
    group: "pad_specific",
    status: "candidate",
    frames: 1,
    paramsM: null,
    library: "bob.paper / official repo",
    pretrain: "ImageNet-1k",
    paper: "Deep Pixel-wise Binary Supervision for Face Presentation Attack Detection",
    why: {
      ko: "화소 단위 감독으로 어디가 가짜인지 위치까지 학습합니다. 근거를 보여 줄 수 있는 쪽입니다.",
      en: "Supervises per pixel, so it learns where the spoof is — a model that can show its evidence.",
    },
  },
  {
    id: "vit_b16",
    label: "ViT-B/16 (frame)",
    group: "frame",
    status: "candidate",
    frames: 1,
    paramsM: 86.0,
    library: "timm",
    pretrain: "ImageNet-21k",
    paper: "An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale",
    why: {
      ko: "프레임 쪽 강한 기준선입니다. 비디오 모델의 이득이 정말 시간에서 오는지 가릅니다.",
      en: "A strong frame-side baseline, which is how you tell whether a video model's gain really comes from time.",
    },
  },
  {
    id: "efficientnet_b0",
    label: "EfficientNet-B0 (frame)",
    group: "frame",
    status: "candidate",
    frames: 1,
    paramsM: 5.3,
    library: "timm",
    pretrain: "ImageNet-1k",
    paper: "EfficientNet: Rethinking Model Scaling for Convolutional Neural Networks",
    why: {
      ko: "가볍습니다. 모바일에서 돌려야 하는 제약이 생기면 기준이 됩니다.",
      en: "Small enough to be the reference if the constraint becomes running on a phone.",
    },
  },
];

export const MODEL_GROUP_LABELS: Record<ModelGroup, { ko: string; en: string }> = {
  frame: { ko: "한 장씩 보는 모델", en: "Reads one frame" },
  clip_3d: { ko: "움직임을 합성곱으로 보는 모델", en: "Reads motion with convolutions" },
  clip_transformer: { ko: "움직임을 주의(attention)로 보는 모델", en: "Reads motion with attention" },
  pad_specific: { ko: "PAD 전용 설계", en: "Designed for PAD" },
};

export const MODEL_GROUP_ORDER: ModelGroup[] = [
  "frame",
  "clip_3d",
  "clip_transformer",
  "pad_specific",
];

export function modelById(id: string): ModelEntry | undefined {
  return MODEL_CATALOG.find((model) => model.id === id);
}

export function implementedModels(): ModelEntry[] {
  return MODEL_CATALOG.filter((model) => model.status === "implemented");
}

/** Models in a group, cheapest first, so a list reads as a cost ladder. */
export function modelsInGroup(group: ModelGroup): ModelEntry[] {
  return MODEL_CATALOG.filter((model) => model.group === group).sort(
    (a, b) => (a.paramsM ?? Number.MAX_SAFE_INTEGER) - (b.paramsM ?? Number.MAX_SAFE_INTEGER),
  );
}

/** True when a run can be launched with this model rather than only drafted. */
export function isRunnableModel(id: string): boolean {
  return modelById(id)?.status === "implemented";
}
