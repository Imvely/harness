/**
 * The datasets a run can be built from, as a tree.
 *
 * A protocol id like `syn_a_to_b_v1` says nothing about what is in it, so choosing one is a
 * guess unless you already know the answer. The tree is the same choice made visible: a domain
 * opens into the splits the dataset itself ships, and each split opens into the conditions a
 * recording carries — lighting, how the attack was presented, which instrument. Anything in it
 * can be assigned to training, validation or test.
 *
 * Numbers: a domain's clip and frame totals and its split sizes are **measured** (the store
 * scan of 2026-09-22, recorded in ADR-013). Everything below a split is **divided out of** that
 * measurement in proportion, because the store's index does not break the counts down that far.
 * `measured` says which is which per node, and the UI marks a divided number with `≈` rather
 * than presenting it as a fact.
 *
 * aihub114 is in the tree and cannot be selected. Its attacks were all filmed on a GoPro and
 * its bona fide clips all on phones, so a camera predicts the label and a perfect score means
 * nothing (ADR-013). Leaving it visible with the reason attached is the point: the next person
 * to ask "why not that one?" gets an answer instead of an absence.
 */

export type LabelKind = "bona_fide" | "spoof";
export type NodeKind = "domain" | "split" | "condition" | "class";
export type TimingSource = "unknown" | "header" | "documented";

export interface CatalogNode {
  /** Path-shaped and stable: `aihub115/train/Light_01_High/attack_01_print_eye_flat`. */
  id: string;
  kind: NodeKind;
  /** The dataset's own name for this level. Never translated: it is what the data calls it. */
  label: string;
  clips: number;
  frames: number;
  /** True when the number comes from the store scan, false when divided out of a parent's. */
  measured: boolean;
  /** Which labels live under this node. A node with both can support a claim on its own. */
  labels: LabelKind[];
  /**
   * Which subjects these clips came from, as the coarsest pool the store lets us tell apart:
   * one per domain and split. Two nodes sharing a pool share people, so putting them in
   * different roles puts the same face on both sides of the evaluation.
   */
  subjectPool: string;
  domainId: string;
  children: CatalogNode[];
  /** Only on a domain: why it cannot be selected. */
  blocked?: "camera_predicts_label";
}

export interface DomainFacts {
  id: string;
  /** What the distribution is called, for the reader who has to find it again. */
  source: string;
  subjects: number;
  clips: number;
  frames: number;
  /** Whether anything records when a frame was taken. `unknown` bars a temporal comparison. */
  timing: TimingSource;
  /** True when the frames were JPEG-compressed a second time by the build. */
  reencoded: boolean;
  attackTypes: string;
  blocked?: "camera_predicts_label";
  /** A fact about this domain the reader needs before using it, as ko/en. */
  caveats: { ko: string; en: string }[];
}

interface SplitSpec {
  label: string;
  clips: number;
}

interface LeafSpec {
  label: string;
  label_: LabelKind;
  weight?: number;
}

interface DomainSpec extends DomainFacts {
  splits: SplitSpec[];
  /** Middle level: the recording condition this dataset varies. Empty means splits hold classes. */
  conditions: string[];
  classes: LeafSpec[];
}

/** Split `total` into shares proportional to `weights`, summing back to exactly `total`. */
export function divide(total: number, weights: number[]): number[] {
  const sum = weights.reduce((acc, weight) => acc + weight, 0);
  if (sum <= 0 || weights.length === 0) return weights.map(() => 0);
  const exact = weights.map((weight) => (total * weight) / sum);
  const floors = exact.map((value) => Math.floor(value));
  let left = total - floors.reduce((acc, value) => acc + value, 0);
  // Largest remainder: the shares closest to rounding up get the leftovers, so the parts add
  // up to the measured parent instead of drifting a few clips away from it.
  const order = exact
    .map((value, index) => ({ index, remainder: value - Math.floor(value) }))
    .sort((a, b) => b.remainder - a.remainder);
  const shares = [...floors];
  for (const { index } of order) {
    if (left <= 0) break;
    shares[index] += 1;
    left -= 1;
  }
  return shares;
}

