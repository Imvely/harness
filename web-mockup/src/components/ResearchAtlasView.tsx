import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from "react";
import type {
  DemoRun,
  EvidenceKind,
  GraphEdgeKind,
  LiteratureEvidenceItem,
  LiteratureFilters,
  LiteratureGraphEdge,
  LiteratureGraphNode,
  LiteraturePaper,
  LiteratureProvider,
  Locale,
  MockDatabaseState,
  PaperExperimentLink,
  PaperStatus,
  ReadingNote,
} from "../types";
import { localeDate, t } from "../i18n";
import { shortHash, unique } from "../utils";
import { SelectBox, SelectField } from "./FilterPanel";

type LiteratureActionResult<T> = {
  ok: boolean;
  message: string;
  item: T | null;
  issues: string[];
};

const defaultFilters: LiteratureFilters = {
  query: "",
  yearMin: 2019,
  yearMax: 2026,
  provider: "all",
  status: "all",
  datasetId: "all",
  methodId: "all",
  minCitations: 0,
  openAccessOnly: false,
};

const evidenceKinds: EvidenceKind[] = ["dataset", "method", "metric", "protocol", "limitation", "claim"];
const paperStatuses: PaperStatus[] = [
  "discovered",
  "queued",
  "reading",
  "extracted",
  "verified",
  "excluded",
  "linked_to_experiment",
];
const providers: LiteratureProvider[] = [
  "mock",
  "openalex",
  "semantic_scholar",
  "crossref",
  "opencitations",
  "arxiv",
];

export function ResearchAtlasView({
  database,
  locale,
  runs,
  selectedPaperId,
  onSelectPaper,
  onQueuePaper,
  onSetPaperStatus,
  onLinkPaper,
  onAddNote,
}: {
  database: MockDatabaseState;
  locale: Locale;
  runs: DemoRun[];
  selectedPaperId: string;
  onSelectPaper: (paperId: string) => void;
  onQueuePaper: (paperId: string) => LiteratureActionResult<LiteraturePaper>;
  onSetPaperStatus: (paperId: string, status: PaperStatus) => LiteratureActionResult<LiteraturePaper>;
  onLinkPaper: (
    paperId: string,
    experimentId: string,
    relation: PaperExperimentLink["relation"],
  ) => LiteratureActionResult<PaperExperimentLink>;
  onAddNote: (paperId: string, text: string) => LiteratureActionResult<ReadingNote>;
}) {
  const [filters, setFilters] = useState<LiteratureFilters>(defaultFilters);
  const [actionMessage, setActionMessage] = useState<string>("");
  const literature = database.literature;
  const filteredPapers = useMemo(
    () => filterLiteraturePapers(database, filters),
    [database, filters],
  );
  const selectedPaper =
    literature.papers.find((paper) => paper.paperId === selectedPaperId) ??
    filteredPapers[0] ??
    literature.papers[0];
  const graph = useMemo(
    () => buildLiteratureGraph(database, selectedPaper?.paperId ?? ""),
    [database, selectedPaper],
  );

  const runAction = <T,>(action: () => LiteratureActionResult<T>) => {
    const result = action();
    const issueText = result.issues.length > 0 ? ` ${result.issues.join(" ")}` : "";
    setActionMessage(`${result.message}${issueText}`);
  };

  return (
    <div className="research-atlas">
      <section className="atlas-hero">
        <div>
          <p className="eyebrow">{t(locale, "researchAtlas")}</p>
          <h2>{locale === "ko" ? "논문, 데이터셋, 방법, 실험을 하나의 근거 지도로 봅니다." : "Map papers, datasets, methods, and experiments before launching runs."}</h2>
          <p>
            {locale === "ko"
              ? "Google Scholar형 탐색 요구를 mock DB로 먼저 구현했습니다. OpenAlex, Semantic Scholar, Crossref, OpenCitations, arXiv 어댑터를 나중에 같은 계약에 붙일 수 있습니다."
              : "This mock DB implements a Google-Scholar-style research flow first. OpenAlex, Semantic Scholar, Crossref, OpenCitations, and arXiv adapters can feed the same contract later."}
          </p>
        </div>
        <div className="atlas-stat-grid" aria-label={locale === "ko" ? "문헌 통계" : "Literature statistics"}>
          <AtlasStat label={locale === "ko" ? "논문" : "Papers"} value={literature.papers.length} />
          <AtlasStat label={locale === "ko" ? "인용 관계" : "Citation edges"} value={literature.citations.length} />
          <AtlasStat label={locale === "ko" ? "증거 항목" : "Evidence items"} value={literature.evidenceItems.length} />
          <AtlasStat label={locale === "ko" ? "실험 연결" : "Experiment links"} value={literature.paperExperimentLinks.length} />
        </div>
      </section>

      <section className="atlas-filter-card">
        <div className="section-heading">
          <p className="eyebrow">{locale === "ko" ? "문헌 필터" : "Literature filters"}</p>
          <h2>{locale === "ko" ? "검색과 좁혀보기" : "Search and refine"}</h2>
        </div>
        <div className="atlas-filter-grid">
          <label className="field field--inline">
            {t(locale, "search")}
            <input
              value={filters.query}
              onChange={(event) => setFilters({ ...filters, query: event.target.value })}
              placeholder={locale === "ko" ? "dataset, method, APCER, domain shift" : "dataset, method, APCER, domain shift"}
              type="search"
            />
          </label>
          <NumberFilter label={locale === "ko" ? "시작 연도" : "Year min"} value={filters.yearMin} min={1980} max={filters.yearMax} onChange={(value) => setFilters({ ...filters, yearMin: value })} />
          <NumberFilter label={locale === "ko" ? "끝 연도" : "Year max"} value={filters.yearMax} min={filters.yearMin} max={2100} onChange={(value) => setFilters({ ...filters, yearMax: value })} />
          <NumberFilter label={locale === "ko" ? "최소 인용 수" : "Min citations"} value={filters.minCitations} min={0} max={500} onChange={(value) => setFilters({ ...filters, minCitations: value })} />
          <SelectField label={locale === "ko" ? "제공자" : "Provider"} locale={locale} value={filters.provider} values={providers} onChange={(value) => setFilters({ ...filters, provider: value as LiteratureFilters["provider"] })} />
          <SelectField label={t(locale, "status")} locale={locale} value={filters.status} values={paperStatuses} onChange={(value) => setFilters({ ...filters, status: value as LiteratureFilters["status"] })} />
          <SelectField label={locale === "ko" ? "데이터셋" : "Dataset"} locale={locale} value={filters.datasetId} values={literature.datasets.map((dataset) => dataset.datasetId)} onChange={(value) => setFilters({ ...filters, datasetId: value })} />
          <SelectField label={t(locale, "method")} locale={locale} value={filters.methodId} values={literature.methods.map((method) => method.methodId)} onChange={(value) => setFilters({ ...filters, methodId: value })} />
          <label className="check-field check-field--large">
            <input
              checked={filters.openAccessOnly}
              onChange={(event) => setFilters({ ...filters, openAccessOnly: event.target.checked })}
              type="checkbox"
            />
            {locale === "ko" ? "arXiv/mock open record만" : "arXiv/mock open records only"}
          </label>
          <button className="button button--secondary" onClick={() => setFilters(defaultFilters)} type="button">
            {locale === "ko" ? "문헌 필터 초기화" : "Reset literature filters"}
          </button>
        </div>
      </section>

      <section className="card card--wide atlas-graph-card">
        <div className="section-heading section-heading--row">
          <div>
            <p className="eyebrow">{locale === "ko" ? "관계도" : "Relationship graph"}</p>
            <h2>{locale === "ko" ? "선택 논문 중심 근거 연결" : "Evidence links around the selected paper"}</h2>
          </div>
          <span className="subtle">{filteredPapers.length} {locale === "ko" ? "개 결과" : "results"}</span>
        </div>
        <LiteratureGraph
          database={database}
          edges={graph.edges}
          locale={locale}
          nodes={graph.nodes}
          onOpenPaper={onSelectPaper}
          runs={runs}
          selectedPaperId={selectedPaper?.paperId ?? ""}
        />
      </section>

      <section className="atlas-grid">
        <div className="atlas-main">
          <section className="card card--wide">
            <div className="section-heading section-heading--row">
              <div>
                <p className="eyebrow">{locale === "ko" ? "논문 검색 결과" : "Paper search results"}</p>
                <h2>{locale === "ko" ? "관련도와 출처를 함께 확인" : "Review relevance with provenance"}</h2>
              </div>
              <span className="subtle">{locale === "ko" ? "mock citation counts" : "mock citation counts"}</span>
            </div>
            <PaperTable
              database={database}
              locale={locale}
              onQueuePaper={(paperId) => runAction(() => onQueuePaper(paperId))}
              onSelectPaper={onSelectPaper}
              papers={filteredPapers}
              selectedPaperId={selectedPaper?.paperId ?? ""}
            />
          </section>

          <section className="card card--wide">
            <div className="section-heading">
              <p className="eyebrow">{locale === "ko" ? "증거 행렬" : "Evidence matrix"}</p>
              <h2>{locale === "ko" ? "논문별 데이터셋·방법·지표·한계 확인" : "Paper-by-paper datasets, methods, metrics, and limitations"}</h2>
            </div>
            <EvidenceMatrix database={database} locale={locale} papers={filteredPapers.slice(0, 8)} />
          </section>
        </div>

        <aside className="atlas-side" aria-label={locale === "ko" ? "문헌 상세와 큐" : "Paper detail and queue"}>
          {selectedPaper && (
            <PaperDetail
              database={database}
              locale={locale}
              onAddNote={(text) => runAction(() => onAddNote(selectedPaper.paperId, text))}
              onLink={(experimentId, relation) => runAction(() => onLinkPaper(selectedPaper.paperId, experimentId, relation))}
              onQueue={() => runAction(() => onQueuePaper(selectedPaper.paperId))}
              onSetStatus={(status) => runAction(() => onSetPaperStatus(selectedPaper.paperId, status))}
              paper={selectedPaper}
              runs={runs}
            />
          )}
          <ResearchQueue database={database} locale={locale} onSelectPaper={onSelectPaper} />
          {actionMessage && (
            <div className="action-message action-message--ok" role="status">
              {actionMessage}
            </div>
          )}
        </aside>
      </section>
    </div>
  );
}

