import type { Locale } from "./types";

/**
 * Plain-language definitions for every term the dashboard puts on screen.
 *
 * Until now the UI showed bare acronyms — APCER, BPCER, tau, PAI, protocol_hash — with no
 * expansion, tooltip or glossary anywhere in the app. Someone opening this for the first time
 * had no way to learn what a number meant from the product itself.
 *
 * The wording follows the research contract section 14 for the metrics and section 16 for the
 * run vocabulary, so the UI and the contract cannot drift into saying different things. Each
 * entry carries a direction (`lower` / `higher` / null) because "is 0.2 good?" is the first
 * question a newcomer asks and the answer flips between APCER and AUC.
 */

export type GlossaryDirection = "lower" | "higher" | null;

/**
 * Every term the UI may point at.
 *
 * Spelled out as a union rather than inferred, so `<Term id="protcol-hash">` is a type error at
 * the call site. A typo would otherwise render the fallback text and silently drop the
 * definition — invisible in the browser, and exactly the kind of quiet gap this panel exists to
 * close.
 */
export type GlossaryId =
  | "apcer"
  | "bpcer"
  | "acer"
  | "hter"
  | "auc"
  | "tau"
  | "dev-test"
  | "eer"
  | "pai"
  | "bona-fide"
  | "spoof"
  | "smoke"
  | "full"
  | "adaptation"
  | "seed"
  | "gate-verdict"
  | "security-regression"
  | "claim-eligibility"
  | "protocol-hash"
  | "science-hash"
  | "spec-hash"
  | "manifest-hash"
  | "research-claim-allowed"
  | "pii-policy";

export interface GlossaryEntry {
  /** Stable key, also the anchor id. */
  id: GlossaryId;
  /** How the term appears in the UI (usually the acronym). */
  term: string;
  /** Full English form, or null where there is no expansion. */
  expansion: string | null;
  /** Korean name to print beside the acronym. */
  ko: string;
  /** One or two sentences, Korean. */
  koDefinition: string;
  /** One or two sentences, English. */
  enDefinition: string;
  direction: GlossaryDirection;
  group: "metric" | "threshold" | "attack" | "run" | "gate" | "provenance";
}

