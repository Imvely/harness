import type { AuditKind, AuditSeverity, GateVerdict, Locale, RunMode, RunStatus } from "./types";

type MessageKey =
  | "activeFilters"
  | "adaptation"
  | "artifactKind"
  | "artifacts"
  | "auditLog"
  | "auditTrail"
  | "baseline"
  | "browserExports"
  | "claimBlocked"
  | "claimEligible"
  | "claimEligibility"
  | "commandCopied"
  | "compare"
  | "configPatchPreview"
  | "controlLab"
  | "copyCommand"
  | "dashboard"
  | "dashboardJson"
  | "databaseState"
  | "devThresholdOnly"
  | "downloadMockDbJson"
  | "downloadReport"
  | "duration"
  | "experiment"
  | "experimentId"
  | "exportPath"
  | "filterNote"
  | "filtered"
  | "filters"
  | "gate"
  | "guardrails"
  | "hardRules"
  | "includeRisky"
  | "includeSmoke"
  | "language"
  | "latestReportActions"
  | "launchGuardrails"
  | "literature"
  | "liveMockStore"
  | "meanApcer"
  | "metricDelta"
  | "metricFirstTable"
  | "metricTrend"
  | "method"
  | "mockDb"
  | "mockDbPanelTitle"
  | "mockDbReset"
  | "mode"
  | "model"
  | "modelFamily"
  | "navAudit"
  | "navCompare"
  | "navControl"
  | "navDashboard"
  | "navLiterature"
  | "navReport"
  | "navRuns"
  | "noRows"
  | "openControlLab"
  | "overview"
  | "paiFocus"
  | "prepareReport"
  | "protocol"
  | "protocolGroups"
  | "protocolHash"
  | "recentDrafts"
  | "recentRuns"
  | "report"
  | "reportStudio"
  | "resetDb"
  | "researchAtlas"
  | "runTable"
  | "runs"
  | "safeCommandPreview"
  | "saveDraft"
  | "search"
  | "securityRegressions"
  | "seed"
  | "seedCheck"
  | "selectedRun"
  | "source"
  | "sourceRunId"
  | "started"
  | "status"
  | "syntheticSafety"
  | "threshold"
  | "thresholdRule"
  | "validateControls"
  | "viewFilters"
  | "whatThisDoesNotProve"
  | "yamlPatch";

