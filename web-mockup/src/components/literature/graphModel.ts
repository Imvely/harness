import type {
  DemoRun,
  EvidenceKind,
  GraphEdgeKind,
  LiteratureEvidenceItem,
  LiteratureGraphEdge,
  LiteratureGraphNode,
  Locale,
  MockDatabaseState,
  PaperStatus,
} from "../../types";
import { t } from "../../i18n";
import { unique } from "../../utils";

/**
 * The relationship graph's geometry and vocabulary, with no JSX in it.
 *
 * Split out of `ResearchAtlasView.tsx`, which had grown to 1,787 lines — over half of every
 * component in the app, holding the view shell, a filter form, a pan-and-zoom SVG workbench, a
 * minimap, a node inspector, an eight-column table, a seven-column matrix, a detail card and a
 * queue. Nothing here touches React, so the layout maths can be read and tested on its own.
 *
 * `evidenceKindLabel` and `statusLabel` live here rather than beside their tables because the
 * node inspector needs them too; keeping them in the view file would make the two modules
 * import each other.
 */

export type GraphTransform = {
  zoom: number;
  panX: number;
  panY: number;
};

export type PositionedGraphNode = {
  node: LiteratureGraphNode;
  x: number;
  y: number;
  radius: number;
};

export type GraphTooltip = {
  x: number;
  y: number;
  node: LiteratureGraphNode;
};

export type GraphNodeDetail = {
  title: string;
  kindLabel: string;
  description: string;
  badges: string[];
  meta: Array<{ label: string; value: string }>;
  relatedPaperIds: string[];
};

export type GraphEdgeGroup = "citation" | "evidence" | "context" | "experiment";

export type GraphBounds = {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
};

export const graphEdgeGroups: GraphEdgeGroup[] = ["citation", "evidence", "context", "experiment"];
export const graphZoomMin = 0.55;
export const graphZoomMax = 3;
export const defaultGraphTransform: GraphTransform = { zoom: 1, panX: 0, panY: 0 };

export function buildGraphLayout(
  nodes: LiteratureGraphNode[],
  selectedPaperId: string,
  width: number,
  height: number,
): PositionedGraphNode[] {
  const center = { x: width / 2, y: height / 2 };
  const outer = nodes.filter((node) => node.id !== selectedPaperId);
  return nodes.map((node) => {
    if (node.id === selectedPaperId) return { node, x: center.x, y: center.y, radius: 34 };
    const index = outer.findIndex((item) => item.id === node.id);
    const angle = (index / Math.max(outer.length, 1)) * Math.PI * 2 - Math.PI / 2;
    const xRadius = graphRadius(node.kind, "x");
    const yRadius = graphRadius(node.kind, "y");
    return {
      node,
      x: center.x + Math.cos(angle) * xRadius,
      y: center.y + Math.sin(angle) * yRadius,
      radius: graphNodeRadius(node.kind),
    };
  });
}

export function graphRadius(kind: LiteratureGraphNode["kind"], axis: "x" | "y"): number {
  if (kind === "paper") return axis === "x" ? 180 : 110;
  if (kind === "author" || kind === "venue") return axis === "x" ? 310 : 150;
  if (kind === "experiment") return axis === "x" ? 290 : 155;
  return axis === "x" ? 250 : 145;
}

export function graphNodeRadius(kind: LiteratureGraphNode["kind"]): number {
  if (kind === "paper") return 24;
  if (kind === "author" || kind === "venue") return 20;
  if (kind === "experiment") return 22;
  return 21;
}

export function graphBounds(layout: PositionedGraphNode[]): GraphBounds {
  if (layout.length === 0) return { minX: 0, minY: 0, maxX: 1, maxY: 1 };
  return layout.reduce<GraphBounds>(
    (bounds, item) => ({
      minX: Math.min(bounds.minX, item.x - item.radius - 56),
      minY: Math.min(bounds.minY, item.y - item.radius - 52),
      maxX: Math.max(bounds.maxX, item.x + item.radius + 56),
      maxY: Math.max(bounds.maxY, item.y + item.radius + 66),
    }),
    {
      minX: Number.POSITIVE_INFINITY,
      minY: Number.POSITIVE_INFINITY,
      maxX: Number.NEGATIVE_INFINITY,
      maxY: Number.NEGATIVE_INFINITY,
    },
  );
}

