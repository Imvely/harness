import { useState } from "react";
import type {
  DemoRun,
  Locale,
  LiteraturePaper,
  MockDatabaseState,
  PaperExperimentLink,
  PaperStatus,
} from "../../types";
import { paperLinks } from "../../db/literatureSearch";
import { localeDate } from "../../i18n";
import { shortHash, unique } from "../../utils";
import { Hint } from "../Hint";
import { PaperLinkRow } from "../PaperLinks";
import { SelectBox } from "../FilterPanel";
import { evidenceKindLabel, relationLabel, statusLabel } from "./graphModel";
import { t } from "../../i18n";

/** The stages a paper moves through while it is being read. */
const paperStatuses: PaperStatus[] = [
  "discovered",
  "queued",
  "reading",
  "extracted",
  "verified",
  "excluded",
  "linked_to_experiment",
];

/**
 * One paper, and everything this project has attached to it.
 *
 * Split out of the atlas view, which had grown past the line budget the literature screens are
 * held to: the table, the matrix, the graph and this panel are four separate readings of the
 * same records and only ever shared the data, never the layout.
 */
export function PaperDetail({
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
        <SelectBox
          describe={(value) => (value === "all" ? (locale === "ko" ? "전체" : "All") : statusLabel(locale, value as PaperStatus))}
          label={t(locale, "status")}
          onChange={(value) => onSetStatus(value as PaperStatus)}
          value={paper.status}
          values={paperStatuses}
        />
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
        <SelectBox
          describe={(value) => relationLabel(locale, value as PaperExperimentLink["relation"])}
          label={locale === "ko" ? "이 실험과 어떤 관계인가요" : "Relation"}
          onChange={(value) => setRelation(value as PaperExperimentLink["relation"])}
          value={relation}
          values={["motivates", "baseline", "dataset", "metric", "limitation"]}
        />
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