const SPECS: DomainSpec[] = [
  {
    id: "aihub115",
    source: "AI Hub 161 · Liveness Detection을 위한 영상",
    subjects: 2661,
    clips: 10740,
    frames: 322200,
    timing: "unknown",
    reencoded: false,
    attackTypes: "print 6종 (원본) / 4종 (팀원 저장소)",
    caveats: [
      {
        ko: "프레임 시각이 기록되지 않아 시간 기반 비교(FFT·옵티컬 플로우)에는 쓰지 않습니다.",
        en: "No frame timing is recorded, so it is not used for time-based comparison (FFT, optical flow).",
      },
      {
        ko: "SR305 한 대가 진짜와 공격을 모두 찍었습니다. 카메라로 라벨을 맞힐 수 없습니다.",
        en: "One SR305 filmed both classes, so the camera cannot give the label away.",
      },
    ],
    splits: [
      { label: "train", clips: 9625 },
      { label: "dev", clips: 1115 },
    ],
    conditions: ["Light_01_High", "Light_02_Mid", "Light_03_Low"],
    classes: [
      { label: "real_01", label_: "bona_fide", weight: 3 },
      { label: "attack_01_print_eye_flat", label_: "spoof" },
      { label: "attack_02_print_eye_curved", label_: "spoof" },
      { label: "attack_03_print_eye_nose_flat", label_: "spoof" },
      { label: "attack_04_print_eye_nose_curved", label_: "spoof" },
      { label: "attack_05_print_eye_nose_mouth_flat", label_: "spoof" },
      { label: "attack_06_print_eye_nose_mouth_curved", label_: "spoof" },
    ],
  },
  {
    id: "siw_mv2",
    source: "SiW-Mv2",
    subjects: 1656,
    clips: 1656,
    frames: 264548,
    timing: "header",
    reencoded: true,
    attackTypes: "14종 (replay·print·마스크·메이크업·부분)",
    caveats: [
      {
        ko: "clip마다 subject가 달라 인물 분리가 곧 clip 분리입니다. 같은 사람이 양쪽에 들어가는 것을 막을 방법이 없습니다.",
        en: "Every clip has its own subject, so subject separation is clip separation; the same person cannot be kept to one side.",
      },
      {
        ko: "공식 split이 없어 dev를 파생해야 합니다(ADR-008).",
        en: "It ships no official split, so a dev set has to be derived (ADR-008).",
      },
    ],
    splits: [{ label: "all", clips: 1656 }],
    conditions: [],
    classes: [
      { label: "Live", label_: "bona_fide", weight: 4 },
      { label: "Replay", label_: "spoof", weight: 2 },
      { label: "Paper", label_: "spoof", weight: 2 },
      { label: "Mask_HalfMask", label_: "spoof" },
      { label: "Mask_TransparentMask", label_: "spoof" },
      { label: "Mask_PaperMask", label_: "spoof" },
      { label: "Silicone", label_: "spoof" },
      { label: "Mannequin", label_: "spoof" },
      { label: "Makeup_Impersonation", label_: "spoof" },
      { label: "Makeup_Obfuscation", label_: "spoof" },
      { label: "Makeup_Cosmetic", label_: "spoof" },
      { label: "Partial_Eye", label_: "spoof" },
      { label: "Partial_Mouth", label_: "spoof" },
      { label: "Partial_FunnyeyeGlasses", label_: "spoof" },
      { label: "Partial_PaperGlasses", label_: "spoof" },
    ],
  },
  {
    id: "idiap_replayattack",
    source: "Idiap Replay-Attack",
    subjects: 35,
    clips: 840,
    frames: 136161,
    timing: "header",
    reencoded: true,
    attackTypes: "print / mobile / highdef × hand·fixed",
    caveats: [
      {
        ko: "공격 clip 700개 중 350쌍이 같은 키를 공유해 프레임 79,091개가 덮어써졌습니다. adapter가 쌍에서 한 쪽만 채택합니다.",
        en: "350 of its 700 attack clips shared a key and 79,091 frames were overwritten; the adapter keeps one clip per pair.",
      },
      {
        ko: "공식 devel 세트가 저장소에 빌드되지 않았습니다. dev는 train에서 파생합니다.",
        en: "Its official devel set was never built into the store, so dev comes out of train.",
      },
    ],
    splits: [
      { label: "train", clips: 360 },
      { label: "test", clips: 480 },
    ],
    conditions: ["hand", "fixed"],
    classes: [
      { label: "real", label_: "bona_fide", weight: 2 },
      { label: "print", label_: "spoof", weight: 2 },
      { label: "mobile", label_: "spoof", weight: 2 },
      { label: "highdef", label_: "spoof", weight: 2 },
    ],
  },
  {
    id: "casia_surf",
    source: "CASIA-SURF",
    subjects: 1000,
    clips: 3991,
    frames: 96584,
    timing: "unknown",
    reencoded: false,
    attackTypes: "print 6종 (컷아웃 위치·평면/곡면)",
    caveats: [
      {
        ko: "배포본이 이미 얼굴 영역으로 잘려 있어 crop 정책을 적용할 수 없습니다.",
        en: "The distribution is already cropped to the face, so no crop policy applies.",
      },
      {
        ko: "clip 하나에 프레임이 1장뿐인 경우가 있습니다. 시간 모델에는 걸러야 합니다.",
        en: "Some clips hold a single frame, which a temporal model has to filter out.",
      },
    ],
    splits: [
      { label: "train", clips: 1200 },
      { label: "dev", clips: 400 },
      { label: "test", clips: 2391 },
    ],
    conditions: [],
    classes: [
      { label: "real", label_: "bona_fide", weight: 3 },
      { label: "01_e_s", label_: "spoof" },
      { label: "02_e_b", label_: "spoof" },
      { label: "03_en_s", label_: "spoof" },
      { label: "04_en_b", label_: "spoof" },
      { label: "05_enm_s", label_: "spoof" },
      { label: "06_enm_b", label_: "spoof" },
    ],
  },
  {
    id: "casia_cefa",
    source: "CASIA-CeFA (protocol 2.2)",
    subjects: 900,
    clips: 1800,
    frames: 165702,
    timing: "unknown",
    reencoded: false,
    attackTypes: "Screen (replay) 1종",
    caveats: [
      {
        ko: "공격이 replay 한 종류뿐입니다. 이 도메인만으로는 print 공격에 대한 주장을 할 수 없습니다.",
        en: "Its only attack is a replay, so it cannot support any claim about print attacks.",
      },
      {
        ko: "test split이 저장소에 없습니다.",
        en: "It has no test split in the store.",
      },
    ],
    splits: [
      { label: "train", clips: 1200 },
      { label: "dev", clips: 600 },
    ],
    conditions: [],
    classes: [
      { label: "Real", label_: "bona_fide" },
      { label: "Screen", label_: "spoof" },
    ],
  },
  {
    id: "aihub114",
    source: "AI Hub 168 · 안면인식 영상",
    subjects: 1686,
    clips: 8475,
    frames: 254250,
    timing: "unknown",
    reencoded: false,
    attackTypes: "print 2종 · replay 2종 · 3D mask",
    blocked: "camera_predicts_label",
    caveats: [
      {
        ko: "공격은 전부 GoPro, 진짜는 전부 스마트폰으로 촬영됐습니다. 카메라만 보고도 라벨을 맞힐 수 있어 성능이 근거가 되지 못합니다.",
        en: "Every attack was filmed on a GoPro and every bona fide clip on a phone: the camera alone gives the label, so a score here proves nothing.",
      },
      {
        ko: "원본 200명을 훑어도 GoPro로 찍은 진짜 영상이 없습니다. 범위를 넓혀도 해결되지 않아 제외했습니다.",
        en: "No GoPro bona fide clip exists across 200 source subjects, so widening the selection cannot fix it. Excluded.",
      },
    ],
    splits: [
      { label: "train", clips: 6950 },
      { label: "dev", clips: 1525 },
    ],
    conditions: ["Light_01_High", "Light_02_Mid", "Light_03_Low"],
    classes: [
      { label: "real_01_phone", label_: "bona_fide", weight: 2 },
      { label: "attack_01_print_none_flat", label_: "spoof" },
      { label: "attack_02_print_eye_nose_mouth_flat", label_: "spoof" },
      { label: "attack_03_replay_phone", label_: "spoof" },
      { label: "attack_04_replay_tablet", label_: "spoof" },
      { label: "attack_05_3d_mask", label_: "spoof" },
    ],
  },
];

