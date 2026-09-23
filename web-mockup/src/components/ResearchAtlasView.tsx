import { useMemo, useState } from "react";
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
import { Hint } from "./Hint";
import { rowClick } from "./rowActivate";
import { LiteratureGraph } from "./literature/LiteratureGraph";
import { PaperLinkRow } from "./PaperLinks";
import { paperLinks } from "../db/literatureSearch";
import { evidenceKindLabel, statusLabel } from "./literature/graphModel";

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
  const [graphOpen, setGraphOpen] = useState(false);
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
      {/* The hero here used to carry a roadmap note — which upstream adapters could be wired to
          this contract later — where the reader expected to learn what is in front of them. The
          counts are what actually orients someone opening this view. */}
      <section className="atlas-hero">
        <div className="atlas-stat-grid" aria-label={locale === "ko" ? "문헌 통계" : "Literature statistics"}>
          <AtlasStat label={locale === "ko" ? "논문" : "Papers"} value={literature.papers.length} />
          <AtlasStat label={locale === "ko" ? "인용 관계" : "Citation edges"} value={literature.citations.length} />
          <AtlasStat label={locale === "ko" ? "증거 항목" : "Evidence items"} value={literature.evidenceItems.length} />
          <AtlasStat label={locale === "ko" ? "실험 연결" : "Experiment links"} value={literature.paperExperimentLinks.length} />
        </div>
        <p className="atlas-hero__note">
          {locale === "ko" ? "예시 문헌 기록" : "Sample literature records"}
          <Hint align="start" label={locale === "ko" ? "문헌 기록 출처" : "Where these records live"}>
            {locale === "ko"
              ? "이 화면의 문헌 기록은 브라우저 저장소(mock DB)에 있습니다. 실제 논문 데이터베이스에 연결되어 있지 않으므로, 인용 수와 초록은 예시입니다."
              : "The literature records on this screen live in the browser store (mock DB). It is not connected to a real paper database, so citation counts and abstracts are examples."}
          </Hint>
        </p>
      </section>

      <section className="atlas-filter-card">
        <div className="section-heading">
          <p className="eyebrow">{locale === "ko" ? "문헌 필터" : "Literature filters"}</p>
          <h2>{locale === "ko" ? "검색" : "Search"}</h2>
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

      {/* Collapsed by default, and not mounted while collapsed.
          The graph workbench is the most demanding thing on the busiest view — pan, zoom, a
          minimap, a node inspector and seven edge kinds — and it sat above the paper table, so
          the first thing a newcomer met was the hardest. The table answers "what is here"; the
          graph answers "how is it connected", which is a later question. Gating the render also
          keeps the SVG from measuring a zero-height container. */}
      <details
        className="card card--wide atlas-graph-card"
        onToggle={(event) => setGraphOpen((event.currentTarget as HTMLDetailsElement).open)}
        open={graphOpen}
      >
        <summary className="section-heading section-heading--row atlas-graph-card__summary">
          <div>
            <p className="eyebrow">{locale === "ko" ? "관계도" : "Relationship graph"}</p>
            <h2>{locale === "ko" ? "관계도" : "Relationship graph"}</h2>
          </div>
          <span className="subtle">
            {graphOpen
              ? `${filteredPapers.length} ${locale === "ko" ? "개 결과" : "results"}`
              : locale === "ko"
                ? "펼쳐서 보기"
                : "Expand to view"}
          </span>
        </summary>
        {graphOpen && (
          <LiteratureGraph
            database={database}
            edges={graph.edges}
            locale={locale}
            nodes={graph.nodes}
            onOpenPaper={onSelectPaper}
            runs={runs}
            selectedPaperId={selectedPaper?.paperId ?? ""}
          />
        )}
      </details>

      <section className="atlas-grid">
        <div className="atlas-main">
          <section className="card card--wide">
            <div className="section-heading section-heading--row">
              <h2>
                {locale === "ko" ? "논문" : "Papers"}
                <Hint label={locale === "ko" ? "논문 표 설명" : "About this table"}>
                  {locale === "ko"
                    ? "행을 누르면 오른쪽에 그 논문의 상세가 열립니다. 인용 수는 예시 값입니다."
                    : "Click a row to open the paper on the right. Citation counts are sample values."}
                </Hint>
              </h2>
              <span className="subtle">{filteredPapers.length}</span>
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
              <h2>
                {locale === "ko" ? "근거 표" : "Evidence"}
                <Hint label={locale === "ko" ? "근거 표 설명" : "About the evidence table"}>
                  {locale === "ko"
                    ? "논문마다 쓴 데이터셋·방법·지표·한계입니다. 진하게 표시된 칸은 원문에서 확인된 것입니다."
                    : "Datasets, methods, metrics and limitations per paper. Solid chips were verified in the primary source."}
                </Hint>
              </h2>
            </div>
            <EvidenceMatrix
              database={database}
              locale={locale}
              onSelectPaper={onSelectPaper}
              papers={filteredPapers.slice(0, 8)}
              selectedPaperId={selectedPaper?.paperId ?? ""}
            />
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
              <tr
                className={paper.paperId === selectedPaperId ? "table-row row-clickable table-row--active" : "table-row row-clickable"}
                key={paper.paperId}
                // The whole row selects the paper; the title button is the keyboard path, and the
                // queue button in the last cell keeps its own action (see rowActivate.ts).
                onClick={rowClick(() => onSelectPaper(paper.paperId))}
              >
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
  selectedPaperId,
  onSelectPaper,
}: {
  database: MockDatabaseState;
  papers: LiteraturePaper[];
  locale: Locale;
  selectedPaperId: string;
  onSelectPaper: (paperId: string) => void;
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
            <tr
              className={paper.paperId === selectedPaperId ? "row-clickable table-row--active" : "row-clickable"}
              key={paper.paperId}
              onClick={rowClick(() => onSelectPaper(paper.paperId))}
            >
              <td>
                <button className="table-run-button" onClick={() => onSelectPaper(paper.paperId)} type="button">
                  <strong>{paper.title}</strong>
                </button>
              </td>
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
      <div className="paper-links">
        <p className="subtle">
          {locale === "ko" ? "원문 찾기" : "Find the paper"}
          <Hint align="start" label={locale === "ko" ? "왜 링크인가" : "Why links"}>
            {locale === "ko"
              ? "이 표의 정보는 조회 결과일 뿐입니다. 수치를 인용할 때는 원문 PDF에서 확인하고 claims에 페이지까지 적습니다."
              : "This table is a lookup result. Cite a number from the PDF, with a page, in claims."}
          </Hint>
        </p>
        <PaperLinkRow
          links={paperLinks(paper.title, paper.arxivId ?? paper.doi ?? undefined)}
          locale={locale}
        />
      </div>
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