export function fitGraphTransform(bounds: GraphBounds, width: number, height: number): GraphTransform {
  const padding = 44;
  const boundsWidth = Math.max(bounds.maxX - bounds.minX, 1);
  const boundsHeight = Math.max(bounds.maxY - bounds.minY, 1);
  const zoom = clamp(Math.min((width - padding * 2) / boundsWidth, (height - padding * 2) / boundsHeight), graphZoomMin, 1.35);
  const centerX = (bounds.minX + bounds.maxX) / 2;
  const centerY = (bounds.minY + bounds.maxY) / 2;
  return {
    zoom,
    panX: width / 2 - centerX * zoom,
    panY: height / 2 - centerY * zoom,
  };
}

export function svgPointFromClient(
  svg: SVGSVGElement,
  clientX: number,
  clientY: number,
  width: number,
  height: number,
): { x: number; y: number } {
  const rect = svg.getBoundingClientRect();
  return {
    x: ((clientX - rect.left) * width) / rect.width,
    y: ((clientY - rect.top) * height) / rect.height,
  };
}

export function connectedNodeSet(edges: LiteratureGraphEdge[], highlightedNodeId: string | null): Set<string> {
  const ids = new Set<string>();
  if (!highlightedNodeId) return ids;
  ids.add(highlightedNodeId);
  for (const edge of edges) {
    if (edge.source === highlightedNodeId) ids.add(edge.target);
    if (edge.target === highlightedNodeId) ids.add(edge.source);
  }
  return ids;
}