export const glossary: GlossaryEntry[] = [
  // --- metrics ---------------------------------------------------------------------------
  {
    id: "apcer",
    term: "APCER",
    expansion: "Attack Presentation Classification Error Rate",
    ko: "공격 통과율",
    koDefinition:
      "공격인데 진짜 얼굴로 통과시킨 비율입니다. 보안 관점의 핵심 지표이고, 공격 도구(PAI) 종류별로 따로 계산합니다. 시스템 수준 값은 종류별 최댓값을 씁니다.",
    enDefinition:
      "The share of attacks that were let through as bona fide. This is the security-critical metric, computed per PAI species; the system-level number is the worst species.",
    direction: "lower",
    group: "metric",
  },
  {
    id: "bpcer",
    term: "BPCER",
    expansion: "Bona Fide Presentation Classification Error Rate",
    ko: "정상 사용자 차단율",
    koDefinition:
      "진짜 사용자인데 공격으로 잘못 막은 비율입니다. 사용 편의성과 직결됩니다.",
    enDefinition:
      "The share of genuine users wrongly rejected as an attack. This is the usability side.",
    direction: "lower",
    group: "metric",
  },
  {
    id: "acer",
    term: "ACER",
    expansion: "Average Classification Error Rate",
    ko: "평균 오류율",
    koDefinition:
      "보통 APCER와 BPCER의 평균으로 쓰지만, 정의는 dataset과 protocol을 그대로 따릅니다. 두 오류를 하나로 합치므로 어느 쪽이 나빠졌는지는 이 값만으로 알 수 없습니다.",
    enDefinition:
      "Usually the mean of APCER and BPCER, but the dataset's and protocol's own definition wins. It merges two different errors, so it cannot tell you which side got worse.",
    direction: "lower",
    group: "metric",
  },
  {
    id: "hter",
    term: "HTER",
    expansion: "Half Total Error Rate",
    ko: "절반 총오류율",
    koDefinition:
      "문헌 비교용 지표입니다. 임계값을 어떻게 정했는지와 어떤 protocol인지를 함께 적지 않으면 다른 논문 수치와 비교할 수 없습니다.",
    enDefinition:
      "Used for comparison with the literature. It means nothing without recording how the threshold was chosen and under which protocol.",
    direction: "lower",
    group: "metric",
  },
  {
    id: "auc",
    term: "AUC",
    expansion: "Area Under the ROC Curve",
    ko: "ROC 곡선 아래 면적",
    koDefinition:
      "임계값과 무관하게 점수의 순위 품질을 재는 값입니다. 높을수록 좋지만, AUC 하나만으로 보안 성능을 결론내지 않습니다 — 공격 종류별 APCER가 나빠졌는데도 AUC는 올라갈 수 있습니다.",
    enDefinition:
      "Threshold-free ranking quality. Higher is better, but AUC alone never settles security: it can rise while per-PAI APCER gets worse.",
    direction: "higher",
    group: "metric",
  },

  // --- threshold -------------------------------------------------------------------------
  {
    id: "tau",
    term: "tau (τ)",
    expansion: null,
    ko: "판정 임계값",
    koDefinition:
      "점수가 이 값 이상이면 공격으로 판정합니다. 반드시 dev split에서만 정하고, test split을 보고 고르면 결과가 부풀려집니다.",
    enDefinition:
      "A sample is called an attack when its score reaches tau. It is fitted on the dev split only; choosing it by looking at test inflates every number below it.",
    direction: null,
    group: "threshold",
  },
  {
    id: "dev-test",
    term: "dev / test",
    expansion: null,
    ko: "개발용 / 평가용 분할",
    koDefinition:
      "dev는 임계값을 정하는 데만, test는 성능을 재는 데만 씁니다. test로 임계값을 고르면 그 성능은 더 이상 예측값이 아닙니다.",
    enDefinition:
      "dev is for fitting the threshold, test is for measuring. A threshold picked on test stops being a prediction of anything.",
    direction: null,
    group: "threshold",
  },
  {
    id: "eer",
    term: "eer",
    expansion: "Equal Error Rate",
    ko: "동일 오류율 지점",
    koDefinition:
      "APCER와 BPCER가 같아지는 지점을 임계값으로 잡는 규칙입니다. 임계값 규칙 중 하나이고, 다른 규칙은 특정 APCER에서의 BPCER를 보는 방식입니다.",
    enDefinition:
      "A threshold rule that picks the point where APCER and BPCER meet. The alternative rule fixes APCER and reads BPCER there.",
    direction: null,
    group: "threshold",
  },

  // --- attacks ---------------------------------------------------------------------------
  {
    id: "pai",
    term: "PAI",
    expansion: "Presentation Attack Instrument",
    ko: "공격 도구",
    koDefinition:
      "위조 얼굴을 제시하는 데 쓰인 물건입니다. 인쇄물(print), 휴대폰 화면 재생(replay_phone), 태블릿 재생(replay_tablet) 등으로 나뉩니다. APCER는 이 종류별로 따로 봐야 합니다 — 평균을 내면 한 종류만 뚫린 것이 가려집니다.",
    enDefinition:
      "The object used to present the fake face: a print, a phone screen replay, a tablet replay. APCER is read per species, because averaging hides a single species that is wide open.",
    direction: null,
    group: "attack",
  },
  {
    id: "bona-fide",
    term: "bona fide",
    expansion: null,
    ko: "진짜 제시",
    koDefinition: "실제 사람이 직접 카메라 앞에 선 경우입니다. 공격(spoof)의 반대말입니다.",
    enDefinition: "A real person presenting their own face. The opposite of a spoof.",
    direction: null,
    group: "attack",
  },
  {
    id: "spoof",
    term: "spoof",
    expansion: null,
    ko: "위조 제시",
    koDefinition: "공격 도구로 위조한 얼굴을 제시한 경우입니다.",
    enDefinition: "A face presented through an attack instrument rather than by its owner.",
    direction: null,
    group: "attack",
  },

  // --- run vocabulary --------------------------------------------------------------------
  {
    id: "smoke",
    term: "smoke",
    expansion: null,
    ko: "스모크 실행",
    koDefinition:
      "데이터가 읽히는지, 모델이 도는지만 확인하는 짧은 실행입니다. 배치 몇 개만 돌기 때문에 성능 주장에는 절대 쓸 수 없습니다.",
    enDefinition:
      "A short run that only checks the data loads and the model executes. It reads a handful of batches, so it can never support a performance claim.",
    direction: null,
    group: "run",
  },
  {
    id: "full",
    term: "full",
    expansion: null,
    ko: "전체 실행",
    koDefinition:
      "실제 학습·평가를 끝까지 하는 실행입니다. 사람이 직접 만든 승인 토큰이 있어야 시작됩니다.",
    enDefinition:
      "A complete training and evaluation run. It cannot start without an approval token a human created.",
    direction: null,
    group: "run",
  },
  {
    id: "adaptation",
    term: "adaptation",
    expansion: null,
    ko: "도메인 적응",
    koDefinition:
      "다른 환경(target)의 데이터로 모델을 맞춰가는 과정입니다. 이 연구에서는 target의 진짜 얼굴만 쓰기 때문에, 공격 탐지 능력이 조용히 나빠질 수 있습니다.",
    enDefinition:
      "Fitting the model to a new environment. Here only the target's bona-fide samples are used, so the ability to catch attacks can quietly degrade.",
    direction: null,
    group: "run",
  },
  {
    id: "seed",
    term: "seed",
    expansion: null,
    ko: "난수 시드",
    koDefinition:
      "무작위성을 고정하는 숫자입니다. 시드를 바꾸면 같은 설정이어도 결과가 달라지므로, 결론을 내려면 시드 3개 이상의 평균과 편차가 필요합니다.",
    enDefinition:
      "Fixes the randomness. The same configuration gives different numbers per seed, so a conclusion needs at least three seeds with their spread.",
    direction: null,
    group: "run",
  },

  // --- gate ------------------------------------------------------------------------------
  {
    id: "gate-verdict",
    term: "gate verdict",
    expansion: null,
    ko: "보안 회귀 판정",
    koDefinition:
      "적응 전후로 공격 종류별 APCER를 비교한 결과입니다. pass(악화 없음), security regression(악화), inconclusive(표본이 적어 판단 불가), comparison blocked(protocol이 달라 비교 불가), no gate(비교 대상 없음) 중 하나입니다.",
    enDefinition:
      "The result of comparing per-PAI APCER before and after adaptation: pass, security regression, inconclusive (too few samples to tell), comparison blocked (different protocols), or no gate (nothing to compare against).",
    direction: null,
    group: "gate",
  },
  {
    id: "security-regression",
    term: "security regression",
    expansion: null,
    ko: "보안 회귀",
    koDefinition:
      "적응 뒤에 어떤 공격 종류의 APCER가 허용치를 넘어 나빠졌다는 뜻입니다. BPCER가 좋아졌더라도 이 판정은 뒤집히지 않습니다.",
    enDefinition:
      "After adaptation, at least one PAI species got worse beyond the allowed tolerance. A better BPCER does not overturn it.",
    direction: null,
    group: "gate",
  },
  {
    id: "claim-eligibility",
    term: "claim eligibility",
    expansion: null,
    ko: "연구 주장 가능 여부",
    koDefinition:
      "이 실행을 논문이나 보고서의 근거로 쓸 수 있는지입니다. 전체 실행일 것, 합성 데이터가 아닐 것, 시드 3개 이상일 것, 공격 종류별 표본이 충분할 것, 임계값이 dev에서 나왔을 것, 보안 회귀가 없을 것, protocol이 하나일 것을 모두 만족해야 합니다.",
    enDefinition:
      "Whether this run may back a claim. It must be a full run on non-synthetic data, with at least three seeds, enough samples per PAI, a dev-fitted threshold, no security regression, and a single protocol.",
    direction: null,
    group: "gate",
  },

  // --- provenance ------------------------------------------------------------------------
  {
    id: "protocol-hash",
    term: "protocol_hash",
    expansion: null,
    ko: "프로토콜 해시",
    koDefinition:
      "어떤 데이터셋을 쓰고, 어떻게 나누고, 임계값을 어떻게 정할지를 담은 정의의 지문입니다. 이 값이 같을 때만 두 실험의 수치를 직접 비교할 수 있습니다.",
    enDefinition:
      "A fingerprint of the datasets, splits and threshold rules in force. Two runs' numbers are directly comparable only when it matches.",
    direction: null,
    group: "provenance",
  },
  {
    id: "science-hash",
    term: "science_hash",
    expansion: null,
    ko: "과학 해시",
    koDefinition:
      "실험 설정에서 실행 방식과 기록 설정을 뺀 나머지의 지문입니다. 같은 실험을 smoke로 돌리든 full로 돌리든 이 값은 같아서, 승인 토큰이 엉뚱한 설정에 재사용되는 것을 막습니다.",
    enDefinition:
      "A fingerprint of the experiment minus its execution and tracking settings. It is identical for the smoke and full runs of one experiment, which is what stops an approval token being reused for a different one.",
    direction: null,
    group: "provenance",
  },
  {
    id: "spec-hash",
    term: "spec_hash",
    expansion: null,
    ko: "스펙 해시",
    koDefinition: "실험 설정 파일 전체의 지문입니다. 실행 방식까지 포함하므로 science_hash보다 잘 바뀝니다.",
    enDefinition:
      "A fingerprint of the whole experiment spec, execution settings included, so it changes more readily than science_hash.",
    direction: null,
    group: "provenance",
  },
  {
    id: "manifest-hash",
    term: "manifest_hash",
    expansion: null,
    ko: "데이터 목록 해시",
    koDefinition:
      "어떤 샘플이 데이터셋에 들어 있는지를 적은 목록의 지문입니다. 데이터가 한 줄이라도 바뀌면 이 값이 바뀝니다.",
    enDefinition:
      "A fingerprint of the sample list making up a dataset. One changed row changes the hash.",
    direction: null,
    group: "provenance",
  },
  {
    id: "research-claim-allowed",
    term: "research_claim_allowed",
    expansion: null,
    ko: "연구 근거 사용 허용",
    koDefinition:
      "내보내기 도구가 붙이는 표시입니다. 데이터셋 중 하나라도 합성이면 false가 되고, 그 실행은 파이프라인 동작만 보여줄 뿐 성능 근거가 되지 못합니다.",
    enDefinition:
      "Set by the exporter. It is false whenever any dataset behind the run is synthetic, which makes the run a demonstration of the pipeline rather than evidence.",
    direction: null,
    group: "provenance",
  },
  {
    id: "pii-policy",
    term: "pii_policy",
    expansion: null,
    ko: "개인정보 정책",
    koDefinition:
      "데이터셋별로 얼굴 데이터를 어떻게 다뤄야 하는지입니다. synthetic(합성), internal_only(내부 전용), licensed_research(연구 목적 라이선스) 중 하나입니다.",
    enDefinition:
      "How each dataset's face data must be handled: synthetic, internal_only, or licensed_research.",
    direction: null,
    group: "provenance",
  },
];