const messages: Record<Locale, Record<MessageKey, string>> = {
  en: {
    activeFilters: "Active filters",
    adaptation: "Adaptation",
    artifactKind: "Artifact kind",
    artifacts: "Artifacts",
    auditLog: "Audit log",
    auditTrail: "Audit trail",
    baseline: "Baseline",
    browserExports: "Browser exports use the mock DB. Harness exports use the command above.",
    claimBlocked: "Blocked in this demo.",
    claimEligible: "Claim eligible",
    claimEligibility: "Claim eligibility",
    commandCopied: "Command copied to clipboard.",
    compare: "Compare",
    configPatchPreview: "Config patch preview",
    controlLab: "Control Lab",
    copyCommand: "Copy command",
    dashboard: "Dashboard",
    dashboardJson: "Dashboard JSON",
    databaseState: "Database state",
    devThresholdOnly: "dev threshold only",
    downloadMockDbJson: "Download mock DB JSON",
    downloadReport: "Download report",
    duration: "Duration",
    experiment: "Experiment",
    experimentId: "Experiment ID",
    exportPath: "Export path",
    filterNote: "Filtered by left panel",
    filtered: "filtered",
    filters: "Filters",
    gate: "Gate",
    guardrails: "Guardrails",
    hardRules: "Hard rules",
    includeRisky: "Include inconclusive/regression rows",
    includeSmoke: "Include smoke rows",
    language: "Language",
    latestReportActions: "Latest report actions",
    launchGuardrails: "Launch guardrails",
    literature: "Literature",
    liveMockStore: "Browser-backed lab store",
    meanApcer: "Mean APCER",
    metricDelta: "Metric delta",
    metricFirstTable: "Metric-first experiment table",
    metricTrend: "Metric trend",
    method: "Method",
    mockDb: "Mock DB",
    mockDbPanelTitle: "Browser-backed lab store",
    mockDbReset: "Reset DB",
    mode: "Mode",
    model: "Model",
    modelFamily: "Model family",
    navAudit: "Audit",
    navCompare: "Compare",
    navControl: "Control",
    navDashboard: "Dashboard",
    navLiterature: "Literature",
    navReport: "Report",
    navRuns: "Runs",
    noRows: "No runs match the active filters.",
    openControlLab: "Open control lab",
    overview: "Overview",
    paiFocus: "PAI focus",
    prepareReport: "Prepare report command",
    protocol: "Protocol",
    protocolGroups: "Protocol groups",
    protocolHash: "Protocol hash",
    recentDrafts: "Recent drafts",
    recentRuns: "Recent runs",
    report: "Report",
    reportStudio: "Report studio",
    resetDb: "Reset DB",
    researchAtlas: "Research Atlas",
    runTable: "Run table",
    runs: "Runs",
    safeCommandPreview: "Safe command preview",
    saveDraft: "Save draft",
    search: "Search",
    securityRegressions: "Security regressions",
    seed: "Seed",
    seedCheck: "Seed check",
    selectedRun: "Selected run",
    source: "Source",
    sourceRunId: "Source run ID",
    started: "Started",
    status: "Status",
    syntheticSafety: "SYNTHETIC SANITY — NOT A RESEARCH RESULT",
    threshold: "Threshold",
    thresholdRule: "Threshold rule",
    validateControls: "Validate controls",
    viewFilters: "View filters",
    whatThisDoesNotProve: "What this does not prove",
    yamlPatch: "YAML patch preview",
  },
  ko: {
    activeFilters: "활성 필터",
    adaptation: "적응",
    artifactKind: "산출물 종류",
    artifacts: "산출물",
    auditLog: "감사 기록",
    auditTrail: "감사 흐름",
    baseline: "기준 실험",
    browserExports: "브라우저 내보내기는 mock DB를 씁니다. 하네스 내보내기는 위 명령을 씁니다.",
    claimBlocked: "이 데모에서는 차단됨.",
    claimEligible: "주장 가능",
    claimEligibility: "주장 가능성",
    commandCopied: "명령을 클립보드에 복사했습니다.",
    compare: "비교",
    configPatchPreview: "설정 패치 미리보기",
    controlLab: "제어 실험실",
    copyCommand: "명령 복사",
    dashboard: "대시보드",
    dashboardJson: "대시보드 JSON",
    databaseState: "DB 상태",
    devThresholdOnly: "dev threshold only",
    downloadMockDbJson: "mock DB JSON 받기",
    downloadReport: "보고서 받기",
    duration: "소요 시간",
    experiment: "실험",
    experimentId: "실험 ID",
    exportPath: "내보내기 경로",
    filterNote: "왼쪽 필터 적용",
    filtered: "필터 적용",
    filters: "필터",
    gate: "게이트",
    guardrails: "안전 기준",
    hardRules: "필수 규칙",
    includeRisky: "불확실/회귀 행 포함",
    includeSmoke: "스모크 행 포함",
    language: "언어",
    latestReportActions: "최근 보고서 동작",
    launchGuardrails: "실행 안전 기준",
    literature: "문헌",
    liveMockStore: "브라우저 mock 연구 저장소",
    meanApcer: "평균 APCER",
    metricDelta: "지표 차이",
    metricFirstTable: "지표 중심 실험 표",
    metricTrend: "지표 추세",
    method: "방법",
    mockDb: "Mock DB",
    mockDbPanelTitle: "브라우저 기반 연구 저장소",
    mockDbReset: "DB 초기화",
    mode: "실행 방식",
    model: "모델",
    modelFamily: "모델 계열",
    navAudit: "감사",
    navCompare: "비교",
    navControl: "제어",
    navDashboard: "대시보드",
    navLiterature: "문헌 지도",
    navReport: "보고서",
    navRuns: "실행 목록",
    noRows: "활성 필터와 맞는 실행이 없습니다.",
    openControlLab: "제어 실험실 열기",
    overview: "개요",
    paiFocus: "PAI 집중 보기",
    prepareReport: "보고서 명령 준비",
    protocol: "프로토콜",
    protocolGroups: "프로토콜 묶음",
    protocolHash: "프로토콜 해시",
    recentDrafts: "최근 초안",
    recentRuns: "최근 실행",
    report: "보고서",
    reportStudio: "보고서 작업실",
    resetDb: "DB 초기화",
    researchAtlas: "리서치 아틀라스",
    runTable: "실행 표",
    runs: "실행",
    safeCommandPreview: "안전 명령 미리보기",
    saveDraft: "초안 저장",
    search: "검색",
    securityRegressions: "보안 회귀",
    seed: "시드",
    seedCheck: "시드 확인",
    selectedRun: "선택한 실행",
    source: "출처",
    sourceRunId: "원본 실행 ID",
    started: "시작",
    status: "상태",
    syntheticSafety: "합성 검증 — 연구 결과 아님",
    threshold: "임계값",
    thresholdRule: "임계값 규칙",
    validateControls: "값 검증",
    viewFilters: "보기 필터",
    whatThisDoesNotProve: "이 결과가 증명하지 않는 것",
    yamlPatch: "YAML 패치 미리보기",
  },
};

