/**
 * What a dataset selection adds up to, and what is wrong with it.
 *
 * The three roles are not interchangeable. Training sees the data, validation is where a
 * threshold may be fitted, and test may never be looked at until the number is final (research
 * contract section 14). Most ways of getting that wrong look perfectly reasonable in a form:
 * two lighting conditions of the same people, one split used twice, a test set with no attacks
 * in it. So every check lives here as a pure function over the selection, runs on every click,
 * and says which role the problem is in.
 *
 * A finding is `blocking` when a number computed from that selection would not mean what it
 * claims, and `warning` when the result is interpretable but narrower than it looks.
 */

import type { CatalogNode, LabelKind } from "../data/datasetCatalog";
import type { Locale } from "../types";
import { DATASET_TREE, DOMAIN_FACTS, findNode, leafIds } from "../data/datasetCatalog";

export type DatasetRole = "train" | "dev" | "test";
export const DATASET_ROLES: DatasetRole[] = ["train", "dev", "test"];

/** Selected node ids per role. A parent id stands for every leaf under it. */
export type DatasetSelection = Record<DatasetRole, string[]>;

export const EMPTY_SELECTION: DatasetSelection = { train: [], dev: [], test: [] };

export interface RoleSummary {
  role: DatasetRole;
  clips: number;
  frames: number;
  bonaFideClips: number;
  spoofClips: number;
  domains: string[];
  subjectPools: string[];
  /** True when every number came from the store scan rather than being divided out of one. */
  measured: boolean;
}

export type FindingCode =
  | "subject_in_two_roles"
  | "role_empty"
  | "one_label_only"
  | "domain_in_train_and_test"
  | "timing_unknown"
  | "single_attack_type"
  | "blocked_domain"
  | "tiny_sample";

export interface Finding {
  code: FindingCode;
  level: "blocking" | "warning";
  roles: DatasetRole[];
  /** The concrete thing that triggered it: a subject pool, a domain, a node id. */
  subject?: string;
}

/** Leaf ids a role covers. Overlapping parent/child selections collapse to the same set. */
export function expand(selection: DatasetSelection, role: DatasetRole): string[] {
  const found = new Set<string>();
  for (const id of selection[role]) {
    const node = findNode(id);
    if (!node) continue;
    for (const leaf of leafIds(node)) found.add(leaf);
  }
  return [...found].sort();
}

function nodesOf(ids: string[]): CatalogNode[] {
  return ids.map(findNode).filter((node): node is CatalogNode => node !== undefined);
}

export function summarise(selection: DatasetSelection, role: DatasetRole): RoleSummary {
  const leaves = nodesOf(expand(selection, role));
  const chosen = nodesOf(selection[role]);
  let clips = 0;
  let frames = 0;
  let bonaFideClips = 0;
  let spoofClips = 0;
  const domains = new Set<string>();
  const pools = new Set<string>();
  for (const leaf of leaves) {
    clips += leaf.clips;
    frames += leaf.frames;
    if (leaf.labels.includes("bona_fide")) bonaFideClips += leaf.clips;
    if (leaf.labels.includes("spoof")) spoofClips += leaf.clips;
    domains.add(leaf.domainId);
    pools.add(leaf.subjectPool);
  }
  return {
    role,
    clips,
    frames,
    bonaFideClips,
    spoofClips,
    domains: [...domains].sort(),
    subjectPools: [...pools].sort(),
    // Whole domains and whole splits are measured; anything narrower is a divided estimate.
    measured: chosen.length > 0 && chosen.every((node) => node.measured),
  };
}

export function labelsIn(selection: DatasetSelection, role: DatasetRole): LabelKind[] {
  const found = new Set<LabelKind>();
  for (const leaf of nodesOf(expand(selection, role))) {
    for (const label of leaf.labels) found.add(label);
  }
  return [...found];
}

