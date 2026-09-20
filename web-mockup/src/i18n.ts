import type { GateVerdict, Locale, RunMode, RunStatus } from "./types";

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
  | "researchDashboard"
  | "researchAtlas"
  | "researchSubtitle"
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
    researchDashboard: "Research-optimized dashboard",
    researchAtlas: "Research Atlas",
    researchSubtitle: "Review execution, gates, metrics, and PAI risk in one workspace.",
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
    researchDashboard: "연구 최적화 대시보드",
    researchAtlas: "리서치 아틀라스",
    researchSubtitle: "실행, 게이트, 지표, PAI 위험을 한 작업공간에서 확인합니다.",
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

export function t(locale: Locale, key: MessageKey): string {
  return messages[locale][key] ?? messages.en[key] ?? key;
}

export function viewLabel(locale: Locale, view: keyof typeof viewMessages): string {
  return viewMessages[view][locale];
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

export function localeDate(locale: Locale, value: string): string {
  return new Date(value).toLocaleString(locale === "ko" ? "ko-KR" : "en-US");
}