export function filterLiteraturePapers(
  database: MockDatabaseState,
  filters: LiteratureFilters,
): LiteraturePaper[] {
  return database.literature.papers
    .filter((paper) => {
      const evidence = database.literature.evidenceItems.filter((item) => item.paperId === paper.paperId);
      const queryText = [
        paper.title,
        paper.abstract,
        paper.year,
        paper.status,
        paper.keywords.join(" "),
        paper.fieldsOfStudy.join(" "),
        evidence.map((item) => `${item.label} ${item.value}`).join(" "),
      ]
        .join(" ")
        .toLowerCase();
      const query = filters.query.trim().toLowerCase();
      const paperDatasetIds = evidence.filter((item) => item.kind === "dataset").map((item) => item.value);
      const paperMethodIds = evidence.filter((item) => item.kind === "method").map((item) => item.value);
      const providerMatch = filters.provider === "all" || paper.providerIds.includes(filters.provider);
      const openRecord = paper.providerIds.includes("arxiv") || paper.providerIds.includes("mock") || paper.arxivId !== null;
      return (
        (query.length === 0 || queryText.includes(query)) &&
        paper.year >= filters.yearMin &&
        paper.year <= filters.yearMax &&
        paper.citationCount >= filters.minCitations &&
        providerMatch &&
        (filters.status === "all" || paper.status === filters.status) &&
        (filters.datasetId === "all" || paperDatasetIds.includes(filters.datasetId)) &&
        (filters.methodId === "all" || paperMethodIds.includes(filters.methodId)) &&
        (!filters.openAccessOnly || openRecord)
      );
    })
    .sort((a, b) => b.relevanceScore - a.relevanceScore || b.citationCount - a.citationCount);
}

export function buildLiteratureGraph(
  database: MockDatabaseState,
  selectedPaperId: string,
): { nodes: LiteratureGraphNode[]; edges: LiteratureGraphEdge[] } {
  const literature = database.literature;
  const paperIds = new Set<string>([selectedPaperId]);
  for (const citation of literature.citations) {
    if (citation.sourcePaperId === selectedPaperId) paperIds.add(citation.targetPaperId);
    if (citation.targetPaperId === selectedPaperId) paperIds.add(citation.sourcePaperId);
  }
  const selectedEvidence = literature.evidenceItems.filter((item) => item.paperId === selectedPaperId);
  const nodes: LiteratureGraphNode[] = [];
  const edges: LiteratureGraphEdge[] = [];
  for (const paperId of paperIds) {
    const paper = literature.papers.find((item) => item.paperId === paperId);
    if (paper) {
      nodes.push({
        id: paper.paperId,
        label: paper.title,
        kind: "paper",
        score: paper.paperId === selectedPaperId ? 1 : paper.relevanceScore,
      });
    }
  }
  const selectedPaper = literature.papers.find((paper) => paper.paperId === selectedPaperId);
  if (selectedPaper) {
    for (const authorId of selectedPaper.authorIds) {
      const author = literature.authors.find((item) => item.authorId === authorId);
      if (!author) continue;
      nodes.push({
        id: author.authorId,
        label: author.name,
        kind: "author",
        score: 0.72,
      });
      edges.push({
        id: `edge_${selectedPaperId}_${author.authorId}`,
        source: selectedPaperId,
        target: author.authorId,
        kind: "shares_author",
      });
    }
    const venue = literature.venues.find((item) => item.venueId === selectedPaper.venueId);
    if (venue) {
      nodes.push({
        id: venue.venueId,
        label: venue.name,
        kind: "venue",
        score: 0.68,
      });
      edges.push({
        id: `edge_${selectedPaperId}_${venue.venueId}`,
        source: selectedPaperId,
        target: venue.venueId,
        kind: "published_in",
      });
    }
  }
  for (const evidence of selectedEvidence) {
    const id = `evidence_${evidence.evidenceId}`;
    nodes.push({
      id,
      label: evidence.label,
      kind: evidence.kind === "dataset" ? "dataset" : evidence.kind === "method" ? "method" : "task",
      score: evidence.confidence,
    });
    edges.push({
      id: `edge_${selectedPaperId}_${id}`,
      source: selectedPaperId,
      target: id,
      kind: edgeKindForEvidence(evidence.kind),
    });
  }
  for (const link of literature.paperExperimentLinks.filter((item) => item.paperId === selectedPaperId)) {
    nodes.push({
      id: `experiment_${link.experimentId}`,
      label: link.experimentId,
      kind: "experiment",
      score: 0.8,
    });
    edges.push({
      id: `edge_${selectedPaperId}_${link.experimentId}`,
      source: selectedPaperId,
      target: `experiment_${link.experimentId}`,
      kind: "linked_experiment",
    });
  }
  for (const citation of literature.citations) {
    if (paperIds.has(citation.sourcePaperId) && paperIds.has(citation.targetPaperId)) {
      edges.push({
        id: `edge_${citation.sourcePaperId}_${citation.targetPaperId}`,
        source: citation.sourcePaperId,
        target: citation.targetPaperId,
        kind: citation.sourcePaperId === selectedPaperId ? "cites" : "cited_by",
      });
    }
  }
  return {
    nodes: dedupeNodes(nodes),
    edges,
  };
}

