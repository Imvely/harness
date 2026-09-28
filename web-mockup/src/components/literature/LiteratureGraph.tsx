import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from "react";
import type {
  DemoRun,
  LiteratureGraphEdge,
  LiteratureGraphNode,
  Locale,
  MockDatabaseState,
} from "../../types";
import type {
  GraphEdgeGroup,
  GraphTooltip,
  GraphTransform,
  PositionedGraphNode,
} from "./graphModel";
import {
  buildGraphLayout,
  buildGraphNodeDetail,
  clamp,
  compactGraphLabel,
  connectedNodeSet,
  defaultGraphTransform,
  edgeKindLabel,
  fitGraphTransform,
  graphBounds,
  graphEdgeGroup,
  graphEdgeGroupLabel,
  graphEdgeGroups,
  graphLabelLines,
  graphNodeKindLabel,
  graphNodeShortKind,
  graphZoomMax,
  graphZoomMin,
  nodeTitle,
  svgPointFromClient,
} from "./graphModel";

/**
 * The pan-and-zoom relationship workbench: the SVG, its minimap and the node inspector.
 *
 * Mounted only when the reader expands it (see `ResearchAtlasView`), so a first visit to the
 * literature view does not start by measuring and laying out a graph nobody asked for.
 */

export function LiteratureGraph({
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