const viewMessages = {
  dashboard: { en: "Dashboard", ko: "대시보드" },
  literature: { en: "Literature", ko: "문헌 지도" },
  runs: { en: "Runs", ko: "실행 목록" },
  compare: { en: "Compare", ko: "비교" },
  audit: { en: "Audit", ko: "감사" },
  report: { en: "Report", ko: "보고서" },
  control: { en: "Control", ko: "제어" },
} as const;

const statusMessages: Record<RunStatus, Record<Locale, string>> = {
  smoke_ok: { en: "smoke ok", ko: "스모크 정상" },
  success: { en: "success", ko: "성공" },
  security_regression: { en: "security regression", ko: "보안 회귀" },
  inconclusive: { en: "inconclusive", ko: "불확실" },
};

const gateMessages: Record<GateVerdict, Record<Locale, string>> = {
  pass: { en: "pass", ko: "통과" },
  no_gate: { en: "no gate", ko: "게이트 없음" },
  security_regression: { en: "security regression", ko: "보안 회귀" },
  inconclusive: { en: "inconclusive", ko: "불확실" },
  comparison_blocked: { en: "comparison blocked", ko: "비교 차단" },
  unknown: { en: "unknown", ko: "알 수 없음" },
};

const modeMessages: Record<RunMode, Record<Locale, string>> = {
  smoke: { en: "smoke", ko: "스모크" },
  full: { en: "full", ko: "전체" },
  unknown: { en: "unknown", ko: "알 수 없음" },
};

/**
 * The seven conditions a run has to meet before it may back a research claim.
 *
 * They were already computed and stored per run, but the drawer printed only the free-text
 * `reasons` list — which meant a reader saw `researchClaimAllowed is false`, a field name, and
 * had no way to tell which of the seven conditions were met. Each label is phrased as the thing
 * that must be true, so a checked box reads as satisfied.
 */
const claimCheckMessages: Record<ClaimCheckKey, Record<Locale, string>> = {
  fullMode: { en: "Ran as a full run, not smoke", ko: "스모크가 아닌 전체 실행" },
  researchClaimAllowed: { en: "No synthetic dataset behind it", ko: "합성 데이터가 아님" },
  atLeastThreeSeeds: { en: "At least three seeds", ko: "시드 3개 이상" },
  enoughPaiSupport: { en: "Enough attack samples per PAI", ko: "공격 종류별 표본 충분" },
  thresholdFromDev: { en: "Threshold fitted on dev only", ko: "임계값을 dev에서만 결정" },
  noSecurityRegression: { en: "No security regression", ko: "보안 회귀 없음" },
  singleProtocolInExperiment: { en: "One protocol across the experiment", ko: "실험 내 프로토콜 단일" },
};

export type ClaimCheckKey =
  | "fullMode"
  | "researchClaimAllowed"
  | "atLeastThreeSeeds"
  | "enoughPaiSupport"
  | "thresholdFromDev"
  | "noSecurityRegression"
  | "singleProtocolInExperiment";

export const claimCheckKeys: ClaimCheckKey[] = [
  "fullMode",
  "researchClaimAllowed",
  "atLeastThreeSeeds",
  "enoughPaiSupport",
  "thresholdFromDev",
  "noSecurityRegression",
  "singleProtocolInExperiment",
];

export function claimCheckLabel(locale: Locale, key: ClaimCheckKey): string {
  return claimCheckMessages[key][locale];
}

export function t(locale: Locale, key: MessageKey): string {
  return messages[locale][key] ?? messages.en[key] ?? key;
}

export function viewLabel(locale: Locale, view: keyof typeof viewMessages): string {
  return viewMessages[view][locale];
}

/**
 * What each screen answers, in one sentence.
 *
 * All seven views shared a single subtitle — "실행, 게이트, 지표, PAI 위험을 한 작업공간에서
 * 확인합니다" — which is true of the app and says nothing about the screen in front of you. A
 * reader who lands on Compare and one who lands on Audit were told the same thing.
 *
 * Each line says what question the screen answers and, where the screen could be mistaken for
 * something that acts, that it does not act.
 */