export function buildGraphNodeDetail(
  database: MockDatabaseState,
  node: LiteratureGraphNode,
  edges: LiteratureGraphEdge[],
  nodes: LiteratureGraphNode[],
  runs: DemoRun[],
  locale: Locale,
): GraphNodeDetail {
  const literature = database.literature;
  const relatedPaperIds = relatedPaperIdsForNode(node, edges, nodes);
  if (node.kind === "paper") {
    const paper = literature.papers.find((item) => item.paperId === node.id);
    const venue = literature.venues.find((item) => item.venueId === paper?.venueId);
    const authors = paper?.authorIds
      .map((authorId) => literature.authors.find((author) => author.authorId === authorId)?.name)
      .filter((name): name is string => Boolean(name)) ?? [];
    return {
      title: paper?.title ?? node.label,
      kindLabel: graphNodeKindLabel(locale, node.kind),
      description: paper?.abstract ?? node.label,
      badges: paper ? [`${paper.year}`, `${paper.citationCount} ${locale === "ko" ? "인용" : "citations"}`, statusLabel(locale, paper.status)] : [],
      meta: [
        { label: locale === "ko" ? "저자" : "Authors", value: authors.join(", ") || "—" },
        { label: "Venue", value: venue?.name ?? paper?.venueId ?? "—" },
        { label: locale === "ko" ? "관련도" : "Relevance", value: `${Math.round(node.score * 100)}%` },
        { label: locale === "ko" ? "제공자" : "Providers", value: paper?.providerIds.join(", ") ?? "—" },
      ],
      relatedPaperIds,
    };
  }
  if (node.kind === "author") {
    const author = literature.authors.find((item) => item.authorId === node.id);
    const authoredPapers = literature.papers.filter((paper) => paper.authorIds.includes(node.id));
    return {
      title: author?.name ?? node.label,
      kindLabel: graphNodeKindLabel(locale, node.kind),
      description: locale === "ko" ? "선택 논문과 연결된 저자 노드입니다." : "Author node connected to the selected paper.",
      badges: [`${authoredPapers.length} ${locale === "ko" ? "편" : "papers"}`],
      meta: [
        { label: locale === "ko" ? "소속" : "Affiliation", value: author?.affiliation ?? "—" },
        { label: locale === "ko" ? "연결 강도" : "Link score", value: `${Math.round(node.score * 100)}%` },
      ],
      relatedPaperIds: authoredPapers.map((paper) => paper.paperId),
    };
  }
  if (node.kind === "venue") {
    const venue = literature.venues.find((item) => item.venueId === node.id);
    const venuePapers = literature.papers.filter((paper) => paper.venueId === node.id);
    return {
      title: venue?.name ?? node.label,
      kindLabel: graphNodeKindLabel(locale, node.kind),
      description: locale === "ko" ? "선택 논문의 출판 venue입니다." : "Publication venue for the selected paper.",
      badges: venue ? [venue.type] : [],
      meta: [
        { label: locale === "ko" ? "논문 수" : "Paper count", value: `${venuePapers.length}` },
        { label: locale === "ko" ? "연결 강도" : "Link score", value: `${Math.round(node.score * 100)}%` },
      ],
      relatedPaperIds: venuePapers.map((paper) => paper.paperId),
    };
  }
  if (node.kind === "experiment") {
    const experimentId = node.id.replace("experiment_", "");
    const experimentRuns = runs.filter((run) => run.experimentId === experimentId);
    return {
      title: experimentId,
      kindLabel: graphNodeKindLabel(locale, node.kind),
      description: locale === "ko"
        ? "문헌 근거와 연결된 mock 실험입니다. 실제 학습 실행을 시작하지 않습니다."
        : "Mock experiment linked to literature evidence. This does not launch a real training run.",
      badges: [`${experimentRuns.length} ${locale === "ko" ? "실행" : "runs"}`],
      meta: [
        { label: t(locale, "adaptation"), value: unique(experimentRuns.map((run) => run.adaptationMethod)).join(", ") || "—" },
        { label: t(locale, "protocol"), value: unique(experimentRuns.map((run) => run.protocolId)).join(", ") || "—" },
        { label: t(locale, "gate"), value: unique(experimentRuns.map((run) => run.gateVerdict)).join(", ") || "—" },
      ],
      relatedPaperIds,
    };
  }
  const evidence = evidenceForGraphNode(database, node);
  const sourcePaper = literature.papers.find((paper) => paper.paperId === evidence?.paperId);
  const dataset = evidence?.kind === "dataset" ? literature.datasets.find((item) => item.datasetId === evidence.value) : null;
  const method = evidence?.kind === "method" ? literature.methods.find((item) => item.methodId === evidence.value) : null;
  const notes = dataset?.notes ?? method?.notes ?? [];
  return {
    title: evidence?.label ?? node.label,
    kindLabel: evidence ? evidenceKindLabel(locale, evidence.kind) : graphNodeKindLabel(locale, node.kind),
    description: notes.join(" ") || evidence?.value || (locale === "ko" ? "선택 논문에서 추출한 근거 노드입니다." : "Evidence node extracted from the selected paper."),
    badges: evidence ? [`${Math.round(evidence.confidence * 100)}%`, evidence.verified ? (locale === "ko" ? "검증됨" : "verified") : (locale === "ko" ? "미검증" : "unverified")] : [],
    meta: [
      { label: locale === "ko" ? "값" : "Value", value: evidence?.value ?? "—" },
      { label: locale === "ko" ? "출처 논문" : "Source paper", value: sourcePaper?.title ?? "—" },
      { label: locale === "ko" ? "수집 방식" : "Extractor", value: evidence?.extractedBy ?? "—" },
    ],
    relatedPaperIds: evidence ? literature.evidenceItems.filter((item) => item.value === evidence.value).map((item) => item.paperId) : relatedPaperIds,
  };
}

export function relatedPaperIdsForNode(
  node: LiteratureGraphNode,
  edges: LiteratureGraphEdge[],
  nodes: LiteratureGraphNode[],
): string[] {
  const nodeMap = new Map(nodes.map((item) => [item.id, item]));
  return unique(
    edges
      .filter((edge) => edge.source === node.id || edge.target === node.id)
      .map((edge) => (edge.source === node.id ? edge.target : edge.source))
      .filter((nodeId) => nodeMap.get(nodeId)?.kind === "paper"),
  );
}

export function evidenceForGraphNode(
  database: MockDatabaseState,
  node: LiteratureGraphNode,
): LiteratureEvidenceItem | null {
  if (!node.id.startsWith("evidence_")) return null;
  const evidenceId = node.id.slice("evidence_".length);
  return database.literature.evidenceItems.find((item) => item.evidenceId === evidenceId) ?? null;
}

export function graphEdgeGroup(kind: GraphEdgeKind): GraphEdgeGroup {
  if (kind === "cites" || kind === "cited_by") return "citation";
  if (kind === "shares_author" || kind === "published_in") return "context";
  if (kind === "linked_experiment") return "experiment";
  return "evidence";
}