export function review(selection: DatasetSelection): Finding[] {
  const findings: Finding[] = [];
  const summaries = Object.fromEntries(
    DATASET_ROLES.map((role) => [role, summarise(selection, role)]),
  ) as Record<DatasetRole, RoleSummary>;

  // A blocked domain is unselectable in the UI; if one arrives anyway, say so rather than
  // quietly counting it.
  for (const role of DATASET_ROLES) {
    for (const domain of summaries[role].domains) {
      if (DOMAIN_FACTS[domain]?.blocked) {
        findings.push({ code: "blocked_domain", level: "blocking", roles: [role], subject: domain });
      }
    }
  }

  for (const role of DATASET_ROLES) {
    if (summaries[role].clips === 0) {
      findings.push({ code: "role_empty", level: "blocking", roles: [role] });
    } else if (labelsIn(selection, role).length < 2) {
      // One label cannot produce an error rate: APCER needs attacks, BPCER needs bona fide.
      findings.push({ code: "one_label_only", level: "blocking", roles: [role] });
    } else if (summaries[role].clips < 20) {
      findings.push({ code: "tiny_sample", level: "warning", roles: [role] });
    }
  }

  // The same people on both sides of an evaluation. The store cannot tell subjects apart more
  // finely than a domain's split, so two nodes from one split are two views of the same people.
  for (let i = 0; i < DATASET_ROLES.length; i += 1) {
    for (let j = i + 1; j < DATASET_ROLES.length; j += 1) {
      const a = DATASET_ROLES[i];
      const b = DATASET_ROLES[j];
      const shared = summaries[a].subjectPools.filter((pool) =>
        summaries[b].subjectPools.includes(pool),
      );
      for (const pool of shared) {
        findings.push({
          code: "subject_in_two_roles",
          level: "blocking",
          roles: [a, b],
          subject: pool,
        });
      }
    }
  }

  // Training and testing on one domain is a valid experiment, but it is not the cross-domain
  // question this project asks, and the number is not comparable with a leave-one-domain-out run.
  for (const domain of summaries.train.domains) {
    if (summaries.test.domains.includes(domain)) {
      findings.push({
        code: "domain_in_train_and_test",
        level: "warning",
        roles: ["train", "test"],
        subject: domain,
      });
    }
  }

  const involved = new Set([
    ...summaries.train.domains,
    ...summaries.dev.domains,
    ...summaries.test.domains,
  ]);
  for (const domain of involved) {
    if (DOMAIN_FACTS[domain]?.timing === "unknown") {
      findings.push({ code: "timing_unknown", level: "warning", roles: [], subject: domain });
    }
  }

  // A target domain with one attack type cannot support a per-PAI claim beyond that instrument.
  const testAttacks = new Set(
    nodesOf(expand(selection, "test"))
      .filter((leaf) => leaf.labels.includes("spoof"))
      .map((leaf) => leaf.label),
  );
  if (summaries.test.clips > 0 && testAttacks.size === 1) {
    findings.push({
      code: "single_attack_type",
      level: "warning",
      roles: ["test"],
      subject: [...testAttacks][0],
    });
  }

  return findings;
}

export function isRunnable(selection: DatasetSelection): boolean {
  return review(selection).every((finding) => finding.level !== "blocking");
}

/** Whether a node is fully, partly or not selected for a role — a checkbox's three states. */
export function nodeState(
  selection: DatasetSelection,
  role: DatasetRole,
  node: CatalogNode,
): "on" | "partial" | "off" {
  const selected = new Set(expand(selection, role));
  const leaves = leafIds(node);
  const hits = leaves.filter((leaf) => selected.has(leaf)).length;
  if (hits === 0) return "off";
  return hits === leaves.length ? "on" : "partial";
}

/**
 * Toggle a node for one role, keeping the stored ids as small as they can be.
 *
 * Selecting is not additive across roles: a node moved into test leaves the role it was in, so
 * one click cannot put the same clips on two sides of the evaluation by accident.
 */
export function toggle(
  selection: DatasetSelection,
  role: DatasetRole,
  node: CatalogNode,
): DatasetSelection {
  const leaves = new Set(leafIds(node));
  const turningOff = nodeState(selection, role, node) === "on";
  const next: DatasetSelection = { train: [], dev: [], test: [] };
  for (const other of DATASET_ROLES) {
    const kept = expand(selection, other).filter((leaf) => !leaves.has(leaf));
    next[other] = kept;
  }
  if (!turningOff) next[role] = [...next[role], ...leaves].sort();
  return { train: collapse(next.train), dev: collapse(next.dev), test: collapse(next.test) };
}

export function clearRole(selection: DatasetSelection, role: DatasetRole): DatasetSelection {
  return { ...selection, [role]: [] };
}

/**
 * Replace a complete set of children with their parent's id, repeatedly.
 *
 * Without it a whole-domain choice would be stored as its hundred leaves, and the YAML preview
 * would read as a hundred lines where the person picked one thing.
 */
export function collapse(ids: string[]): string[] {
  const covered = new Set<string>();
  for (const id of ids) {
    const node = findNode(id);
    if (node) for (const leaf of leafIds(node)) covered.add(leaf);
  }
  const chosen: string[] = [];
  const walk = (node: CatalogNode) => {
    const leaves = leafIds(node);
    // Fully covered: this node *is* the selection, and nothing under it needs naming.
    if (leaves.every((leaf) => covered.has(leaf))) {
      chosen.push(node.id);
      return;
    }
    node.children.forEach(walk);
  };
  DATASET_TREE.forEach(walk);
  return chosen.sort();
}