function leaves(
  spec: DomainSpec,
  parentId: string,
  subjectPool: string,
  clips: number,
  frames: number,
): CatalogNode[] {
  const weights = spec.classes.map((leaf) => leaf.weight ?? 1);
  const clipShares = divide(clips, weights);
  const frameShares = divide(frames, weights);
  return spec.classes.map((leaf, index) => ({
    id: `${parentId}/${leaf.label}`,
    kind: "class" as const,
    label: leaf.label,
    clips: clipShares[index],
    frames: frameShares[index],
    measured: false,
    labels: [leaf.label_],
    subjectPool,
    domainId: spec.id,
    children: [],
  }));
}

function labelsOf(children: CatalogNode[]): LabelKind[] {
  const found = new Set<LabelKind>();
  for (const child of children) for (const label of child.labels) found.add(label);
  return [...found];
}

function buildDomain(spec: DomainSpec): CatalogNode {
  const framesPerSplit = divide(
    spec.frames,
    spec.splits.map((split) => split.clips),
  );
  const splits = spec.splits.map((split, splitIndex) => {
    const splitId = `${spec.id}/${split.label}`;
    const subjectPool = splitId;
    const splitFrames = framesPerSplit[splitIndex];
    let children: CatalogNode[];
    if (spec.conditions.length === 0) {
      children = leaves(spec, splitId, subjectPool, split.clips, splitFrames);
    } else {
      const conditionClips = divide(
        split.clips,
        spec.conditions.map(() => 1),
      );
      const conditionFrames = divide(
        splitFrames,
        spec.conditions.map(() => 1),
      );
      children = spec.conditions.map((condition, index) => {
        const conditionId = `${splitId}/${condition}`;
        const grandchildren = leaves(
          spec,
          conditionId,
          subjectPool,
          conditionClips[index],
          conditionFrames[index],
        );
        return {
          id: conditionId,
          kind: "condition" as const,
          label: condition,
          clips: conditionClips[index],
          frames: conditionFrames[index],
          measured: false,
          labels: labelsOf(grandchildren),
          subjectPool,
          domainId: spec.id,
          children: grandchildren,
        };
      });
    }
    return {
      id: splitId,
      kind: "split" as const,
      label: split.label,
      clips: split.clips,
      frames: splitFrames,
      measured: true,
      labels: labelsOf(children),
      subjectPool,
      domainId: spec.id,
      children,
    };
  });
  return {
    id: spec.id,
    kind: "domain",
    label: spec.id,
    clips: spec.clips,
    frames: spec.frames,
    measured: true,
    labels: labelsOf(splits),
    subjectPool: spec.id,
    domainId: spec.id,
    children: splits,
    blocked: spec.blocked,
  };
}