type GraphTransform = {
  zoom: number;
  panX: number;
  panY: number;
};

type PositionedGraphNode = {
  node: LiteratureGraphNode;
  x: number;
  y: number;
  radius: number;
};

type GraphTooltip = {
  x: number;
  y: number;
  node: LiteratureGraphNode;
};

type GraphNodeDetail = {
  title: string;
  kindLabel: string;
  description: string;
  badges: string[];
  meta: Array<{ label: string; value: string }>;
  relatedPaperIds: string[];
};

type GraphEdgeGroup = "citation" | "evidence" | "context" | "experiment";

type GraphBounds = {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
};

const graphEdgeGroups: GraphEdgeGroup[] = ["citation", "evidence", "context", "experiment"];
const graphZoomMin = 0.55;
const graphZoomMax = 3;
const defaultGraphTransform: GraphTransform = { zoom: 1, panX: 0, panY: 0 };

function LiteratureGraph({
  database,
  nodes,
  edges,
  locale,
  runs,
  selectedPaperId,
  onOpenPaper,
}: {
  database: MockDatabaseState;
  nodes: LiteratureGraphNode[];
  edges: LiteratureGraphEdge[];
  locale: Locale;
  runs: DemoRun[];
  selectedPaperId: string;
  onOpenPaper: (paperId: string) => void;
}) {
  const width = 820;
  const height = 390;
  const center = { x: width / 2, y: height / 2 };
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const panStartRef = useRef<{
    clientX: number;
    clientY: number;
    panX: number;
    panY: number;
    zoom: number;
  } | null>(null);
  const [activeNodeId, setActiveNodeId] = useState(selectedPaperId);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState<GraphTooltip | null>(null);
  const [transform, setTransform] = useState<GraphTransform>(defaultGraphTransform);
  const [showLabels, setShowLabels] = useState(true);
  const [showConnectedOnly, setShowConnectedOnly] = useState(false);
  const [activeEdgeGroups, setActiveEdgeGroups] = useState<GraphEdgeGroup[]>(() => [...graphEdgeGroups]);
  const [isPanning, setIsPanning] = useState(false);

  const zoomAt = useCallback((factor: number, anchor?: { x: number; y: number }) => {
    setTransform((current) => {
      const zoom = clamp(current.zoom * factor, graphZoomMin, graphZoomMax);
      if (!anchor) return { ...current, zoom };
      const worldX = (anchor.x - current.panX) / current.zoom;
      const worldY = (anchor.y - current.panY) / current.zoom;
      return {
        zoom,
        panX: anchor.x - worldX * zoom,
        panY: anchor.y - worldY * zoom,
      };
    });
  }, []);

  useEffect(() => {
    setActiveNodeId(selectedPaperId);
  }, [selectedPaperId]);

  useEffect(() => {
    if (!nodes.some((node) => node.id === activeNodeId)) {
      setActiveNodeId(nodes.some((node) => node.id === selectedPaperId) ? selectedPaperId : nodes[0]?.id ?? "");
    }
  }, [activeNodeId, nodes, selectedPaperId]);

  const layout = useMemo(
    () => buildGraphLayout(nodes, selectedPaperId, width, height),
    [nodes, selectedPaperId],
  );

  useEffect(() => {
    if (layout.length > 0) {
      setTransform(fitGraphTransform(graphBounds(layout), width, height));
    }
  }, [layout]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const svg = svgRef.current;
    if (!canvas || !svg) return;
    const handleNativeWheel = (event: WheelEvent) => {
      event.preventDefault();
      event.stopPropagation();
      zoomAt(event.deltaY < 0 ? 1.12 : 0.88, svgPointFromClient(svg, event.clientX, event.clientY, width, height));
    };
    canvas.addEventListener("wheel", handleNativeWheel, { passive: false });
    return () => {
      canvas.removeEventListener("wheel", handleNativeWheel);
    };
  }, [zoomAt]);

  const position = useMemo(
    () => new Map(layout.map((item) => [item.node.id, item])),
    [layout],
  );
  const activeNode = nodes.find((node) => node.id === activeNodeId) ?? nodes[0] ?? null;
  const visibleEdges = useMemo(() => {
    const groups = new Set(activeEdgeGroups);
    return edges.filter((edge) => groups.has(graphEdgeGroup(edge.kind)));
  }, [activeEdgeGroups, edges]);
  const highlightedNodeId = hoveredNodeId ?? activeNode?.id ?? null;
  const highlightedConnectedNodeIds = useMemo(
    () => connectedNodeSet(visibleEdges, highlightedNodeId),
    [visibleEdges, highlightedNodeId],
  );
  const activeConnectedNodeIds = useMemo(
    () => connectedNodeSet(visibleEdges, activeNode?.id ?? selectedPaperId),
    [activeNode, selectedPaperId, visibleEdges],
  );
  const nodeIdsWithVisibleEdges = useMemo(() => {
    const ids = new Set<string>([selectedPaperId]);
    if (activeNode) ids.add(activeNode.id);
    for (const edge of visibleEdges) {
      ids.add(edge.source);
      ids.add(edge.target);
    }
    return ids;
  }, [activeNode, selectedPaperId, visibleEdges]);
  const visibleLayout = useMemo(
    () => layout.filter(({ node }) => nodeIdsWithVisibleEdges.has(node.id) && (!showConnectedOnly || activeConnectedNodeIds.has(node.id))),
    [activeConnectedNodeIds, layout, nodeIdsWithVisibleEdges, showConnectedOnly],
  );
  const visibleNodeIds = useMemo(
    () => new Set(visibleLayout.map(({ node }) => node.id)),
    [visibleLayout],
  );
  const renderEdges = useMemo(
    () => visibleEdges.filter((edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target)),
    [visibleEdges, visibleNodeIds],
  );
  const edgeGroupCounts = useMemo(() => {
    const counts = new Map<GraphEdgeGroup, number>();
    for (const group of graphEdgeGroups) counts.set(group, 0);
    for (const edge of edges) {
      const group = graphEdgeGroup(edge.kind);
      counts.set(group, (counts.get(group) ?? 0) + 1);
    }
    return counts;
  }, [edges]);
  const paperCount = visibleLayout.filter(({ node }) => node.kind === "paper").length;
  const evidenceCount = visibleLayout.filter(({ node }) => node.kind === "dataset" || node.kind === "method" || node.kind === "task").length;
  const activeDegree = activeNode ? visibleEdges.filter((edge) => edge.source === activeNode.id || edge.target === activeNode.id).length : 0;
  const tooltipDegree = tooltip
    ? visibleEdges.filter((edge) => edge.source === tooltip.node.id || edge.target === tooltip.node.id).length
    : 0;
  const tooltipDetail = tooltip ? buildGraphNodeDetail(database, tooltip.node, visibleEdges, nodes, runs, locale) : null;

  const selectNode = (node: LiteratureGraphNode) => {
    setActiveNodeId(node.id);
    if (node.kind === "paper") onOpenPaper(node.id);
  };

  const selectNodeById = (nodeId: string) => {
    const node = nodes.find((item) => item.id === nodeId);
    if (node) selectNode(node);
  };

  const zoomBy = (factor: number) => {
    zoomAt(factor, center);
  };

  const resetView = () => {
    setTransform(defaultGraphTransform);
  };

  const fitView = () => {
    setTransform(fitGraphTransform(graphBounds(layout), width, height));
  };

  const focusNode = (node: LiteratureGraphNode) => {
    const item = position.get(node.id);
    if (!item) return;
    const zoom = 1.45;
    setTransform({
      zoom,
      panX: center.x - item.x * zoom,
      panY: center.y - item.y * zoom,
    });
  };

  const focusActiveNode = () => {
    if (activeNode) focusNode(activeNode);
  };

  const toggleEdgeGroup = (group: GraphEdgeGroup) => {
    setActiveEdgeGroups((current) => {
      if (current.includes(group)) {
        if (current.length === 1) return current;
        return current.filter((item) => item !== group);
      }
      return graphEdgeGroups.filter((item) => item === group || current.includes(item));
    });
  };

  const showAllEdgeGroups = () => {
    setActiveEdgeGroups([...graphEdgeGroups]);
  };

  const handlePanStart = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (event.button !== 0) return;
    const target = event.target as Element;
    if (target.closest(".graph-node")) return;
    setIsPanning(true);
    setTooltip(null);
    panStartRef.current = {
      clientX: event.clientX,
      clientY: event.clientY,
      panX: transform.panX,
      panY: transform.panY,
      zoom: transform.zoom,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handlePanMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    const start = panStartRef.current;
    if (!start) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const dx = ((event.clientX - start.clientX) * width) / rect.width;
    const dy = ((event.clientY - start.clientY) * height) / rect.height;
    setTransform({
      zoom: start.zoom,
      panX: start.panX + dx,
      panY: start.panY + dy,
    });
  };

  const handlePanEnd = (event: ReactPointerEvent<SVGSVGElement>) => {
    panStartRef.current = null;
    setIsPanning(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };

  const handleCanvasKeyDown = (event: ReactKeyboardEvent<SVGSVGElement>) => {
    const panStep = event.shiftKey ? 64 : 28;
    if (event.key === "+" || event.key === "=") {
      event.preventDefault();
      zoomBy(1.12);
    }
    if (event.key === "-" || event.key === "_") {
      event.preventDefault();
      zoomBy(0.88);
    }
    if (event.key === "Home") {
      event.preventDefault();
      fitView();
    }
    if (event.key === "ArrowLeft" || event.key === "ArrowRight" || event.key === "ArrowUp" || event.key === "ArrowDown") {
      event.preventDefault();
      setTransform((current) => ({
        ...current,
        panX: current.panX + (event.key === "ArrowLeft" ? panStep : event.key === "ArrowRight" ? -panStep : 0),
        panY: current.panY + (event.key === "ArrowUp" ? panStep : event.key === "ArrowDown" ? -panStep : 0),
      }));
    }
  };

  const moveTooltip = (event: ReactPointerEvent<SVGGElement>, node: LiteratureGraphNode) => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    setTooltip({
      x: event.clientX - rect.left + 12,
      y: event.clientY - rect.top + 12,
      node,
    });
  };

  const hideTooltip = () => {
    setHoveredNodeId(null);
    setTooltip(null);
  };

  return (
    <div className="literature-graph">
      <div className="graph-toolbar">
        <div className="graph-toolbar__copy">
          <strong>{locale === "ko" ? "상호작용 관계도" : "Interactive graph"}</strong>
          <span>
            {locale === "ko"
              ? "휠 확대, 빈 공간 드래그 이동, 노드 선택, 방향키 이동을 지원합니다."
              : "Zoom with the wheel, pan empty space, select nodes, or use arrow keys."}
          </span>
        </div>
        <div className="graph-toolbar__actions" aria-label={locale === "ko" ? "관계도 보기 조절" : "Graph view controls"}>
          <span className="graph-zoom-pill">{Math.round(transform.zoom * 100)}%</span>
          <button aria-label={locale === "ko" ? "축소" : "Zoom out"} className="button button--secondary button--small" onClick={() => zoomBy(0.88)} type="button">
            −
          </button>
          <button aria-label={locale === "ko" ? "확대" : "Zoom in"} className="button button--secondary button--small" onClick={() => zoomBy(1.12)} type="button">
            +
          </button>
          <button className="button button--secondary button--small" onClick={focusActiveNode} type="button">
            {locale === "ko" ? "선택 중심" : "Focus"}
          </button>
          <button className="button button--secondary button--small" onClick={fitView} type="button">
            {locale === "ko" ? "맞춤" : "Fit"}
          </button>
          <button className="button button--secondary button--small" onClick={resetView} type="button">
            {locale === "ko" ? "초기화" : "Reset"}
          </button>
        </div>
      </div>

      <div className="graph-control-strip">
        <div className="graph-edge-filters" role="group" aria-label={locale === "ko" ? "관계 종류 필터" : "Relationship type filters"}>
          {graphEdgeGroups.map((group) => {
            const active = activeEdgeGroups.includes(group);
            return (
              <button
                aria-pressed={active}
                className={active ? "graph-filter-chip graph-filter-chip--active" : "graph-filter-chip"}
                key={group}
                onClick={() => toggleEdgeGroup(group)}
                type="button"
              >
                <span>{graphEdgeGroupLabel(locale, group)}</span>
                <strong>{edgeGroupCounts.get(group) ?? 0}</strong>
              </button>
            );
          })}
          <button className="graph-filter-chip graph-filter-chip--plain" onClick={showAllEdgeGroups} type="button">
            {locale === "ko" ? "전체" : "All"}
          </button>
        </div>
        <div className="graph-control-strip__right">
          <label className="graph-node-picker">
            <span>{locale === "ko" ? "노드 찾기" : "Find node"}</span>
            <select value={activeNode?.id ?? ""} onChange={(event) => selectNodeById(event.target.value)}>
              {nodes.map((node) => (
                <option key={node.id} value={node.id}>
                  {graphNodeKindLabel(locale, node.kind)} · {compactGraphLabel(node.label, 52)}
                </option>
              ))}
            </select>
          </label>
          <label className="graph-label-toggle">
            <input checked={showConnectedOnly} onChange={(event) => setShowConnectedOnly(event.target.checked)} type="checkbox" />
            {locale === "ko" ? "선택 연결만" : "Connected only"}
          </label>
          <label className="graph-label-toggle">
            <input checked={showLabels} onChange={(event) => setShowLabels(event.target.checked)} type="checkbox" />
            {locale === "ko" ? "라벨" : "Labels"}
          </label>
        </div>
      </div>

      <div className="graph-workbench">
        <div className={isPanning ? "graph-canvas graph-canvas--panning" : "graph-canvas"} ref={canvasRef}>
          <svg
            aria-labelledby="literature-graph-title literature-graph-desc"
            onDoubleClick={fitView}
            onKeyDown={handleCanvasKeyDown}
            onPointerCancel={handlePanEnd}
            onPointerDown={handlePanStart}
            onPointerLeave={(event) => {
              hideTooltip();
              if (panStartRef.current) handlePanEnd(event);
            }}
            onPointerMove={handlePanMove}
            onPointerUp={handlePanEnd}
            ref={svgRef}
            role="img"
            tabIndex={0}
            viewBox={`0 0 ${width} ${height}`}
          >
            <title id="literature-graph-title">{locale === "ko" ? "문헌 관계 그래프" : "Literature relationship graph"}</title>
            <desc id="literature-graph-desc">
              {locale === "ko"
                ? "선택한 논문과 인용, 데이터셋, 방법, 저자, venue, 실험 노드를 연결합니다."
                : "The selected paper is connected to citation, dataset, method, author, venue, and experiment nodes."}
            </desc>
            <defs>
              <marker id="graph-arrow" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="4" viewBox="0 0 8 8">
                <path d="M0,0 L8,4 L0,8 Z" fill="rgba(95, 99, 104, 0.55)" />
              </marker>
            </defs>
            <rect className="graph-pan-surface" height={height} width={width} x="0" y="0" />
            <g transform={`matrix(${transform.zoom} 0 0 ${transform.zoom} ${transform.panX} ${transform.panY})`}>
              {renderEdges.map((edge) => {
                const source = position.get(edge.source);
                const target = position.get(edge.target);
                if (!source || !target) return null;
                const highlighted = highlightedNodeId === edge.source || highlightedNodeId === edge.target;
                const dimmed = highlightedNodeId !== null && !highlighted;
                const midX = (source.x + target.x) / 2;
                const midY = (source.y + target.y) / 2;
                return (
                  <g className="graph-edge-group" key={edge.id}>
                    <title>{`${nodeTitle(source.node)} ${edgeKindLabel(locale, edge.kind)} ${nodeTitle(target.node)}`}</title>
                    <line
                      className={`graph-edge graph-edge--${edge.kind}${highlighted ? " graph-edge--highlighted" : ""}${dimmed ? " graph-edge--dimmed" : ""}`}
                      markerEnd={edge.kind === "cites" || edge.kind === "cited_by" ? "url(#graph-arrow)" : undefined}
                      x1={source.x}
                      x2={target.x}
                      y1={source.y}
                      y2={target.y}
                    />
                    {highlighted && showLabels && (
                      <text className="graph-edge-label" textAnchor="middle" x={midX} y={midY - 6}>
                        {edgeKindLabel(locale, edge.kind)}
                      </text>
                    )}
                  </g>
                );
              })}
              {visibleLayout.map(({ node, x, y, radius }) => {
                const highlighted = highlightedNodeId === node.id;
                const dimmed = highlightedNodeId !== null && !highlightedConnectedNodeIds.has(node.id);
                const labelLines = graphLabelLines(node.label);
                return (
                  <g
                    aria-label={`${graphNodeKindLabel(locale, node.kind)}: ${node.label}`}
                    className={`graph-node${highlighted ? " graph-node--active" : ""}${dimmed ? " graph-node--dimmed" : ""}`}
                    key={node.id}
                    onClick={() => selectNode(node)}
                    onDoubleClick={(event) => {
                      event.stopPropagation();
                      selectNode(node);
                      focusNode(node);
                    }}
                    onKeyDown={(event: ReactKeyboardEvent<SVGGElement>) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        selectNode(node);
                      }
                    }}
                    onPointerDown={(event) => event.stopPropagation()}
                    onPointerEnter={(event) => {
                      setHoveredNodeId(node.id);
                      moveTooltip(event, node);
                    }}
                    onPointerLeave={hideTooltip}
                    onPointerMove={(event) => moveTooltip(event, node)}
                    role="button"
                    tabIndex={0}
                  >
                    <title>{node.label}</title>
                    <circle className={`graph-node__circle graph-node__circle--${node.kind}`} cx={x} cy={y} r={radius} />
                    <circle className="graph-node__focus-ring" cx={x} cy={y} r={radius + 7} />
                    <text className="graph-node__score" textAnchor="middle" x={x} y={y + 4}>
                      {node.kind === "paper" ? Math.round(node.score * 100) : graphNodeShortKind(node.kind)}
                    </text>
                    {showLabels && (
                      <text className="graph-node__label" textAnchor="middle" x={x} y={y + radius + 17}>
                        {labelLines.map((line, index) => (
                          <tspan dy={index === 0 ? 0 : 13} key={`${node.id}_${line}`} x={x}>
                            {line}
                          </tspan>
                        ))}
                      </text>
                    )}
                  </g>
                );
              })}
            </g>
          </svg>
          <GraphMiniMap
            activeNodeId={activeNode?.id ?? selectedPaperId}
            edges={renderEdges}
            height={height}
            layout={visibleLayout}
            locale={locale}
            transform={transform}
            visibleNodeIds={visibleNodeIds}
            width={width}
          />
          {tooltip && tooltipDetail && (
            <div className="graph-tooltip" style={{ left: tooltip.x, top: tooltip.y }} role="tooltip">
              <strong>{tooltip.node.label}</strong>
              <span>
                {graphNodeKindLabel(locale, tooltip.node.kind)} · {Math.round(tooltip.node.score * 100)}% · {tooltipDegree} {locale === "ko" ? "연결" : "links"}
              </span>
              <small>{compactGraphLabel(tooltipDetail.description, 96)}</small>
            </div>
          )}
        </div>
        <GraphNodeInspector
          activeDegree={activeDegree}
          activeNode={activeNode}
          database={database}
          edges={visibleEdges}
          locale={locale}
          nodes={nodes}
          onOpenPaper={onOpenPaper}
          onSelectNode={selectNode}
          runs={runs}
        />
      </div>
      <div className="graph-summary-row" aria-label={locale === "ko" ? "관계도 요약" : "Graph summary"}>
        <span>{locale === "ko" ? `표시 노드 ${visibleLayout.length}` : `${visibleLayout.length} visible nodes`}</span>
        <span>{locale === "ko" ? `논문 ${paperCount}` : `${paperCount} papers`}</span>
        <span>{locale === "ko" ? `근거 ${evidenceCount}` : `${evidenceCount} evidence nodes`}</span>
        <span>{locale === "ko" ? `관계 ${renderEdges.length}` : `${renderEdges.length} relationships`}</span>
      </div>
      <div className="graph-legend" aria-label={locale === "ko" ? "노드 범례" : "Node legend"}>
        {(["paper", "dataset", "method", "task", "author", "venue", "experiment"] as const).map((kind) => (
          <span className="graph-legend__item" key={kind}>
            <i className={`graph-legend__dot graph-legend__dot--${kind}`} />
            {graphNodeKindLabel(locale, kind)}
          </span>
        ))}
      </div>
      <div className="graph-node-list" aria-label={locale === "ko" ? "그래프 노드 목록" : "Graph node list"}>
        {visibleLayout.map(({ node }) => (
          <button
            className={node.id === activeNode?.id ? "graph-node-chip graph-node-chip--active" : "graph-node-chip"}
            key={node.id}
            onClick={() => selectNode(node)}
            type="button"
          >
            <span>{graphNodeKindLabel(locale, node.kind)}</span>
            {node.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function GraphNodeInspector({
  activeDegree,
  activeNode,
  database,
  edges,
  locale,
  nodes,
  runs,
  onOpenPaper,
  onSelectNode,
}: {
  activeDegree: number;
  activeNode: LiteratureGraphNode | null;
  database: MockDatabaseState;
  edges: LiteratureGraphEdge[];
  locale: Locale;
  nodes: LiteratureGraphNode[];
  runs: DemoRun[];
  onOpenPaper: (paperId: string) => void;
  onSelectNode: (node: LiteratureGraphNode) => void;
}) {
  if (!activeNode) {
    return (
      <aside className="graph-inspector">
        <p className="subtle">{locale === "ko" ? "노드를 선택해 상세를 확인하세요." : "Select a node to inspect details."}</p>
      </aside>
    );
  }
  const detail = buildGraphNodeDetail(database, activeNode, edges, nodes, runs, locale);
  const connectedEdges = edges.filter((edge) => edge.source === activeNode.id || edge.target === activeNode.id);
  const nodeLabel = (nodeId: string) => nodes.find((node) => node.id === nodeId)?.label ?? nodeId;

  return (
    <aside className="graph-inspector" aria-live="polite">
      <div className="section-heading">
        <p className="eyebrow">{locale === "ko" ? "노드 상세" : "Node detail"}</p>
        <h3>{detail.title}</h3>
      </div>
      <div className="graph-inspector__badges">
        <span className="badge badge--muted">{detail.kindLabel}</span>
        <span className="badge badge--muted">{activeDegree} {locale === "ko" ? "연결" : "links"}</span>
        {detail.badges.map((badge) => (
          <span className="badge badge--muted" key={badge}>{badge}</span>
        ))}
      </div>
      <p>{detail.description}</p>
      <dl className="detail-list graph-detail-list">
        {detail.meta.map((item) => (
          <div key={item.label}>
            <dt>{item.label}</dt>
            <dd>{item.value}</dd>
          </div>
        ))}
      </dl>
      <section className="graph-inspector__section">
        <strong>{locale === "ko" ? "연결 관계" : "Connections"}</strong>
        <ul>
          {connectedEdges.slice(0, 6).map((edge) => (
            <li key={edge.id}>
              {nodeLabel(edge.source)} <span>{edgeKindLabel(locale, edge.kind)}</span> {nodeLabel(edge.target)}
            </li>
          ))}
          {connectedEdges.length === 0 && <li>{locale === "ko" ? "직접 연결 없음" : "No direct connections"}</li>}
        </ul>
      </section>
      {detail.relatedPaperIds.length > 0 && (
        <section className="graph-inspector__section">
          <strong>{locale === "ko" ? "관련 논문 바로가기" : "Related papers"}</strong>
          <div className="graph-related-papers">
            {detail.relatedPaperIds.slice(0, 4).map((paperId) => {
              const node = nodes.find((item) => item.id === paperId);
              const paper = database.literature.papers.find((item) => item.paperId === paperId);
              if (!node && !paper) return null;
              return (
                <button
                  className="graph-related-paper"
                  key={paperId}
                  onClick={() => {
                    if (node) onSelectNode(node);
                    else if (paper) onOpenPaper(paper.paperId);
                  }}
                  type="button"
                >
                  {paper?.title ?? node?.label}
                </button>
              );
            })}
          </div>
        </section>
      )}
      {activeNode.kind === "paper" && (
        <button className="button button--secondary button--small" onClick={() => onOpenPaper(activeNode.id)} type="button">
          {locale === "ko" ? "오른쪽 상세 패널에 열기" : "Open in the detail rail"}
        </button>
      )}
    </aside>
  );
}

function GraphMiniMap({
  activeNodeId,
  edges,
  height,
  layout,
  locale,
  transform,
  visibleNodeIds,
  width,
}: {
  activeNodeId: string;
  edges: LiteratureGraphEdge[];
  height: number;
  layout: PositionedGraphNode[];
  locale: Locale;
  transform: GraphTransform;
  visibleNodeIds: Set<string>;
  width: number;
}) {
  if (layout.length === 0) return null;
  const miniWidth = 156;
  const miniHeight = 88;
  const bounds = graphBounds(layout);
  const boundsWidth = Math.max(bounds.maxX - bounds.minX, 1);
  const boundsHeight = Math.max(bounds.maxY - bounds.minY, 1);
  const scale = Math.min((miniWidth - 18) / boundsWidth, (miniHeight - 18) / boundsHeight);
  const offsetX = (miniWidth - boundsWidth * scale) / 2;
  const offsetY = (miniHeight - boundsHeight * scale) / 2;
  const mapX = (x: number) => offsetX + (x - bounds.minX) * scale;
  const mapY = (y: number) => offsetY + (y - bounds.minY) * scale;
  const viewport = {
    x: (-transform.panX / transform.zoom - bounds.minX) * scale + offsetX,
    y: (-transform.panY / transform.zoom - bounds.minY) * scale + offsetY,
    width: (width / transform.zoom) * scale,
    height: (height / transform.zoom) * scale,
  };

  return (
    <div className="graph-minimap" aria-label={locale === "ko" ? "관계도 미니맵" : "Graph minimap"}>
      <span>{locale === "ko" ? "미니맵" : "Minimap"}</span>
      <svg aria-hidden="true" viewBox={`0 0 ${miniWidth} ${miniHeight}`}>
        {edges.map((edge) => {
          const source = layout.find((item) => item.node.id === edge.source);
          const target = layout.find((item) => item.node.id === edge.target);
          if (!source || !target) return null;
          return (
            <line
              className="graph-minimap__edge"
              key={edge.id}
              x1={mapX(source.x)}
              x2={mapX(target.x)}
              y1={mapY(source.y)}
              y2={mapY(target.y)}
            />
          );
        })}
        {layout.map(({ node, x, y }) => (
          <circle
            className={node.id === activeNodeId ? "graph-minimap__node graph-minimap__node--active" : "graph-minimap__node"}
            cx={mapX(x)}
            cy={mapY(y)}
            key={node.id}
            r={node.kind === "paper" ? 3.4 : 2.4}
          />
        ))}
        <rect
          className="graph-minimap__viewport"
          height={Math.min(viewport.height, miniHeight)}
          width={Math.min(viewport.width, miniWidth)}
          x={clamp(viewport.x, 0, miniWidth)}
          y={clamp(viewport.y, 0, miniHeight)}
        />
      </svg>
      <small>{visibleNodeIds.size} {locale === "ko" ? "노드" : "nodes"}</small>
    </div>
  );
}

function buildGraphLayout(
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

function graphRadius(kind: LiteratureGraphNode["kind"], axis: "x" | "y"): number {
  if (kind === "paper") return axis === "x" ? 180 : 110;
  if (kind === "author" || kind === "venue") return axis === "x" ? 310 : 150;
  if (kind === "experiment") return axis === "x" ? 290 : 155;
  return axis === "x" ? 250 : 145;
}

function graphNodeRadius(kind: LiteratureGraphNode["kind"]): number {
  if (kind === "paper") return 24;
  if (kind === "author" || kind === "venue") return 20;
  if (kind === "experiment") return 22;
  return 21;
}

function graphBounds(layout: PositionedGraphNode[]): GraphBounds {
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

function fitGraphTransform(bounds: GraphBounds, width: number, height: number): GraphTransform {
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

function svgPointFromClient(
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

function connectedNodeSet(edges: LiteratureGraphEdge[], highlightedNodeId: string | null): Set<string> {
  const ids = new Set<string>();
  if (!highlightedNodeId) return ids;
  ids.add(highlightedNodeId);
  for (const edge of edges) {
    if (edge.source === highlightedNodeId) ids.add(edge.target);
    if (edge.target === highlightedNodeId) ids.add(edge.source);
  }
  return ids;
}

function buildGraphNodeDetail(
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

function relatedPaperIdsForNode(
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

function evidenceForGraphNode(
  database: MockDatabaseState,
  node: LiteratureGraphNode,
): LiteratureEvidenceItem | null {
  if (!node.id.startsWith("evidence_")) return null;
  const evidenceId = node.id.slice("evidence_".length);
  return database.literature.evidenceItems.find((item) => item.evidenceId === evidenceId) ?? null;
}

function graphEdgeGroup(kind: GraphEdgeKind): GraphEdgeGroup {
  if (kind === "cites" || kind === "cited_by") return "citation";
  if (kind === "shares_author" || kind === "published_in") return "context";
  if (kind === "linked_experiment") return "experiment";
  return "evidence";
}

function graphEdgeGroupLabel(locale: Locale, group: GraphEdgeGroup): string {
  const labels: Record<GraphEdgeGroup, Record<Locale, string>> = {
    citation: { en: "Citations", ko: "인용" },
    evidence: { en: "Evidence", ko: "근거" },
    context: { en: "Authors/Venue", ko: "저자·Venue" },
    experiment: { en: "Experiments", ko: "실험" },
  };
  return labels[group][locale];
}

function edgeKindLabel(locale: Locale, kind: GraphEdgeKind): string {
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

function graphNodeShortKind(kind: LiteratureGraphNode["kind"]): string {
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

function graphNodeKindLabel(locale: Locale, kind: LiteratureGraphNode["kind"]): string {
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

function graphLabelLines(label: string): string[] {
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

function nodeTitle(node: LiteratureGraphNode): string {
  return compactGraphLabel(node.label, 42);
}

function compactGraphLabel(label: string, maxLength = 30): string {
  return label.length > maxLength ? `${label.slice(0, Math.max(1, maxLength - 1))}…` : label;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function PaperTable({
  papers,
  database,
  locale,
  selectedPaperId,
  onSelectPaper,
  onQueuePaper,
}: {
  papers: LiteraturePaper[];
  database: MockDatabaseState;
  locale: Locale;
  selectedPaperId: string;
  onSelectPaper: (paperId: string) => void;
  onQueuePaper: (paperId: string) => void;
}) {
  return (
    <div className="table-wrap">
      <table className="runs-table literature-table">
        <thead>
          <tr>
            <th scope="col">{locale === "ko" ? "논문" : "Paper"}</th>
            <th scope="col">{locale === "ko" ? "연도" : "Year"}</th>
            <th scope="col">{locale === "ko" ? "인용" : "Citations"}</th>
            <th scope="col">{locale === "ko" ? "관련도" : "Relevance"}</th>
            <th scope="col">{t(locale, "status")}</th>
            <th scope="col">{locale === "ko" ? "데이터셋" : "Datasets"}</th>
            <th scope="col">{t(locale, "method")}</th>
            <th scope="col">{locale === "ko" ? "동작" : "Action"}</th>
          </tr>
        </thead>
        <tbody>
          {papers.map((paper) => {
            const evidence = database.literature.evidenceItems.filter((item) => item.paperId === paper.paperId);
            return (
              <tr className={paper.paperId === selectedPaperId ? "table-row table-row--active" : "table-row"} key={paper.paperId}>
                <td>
                  <button className="table-run-button" onClick={() => onSelectPaper(paper.paperId)} type="button">
                    <strong>{paper.title}</strong>
                    <span>{paper.keywords.join(" · ")}</span>
                  </button>
                </td>
                <td>{paper.year}</td>
                <td>{paper.citationCount}</td>
                <td>{Math.round(paper.relevanceScore * 100)}%</td>
                <td><span className="badge badge--muted">{statusLabel(locale, paper.status)}</span></td>
                <td>{labelsForEvidence(evidence, "dataset").join(", ") || "—"}</td>
                <td>{labelsForEvidence(evidence, "method").join(", ") || "—"}</td>
                <td>
                  <button className="button button--secondary button--small" onClick={() => onQueuePaper(paper.paperId)} type="button">
                    {locale === "ko" ? "큐 추가" : "Queue"}
                  </button>
                </td>
              </tr>
            );
          })}
          {papers.length === 0 && (
            <tr>
              <td colSpan={8}>{locale === "ko" ? "검색 조건과 맞는 논문이 없습니다." : "No papers match the active filters."}</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function EvidenceMatrix({
  database,
  papers,
  locale,
}: {
  database: MockDatabaseState;
  papers: LiteraturePaper[];
  locale: Locale;
}) {
  return (
    <div className="table-wrap">
      <table className="runs-table runs-table--compact evidence-table">
        <thead>
          <tr>
            <th scope="col">{locale === "ko" ? "논문" : "Paper"}</th>
            {evidenceKinds.map((kind) => (
              <th key={kind} scope="col">{evidenceKindLabel(locale, kind)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {papers.map((paper) => (
            <tr key={paper.paperId}>
              <td>{paper.title}</td>
              {evidenceKinds.map((kind) => {
                const items = database.literature.evidenceItems.filter((item) => item.paperId === paper.paperId && item.kind === kind);
                return (
                  <td key={kind}>
                    {items.length > 0 ? (
                      <div className="evidence-chip-list">
                        {items.map((item) => (
                          <span className={item.verified ? "evidence-chip evidence-chip--verified" : "evidence-chip"} key={item.evidenceId}>
                            {item.label}
                          </span>
                        ))}
                      </div>
                    ) : "—"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PaperDetail({
  paper,
  database,
  runs,
  locale,
  onQueue,
  onSetStatus,
  onLink,
  onAddNote,
}: {
  paper: LiteraturePaper;
  database: MockDatabaseState;
  runs: DemoRun[];
  locale: Locale;
  onQueue: () => void;
  onSetStatus: (status: PaperStatus) => void;
  onLink: (experimentId: string, relation: PaperExperimentLink["relation"]) => void;
  onAddNote: (text: string) => void;
}) {
  const [noteText, setNoteText] = useState("");
  const [experimentId, setExperimentId] = useState(runs[0]?.experimentId ?? "");
  const [relation, setRelation] = useState<PaperExperimentLink["relation"]>("motivates");
  const venue = database.literature.venues.find((item) => item.venueId === paper.venueId);
  const authors = paper.authorIds
    .map((authorId) => database.literature.authors.find((author) => author.authorId === authorId)?.name)
    .filter((name): name is string => Boolean(name));
  const evidence = database.literature.evidenceItems.filter((item) => item.paperId === paper.paperId);
  const notes = database.literature.readingNotes.filter((note) => note.paperId === paper.paperId);
  const experimentIds = unique(runs.map((run) => run.experimentId));

  return (
    <section className="paper-detail-card">
      <div className="section-heading">
        <p className="eyebrow">{locale === "ko" ? "선택 논문" : "Selected paper"}</p>
        <h2>{paper.title}</h2>
      </div>
      <div className="drawer-badges">
        <span className="badge badge--success">{statusLabel(locale, paper.status)}</span>
        <span className="badge badge--muted">{paper.year}</span>
        <span className="badge badge--muted">{paper.citationCount} {locale === "ko" ? "인용" : "citations"}</span>
      </div>
      <p className="paper-abstract">{paper.abstract}</p>
      <dl className="detail-list">
        <div>
          <dt>{locale === "ko" ? "저자" : "Authors"}</dt>
          <dd>{authors.join(", ")}</dd>
        </div>
        <div>
          <dt>Venue</dt>
          <dd>{venue?.name ?? paper.venueId}</dd>
        </div>
        <div>
          <dt>OpenAlex</dt>
          <dd><code>{paper.openAlexId}</code></dd>
        </div>
        <div>
          <dt>Semantic Scholar</dt>
          <dd><code>{paper.semanticScholarId}</code></dd>
        </div>
        <div>
          <dt>{locale === "ko" ? "수집 시각" : "Retrieved"}</dt>
          <dd>{localeDate(locale, paper.retrievedAt)}</dd>
        </div>
        <div>
          <dt>{locale === "ko" ? "응답 해시" : "Payload hash"}</dt>
          <dd><code>{shortHash(paper.providerPayloadHash)}</code></dd>
        </div>
      </dl>
      <div className="paper-action-grid">
        <button className="button button--secondary" onClick={onQueue} type="button">
          {locale === "ko" ? "읽기 큐에 추가" : "Add to reading queue"}
        </button>
        <SelectBox label={t(locale, "status")} value={paper.status} values={paperStatuses} onChange={(value) => onSetStatus(value as PaperStatus)} />
      </div>
      <section className="note-panel">
        <h3>{locale === "ko" ? "추출된 근거" : "Extracted evidence"}</h3>
        <div className="evidence-stack">
          {evidence.map((item) => (
            <article className={item.verified ? "evidence-card evidence-card--verified" : "evidence-card"} key={item.evidenceId}>
              <span>{evidenceKindLabel(locale, item.kind)} · {Math.round(item.confidence * 100)}%</span>
              <strong>{item.label}</strong>
              <p>{item.value}</p>
            </article>
          ))}
        </div>
      </section>
      <section className="note-panel">
        <h3>{locale === "ko" ? "실험 연결" : "Experiment link"}</h3>
        <SelectBox label={t(locale, "experiment")} value={experimentId} values={experimentIds} onChange={setExperimentId} />
        <SelectBox label={locale === "ko" ? "관계" : "Relation"} value={relation} values={["motivates", "baseline", "dataset", "metric", "limitation"]} onChange={(value) => setRelation(value as PaperExperimentLink["relation"])} />
        <button className="button button--primary" onClick={() => onLink(experimentId, relation)} type="button">
          {locale === "ko" ? "실험에 연결" : "Link to experiment"}
        </button>
      </section>
      <section className="note-panel">
        <h3>{locale === "ko" ? "읽기 메모" : "Reading notes"}</h3>
        <label className="field">
          {locale === "ko" ? "새 메모" : "New note"}
          <textarea
            value={noteText}
            onChange={(event) => setNoteText(event.target.value)}
            placeholder={locale === "ko" ? "프로토콜, 한계, 실험 아이디어를 기록" : "Capture protocol, limitation, or experiment ideas"}
          />
        </label>
        <button
          className="button button--secondary"
          onClick={() => {
            onAddNote(noteText);
            setNoteText("");
          }}
          type="button"
        >
          {locale === "ko" ? "메모 저장" : "Save note"}
        </button>
        <ol className="timeline-list">
          {notes.map((note) => (
            <li key={note.noteId}>
              <strong>{localeDate(locale, note.createdAt)}</strong>
              <span>{note.text}</span>
            </li>
          ))}
        </ol>
      </section>
    </section>
  );
}

function ResearchQueue({
  database,
  locale,
  onSelectPaper,
}: {
  database: MockDatabaseState;
  locale: Locale;
  onSelectPaper: (paperId: string) => void;
}) {
  const statuses: PaperStatus[] = ["queued", "reading", "extracted", "verified"];
  return (
    <section className="paper-detail-card">
      <div className="section-heading">
        <p className="eyebrow">{locale === "ko" ? "리서치 큐" : "Research queue"}</p>
        <h2>{locale === "ko" ? "읽기 흐름" : "Reading flow"}</h2>
      </div>
      <div className="queue-lanes">
        {statuses.map((status) => {
          const papers = database.literature.papers.filter((paper) => paper.status === status);
          return (
            <section className="queue-lane" key={status}>
              <h3>{statusLabel(locale, status)}</h3>
              {papers.map((paper) => (
                <button className="queue-paper" key={paper.paperId} onClick={() => onSelectPaper(paper.paperId)} type="button">
                  <strong>{paper.title}</strong>
                  <span>{paper.year} · {Math.round(paper.relevanceScore * 100)}%</span>
                </button>
              ))}
              {papers.length === 0 && <p className="subtle">{locale === "ko" ? "비어 있음" : "Empty"}</p>}
            </section>
          );
        })}
      </div>
    </section>
  );
}

function AtlasStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="atlas-stat">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function NumberFilter({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="field field--inline">
      {label}
      <input
        max={max}
        min={min}
        type="number"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

function labelsForEvidence(items: LiteratureEvidenceItem[], kind: EvidenceKind): string[] {
  return items.filter((item) => item.kind === kind).map((item) => item.label);
}

function dedupeNodes(nodes: LiteratureGraphNode[]): LiteratureGraphNode[] {
  const seen = new Set<string>();
  return nodes.filter((node) => {
    if (seen.has(node.id)) return false;
    seen.add(node.id);
    return true;
  });
}

function edgeKindForEvidence(kind: EvidenceKind): GraphEdgeKind {
  if (kind === "dataset") return "uses_dataset";
  if (kind === "method") return "related_method";
  if (kind === "protocol") return "defines_protocol";
  if (kind === "claim") return "states_claim";
  if (kind === "limitation") return "notes_limitation";
  return "reports_metric";
}

function evidenceKindLabel(locale: Locale, kind: EvidenceKind): string {
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

function statusLabel(locale: Locale, status: PaperStatus): string {
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