export function graphEdgeGroupLabel(locale: Locale, group: GraphEdgeGroup): string {
  const labels: Record<GraphEdgeGroup, Record<Locale, string>> = {
    citation: { en: "Citations", ko: "인용" },
    evidence: { en: "Evidence", ko: "근거" },
    context: { en: "Authors/Venue", ko: "저자·Venue" },
    experiment: { en: "Experiments", ko: "실험" },
  };
  return labels[group][locale];
}

export function edgeKindLabel(locale: Locale, kind: GraphEdgeKind): string {
  const labels: Record<GraphEdgeKind, Record<Locale, string>> = {
    cites: { en: "cites", ko: "인용" },
    cited_by: { en: "cited by", ko: "인용됨" },
    uses_dataset: { en: "uses dataset", ko: "데이터셋 사용" },
    evaluates_on: { en: "evaluates on", ko: "평가" },
    reports_metric: { en: "reports metric", ko: "지표 보고" },
    shares_author: { en: "author", ko: "저자" },
    published_in: { en: "published in", ko: "출판" },
    defines_protocol: { en: "defines protocol", ko: "프로토콜 정의" },
    states_claim: { en: "states claim", ko: "주장" },
    notes_limitation: { en: "notes limitation", ko: "한계" },
    related_method: { en: "related method", ko: "방법 연결" },
    linked_experiment: { en: "linked experiment", ko: "실험 연결" },
  };
  return labels[kind][locale];
}

export function graphNodeShortKind(kind: LiteratureGraphNode["kind"]): string {
  const labels: Record<LiteratureGraphNode["kind"], string> = {
    paper: "P",
    author: "A",
    dataset: "D",
    method: "M",
    task: "E",
    venue: "V",
    experiment: "X",
  };
  return labels[kind];
}

export function graphNodeKindLabel(locale: Locale, kind: LiteratureGraphNode["kind"]): string {
  const labels: Record<LiteratureGraphNode["kind"], Record<Locale, string>> = {
    paper: { en: "Paper", ko: "논문" },
    author: { en: "Author", ko: "저자" },
    dataset: { en: "Dataset", ko: "데이터셋" },
    method: { en: "Method", ko: "방법" },
    task: { en: "Evidence", ko: "근거" },
    venue: { en: "Venue", ko: "Venue" },
    experiment: { en: "Experiment", ko: "실험" },
  };
  return labels[kind][locale];
}

export function graphLabelLines(label: string): string[] {
  const words = label.split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let current = "";
  let overflow = false;
  for (const word of words) {
    const next = current.length === 0 ? word : `${current} ${word}`;
    if (next.length > 24 && current.length > 0) {
      lines.push(current);
      if (lines.length === 2) {
        overflow = true;
        break;
      }
      current = word;
    } else {
      current = next;
    }
  }
  if (!overflow && current && lines.length < 2) lines.push(current);
  if (lines.length === 0) lines.push(label);
  return lines.slice(0, 2).map((line, index) => {
    const truncated = compactGraphLabel(line, 28);
    return index === 1 && overflow ? `${truncated.replace(/…$/, "")}…` : truncated;
  });
}

export function nodeTitle(node: LiteratureGraphNode): string {
  return compactGraphLabel(node.label, 42);
}

export function compactGraphLabel(label: string, maxLength = 30): string {
  return label.length > maxLength ? `${label.slice(0, Math.max(1, maxLength - 1))}…` : label;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}


export function evidenceKindLabel(locale: Locale, kind: EvidenceKind): string {
  const labels: Record<EvidenceKind, Record<Locale, string>> = {
    dataset: { en: "Dataset", ko: "데이터셋" },
    method: { en: "Method", ko: "방법" },
    metric: { en: "Metric", ko: "지표" },
    claim: { en: "Claim", ko: "주장" },
    limitation: { en: "Limitation", ko: "한계" },
    protocol: { en: "Protocol", ko: "프로토콜" },
  };
  return labels[kind][locale];
}


export function statusLabel(locale: Locale, status: PaperStatus): string {
  const labels: Record<PaperStatus, Record<Locale, string>> = {
    discovered: { en: "discovered", ko: "발견" },
    queued: { en: "queued", ko: "대기" },
    reading: { en: "reading", ko: "읽는 중" },
    extracted: { en: "extracted", ko: "추출됨" },
    verified: { en: "verified", ko: "검증됨" },
    excluded: { en: "excluded", ko: "제외" },
    linked_to_experiment: { en: "linked", ko: "실험 연결" },
  };
  return labels[status][locale];
}