/** The protocol block a selection stands for, as it would appear in a config file. */
export function selectionYaml(selection: DatasetSelection): string {
  const lines = ["protocol:"];
  for (const role of DATASET_ROLES) {
    const ids = selection[role];
    if (ids.length === 0) {
      lines.push(`  ${role}: []   # nothing selected`);
      continue;
    }
    lines.push(`  ${role}:`);
    for (const id of ids) lines.push(`    - ${id}`);
  }
  return lines.join("\n");
}

export function roleName(locale: Locale, role: DatasetRole): string {
  if (locale === "ko") {
    return role === "train" ? "학습" : role === "dev" ? "검증" : "테스트";
  }
  return role === "train" ? "training" : role === "dev" ? "validation" : "test";
}

/**
 * A finding as one sentence that names the problem and what to do.
 *
 * Not "SUBJECT_OVERLAP": a code tells you it is wrong, a sentence tells you why it is wrong,
 * and the difference decides whether the check gets respected or clicked past.
 */
export function findingText(locale: Locale, finding: Finding): string {
  const roles = finding.roles.map((role) => roleName(locale, role)).join(locale === "ko" ? "·" : " / ");
  switch (finding.code) {
    case "subject_in_two_roles":
      return locale === "ko"
        ? `같은 사람이 ${roles}에 동시에 들어갑니다(${finding.subject}). 외운 얼굴을 다시 맞히는 것이라 점수가 실제보다 높게 나옵니다. 한쪽에서 빼세요.`
        : `The same people are in ${roles} (${finding.subject}). The score would come from recognising a memorised face, not from detecting a spoof. Remove one side.`;
    case "role_empty": {
      // One sentence per role: what is missing differs, and "role is empty" alone says nothing
      // about why it matters. The `에` form also sidesteps the ko subject particle.
      const why =
        finding.roles[0] === "train"
          ? { ko: "모델이 볼 데이터가 없습니다.", en: "the model has nothing to learn from." }
          : finding.roles[0] === "dev"
            ? {
                ko: "임계값을 정할 데이터가 없습니다. 임계값은 테스트에서 고를 수 없습니다.",
                en: "there is nothing to fit the threshold on, and it may never be chosen on test.",
              }
            : { ko: "낼 숫자가 없습니다.", en: "there is no number to report." };
      return locale === "ko" ? `${roles}에 아무것도 없습니다. ${why.ko}` : `${roles} is empty: ${why.en}`;
    }
    case "one_label_only":
      return locale === "ko"
        ? `${roles}에 진짜나 공격 한쪽만 있습니다. 오류율은 양쪽이 있어야 계산됩니다.`
        : `${roles} holds only one class. An error rate needs both bona fide and attacks.`;
    case "domain_in_train_and_test":
      return locale === "ko"
        ? `${finding.subject}가 학습과 테스트 양쪽에 있습니다. 같은 도메인 안의 성능이라 도메인 간 일반화를 말할 수는 없습니다.`
        : `${finding.subject} is in both training and test. That measures within-domain performance, not generalisation across domains.`;
    case "timing_unknown":
      return locale === "ko"
        ? `${finding.subject}는 프레임 시각이 기록돼 있지 않습니다. FFT나 옵티컬 플로우처럼 시간 간격이 필요한 분석에는 쓰지 마세요.`
        : `${finding.subject} records no frame timing, so it cannot back an analysis that needs an interval (FFT, optical flow).`;
    case "single_attack_type":
      return locale === "ko"
        ? `테스트의 공격이 ${finding.subject} 한 종류뿐입니다. 이 결과는 그 공격에 대해서만 말할 수 있습니다.`
        : `The test attacks are all ${finding.subject}. The result speaks for that instrument only.`;
    case "blocked_domain":
      return locale === "ko"
        ? `${finding.subject}는 카메라만으로 라벨이 맞혀지는 도메인입니다. 어떤 점수도 근거가 되지 못합니다.`
        : `${finding.subject} lets the camera alone predict the label, so no score from it is evidence.`;
    case "tiny_sample":
      return locale === "ko"
        ? `${roles}의 표본이 20개 미만입니다. 신뢰구간이 넓어 차이를 말하기 어렵습니다.`
        : `${roles} holds fewer than 20 clips; the interval will be too wide to claim a difference.`;
  }
}