const byId = new Map<string, GlossaryEntry>(glossary.map((entry) => [entry.id, entry]));

/**
 * Accepts a plain string so callers holding a `MetricKey` need no cast; the union above is what
 * constrains the `<Term>` and `<TermMark>` props, where typos actually happen.
 */
export function glossaryEntry(id: string): GlossaryEntry | undefined {
  return byId.get(id);
}

/** The short "낮을수록 안전" style hint shown next to a metric. */
export function directionHint(entry: GlossaryEntry, locale: Locale): string | null {
  if (entry.direction === null) return null;
  if (entry.direction === "lower") return locale === "ko" ? "낮을수록 안전" : "lower is safer";
  return locale === "ko" ? "높을수록 좋음" : "higher is better";
}

/** `공격 통과율 (APCER)` in Korean, `APCER` in English. */
export function termLabel(entry: GlossaryEntry, locale: Locale): string {
  return locale === "ko" ? `${entry.ko} (${entry.term})` : entry.term;
}

export function definition(entry: GlossaryEntry, locale: Locale): string {
  return locale === "ko" ? entry.koDefinition : entry.enDefinition;
}

export const glossaryGroups: Array<{ group: GlossaryEntry["group"]; ko: string; en: string }> = [
  { group: "metric", ko: "지표", en: "Metrics" },
  { group: "threshold", ko: "임계값", en: "Threshold" },
  { group: "attack", ko: "공격", en: "Attacks" },
  { group: "run", ko: "실행", en: "Runs" },
  { group: "gate", ko: "보안 판정", en: "Security gate" },
  { group: "provenance", ko: "출처 추적", en: "Provenance" },
];