const viewPurposeMessages: Record<keyof typeof viewMessages, Record<Locale, string>> = {
  dashboard: {
    en: "Which run needs attention first: security regressions, metric trends and per-attack risk across the filtered runs.",
    ko: "지금 어떤 실행을 먼저 봐야 하는가 — 필터된 실행들의 보안 회귀, 지표 추세, 공격 종류별 위험.",
  },
  literature: {
    en: "Which paper backs which experiment: the links between papers, datasets, methods and runs.",
    ko: "어떤 논문이 어떤 실험의 근거인가 — 논문·데이터셋·방법·실행의 연결 관계.",
  },
  runs: {
    en: "What has been run: filter the experiment table, then open a row for its provenance.",
    ko: "어떤 실행이 있었는가 — 조건으로 걸러 보고, 행을 눌러 그 실행의 출처를 확인합니다.",
  },
  compare: {
    en: "Whether two experiments may be put side by side. Metric deltas appear only when the protocol hash matches.",
    ko: "두 실험을 나란히 놓아도 되는가 — protocol hash가 같을 때만 지표 차이를 보여줍니다.",
  },
  audit: {
    en: "Whether these numbers can be trusted: hashes, threshold provenance and claim eligibility.",
    ko: "이 숫자를 믿어도 되는가 — 해시, 임계값 출처, 연구 주장 가능 여부.",
  },
  report: {
    en: "How to write the report command. This screen composes command text and never runs it.",
    ko: "보고서 명령을 어떻게 쓰는가 — 명령문을 만들어 보여줄 뿐, 실행하지 않습니다.",
  },
  control: {
    en: "How to write an experiment spec. This screen previews YAML and a command, and never launches training.",
    ko: "실험 설정을 어떻게 적는가 — YAML과 명령을 미리 보여줄 뿐, 학습을 시작하지 않습니다.",
  },
};

export function viewPurpose(locale: Locale, view: keyof typeof viewMessages): string {
  return viewPurposeMessages[view][locale];
}

export function statusText(locale: Locale, status: RunStatus): string {
  return statusMessages[status][locale];
}

export function gateText(locale: Locale, gate: GateVerdict): string {
  return gateMessages[gate][locale];
}

export function modeText(locale: Locale, mode: RunMode): string {
  return modeMessages[mode][locale];
}

/**
 * What each audit entry records.
 *
 * Derived from the stored `kind` at render time rather than read from the stored `title`. The
 * title is written once, in whatever language was active then, and persists in the browser — so
 * a reader who switches to Korean would still see an English log, including entries written
 * before they arrived. The kind is a stable enum, so it translates on every render.
 */
const auditKindMessages: Record<AuditKind, Record<Locale, string>> = {
  db_seeded: { en: "Store seeded", ko: "저장소 초기 적재" },
  db_recovered: { en: "Store recovered", ko: "저장소 복구" },
  db_reset: { en: "Store reset", ko: "저장소 초기화" },
  draft_saved: { en: "Draft saved", ko: "초안 저장" },
  command_copied: { en: "Command copied", ko: "명령 복사" },
  report_generated: { en: "Report command prepared", ko: "보고서 명령 준비" },
  paper_queued: { en: "Paper queued for reading", ko: "논문 읽기 큐 추가" },
  paper_status_changed: { en: "Paper status changed", ko: "논문 상태 변경" },
  paper_linked: { en: "Paper linked to an experiment", ko: "논문을 실험과 연결" },
};

/** Severity carried an icon and a word, never a border colour on its own. */
const severityMessages: Record<AuditSeverity, { en: string; ko: string; icon: string }> = {
  info: { en: "info", ko: "정보", icon: "ⓘ" },
  success: { en: "done", ko: "완료", icon: "✓" },
  warning: { en: "warning", ko: "주의", icon: "!" },
  danger: { en: "problem", ko: "문제", icon: "✕" },
};

export function auditKindLabel(locale: Locale, kind: AuditKind): string {
  return auditKindMessages[kind][locale];
}

export function severityLabel(locale: Locale, severity: AuditSeverity): string {
  return severityMessages[severity][locale];
}

export function severityIcon(severity: AuditSeverity): string {
  return severityMessages[severity].icon;
}

export function localeDate(locale: Locale, value: string): string {
  return new Date(value).toLocaleString(locale === "ko" ? "ko-KR" : "en-US");
}