/** The tree, built once: the five domains we use, then the one that is out and why. */
export const DATASET_TREE: CatalogNode[] = SPECS.map(buildDomain);

export const DOMAIN_FACTS: Record<string, DomainFacts> = Object.fromEntries(
  SPECS.map((spec) => [
    spec.id,
    {
      id: spec.id,
      source: spec.source,
      subjects: spec.subjects,
      clips: spec.clips,
      frames: spec.frames,
      timing: spec.timing,
      reencoded: spec.reencoded,
      attackTypes: spec.attackTypes,
      blocked: spec.blocked,
      caveats: spec.caveats,
    },
  ]),
);

/** Every node by id, for turning a selection back into counts without walking the tree. */
export const NODE_INDEX: Map<string, CatalogNode> = (() => {
  const index = new Map<string, CatalogNode>();
  const walk = (node: CatalogNode) => {
    index.set(node.id, node);
    node.children.forEach(walk);
  };
  DATASET_TREE.forEach(walk);
  return index;
})();

export function findNode(id: string): CatalogNode | undefined {
  return NODE_INDEX.get(id);
}

/** The leaf ids under a node — what a selection actually stands for. */
export function leafIds(node: CatalogNode): string[] {
  if (node.children.length === 0) return [node.id];
  return node.children.flatMap(leafIds);
}

export function selectableDomains(): CatalogNode[] {
  return DATASET_TREE.filter((domain) => domain.blocked === undefined);
}
